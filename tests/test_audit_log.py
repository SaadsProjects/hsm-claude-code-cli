"""
Tests for the audit trail module (mock_hsm/audit.py): first the storage layer
(file layout, old-layout reading, torn lines, permissions, the purge swap),
then the business logic (append, batch append, the size cap, paging,
visibility, the lazy purge and logging), then the `perf` timing targets.

Every test gets its own audit file from the autouse ``audit_path`` fixture in
conftest.py. The clock is injected with ``configure(clock=...)``; nothing
sleeps for real time.
"""
import json
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mock_hsm import audit

PROJECT_ROOT = Path(__file__).resolve().parent.parent

T0 = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

REGIONAL = {"user_id": "user_regional_atl", "persona": "REGIONAL_MANAGER",
            "site_ids": ["site_001", "site_002", "site_003"], "region_id": "region_atl"}
RM = {"user_id": "user_rm_midtown", "persona": "RESTAURANT_MANAGER", "site_ids": ["site_001"], "region_id": None}
ADMIN = {"user_id": "user_dev_tester", "persona": "SYSTEM_ADMIN", "site_ids": [], "region_id": None}


class FakeClock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


def _entry(**overrides):
    entry = {"user_id": "user_rm_midtown", "persona": "RESTAURANT_MANAGER", "session_id": "sess-1",
             "source": "dashboard", "action": "add", "outcome": "allowed", "kind": "employee",
             "record_id": "emp_1", "site_id": "site_001", "changes": {"name": "Ana"}}
    entry.update(overrides)
    return entry


def _all_ids(viewer=REGIONAL):
    ids, before = [], None
    while True:
        result = audit.page(viewer, before)
        ids += [e["entry_id"] for e in result["entries"]]
        before = result["next_before"]
        if before is None:
            return ids


def _stored_lines(path):
    """Every stored line, parsed."""
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def _legacy_entry(entry_id, timestamp=T0 - timedelta(days=1), site_id="site_001"):
    return {"entry_id": f"{entry_id:012d}", "timestamp": timestamp.isoformat(), "user_id": "user_rm_midtown",
            "persona": "RESTAURANT_MANAGER", "session_id": None, "source": "claude_code_workflow",
            "action": "publish_schedule", "outcome": "allowed", "kind": "schedule", "record_id": site_id,
            "site_id": site_id, "changes": None, "reason": None, "file_row": None}


def _error_lines(err):
    return [line for line in err.splitlines() if line.startswith("[mock-hsm] ERROR audit:")]


# ============================================================ storage layer

def test_round_trip_after_restart_single_and_batch(audit_path):
    single = audit.append(_entry(record_id="emp_a"))
    batch = audit.append_batch([_entry(action="bulk_row", record_id=f"emp_{i}", file_row=i) for i in (1, 2, 3)])
    assert [single, *batch] == ["000000000001", "000000000002", "000000000003", "000000000004"]

    # One line per call, each carrying the high-water mark after it (NFR3.15).
    lines = _stored_lines(audit_path)
    assert [(line["hwm"], [e["entry_id"] for e in line["entries"]]) for line in lines] == [
        (1, ["000000000001"]), (4, ["000000000002", "000000000003", "000000000004"])]

    audit.configure()  # restart on the same file (NFR3.1)
    entries = audit.page(REGIONAL)["entries"]
    assert [e["entry_id"] for e in entries] == [*batch[::-1], single]
    assert {k: entries[-1][k] for k in _entry()} == _entry(record_id="emp_a")
    assert [e["file_row"] for e in entries[:3]] == [3, 2, 1]
    assert audit.append(_entry()) == "000000000005"


def test_torn_batch_line_is_dropped_whole(audit_path, capsys):
    audit.append(_entry(record_id="kept"))
    good = audit_path.read_bytes()
    torn = audit._encode_call(4, [json.dumps(_legacy_entry(i)).encode() for i in (2, 3, 4)])
    assert torn.endswith(b"\n")
    audit_path.write_bytes(good + torn[:-1])  # the batch line lost only its newline
    capsys.readouterr()

    audit.configure()
    assert "torn line dropped" in capsys.readouterr().err
    assert audit_path.read_bytes() == good  # cut back to the previous line end
    assert _all_ids() == ["000000000001"]  # none of the batch's entries
    assert audit.append(_entry(record_id="after")) == "000000000002"  # the torn batch consumed no id

    audit.configure()
    assert [e["record_id"] for e in audit.page(REGIONAL)["entries"]] == ["after", "kept"]


