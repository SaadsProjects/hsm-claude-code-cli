"""
Unit tests for the U1 building blocks in mock_hsm/writes.py and the batch
append in mock_hsm/audit.py: the kind catalog, record metadata, the audit
batch, the record store adapter, id counters, the validator, sessions,
quotas and the request log. No HTTP server is needed.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mock_hsm import audit, db, writes
from mock_hsm.auth import mint_token, verify_token

ALL_SEEING = {"user_id": "test-auditor", "persona": "SYSTEM_ADMIN", "site_ids": [], "region_id": None}


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    fake = FakeClock()
    writes.set_clock(fake)
    return fake  # WriteTestReset restores the real clock


def _claims(user):
    return verify_token(mint_token(user))


def _entries():
    entries, before = [], None
    while True:
        page = audit.page(ALL_SEEING, before)
        entries += page["entries"]
        before = page["next_before"]
        if before is None:
            return entries[::-1]


def _entry(**overrides):
    return {"user_id": "user_regional_atl", "persona": "REGIONAL_MANAGER", "session_id": "s1",
            "source": "dashboard", "action": "bulk_row", "outcome": "allowed", "kind": "uom",
            "record_id": "u1", "site_id": None, "changes": {"record": {}}, "reason": None, "file_row": 1,
            **overrides}


class Session:
    """A persona's login session driving the write service directly."""

    def __init__(self, user):
        self.claims = _claims(user)
        status, body = writes.start_session(self.claims)
        assert status == 201
        self.id = body["session_id"]

    def add(self, kind, record, site=None):
        body = {"session_id": self.id, "request_id": str(uuid.uuid4()), "record": record}
        return writes.write(kind, "add", self.claims, site, None, body)

    def bulk(self, kind, records, site=None):
        rows = [{"row": i, "record": r} for i, r in enumerate(records, start=1)]
        body = {"session_id": self.id, "request_id": str(uuid.uuid4()), "source": "csv", "file_name": "f.csv",
                "rows": rows}
        return writes.bulk(kind, self.claims, site, body)


def _uom(uom_id, base=None):
    return {"uom_id": uom_id, "name": f"unit {uom_id}", "base": base or uom_id, "factor_to_base": 1}


def _employee(job_code="jc_core"):
    return {"name": "Robin", "job_code": job_code, "hourly_rate": 15, "max_weekly_hours_preference": 30,
            "available_days": ["Mon", "Tue"]}


# =================================================================== catalog

def test_catalog_has_the_eleven_kinds():
    assert set(writes.KINDS) == {"menu_item", "recipe", "raw_material", "uom", "vendor", "employee", "job_code",
                                 "on_hand", "par_level", "reorder_point", "labor_rule"}
    assert {k for k, kind in writes.KINDS.items() if kind.scope == "site"} == {"employee", "on_hand"}


@pytest.mark.parametrize("kind_name", ["menu_item", "raw_material", "uom", "vendor", "job_code", "labor_rule"])
def test_catalog_fields_match_the_seeded_records(kind_name):
    kind = writes.KINDS[kind_name]
    for record in getattr(db, kind.attr).values():
        assert set(record) == {f.name for f in kind.fields}
    assert tuple(f.name for f in kind.fields) == kind.csv_columns


def test_catalog_columns_for_the_other_kinds_match_seeded_shapes():
    employee = writes.KINDS["employee"]
    derived = {"employee_id", "site_id", "jurisdiction"}
    for record in db.EMPLOYEES.values():
        assert set(record) - derived == set(employee.csv_columns)
    for line in db.RECIPES["mi_burger"]:
        assert set(line) | {"menu_item_id"} == set(writes.KINDS["recipe"].csv_columns)
    for name in ("on_hand", "par_level", "reorder_point"):
        assert writes.KINDS[name].csv_columns == ("raw_material_id", "qty")


def test_template_is_columns_and_a_header_line():
    status, body = writes.template("vendor", _claims("user_regional_atl"))
    assert status == 200
    assert body == {"columns": ["vendor_id", "name", "lead_time_days", "price_list", "min_order_value"],
                    "csv": "vendor_id,name,lead_time_days,price_list,min_order_value\n"}


