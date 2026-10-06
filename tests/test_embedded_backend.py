"""
Tests for the mock backend that runs inside the dashboard process (unit U2,
``mock_hsm/embedded.py``) and the audit readiness query it relies on.

Every server here binds port 0 on loopback. The ``holder`` fixture resets the
module's process-wide holder before each test and retires whatever the test
started, so tests never share an instance. tests/conftest.py supplies a fresh
signing secret and a per-test ``HSM_AUDIT_PATH``.
"""

import ast
import logging
import os
import socket
import stat
import sys
import tempfile
import threading
import time
from datetime import timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hsm_client import HsmClient
from mock_hsm import audit, embedded
from mock_hsm.auth import mint_token

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RM = "user_rm_midtown"
ALLOWED_IMPORTS = {
    "dataclasses",
    "datetime",
    "http",
    "logging",
    "os",
    "pathlib",
    "socket",
    "stat",
    "tempfile",
    "threading",
    "mock_hsm",
}


@pytest.fixture(autouse=True)
def holder():
    """A clean process-wide holder for each test; whatever the test started is retired after it."""
    embedded.reset_for_tests()
    yield
    embedded.reset_for_tests()


def _get_sites(handle):
    return HsmClient(mint_token(RM), base_url=handle.address, timeout=5).get_sites()


@pytest.fixture
def private_temp(monkeypatch, tmp_path):
    """HSM_AUDIT_PATH unset and the system temp dir redirected, so the default audit directory is exercised."""
    monkeypatch.delenv(audit.ENV_PATH, raising=False)
    temp = tmp_path / "systemp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(temp))
    return temp


@pytest.fixture
def servers(monkeypatch):
    """Every server the module constructs, in order."""
    made = []

    class CountingServer(ThreadingHTTPServer):
        def __init__(self, *args, **kwargs):
            made.append(self)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(embedded, "ThreadingHTTPServer", CountingServer)
    return made


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ------------------------------------------------------- audit readiness (R3)


def test_unavailable_reason_is_none_after_a_good_configure(tmp_path):
    audit.configure(tmp_path / "trail" / "audit.jsonl")
    assert audit.unavailable_reason() is None