@pytest.mark.parametrize("corrupt_at, line_no", [("middle", 2), ("last", 2)])
def test_newline_terminated_corrupt_line_makes_trail_unavailable(audit_path, capsys, corrupt_at, line_no):
    audit.append(_entry())
    with open(audit_path, "ab") as f:
        f.write(b'{"hwm": 2, "entries": [{"entry_id": \n')
    if corrupt_at == "middle":
        audit.append(_entry())
    before = audit_path.read_bytes()
    capsys.readouterr()

    audit.configure()
    assert _error_lines(capsys.readouterr().err) == [
        f"[mock-hsm] ERROR audit: trail unavailable, unreadable line {line_no} in {audit_path}"]
    for call in (lambda: audit.append(_entry()), lambda: audit.append_batch([_entry()]),
                 lambda: audit.page(REGIONAL)):
        with pytest.raises(audit.AuditUnavailable):
            call()
    assert audit_path.read_bytes() == before  # never repaired or cut off by the module


@pytest.mark.parametrize("bad_line", [
    b"",                                                         # an empty line
    b"[1, 2, 3]",                                                # not an object
    b'{"hwm": 9, "entries": [{"entry_id": "000000000009"}]}',     # entry without a timestamp
    b'{"hwm": 1, "entries": [' + json.dumps(_legacy_entry(5)).encode() + b"]}",  # id above its hwm
    b'{"hwm": 9, "entries": [' + json.dumps(_legacy_entry(1)).encode() + b"]}",  # id not increasing
    b'{"_meta": {"next_id": 7}}',                                # metadata line is only valid first
])
def test_unreadable_lines_in_either_layout(audit_path, bad_line):
    audit.append(_entry())
    with open(audit_path, "ab") as f:
        f.write(bad_line + b"\n")
    audit.configure()
    with pytest.raises(audit.AuditUnavailable, match="unreadable line 2"):
        audit.page(REGIONAL)


def test_old_layout_file_loads_and_is_rewritten_in_the_new_layout(audit_path, capsys):
    legacy_meta = b'{"_meta": {"next_id":           41}}'  # the old fixed-width metadata line
    audit_path.write_bytes(b"\n".join([legacy_meta, json.dumps(_legacy_entry(30)).encode(),
                                       json.dumps(_legacy_entry(33, site_id="site_002")).encode()]) + b"\n")
    capsys.readouterr()

    audit.configure(clock=FakeClock(T0))
    assert "loaded 2 entries, torn line none, purged 0, high-water mark 000000000040" in capsys.readouterr().err
    assert _all_ids() == ["000000000033", "000000000030"]
    # The startup purge rewrote it: a leading metadata line, then one line per old entry.
    assert [(line["hwm"], len(line["entries"])) for line in _stored_lines(audit_path)] == [(40, 0), (30, 1), (33, 1)]
    assert audit.append(_entry()) == "000000000041"  # continues from the old metadata, not the highest id

    audit.configure(clock=FakeClock(T0))
    assert _all_ids() == ["000000000041", "000000000033", "000000000030"]


def test_mixed_layout_file_loads_after_a_failed_rewrite(audit_path, monkeypatch):
    audit_path.write_bytes(json.dumps(_legacy_entry(7)).encode() + b"\n")

    def no_replace(src, dst):
        raise OSError("rename refused")

    with monkeypatch.context() as mp:
        mp.setattr(audit.os, "replace", no_replace)
        audit.configure(clock=FakeClock(T0))  # the legacy rewrite fails before the swap: old file kept
    assert audit.append(_entry()) == "000000000008"  # appended in the new layout after the old line
    audit.configure(clock=FakeClock(T0))
    assert _all_ids() == ["000000000008", "000000000007"]
    assert [sorted(line) for line in _stored_lines(audit_path)] == [["entries", "hwm"]] * 3