def test_site_template_needs_a_site_in_scope():
    rm = _claims("user_rm_midtown")
    assert writes.template("employee", rm, "site_001")[0] == 200
    assert writes.template("employee", rm, "site_002")[0] == 403
    assert writes.template("on_hand", rm, "site_404")[0] == 404


# ====================================================================== meta

def test_every_seeded_record_has_system_meta_at_version_1():
    total = 0
    for kind in writes.KINDS.values():
        for site_id, key in writes.iter_keys(kind):
            meta = writes.get_meta(kind, site_id, key)
            assert (meta["origin"], meta["created_by"], meta["version"]) == ("seeded", "system", 1)
            assert meta["created_session"] is None
            total += 1
    assert total == 116


def test_wire_meta_has_exactly_the_six_fields():
    meta = writes.meta_map("uom")["lb"]
    assert set(meta) == {"origin", "created_by", "created_at", "updated_by", "updated_at", "version"}
    assert datetime.fromisoformat(meta["created_at"]).tzinfo is not None


def test_site_meta_is_listed_per_site():
    assert set(writes.meta_map("on_hand", "site_002")) == set(db.ON_HAND["site_002"])
    assert set(writes.meta_map("employee", "site_003")) == {k for k, e in db.EMPLOYEES.items()
                                                            if e["site_id"] == "site_003"}


# ============================================================= append_batch

def test_append_batch_writes_entries_with_consecutive_ids(audit_path):
    first = audit.append(_entry(action="login", kind=None, record_id=None, file_row=None, changes=None))
    ids = audit.append_batch([_entry(file_row=1), _entry(file_row=2, record_id="u2"), _entry(file_row=3)])
    assert [int(i) for i in ids] == [int(first) + 1, int(first) + 2, int(first) + 3]
    assert [e["file_row"] for e in _entries()[1:]] == [1, 2, 3]
    # One line per call: the login, then the whole batch as one line (BR1.2, NFR3.3).
    lines = [json.loads(line) for line in audit_path.read_bytes().splitlines()]
    assert [[e["entry_id"] for e in line["entries"]] for line in lines] == [[first], ids]
    audit.configure(audit_path)  # reload: the batch line is read back whole
    assert [e["entry_id"] for e in _entries()] == [first, *ids]