def test_unavailable_reason_reports_a_corrupt_trail(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_text("this is not json\n")
    audit.configure(path)
    reason = audit.unavailable_reason()
    assert reason and "line 1" in reason


def test_unavailable_reason_reports_an_unwritable_path(tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    audit.configure(blocker / "audit.jsonl")  # the parent is a file, so nothing can be created under it
    reason = audit.unavailable_reason()
    assert reason and "cannot open" in reason


# ------------------------------------------------- start on loopback (S1, S5)


def test_start_returns_a_running_handle_on_loopback_that_answers():
    handle = embedded.start()
    assert handle.status == "running" and handle.failure_cause is None
    assert handle.host == "127.0.0.1" and handle.port > 0
    assert handle.address == f"http://127.0.0.1:{handle.port}"
    assert handle.started_at.tzinfo is timezone.utc
    assert embedded.current() == handle
    assert [s["site_id"] for s in _get_sites(handle)] == ["site_001"]


def test_an_explicit_port_still_binds_loopback_only():
    port = _free_port()
    handle = embedded.start(port=port)
    assert handle.status == "running" and handle.port == port
    assert embedded.bound_address() == ("127.0.0.1", port)


def test_embedded_imports_only_the_standard_library_and_mock_hsm():
    tree = ast.parse((PROJECT_ROOT / "mock_hsm" / "embedded.py").read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative imports are not used in mock_hsm"
            roots.add(node.module.split(".")[0])
    assert roots <= ALLOWED_IMPORTS, roots - ALLOWED_IMPORTS


# ------------------------------------------------------ secret refusal (S2)


def test_start_without_a_secret_fails_binds_nothing_and_creates_no_audit_dir(monkeypatch, private_temp):
    monkeypatch.setenv("HSM_SIGNING_SECRET", "")
    handle = embedded.start()
    assert handle.status == "failed"
    assert "HSM_SIGNING_SECRET" in handle.failure_cause
    assert embedded.current() is None and embedded.bound_address() is None
    assert list(private_temp.iterdir()) == []


def test_a_short_secret_is_refused_and_its_value_never_appears_in_the_cause(monkeypatch):
    value = "too-short-" + "x" * 8
    monkeypatch.setenv("HSM_SIGNING_SECRET", value)
    handle = embedded.start()
    assert handle.status == "failed" and embedded.bound_address() is None
    assert "HSM_SIGNING_SECRET" in handle.failure_cause and value not in handle.failure_cause


# ------------------------------------------- audit directory and readiness (S3, R3)


def _demo_dir(temp, uid=None):
    return temp / f"hsm-demo-{os.getuid() if uid is None else uid}"


def _configured_path():
    return audit._current.state.path


def test_a_fresh_start_creates_a_private_audit_dir_and_leaves_the_temp_dir_alone(private_temp):
    private_temp.chmod(0o1777)  # a shared temp dir, like /tmp
    handle = embedded.start()
    assert handle.status == "running"
    demo = _demo_dir(private_temp)
    assert stat.S_IMODE(demo.lstat().st_mode) == 0o700
    assert stat.S_IMODE(private_temp.stat().st_mode) == 0o1777
    assert _configured_path() == demo / "audit.jsonl" and (demo / "audit.jsonl").exists()


def test_an_existing_audit_dir_with_group_or_other_access_fails_the_start(private_temp):
    demo = _demo_dir(private_temp)
    demo.mkdir(mode=0o755)
    demo.chmod(0o755)
    handle = embedded.start()
    assert handle.status == "failed" and "audit directory" in handle.failure_cause
    assert embedded.bound_address() is None
    assert stat.S_IMODE(demo.stat().st_mode) == 0o755  # never changes a directory it did not create


def test_a_symlink_in_place_of_the_audit_dir_fails_the_start(private_temp, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o700)
    _demo_dir(private_temp).symlink_to(target)
    handle = embedded.start()
    assert handle.status == "failed" and "symlink" in handle.failure_cause
    assert embedded.bound_address() is None


def test_an_audit_dir_owned_by_another_user_fails_the_start(monkeypatch, private_temp):
    other = os.getuid() + 1
    _demo_dir(private_temp, other).mkdir(mode=0o700)  # owned by us, named for "another" uid
    monkeypatch.setattr(os, "getuid", lambda: other)
    handle = embedded.start()
    assert handle.status == "failed" and "owned by" in handle.failure_cause
    assert embedded.bound_address() is None


def test_an_existing_private_audit_dir_is_reused_unchanged(private_temp):
    demo = _demo_dir(private_temp)
    demo.mkdir(mode=0o700)
    demo.chmod(0o700)
    assert embedded.start().status == "running"
    assert _configured_path() == demo / "audit.jsonl" and stat.S_IMODE(demo.stat().st_mode) == 0o700


@pytest.mark.parametrize("problem", ["not a directory", "cannot be created"])
def test_an_audit_dir_that_is_a_file_or_cannot_be_made_fails_the_start(monkeypatch, private_temp, problem):
    if problem == "not a directory":
        _demo_dir(private_temp).write_text("")
    else:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(private_temp / "missing"))
    handle = embedded.start()
    assert handle.status == "failed" and "audit directory" in handle.failure_cause
    assert problem in handle.failure_cause and embedded.bound_address() is None


def test_without_getuid_the_dir_is_named_for_the_login_and_ownership_is_not_checked(monkeypatch, private_temp):
    monkeypatch.delattr(os, "getuid")
    monkeypatch.setattr(os, "getlogin", lambda: "tester")
    assert embedded.start().status == "running"
    assert _configured_path() == private_temp / "hsm-demo-tester" / "audit.jsonl"


@pytest.mark.parametrize("problem", ["corrupt", "unwritable"])
def test_an_unusable_trail_at_an_explicit_path_fails_the_start_with_the_audit_reason(monkeypatch, tmp_path, problem):
    if problem == "corrupt":
        path = tmp_path / "audit.jsonl"
        path.write_text("not json\n")
    else:
        (tmp_path / "a-file").write_text("")
        path = tmp_path / "a-file" / "audit.jsonl"
    monkeypatch.setenv(audit.ENV_PATH, str(path))
    handle = embedded.start()
    assert handle.status == "failed" and embedded.bound_address() is None
    assert handle.failure_cause == audit.unavailable_reason()


def test_an_explicit_audit_path_is_passed_through_unchanged(monkeypatch, private_temp, tmp_path):
    path = tmp_path / "operator" / "trail.jsonl"
    monkeypatch.setenv(audit.ENV_PATH, str(path))
    assert embedded.start().status == "running"
    assert _configured_path() == path
    assert list(private_temp.iterdir()) == []


# --------------------------------------------------- one backend per process (SC1)


def test_two_start_calls_return_the_same_backend(servers):
    first = embedded.start()
    second = embedded.start()
    assert second == first and len(servers) == 1


def test_a_port_passed_on_reuse_is_ignored(servers):
    first = embedded.start()
    assert embedded.start(port=_free_port()) == first and len(servers) == 1


def test_two_threads_starting_at_once_get_one_backend(servers):
    barrier = threading.Barrier(2)
    results = []

    def call():
        barrier.wait()
        results.append(embedded.start())

    threads = [threading.Thread(target=call) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(results) == 2 and results[0].address == results[1].address
    assert len(servers) == 1


# ------------------------------------------------ liveness and replacement (P2, R1, R2)

REPLACED = "embedded backend replaced on a new port; the demo data is kept"


def _timeout(*args, **kwargs):
    raise TimeoutError("timed out")  # what socket.timeout is an alias of


def test_the_liveness_connect_uses_a_half_second_timeout(monkeypatch):
    assert embedded.LIVENESS_TIMEOUT_S == 0.5
    handle = embedded.start()
    calls = []

    def spy(address, timeout):
        calls.append((address, timeout))
        return socket.create_connection(address, timeout=timeout)

    monkeypatch.setattr(embedded, "_connect", spy)
    assert embedded.current() == handle
    assert calls == [(("127.0.0.1", handle.port), 0.5)]


def test_a_refused_or_timed_out_connect_counts_as_not_live(monkeypatch):
    assert embedded._probe(_free_port()) is False  # refused: nothing listens there
    embedded.start()
    monkeypatch.setattr(embedded, "_connect", _timeout)
    assert embedded.current() is None


def test_the_check_against_a_closed_port_returns_quickly():
    port = _free_port()
    began = time.monotonic()
    assert embedded._probe(port) is False
    assert time.monotonic() - began < 1.5


def test_a_stopped_backend_is_closed_and_replaced_with_a_warning(caplog, servers):
    first = embedded.start()
    old = servers[0]
    old.shutdown()  # the serve loop ends; the socket stays open until retired
    assert embedded.current() is None
    with caplog.at_level(logging.WARNING, logger="mock_hsm.embedded"):
        second = embedded.start()
    assert second.status == "running" and second != first
    assert old.socket.fileno() == -1 and len(servers) == 2
    assert REPLACED in caplog.text
    assert [s["site_id"] for s in _get_sites(second)] == ["site_001"]


def test_a_backend_alive_but_not_answering_is_shut_down_before_replacement(monkeypatch, servers):
    embedded.start()
    old_thread = embedded._holder.thread
    monkeypatch.setattr(embedded, "_connect", _timeout)
    second = embedded.start()
    assert second.status == "running" and len(servers) == 2
    assert not old_thread.is_alive() and servers[0].socket.fileno() == -1


def test_an_audit_trail_failed_at_runtime_makes_the_backend_not_live_and_is_reconfigured(servers):
    embedded.start()
    audit._fail_locked(audit._current.state, "append failed (test)")
    assert embedded.current() is None
    assert embedded.start().status == "running" and len(servers) == 2
    assert audit.unavailable_reason() is None


def test_a_bind_failure_is_reported_once_and_never_retried_in_the_call(servers):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        handle = embedded.start(port=port)
        assert handle.status == "failed" and str(port) in handle.failure_cause
        assert len(servers) == 1 and embedded.current() is None
        assert embedded.start(port=port).status == "failed" and len(servers) == 2  # one new attempt per call


# ------------------------------------------------------------------ logging (O1)


def test_every_failed_start_logs_a_warning_with_the_cause_and_never_the_secret(monkeypatch, caplog):
    original, value = os.environ["HSM_SIGNING_SECRET"], "short-" + "y" * 10
    monkeypatch.setenv("HSM_SIGNING_SECRET", value)
    with caplog.at_level(logging.INFO, logger="mock_hsm.embedded"):
        refused = embedded.start()
    monkeypatch.setenv("HSM_SIGNING_SECRET", original)
    with socket.socket() as taken, caplog.at_level(logging.INFO, logger="mock_hsm.embedded"):
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        unbound = embedded.start(port=taken.getsockname()[1])
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [
        f"embedded backend failed to start: {refused.failure_cause}",
        f"embedded backend failed to start: {unbound.failure_cause}",
    ]
    assert value not in caplog.text and original not in caplog.text


def test_a_successful_start_logs_its_address_at_info_and_never_the_secret(caplog):
    with caplog.at_level(logging.INFO, logger="mock_hsm.embedded"):
        handle = embedded.start()
        embedded.start()  # reuse logs nothing
    infos = [r.getMessage() for r in caplog.records if r.name == "mock_hsm.embedded"]
    assert infos == [f"embedded backend listening on {handle.address}"]
    assert os.environ["HSM_SIGNING_SECRET"] not in caplog.text


# --------------------------------------------- concurrency and start time (P1, SC2)


def test_a_fresh_start_takes_under_two_seconds():
    # An ordinary test, not perf-marked: a loopback start takes milliseconds,
    # so the bound has a wide margin and CI's single retry covers a hiccup.
    began = time.monotonic()
    handle = embedded.start()
    assert handle.status == "running" and time.monotonic() - began < 2.0


def test_ten_concurrent_authenticated_requests_all_succeed():
    handle = embedded.start()
    barrier = threading.Barrier(10)
    results, errors = [], []

    def call():
        barrier.wait()
        try:
            results.append(_get_sites(handle))
        except Exception as e:  # noqa: BLE001 -- collected and asserted below
            errors.append(e)

    threads = [threading.Thread(target=call) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    assert errors == [] and len(results) == 10
    assert all([s["site_id"] for s in r] == ["site_001"] for r in results)