def test_file_and_directory_permissions(tmp_path):
    path = tmp_path / "fresh" / "audit.jsonl"
    audit.configure(path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700

    wide = tmp_path / "wide" / "audit.jsonl"
    wide.parent.mkdir(mode=0o755)
    os.chmod(wide.parent, 0o755)
    wide.write_bytes(b"")
    os.chmod(wide, 0o644)
    audit._tmp_path(wide).write_bytes(b"leftover from a crashed purge")
    audit.configure(wide)
    assert wide.stat().st_mode & 0o777 == 0o600
    assert wide.parent.stat().st_mode & 0o777 == 0o700
    assert not audit._tmp_path(wide).exists()


def test_purge_temp_file_is_owner_only(audit_path, monkeypatch):
    clock = FakeClock(T0 - timedelta(days=100))
    audit.configure(clock=clock)
    audit.append(_entry())
    seen = []
    real_replace = os.replace

    def checking_replace(src, dst):
        seen.append(os.stat(src).st_mode & 0o777)
        real_replace(src, dst)

    monkeypatch.setattr(audit.os, "replace", checking_replace)
    clock.now = T0
    audit.configure(clock=clock)
    assert seen == [0o600]
    assert audit_path.stat().st_mode & 0o777 == 0o600


_KILL_SCRIPT = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, sys.argv[1])
    from mock_hsm import audit
    audit.configure(sys.argv[2])
    entry = {"user_id": "user_rm_midtown", "source": "dashboard", "action": "add", "outcome": "allowed",
             "kind": "employee", "record_id": "emp_killed", "site_id": "site_001"}
    print(audit.append(entry), flush=True)
    time.sleep(60)