def test_failed_batch_write_leaves_no_entries_and_fails_closed(monkeypatch, audit_path):
    audit.append(_entry(action="login", kind=None, record_id=None, file_row=None, changes=None))
    before = audit_path.read_bytes()

    def half_then_fail(fd, data):
        os.write(fd, data[: len(data) // 2])
        raise OSError("disk full")

    monkeypatch.setattr(audit, "_write_all", half_then_fail)
    with pytest.raises(audit.AuditUnavailable):
        audit.append_batch([_entry(file_row=1), _entry(file_row=2)])
    assert audit_path.read_bytes() == before  # the partial write was truncated back
    monkeypatch.undo()
    with pytest.raises(audit.AuditUnavailable):
        audit.append(_entry())


def test_invalid_entry_in_a_batch_writes_nothing(audit_path):
    with pytest.raises(audit.InvalidEntry):
        audit.append_batch([_entry(file_row=1), _entry(outcome="violation", reason=None)])
    with pytest.raises(audit.InvalidEntry):
        audit.append_batch([])
    assert audit_path.read_bytes() == b""
    assert len(audit.append_batch([_entry()])) == 1  # the trail is still up


def test_batch_exceeding_the_id_space_is_refused_whole(audit_path):
    audit._current.state.next_id = 10 ** audit.ID_WIDTH - 2
    with pytest.raises(audit.AuditUnavailable, match="exhausted"):
        audit.append_batch([_entry(), _entry(), _entry()])
    assert audit_path.read_bytes() == b""
    assert len(audit.append_batch([_entry(), _entry()])) == 2  # exactly fits


# ============================================================== record store

def test_added_record_appears_in_its_collection():
    regional = Session("user_regional_atl")
    status, body = regional.add("uom", _uom("u_core"))
    assert status == 201
    assert db.UOM["u_core"] == {"uom_id": "u_core", "name": "unit u_core", "base": "u_core", "factor_to_base": 1}
    assert body == {"record": db.UOM["u_core"], "meta": writes.meta_map("uom")["u_core"]}
    assert body["meta"]["origin"] == "dashboard" and body["meta"]["created_by"] == "user_regional_atl"


def test_a_record_at_another_site_is_not_found():
    kind = writes.KINDS["employee"]
    assert writes.find(kind, "site_001", "emp_site_001_01")[0]
    assert writes.find(kind, "site_002", "emp_site_001_01") == (False, None)
    assert writes.find(kind, "site_404", "emp_site_001_01") == (False, None)


def test_in_use_lists_name_the_records_that_refer():
    regional = Session("user_regional_atl")
    regional.add("uom", _uom("u_a"))
    regional.add("uom", _uom("u_b", base="u_a"))
    regional.add("raw_material", {"raw_material_id": "rm_a", "name": "A", "uom": "u_a"})
    regional.add("menu_item", {"menu_item_id": "mi_a", "name": "A", "gl_code": "GL-FOOD"})
    regional.add("recipe", {"menu_item_id": "mi_a", "lines": [{"raw_material_id": "rm_a", "qty": 1, "uom": "u_a"}]})
    regional.add("vendor", {"vendor_id": "v_a", "name": "V", "lead_time_days": 1, "price_list": {"rm_a": 2},
                            "min_order_value": 0})
    regional.add("on_hand", {"raw_material_id": "rm_a", "qty": 3}, site="site_002")
    regional.add("par_level", {"raw_material_id": "rm_a", "qty": 3})
    kinds = writes.KINDS
    assert writes.users_of(kinds["raw_material"], "rm_a") == [
        ("recipe", "mi_a"), ("vendor", "v_a"), ("on_hand", "site_002/rm_a"), ("par_level", "rm_a")]
    assert writes.users_of(kinds["uom"], "u_a") == [("raw_material", "rm_a"), ("recipe", "mi_a"), ("uom", "u_b")]
    assert writes.users_of(kinds["menu_item"], "mi_a") == [("recipe", "mi_a")]
    assert writes.users_of(kinds["uom"], "u_b") == []


def test_copy_and_swap_leaves_nothing_behind_on_a_failure_mid_file(monkeypatch):
    regional = Session("user_regional_atl")
    regional.add("uom", _uom("u_swap"))
    before = dict(db.RAW_MATERIALS)
    real_build, calls = writes.build_stored, []

    def fail_on_third(*args):
        calls.append(args)
        if len(calls) == 3:
            raise RuntimeError("boom")
        return real_build(*args)

    monkeypatch.setattr(writes, "build_stored", fail_on_third)
    status, body = regional.bulk("raw_material", [{"raw_material_id": f"rm_s{i}", "name": "S", "uom": "u_swap"}
                                                  for i in range(5)])
    assert (status, body) == (500, {"error": "failed after audit"})
    assert before == db.RAW_MATERIALS
    assert set(writes.meta_map("raw_material")) == set(before)
    entries = [e for e in _entries() if e["kind"] == "raw_material"]
    assert [e["outcome"] for e in entries] == ["allowed"] * 5 + ["violation"] * 5
    assert entries[-1]["reason"] == "failed after audit: RuntimeError"


def test_employee_ids_are_monotonic_per_site_and_only_a_503_releases_one(monkeypatch, audit_path):
    regional = Session("user_regional_atl")
    regional.add("job_code", {"job_code": "jc_core", "title": "Core"})
    assert regional.add("employee", _employee(), site="site_001")[1]["record"]["employee_id"] == "emp_site_001_d001"
    assert regional.add("employee", _employee(), site="site_002")[1]["record"]["employee_id"] == "emp_site_002_d001"

    # A 500 after audit keeps the id: the entries name it.
    monkeypatch.setattr(writes, "build_stored", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert regional.add("employee", _employee(), site="site_001")[0] == 500
    monkeypatch.undo()
    assert regional.add("employee", _employee(), site="site_001")[1]["record"]["employee_id"] == "emp_site_001_d003"

    # A 503 gives the id back.
    monkeypatch.setattr(audit, "_write_all", lambda fd, data: (_ for _ in ()).throw(OSError("ro")))
    assert regional.add("employee", _employee(), site="site_001")[0] == 503
    monkeypatch.undo()
    audit.configure(audit_path)
    assert regional.add("employee", _employee(), site="site_001")[1]["record"]["employee_id"] == "emp_site_001_d004"


def test_id_counters_start_above_the_highest_existing_d_number(monkeypatch):
    monkeypatch.setitem(db.EMPLOYEES, "emp_site_003_d041", {"employee_id": "emp_site_003_d041", "site_id": "site_003"})
    assert writes._seed_id_counters() == {"site_001": 0, "site_002": 0, "site_003": 41}


def test_reset_removes_every_key_not_present_at_seeding():
    seeded = {name: dict(getattr(db, name)) for name in ("UOM", "RAW_MATERIALS", "PAR_LEVELS", "EMPLOYEES")}
    on_hand = {site: dict(table) for site, table in db.ON_HAND.items()}
    regional = Session("user_regional_atl")
    regional.bulk("uom", [_uom("u_r1"), _uom("u_r2")])
    regional.add("raw_material", {"raw_material_id": "rm_r", "name": "R", "uom": "u_r1"})
    regional.add("on_hand", {"raw_material_id": "rm_r", "qty": 1}, site="site_003")
    regional.add("par_level", {"raw_material_id": "rm_r", "qty": 1})
    db.UOM["stray"] = {"uom_id": "stray"}  # a key with no meta is removed too
    writes.reset_for_tests()
    assert {name: getattr(db, name) for name in seeded} == seeded
    assert on_hand == db.ON_HAND
    assert writes._state["sessions"] == {} and writes._state["quota"] == {}
    assert sum(len(m) for m in writes._state["meta"].values()) == 116


# ================================================================= validator

def test_depth_is_measured_without_recursion():
    nested = {}
    for _ in range(20000):
        nested = {"a": nested}
    assert writes.depth_exceeds(nested)
    assert not writes.depth_exceeds({"a": [{"b": 1}]}, limit=3)
    assert writes.depth_exceeds({"a": [{"b": {}}]}, limit=3)


@pytest.mark.parametrize("body, action, field", [
    ([], "add", "body"),
    ({"request_id": ["x"], "record": {}}, "add", "request_id"),
    ({"session_id": 7, "record": {}}, "add", "session_id"),
    ({"record": "x"}, "add", "record"),
    ({"record": {}, "version": 0}, "update", "version"),
    ({"version": True}, "delete", "version"),
    ({"rows": {}}, "bulk", "rows"),
    ({"rows": [{"row": 1, "record": {}}, {"row": 1, "record": {}}]}, "bulk", "rows[1].row"),
    ({"rows": [{"row": 1}]}, "bulk", "rows[0]"),
    ({"rows": [{"row": 1, "record": {}, "parse_error": "x"}]}, "bulk", "rows[0]"),
])
def test_envelope_problems(body, action, field):
    assert field in [p["field"] for p in writes.envelope_problems(body, action)]


def test_well_formed_envelopes_pass():
    assert writes.envelope_problems({"session_id": "s", "request_id": "r", "record": {}}, "add") == []
    assert writes.envelope_problems({"record": {}, "version": 2}, "update") == []
    assert writes.envelope_problems({"rows": [{"row": 2, "parse_error": "bad"}]}, "bulk") == []


def _job_code_problems(title, cell=False):
    return writes.validate_record(writes.KINDS["job_code"], {"job_code": "jc_v", "title": title},
                                  action="add", cell=cell)[1]


@pytest.mark.parametrize("title", ["Fresh & Co.", "O'Brien's", "a" * 100, "Mon - Fri", "x > y"])
def test_ordinary_text_is_accepted(title):
    assert _job_code_problems(title) == []


@pytest.mark.parametrize("title, reason", [
    ("<script>", "not allowed: markup such as <...>"),
    ("a<b>c", "not allowed: markup such as <...>"),
    ("tab\there", "not allowed: control character"),
    ("bell\x07", "not allowed: control character"),
    ("c1\x85", "not allowed: control character"),
    ("a" * 101, "too long (max 100 characters)"),
    ("   ", "is required"),
    (5, "must be text"),
])
def test_bad_text_is_refused(title, reason):
    assert _job_code_problems(title) == [{"field": "title", "reason": reason}]


@pytest.mark.parametrize("cell", ["=SUM(A1)", "+1", "-x", "@cmd", "  =1"])
def test_formula_shaped_cells_are_refused_only_in_files(cell):
    assert _job_code_problems(cell) == []
    assert _job_code_problems(cell, cell=True) == [
        {"field": "title", "reason": "not allowed: a cell may not start with =, +, - or @"}]


@pytest.mark.parametrize("job_code, reason", [
    ("_x", "must be letters, digits, _ or -, starting with a letter or digit"),
    ("a b", "must be letters, digits, _ or -, starting with a letter or digit"),
    ("a" * 101, "too long (max 100 characters)"),
    ("template", "is reserved"),
    ("bulk", "is reserved"),
])
def test_bad_ids_are_refused(job_code, reason):
    problems = writes.validate_record(writes.KINDS["job_code"], {"job_code": job_code, "title": "T"},
                                      action="add")[1]
    assert problems == [{"field": "job_code", "reason": reason}]


@pytest.mark.parametrize("value, cell, expected", [
    (0, False, (0, None)), (2.5, False, (2.5, None)), ("3", True, (3, None)), (" 1.5 ", True, (1.5, None)),
    (-1, False, (None, "must be zero or more")), (True, False, (None, "must be a number")),
    (float("nan"), False, (None, "must be a finite number")), ("inf", True, (None, "must be a number")),
    ("3", False, (None, "must be a number")), ("abc", True, (None, "must be a number")),
])
def test_numbers(value, cell, expected):
    assert writes._number(value, cell, integer=False) == expected


def test_integer_fields_take_whole_numbers():
    assert writes._number(4.0, False, integer=True) == (4, None)
    assert writes._number(4.5, False, integer=True) == (None, "must be a whole number")
    assert writes._number("7", True, integer=True) == (7, None)


def test_cell_forms_are_read():
    vendor = writes.KINDS["vendor"]
    clean, problems = writes.validate_record(vendor, {
        "vendor_id": "v1", "name": "V", "lead_time_days": "2", "price_list": "rm_a=1.5; rm_b = 2",
        "min_order_value": "10"}, action="add", cell=True)
    assert problems == []
    assert clean["price_list"] == {"rm_a": 1.5, "rm_b": 2} and clean["lead_time_days"] == 2
    employee = writes.KINDS["employee"]
    clean, problems = writes.validate_record(employee, {**_employee(), "available_days": "Mon|Sat",
                                                        "hourly_rate": "12.5", "max_weekly_hours_preference": "20"},
                                             action="add", cell=True)
    assert problems == [] and clean["available_days"] == ["Mon", "Sat"]


@pytest.mark.parametrize("field, value, reason", [
    ("price_list", "rm_a:1", "must have the form rm_id=price;rm_id=price"),
    ("price_list", "rm_a=1;", "must have the form rm_id=price;rm_id=price"),
    ("price_list", "rm_a=x", "entry 1: price must be a number"),
    ("price_list", "rm_a=1;rm_a=2", "entry 2: repeats raw material rm_a"),
    ("available_days", "Mon|Funday", "days must be Mon, Tue, Wed, Thu, Fri, Sat or Sun"),
    ("available_days", "Mon|Mon", "must not repeat a day"),
    ("available_days", ["Mon"], "must be the cell text from the file"),
])
def test_cells_that_do_not_follow_their_form_are_field_problems(field, value, reason):
    kind = writes.KINDS["vendor" if field == "price_list" else "employee"]
    record = ({"vendor_id": "v1", "name": "V", "lead_time_days": 1, "min_order_value": 1} if field == "price_list"
              else _employee())
    problems = writes.validate_record(kind, {**record, field: value}, action="add", cell=True)[1]
    assert problems == [{"field": field, "reason": reason}]


def test_every_problem_is_listed_at_once():
    problems = writes.validate_record(writes.KINDS["labor_rule"], {"jurisdiction": "<x>", "ot_multiplier": -1},
                                      action="add")[1]
    assert len(problems) == 8
    assert {"field": "ot_multiplier", "reason": "must be zero or more"} in problems


def test_menu_items_take_only_the_fixed_gl_codes():
    menu_item = writes.KINDS["menu_item"]
    record = {"menu_item_id": "mi_x", "name": "X", "gl_code": "GL-NEW"}
    assert writes.validate_record(menu_item, record, action="add")[1] == [
        {"field": "gl_code", "reason": "must be one of GL-BEV, GL-FOOD"}]


def test_unit_base_loops_are_detected():
    regional = Session("user_regional_atl")
    regional.add("uom", _uom("u_1"))
    regional.add("uom", _uom("u_2", base="u_1"))
    assert not writes._base_loops("u_1", "u_1")
    assert writes._base_loops("u_1", "u_2")      # u_1 -> u_2 -> u_1
    assert not writes._base_loops("u_3", "u_2")  # u_3 -> u_2 -> u_1 (self-based)
    assert writes._base_loops("u_9", "u_8", pending={"u_8": "u_9"})


# ========================================================= sessions + quota

def test_session_ids_are_long_random_and_never_repeat():
    claims = _claims("user_dev_tester")
    ids = {writes.start_session(claims)[1]["session_id"] for _ in range(1000)}
    assert len(ids) == 1000
    assert all(len(i) >= 43 for i in ids)  # token_urlsafe(32): 256 bits


def test_the_sweep_removes_idle_sessions_and_their_counters(clock):
    idle, fresh = Session("user_regional_atl"), None
    idle.add("uom", _uom("u_idle"))
    assert writes._state["quota"] == {(idle.id, "uom"): 1}
    clock.advance(minutes=15)
    fresh = Session("user_regional_atl")
    assert set(writes._state["sessions"]) == {fresh.id}
    assert writes._state["quota"] == {}
    assert writes.session_status(idle.claims, idle.id) == (200, {"active": False, "ended_reason": "idle"})
    clock.advance(minutes=15)
    writes.sweep_sessions()
    assert idle.id not in writes._state["ended"]


def test_a_session_under_fifteen_idle_minutes_stays():
    clock = FakeClock()
    writes.set_clock(clock)
    session = Session("user_regional_atl")
    clock.advance(minutes=14, seconds=59)
    writes.sweep_sessions()
    assert session.id in writes._state["sessions"]


# =============================================================== request log

def test_request_records_are_forgotten_after_fifteen_minutes(clock):
    writes.remember_request("u", "r1", "fp", (201, {"ok": 1}), clock())
    clock.advance(minutes=14)
    assert writes.lookup_request("u", "r1", clock())["payload"] == {"ok": 1}
    clock.advance(minutes=1)
    assert writes.lookup_request("u", "r1", clock()) is None
    assert writes._state["requests"] == {}


def test_request_log_keeps_1000_per_user_dropping_the_oldest(clock):
    for i in range(1001):
        writes.remember_request("u", f"r{i}", "fp", (200, {}), clock())
    assert writes.lookup_request("u", "r0", clock()) is None
    assert writes.lookup_request("u", "r1", clock()) is not None
    assert len(writes._state["requests"]["u"]) == 1000


def test_a_stored_request_record_is_never_replaced(clock):
    writes.remember_request("u", "r1", "first", (201, {"a": 1}), clock())
    writes.remember_request("u", "r1", "second", (409, {"b": 2}), clock())
    record = writes.lookup_request("u", "r1", clock())
    assert (record["fingerprint"], record["status"]) == ("first", 201)


def test_request_records_are_kept_per_user(clock):
    writes.remember_request("u1", "r", "fp", (200, {}), clock())
    assert writes.lookup_request("u2", "r", clock()) is None


# ============================================================ audit adapter

MARKER = {"truncated": True, "unserializable": True}
CUT = writes.MAX_AUDIT_TEXT


def _cut(text):
    """What clip_text makes of an over-long text: 1,024 characters, marker last."""
    return text[:CUT - len("...(truncated)")] + "...(truncated)"


def test_clip_value_clips_every_text_and_key_in_nested_dicts_and_lists():
    long = "x" * 5_000
    value = {"record": {"name": long, "lines": [{"uom": long}, long, 3, None, True]}, long: "k"}
    clipped = writes.clip_value(value)
    assert clipped["record"]["name"] == _cut(long) and len(clipped["record"]["name"]) == CUT
    assert clipped["record"]["lines"] == [{"uom": _cut(long)}, _cut(long), 3, None, True]
    assert clipped[_cut(long)] == "k"
    assert value["record"]["name"] == long  # the caller's value is never changed


def test_clip_value_keeps_short_values_and_exact_1024_character_text():
    exact = "y" * CUT
    value = {"record": {"name": "Ana", "qty": 2.5, "note": exact}, "version": 3}
    assert writes.clip_value(value) == value
    assert writes.clip_value(None) is None


def test_clip_value_records_non_finite_numbers_as_their_repr():
    value = {"record": {"qty": float("nan"), "hi": float("inf"), "lo": [float("-inf")]}}
    assert writes.clip_value(value) == {"record": {"qty": "nan", "hi": "inf", "lo": ["-inf"]}}


@pytest.mark.parametrize("bad", [{"x": {1, 2}}, {1: "non-text key"}, {"x": object()}])
def test_clip_value_turns_values_json_cannot_store_into_the_marker(bad):
    assert writes.clip_value(bad) == MARKER


def test_clip_value_turns_nesting_past_the_body_cap_into_the_marker():
    def nested(levels):
        value = {}
        for _ in range(levels - 1):
            value = {"a": value}
        return value

    at_cap = nested(writes.MAX_DEPTH + 1)
    assert writes.clip_value(at_cap) == at_cap
    assert writes.clip_value(nested(writes.MAX_DEPTH + 2)) == MARKER
    assert writes.clip_value(nested(5_000)) == MARKER  # never a RecursionError


def test_build_entry_clips_text_fields_but_never_identity_fields():
    session = Session("user_regional_atl")
    long = "z" * 5_000
    entry = writes.build_entry(user_id="user_regional_atl", persona="REGIONAL_MANAGER", session_id=session.id,
                               action="add", outcome="violation", kind="k" * 2_000, record_id=long,
                               site_id="s" * 2_000, changes={"record": {"name": long}}, reason=long,
                               caller="user_regional_atl")
    assert entry["record_id"] == entry["reason"] == _cut(long)
    assert (entry["kind"], entry["site_id"]) == (_cut("k" * 2_000), _cut("s" * 2_000))
    assert entry["changes"] == {"record": {"name": _cut(long)}}
    assert (entry["user_id"], entry["persona"], entry["session_id"]) == (
        "user_regional_atl", "REGIONAL_MANAGER", session.id)
    audit.append(entry)  # the audit module takes it as built
    assert _entries()[-1]["reason"] == _cut(long)


def test_build_entry_records_only_a_session_id_that_names_the_callers_session():
    session = Session("user_regional_atl")

    def recorded(session_id, caller="user_regional_atl", **extra):
        return writes.build_entry(user_id="u", persona=None, session_id=session_id, action="add",
                                  outcome="violation", caller=caller, **extra)["session_id"]

    assert recorded(session.id) == session.id
    assert recorded(session.id, caller="user_dev_tester") is None  # someone else's live session
    assert recorded(session.id, caller=None) is None
    assert recorded("no-such-session") is None
    assert recorded(5) is None and recorded("") is None
    # Login and logout entries carry the id the backend itself issued or ended.
    assert recorded("just-issued", issued_session=True) == "just-issued"


def test_record_audit_does_not_retry_an_invalid_entry(monkeypatch, capsys):
    calls = []

    def refuse(entry):
        calls.append(entry)
        raise audit.InvalidEntry("still too big")

    monkeypatch.setattr(audit, "append", refuse)
    entry = writes.build_entry(user_id="u", persona=None, session_id=None, action="add", outcome="allowed",
                               changes={"record": {"name": "A"}})
    with pytest.raises(writes.AuditFailure) as raised:
        writes.record_audit([entry], "add uom/u1")
    assert raised.value.message == "audit could not record the attempt"
    assert calls == [entry]  # one call, with the entry exactly as built
    assert capsys.readouterr().err.count("[mock-hsm] ERROR writes:") == 1


def test_record_audit_maps_an_unavailable_audit_to_its_own_503(monkeypatch):
    monkeypatch.setattr(audit, "append_batch", lambda entries: (_ for _ in ()).throw(audit.AuditUnavailable("x")))
    with pytest.raises(writes.AuditFailure) as raised:
        writes.record_audit([{}], "bulk_row uom/none", batch=True, log=False)
    assert raised.value.message == "audit unavailable"