""")


def test_append_survives_sigkill(tmp_path):
    path = tmp_path / "killed" / "audit.jsonl"
    proc = subprocess.Popen([sys.executable, "-c", _KILL_SCRIPT, str(PROJECT_ROOT), str(path)],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        entry_id = proc.stdout.readline().strip()
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=10)
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == -signal.SIGKILL
    assert entry_id == "000000000001"

    audit.configure(path)  # restart after the kill
    [entry] = audit.page(REGIONAL)["entries"]
    assert (entry["entry_id"], entry["record_id"]) == (entry_id, "emp_killed")


def test_purge_failure_before_the_swap_keeps_the_original_file(audit_path, monkeypatch, capsys):
    clock = FakeClock(T0 - timedelta(days=100))
    audit.configure(clock=clock)
    old = audit.append(_entry(record_id="old"))
    clock.now = T0
    original = audit_path.read_bytes()
    capsys.readouterr()

    def no_replace(src, dst):
        raise OSError("rename refused")

    with monkeypatch.context() as mp:
        mp.setattr(audit.os, "replace", no_replace)
        recent = audit.append(_entry(record_id="recent"))  # the due purge fails first; the append still works
    assert _error_lines(capsys.readouterr().err) == [
        "[mock-hsm] ERROR audit: purge failed before swap, replacing file (rename refused); "
        "old file kept, trail available, retry in 24 hours"]
    assert audit_path.read_bytes().startswith(original)
    assert not audit._tmp_path(audit_path).exists()
    assert _all_ids() == [recent, old]

    clock.now = T0 + timedelta(hours=23)  # not retried before the next 24-hour check
    audit.append(_entry())
    assert old in _all_ids()
    clock.now = T0 + timedelta(hours=24)
    assert old not in _all_ids()  # retried, and this time it worked


def test_purge_failure_after_the_swap_fails_closed(audit_path, monkeypatch, capsys):
    clock = FakeClock(T0 - timedelta(days=100))
    audit.configure(clock=clock)
    audit.append(_entry())
    clock.now = T0
    capsys.readouterr()

    def broken_dir_fsync(path):
        raise OSError("I/O error")

    monkeypatch.setattr(audit, "_fsync_dir", broken_dir_fsync)
    with pytest.raises(audit.AuditUnavailable):
        audit.append(_entry())
    assert _error_lines(capsys.readouterr().err) == [
        "[mock-hsm] ERROR audit: purge failed after swap, reopening file (I/O error); trail unavailable"]
    with pytest.raises(audit.AuditUnavailable):
        audit.page(REGIONAL)


# =========================================================== business logic

def test_lazy_initialization_on_first_use(audit_path, monkeypatch):
    monkeypatch.setattr(audit._current, "state", None)
    assert audit.append(_entry()) == "000000000001"
    assert audit_path.exists() and audit_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("overrides", [
    {"user_id": None}, {"user_id": ""}, {"source": None}, {"action": None}, {"outcome": None},
    {"source": "cli"}, {"action": "rename"}, {"outcome": "maybe"},
    {"outcome": "violation", "reason": None}, {"outcome": "violation", "reason": "  "},
    {"action": "login", "outcome": "violation", "reason": "bad password"},
    {"persona_site_ids": ["site_001"]}, {"changes": ["not", "an", "object"]},
    {"file_row": 0}, {"file_row": True}, {"file_row": "3"}, {"site_id": 7}, {"reason": b"bytes"},
])
def test_incomplete_entries_are_refused(audit_path, overrides):
    with pytest.raises(audit.InvalidEntry):
        audit.append(_entry(**overrides))
    with pytest.raises(audit.InvalidEntry):  # one bad item refuses the whole batch
        audit.append_batch([_entry(), _entry(**overrides)])
    assert audit.page(REGIONAL)["total"] == 0
    assert audit_path.read_bytes() == b""
    assert audit.append(_entry()) == "000000000001"  # a refusal consumes no id


@pytest.mark.parametrize("entries", [[], None, "entry", {"user_id": "u"}])
def test_batch_must_be_a_non_empty_list(audit_path, entries):
    with pytest.raises(audit.InvalidEntry):
        audit.append_batch(entries)


def test_unknown_session_less_write_is_recorded(audit_path):
    entry_id = audit.append(_entry(user_id=audit.UNKNOWN_USER, persona=None, session_id=None,
                                   outcome="violation", reason="no session"))
    [stored] = audit.page(REGIONAL)["entries"]
    assert stored["entry_id"] == entry_id
    assert (stored["user_id"], stored["persona"], stored["session_id"], stored["outcome"]) == (
        "unknown", None, None, "violation")


def test_developer_tester_keeps_its_own_user_id_uncut(audit_path):
    long_id = "user_dev_tester_" + "x" * 2_000  # identity fields are never cut (NFR6.1)
    audit.append(_entry(user_id="user_regional_atl", persona="REGIONAL_MANAGER"))
    audit.append(_entry(user_id="user_dev_tester", persona="SYSTEM_ADMIN"))
    audit.append(_entry(user_id=long_id, persona="SYSTEM_ADMIN", session_id="s" * 2_000))
    users = [(e["user_id"], e["persona"]) for e in audit.page(REGIONAL)["entries"]]
    assert users == [(long_id, "SYSTEM_ADMIN"), ("user_dev_tester", "SYSTEM_ADMIN"),
                     ("user_regional_atl", "REGIONAL_MANAGER")]
    assert audit.page(REGIONAL)["entries"][0]["session_id"] == "s" * 2_000


def _entry_bytes(stored):
    return len(json.dumps(stored, separators=(",", ":")))


def test_oversized_changes_are_truncated_to_the_marker(audit_path):
    big = {"notes": "x" * 50_000}
    audit.append(_entry(action="bulk_row", file_row=3, changes=big))
    [stored] = audit.page(REGIONAL)["entries"]
    assert _entry_bytes(stored) <= audit.ENTRY_MAX_BYTES
    assert stored["changes"] == {"truncated": True, "original_bytes": len(json.dumps(big, separators=(",", ":")))}
    assert (stored["file_row"], stored["record_id"]) == (3, "emp_1")  # the rest of the entry is kept


def test_long_text_fields_are_cut_to_1024_characters(audit_path):
    audit.append(_entry(outcome="violation", reason="r" * 5_000, site_id="s" * 5_000,
                        kind="k" * 5_000, record_id="i" * 5_000))
    [stored] = audit.page(REGIONAL)["entries"]
    assert [len(stored[f]) for f in ("reason", "site_id", "kind", "record_id")] == [audit.TEXT_MAX_CHARS] * 4
    assert stored["changes"] == {"name": "Ana"}  # fits once the text is cut, so changes is kept
    assert _entry_bytes(stored) <= audit.ENTRY_MAX_BYTES


def test_non_ascii_text_that_cannot_fit_is_refused(audit_path):
    wide = "\U0001f600" * 1_024  # 12 encoded bytes per character
    with pytest.raises(audit.InvalidEntry, match="exceeds"):
        audit.append(_entry(outcome="violation", reason=wide, site_id=wide, kind=wide, record_id=wide))
    assert audit_path.read_bytes() == b""


@pytest.mark.parametrize("bad_changes", [{"x": float("nan")}, {"x": {1, 2}}, {("a", "b"): 1}])
def test_unserializable_changes_are_replaced_by_the_marker(audit_path, bad_changes):
    audit.append(_entry(changes=bad_changes))
    [stored] = audit.page(REGIONAL)["entries"]
    assert stored["changes"] == {"truncated": True, "unserializable": True}


def test_an_entry_exactly_at_the_cap_is_stored(audit_path):
    audit.append(_entry(changes={"pad": ""}))
    base = _entry_bytes(audit.page(REGIONAL)["entries"][0])
    fill = audit.ENTRY_MAX_BYTES - base

    audit.append(_entry(changes={"pad": "p" * fill}))
    exact = audit.page(REGIONAL)["entries"][0]
    assert exact["changes"] == {"pad": "p" * fill}
    assert _entry_bytes(exact) == audit.ENTRY_MAX_BYTES

    audit.append(_entry(changes={"pad": "p" * (fill + 1)}))  # one byte over: marker
    assert audit.page(REGIONAL)["entries"][0]["changes"]["truncated"] is True


def test_page_returns_copies(audit_path):
    audit.append(_entry())
    audit.page(REGIONAL)["entries"][0]["changes"]["name"] = "tampered"
    assert audit.page(REGIONAL)["entries"][0]["changes"] == {"name": "Ana"}


def test_caller_objects_are_copied_in(audit_path):
    changes = {"name": "Ana"}
    audit.append(_entry(changes=changes))
    changes["name"] = "changed after the append"
    assert audit.page(REGIONAL)["entries"][0]["changes"] == {"name": "Ana"}


def test_purge_removes_only_entries_older_than_90_days(audit_path, capsys):
    clock = FakeClock(T0 - timedelta(days=91))
    audit.configure(clock=clock)
    old = audit.append(_entry(record_id="old"))
    clock.now = T0 - timedelta(days=1)
    recent = audit.append(_entry(record_id="recent"))  # 90 days on: old is exactly 90 days old, kept
    assert _all_ids() == [recent, old]
    capsys.readouterr()

    clock.now = T0
    audit.configure(clock=clock)  # restart: old is now 91 days old
    assert "loaded 2 entries, torn line none, purged 1, high-water mark 000000000002" in capsys.readouterr().err
    assert _all_ids() == [recent]
    assert [len(line["entries"]) for line in _stored_lines(audit_path)] == [0, 1]
    assert audit.append(_entry()) == "000000000003"  # appends go to the new file
    audit.configure(clock=clock)
    assert _all_ids() == ["000000000003", recent]


def test_purging_everything_never_reuses_ids(audit_path):
    clock = FakeClock(T0 - timedelta(days=200))
    audit.configure(clock=clock)
    audit.append(_entry())
    audit.append_batch([_entry(), _entry()])
    clock.now = T0
    assert audit.page(REGIONAL)["total"] == 0  # the due lazy purge removed all three

    audit.configure(clock=clock)  # restart with an entry-less file
    assert _stored_lines(audit_path) == [{"hwm": 3, "entries": []}]
    assert audit.page(REGIONAL)["total"] == 0  # the metadata line is never shown
    assert audit.append(_entry()) == "000000000004"


def test_lazy_purge_runs_once_24_hours_have_passed(audit_path):
    clock = FakeClock(T0)
    audit.configure(clock=clock)  # startup purge at T0
    clock.now = T0 - timedelta(days=95)
    expired = audit.append(_entry(record_id="expired"))  # clock went back: no purge, an old entry
    clock.now = T0 + timedelta(hours=23)
    audit.append(_entry())
    assert expired in _all_ids()  # 23 hours since the last purge: not due

    clock.now = T0 + timedelta(hours=25)
    third = audit.append(_entry(record_id="third"))  # due: the purge runs first, then the append
    # Rewritten before the third entry was added: metadata line, entry 2, then entry 3.
    assert [(line["hwm"], [e["entry_id"] for e in line["entries"]]) for line in _stored_lines(audit_path)] == [
        (2, []), (2, ["000000000002"]), (3, [third])]
    assert _all_ids() == [third, "000000000002"]


def test_a_page_call_also_runs_a_due_purge(audit_path):
    clock = FakeClock(T0 - timedelta(days=100))
    audit.configure(clock=clock)
    audit.append(_entry())
    clock.now = T0
    assert audit.page(REGIONAL)["total"] == 0
    assert _stored_lines(audit_path) == [{"hwm": 1, "entries": []}]


def test_concurrent_appends_are_serialized(audit_path):
    errors, pages = [], []
    stop = threading.Event()

    def writer(n):
        try:
            for i in range(50):
                audit.append(_entry(record_id=f"w{n}-{i}"))
        except Exception as e:  # noqa: BLE001 -- surfaced through the errors list below
            errors.append(e)

    def reader():
        while not stop.is_set():
            pages.append(audit.page(REGIONAL))

    read_thread = threading.Thread(target=reader)
    read_thread.start()
    writers = [threading.Thread(target=writer, args=(n,)) for n in range(20)]
    for t in writers:
        t.start()
    for t in writers:
        t.join()
    stop.set()
    read_thread.join()

    assert not errors
    ids = _all_ids()
    assert len(ids) == len(set(ids)) == 1000
    assert sorted(int(i) for i in ids) == list(range(1, 1001))
    lines = _stored_lines(audit_path)
    assert len(lines) == 1000 and all(len(line["entries"]) == 1 for line in lines)  # never interleaved
    assert len(pages) > 1
    for result in pages:  # every concurrent page is a consistent, gap-free snapshot
        page_ids = [int(e["entry_id"]) for e in result["entries"]]
        if page_ids:
            assert page_ids[0] == result["total"]
            assert page_ids == list(range(page_ids[0], page_ids[0] - len(page_ids), -1))


def _seed_visibility_entries():
    unknown = {"user_id": audit.UNKNOWN_USER, "persona": None, "session_id": None, "outcome": "violation",
               "reason": "no session"}
    return {
        "rm_site1": audit.append(_entry()),
        "regional_site2": audit.append(_entry(user_id="user_regional_atl", persona="REGIONAL_MANAGER",
                                              site_id="site_002")),
        "regional_region_po": audit.append(_entry(user_id="user_regional_atl", persona="REGIONAL_MANAGER",
                                                  site_id=None, kind="purchase_order")),
        "unknown_site1": audit.append(_entry(**unknown)),
        "unknown_shared": audit.append(_entry(**unknown, kind="uom", site_id=None)),
        "unknown_site2": audit.append(_entry(**unknown, site_id="site_002")),
        "rm_login": audit.append(_entry(action="login", kind=None, record_id=None, site_id=None, changes=None)),
        "dev_site3": audit.append(_entry(user_id="user_dev_tester", persona="SYSTEM_ADMIN", site_id="site_003")),
    }


EVERYTHING = {"rm_site1", "regional_site2", "regional_region_po", "unknown_site1", "unknown_shared",
              "unknown_site2", "rm_login", "dev_site3"}


@pytest.mark.parametrize("viewer, expected", [
    (REGIONAL, EVERYTHING),
    (ADMIN, EVERYTHING),
    # BR4.2: the same site/own test for every entry, "unknown" ones included.
    (RM, {"rm_site1", "unknown_site1", "rm_login"}),
    ({"user_id": "user_rm_buckhead", "persona": "RESTAURANT_MANAGER", "site_ids": ["site_002"],
      "region_id": None}, {"regional_site2", "unknown_site2"}),
    ({"user_id": "nobody", "persona": "RESTAURANT_MANAGER", "site_ids": None, "region_id": None}, set()),
])
def test_visibility_follows_token_scope(audit_path, viewer, expected):
    ids = _seed_visibility_entries()
    result = audit.page(viewer)
    assert {e["entry_id"] for e in result["entries"]} == {ids[k] for k in expected}
    assert result["total"] == len(expected)


def test_viewer_without_a_user_id_is_refused(audit_path):
    with pytest.raises(ValueError, match="user_id"):
        audit.page({"persona": "SYSTEM_ADMIN", "site_ids": [], "region_id": None})


def test_paging_by_before_newest_first(audit_path):
    for i in range(130):  # every third entry is another site's, invisible to the RM
        audit.append(_entry(site_id="site_002" if i % 3 == 2 else "site_001",
                            user_id="user_regional_atl" if i % 3 == 2 else "user_rm_midtown"))
    first = audit.page(REGIONAL)
    assert (first["limit"], first["total"], len(first["entries"])) == (50, 130, 50)
    assert first["entries"][0]["entry_id"] == "000000000130"
    assert first["next_before"] == "000000000081"
    second = audit.page(REGIONAL, first["next_before"])
    assert [e["entry_id"] for e in second["entries"]] == [f"{i:012d}" for i in range(80, 30, -1)]
    third = audit.page(REGIONAL, second["next_before"])
    assert len(third["entries"]) == 30 and third["next_before"] is None and third["total"] == 130

    rm_ids = _all_ids(RM)
    assert len(rm_ids) == audit.page(RM)["total"] == 87
    assert all(int(i) % 3 != 0 for i in rm_ids)  # ids 3, 6, ... are site_002's


def test_any_well_formed_before_is_accepted(audit_path):
    clock = FakeClock(T0 - timedelta(days=100))
    audit.configure(clock=clock)
    purged = [audit.append(_entry()) for _ in range(3)]
    clock.now = T0
    kept = [audit.append(_entry()) for _ in range(3)]  # the due purge removed the first three

    assert audit.page(REGIONAL, purged[-1]) == {"entries": [], "next_before": None, "limit": 50, "total": 3}
    beyond = audit.page(REGIONAL, "000000009999")  # an id never assigned: everything is older
    assert [e["entry_id"] for e in beyond["entries"]] == kept[::-1]
    hidden = audit.append(_entry(site_id="site_002", user_id="user_regional_atl"))
    assert [e["entry_id"] for e in audit.page(RM, hidden)["entries"]] == kept[::-1]  # a hidden id is just a position


@pytest.mark.parametrize("before", ["abc", "42", "0000000000042", "00000000004x", " 00000000042", 42, ["x"]])
def test_malformed_before_is_refused(audit_path, before):
    audit.append(_entry())
    with pytest.raises(audit.InvalidPageRequest):
        audit.page(REGIONAL, before)


def test_page_never_writes(audit_path):
    for _ in range(60):
        audit.append(_entry())
    before = audit_path.read_bytes()
    _all_ids(REGIONAL)
    _all_ids(RM)
    assert audit_path.read_bytes() == before


def test_failed_append_fails_closed_with_one_error_line(audit_path, monkeypatch, capsys):
    assert audit.append(_entry()) == "000000000001"
    size = audit_path.stat().st_size
    capsys.readouterr()

    def broken_write(fd, data):
        raise OSError("No space left on device")

    with monkeypatch.context() as mp:
        mp.setattr(audit, "_write_all", broken_write)
        with pytest.raises(audit.AuditUnavailable):
            audit.append(_entry(kind="employee", record_id="emp_9"))
    for call in (lambda: audit.append(_entry()), lambda: audit.append_batch([_entry()]),
                 lambda: audit.page(REGIONAL)):  # stays unavailable even though writes work again
        with pytest.raises(audit.AuditUnavailable):
            call()
    assert _error_lines(capsys.readouterr().err) == [
        "[mock-hsm] ERROR audit: append failed (No space left on device) for add employee/emp_9; "
        "trail unavailable"]
    assert audit_path.stat().st_size == size

    audit.configure()  # operator restart
    assert audit.append(_entry()) == "000000000002"  # the failed append consumed no id


def test_failed_batch_append_logs_its_first_entry(audit_path, monkeypatch, capsys):
    def half_then_fail(fd, data):
        os.write(fd, data[: len(data) // 2])
        raise OSError("disk full")

    monkeypatch.setattr(audit, "_write_all", half_then_fail)
    with pytest.raises(audit.AuditUnavailable):
        audit.append_batch([_entry(action="bulk_row", file_row=1, record_id="r1"), _entry(file_row=2)])
    assert _error_lines(capsys.readouterr().err) == [
        "[mock-hsm] ERROR audit: batch append failed (disk full) for 2 entries, first bulk_row employee/r1; "
        "trail unavailable"]
    assert audit_path.read_bytes() == b""  # the partial line was truncated back


def test_failed_rollback_names_the_offset(audit_path, monkeypatch, capsys):
    audit.append(_entry())
    offset = audit_path.stat().st_size
    capsys.readouterr()

    def half_then_fail(fd, data):
        os.write(fd, data[: len(data) // 2])
        raise OSError("disk full")

    def no_truncate(fd, length):
        raise OSError("read-only file system")

    with monkeypatch.context() as mp:
        mp.setattr(audit, "_write_all", half_then_fail)
        mp.setattr(audit.os, "ftruncate", no_truncate)
        with pytest.raises(audit.AuditUnavailable):
            audit.append(_entry(record_id="emp_2"))
    assert _error_lines(capsys.readouterr().err) == [
        "[mock-hsm] ERROR audit: append failed (disk full) for add employee/emp_2; trail unavailable; "
        f"rollback failed (read-only file system): remove every byte from offset {offset} onward in "
        f"{audit_path} before restarting"]
    assert audit_path.stat().st_size > offset  # the half line is still there

    audit.configure()  # the leftover is an unterminated line, so startup drops it as torn
    assert audit_path.stat().st_size == offset
    assert audit.append(_entry()) == "000000000002"


def test_record_id_with_a_newline_gives_one_log_line(audit_path, monkeypatch, capsys):
    monkeypatch.setattr(audit, "_write_all", lambda fd, data: (_ for _ in ()).throw(OSError("eio")))
    capsys.readouterr()
    with pytest.raises(audit.AuditUnavailable):
        audit.append(_entry(record_id="emp_1\n[mock-hsm] ERROR audit: forged\x1b[2J" + "z" * 300))
    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1
    assert "forged" in err and "\x1b" not in err and "z" * 101 not in err
    assert "Ana" not in err and "sess-1" not in err  # never changes or session ids


def test_startup_line_counts(audit_path, capsys):
    clock = FakeClock(T0 - timedelta(days=100))
    audit.configure(clock=clock)
    audit.append(_entry())
    clock.now = T0
    audit.configure(clock=clock)  # purges the first entry at startup
    audit.append_batch([_entry(), _entry()])
    with open(audit_path, "ab") as f:
        f.write(b'{"hwm": 9, "entries": [')  # a torn last line
    capsys.readouterr()

    audit.configure(clock=clock)
    info = [line for line in capsys.readouterr().err.splitlines() if " INFO " in line]
    assert info == ["[mock-hsm] INFO audit: loaded 2 entries, torn line dropped, purged 0, "
                    "high-water mark 000000000003"]


# ------------------------------------------------------------------- perf
# NFR3.5-NFR3.8 on the machine running the suite. Each failure reports the
# measured value next to its target; the measured values are also printed
# (visible with `pytest -s`).

def _write_large_trail(path, count, now, expired=1_000):
    """Write ``count`` entries directly in the new layout: ``expired`` of them
    older than 90 days, spread across three sites and users, every tenth line
    a five-entry batch, ending in a torn line."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    old_ts = (now - timedelta(days=120)).isoformat(timespec="microseconds")
    new_ts = (now - timedelta(days=1)).isoformat(timespec="microseconds")
    users = ["user_rm_midtown", "user_regional_atl", "user_rm_buckhead"]

    def entry(i):
        return json.dumps({
            "entry_id": f"{i:012d}", "timestamp": old_ts if i <= expired else new_ts,
            "user_id": users[i % 3], "persona": "RESTAURANT_MANAGER", "session_id": None,
            "source": "dashboard", "action": "update", "outcome": "allowed", "kind": "on_hand",
            "record_id": f"rm_{i % 12}", "site_id": f"site_00{i % 3 + 1}",
            "changes": {"before": {"qty": i - 1}, "after": {"qty": i}}, "reason": None, "file_row": None,
        }, separators=(",", ":")).encode()

    lines, i = [], 1
    while i <= count:
        size = 5 if len(lines) % 10 == 9 else 1
        ids = range(i, min(i + size, count + 1))
        lines.append(audit._encode_call(ids[-1], [entry(n) for n in ids]))
        i = ids[-1] + 1
    path.write_bytes(b"".join(lines) + b'{"hwm": ' + str(count + 1).encode())
    os.chmod(path, 0o600)


def _report(name, seconds, target):
    print(f"\n[perf] {name}: {seconds * 1000:.1f} ms (target {target * 1000:.0f} ms)")


@pytest.mark.perf
def test_perf_append_p95_under_50ms(audit_path):
    durations = []
    for i in range(1_000):
        start = time.perf_counter()
        audit.append(_entry(record_id=f"emp_{i}"))
        durations.append(time.perf_counter() - start)
    p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
    _report("append p95 of 1,000", p95, 0.050)
    assert p95 <= 0.050, f"append p95 {p95 * 1000:.1f} ms exceeds the 50 ms target (NFR3.5)"


@pytest.mark.perf
def test_perf_batch_of_500_under_2s(audit_path):
    rows = [_entry(action="bulk_row", file_row=i, record_id=f"rm_{i}", changes={"record": {"qty": i, "uom": "lb"}})
            for i in range(1, 501)]
    start = time.perf_counter()
    ids = audit.append_batch(rows)
    elapsed = time.perf_counter() - start
    _report("500-entry batch", elapsed, 2.0)
    assert len(ids) == 500 and len(_stored_lines(audit_path)) == 1
    assert elapsed <= 2.0, f"500-entry batch took {elapsed:.3f} s; target 2 s (NFR3.6)"


@pytest.mark.perf
def test_perf_startup_and_page_at_100k_entries(audit_path):
    _write_large_trail(audit_path, 100_000, T0)
    clock = FakeClock(T0)

    start = time.perf_counter()
    audit.configure(clock=clock)  # load + torn line + purge of 1,000 + in-memory copy
    startup = time.perf_counter() - start
    _report("startup with 100,000 entries", startup, 5.0)
    assert startup <= 5.0, f"startup took {startup:.2f} s; target 5 s (NFR3.8)"
    assert audit.page(REGIONAL)["total"] == 99_000

    for viewer in (REGIONAL, RM):
        before = None
        for page_no in (1, 2):
            start = time.perf_counter()
            result = audit.page(viewer, before)
            elapsed = time.perf_counter() - start
            _report(f"page {page_no} for {viewer['persona']}", elapsed, 1.0)
            assert len(result["entries"]) == 50
            assert elapsed <= 1.0, (f"page {page_no} for {viewer['persona']} took {elapsed:.3f} s; "
                                    f"target 1 s (NFR3.7)")
            before = result["next_before"]
