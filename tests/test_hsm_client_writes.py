"""
Tests for the shared client's data-write additions (unit U3,
``agents/hsm_client.py``): the error types, the kind table, the sender and
reshaper, the write retry and ``retry_write``, and every new public method.

- Integration tests run the real backend in process
  (``ThreadingHTTPServer(("127.0.0.1", 0), mock_hsm.server.Handler)``).
- Failure cases use ``FakeServer``, a small HTTP server on an ephemeral port
  that drops, hangs, garbles or forwards each request as told, so urllib
  raises its real exception types (no patching of urllib).
- The clock is changed only through ``agents.hsm_client._now``.

tests/conftest.py gives every test its own audit file and resets the
backend's write state afterwards.
"""

import copy
import http.client
import json
import socket
import struct
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import hsm_client
from agents.hsm_client import (
    KIND_TABLE,
    RETRY_WINDOW,
    HsmApiError,
    HsmClient,
    HsmUnavailable,
    SessionExpired,
)
from mock_hsm import audit, auth, db, writes
from mock_hsm.auth import mint_token
from mock_hsm.server import Handler

RM, REGIONAL = "user_rm_midtown", "user_regional_atl"
ALL_SEEING = {"user_id": "test-auditor", "persona": "SYSTEM_ADMIN", "site_ids": [], "region_id": None}
SITE = "site_001"
FIXED_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

# NFR4.3 target. Never relax it to make a test pass.
RESHAPE_1000_SECONDS = 0.050


# ------------------------------------------------------------------ servers


@pytest.fixture(scope="module")
def backend_url():
    """The real backend, in process, on an ephemeral port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


class FakeServer:
    """An HTTP server that handles each request by the next queued action,
    falling back to ``default``. Every request it reads is recorded as
    ``(method, path, body bytes)``.

    Actions: ``"drop"`` (close without answering), ``"hang"`` (never answer),
    ``"reset"`` (close with a TCP reset), ``"bad_status"`` (a garbage status
    line), ``"forward"`` (proxy to the real backend and relay its answer),
    ``"forward_drop"`` (proxy, then close without relaying), or a tuple
    ``("raw", status, body bytes)`` / ``("cut", status, body bytes, length)``
    for a reply whose Content-Length is ``length`` but whose body stops early.
    """

    def __init__(self, upstream=None, default="forward"):
        self.upstream, self.default = upstream, default
        self.actions, self.requests = [], []
        self.release = threading.Event()
        fake = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                fake.requests.append((self.command, self.path, body))
                action = fake.actions.pop(0) if fake.actions else fake.default
                fake.act(self, action, body)

            do_GET = do_POST = do_PUT = do_DELETE = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _forward(self, handler, body):
        host, port = self.upstream.removeprefix("http://").split(":")
        conn = http.client.HTTPConnection(host, int(port), timeout=10)
        headers = {k: v for k, v in handler.headers.items() if k.lower() in ("authorization", "content-type")}
        conn.request(handler.command, handler.path, body=body or None, headers=headers)
        response = conn.getresponse()
        status, payload = response.status, response.read()
        conn.close()
        return status, payload

    @staticmethod
    def _reply(handler, status, payload, length=None):
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(payload) if length is None else length))
        handler.end_headers()
        handler.wfile.write(payload)
        handler.wfile.flush()

    def act(self, handler, action, body):
        handler.close_connection = True
        if action == "drop":
            return
        if action == "hang":
            self.release.wait(10)
            return
        if action == "reset":
            handler.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            return
        if action == "bad_status":
            handler.wfile.write(b"garbage\r\n\r\n")
            return
        if action in ("forward", "forward_drop"):
            status, payload = self._forward(handler, body)
            if action == "forward":
                self._reply(handler, status, payload)
            return
        if action[0] == "raw":
            self._reply(handler, action[1], action[2])
            return
        if action[0] == "cut":
            self._reply(handler, action[1], action[2], length=action[3])
            return
        raise AssertionError(f"unknown action {action!r}")

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake(backend_url):
    server = FakeServer(upstream=backend_url)
    yield server
    server.close()


@pytest.fixture
def refused_url():
    """A local port with nothing listening."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def fixed_clock(monkeypatch):
    """Pin hsm_client._now; returns a setter to move it."""
    state = {"now": FIXED_NOW}
    monkeypatch.setattr(hsm_client, "_now", lambda: state["now"])

    def move_to(when):
        state["now"] = when

    return move_to


# ------------------------------------------------------------------ helpers


def client_for(url, user=REGIONAL, timeout=10):
    return HsmClient(mint_token(user), base_url=url, timeout=timeout)


def audit_entries(action=None):
    entries, before = [], None
    while True:
        page = audit.page(ALL_SEEING, before)
        entries += page["entries"]
        before = page["next_before"]
        if before is None:
            break
    return [e for e in entries if action is None or e["action"] == action]


def job_code(tag):
    return {"job_code": f"jc_{tag}", "title": f"Title {tag}"}


def last_body(fake_server, index=-1):
    return json.loads(fake_server.requests[index][2])


# ======================================================= Errors and KindTable


def test_api_error_two_argument_form_still_works():
    error = HsmApiError(404, "no such thing")
    assert (error.status, error.message, error.problems) == (404, "no such thing", [])
    assert str(error) == "HSM API error 404: no such thing"
    assert isinstance(error, RuntimeError)


def test_api_error_carries_problems():
    problems = [{"field": "name", "reason": "is required"}]
    error = HsmApiError(400, "invalid record", problems)
    assert error.problems == problems
    assert error.problems is not problems  # a copy, so the caller's list can't change it


def test_session_expired_fields():
    error = SessionExpired()
    assert isinstance(error, HsmApiError)
    assert (error.status, error.message, error.problems) == (401, "no active session", [])


def test_unavailable_fields_for_a_read():
    error = HsmUnavailable("no answer from HSM: TimeoutError")
    assert isinstance(error, HsmApiError)
    assert (error.status, error.problems) == (0, [])
    assert (error.outcome_unknown, error.request_id, error.retry_deadline) == (False, None, None)


def test_unavailable_never_shows_the_session_id_or_body(fake, fixed_clock):
    fake.actions = ["drop", "drop"]
    client = client_for(fake.url)
    with pytest.raises(HsmUnavailable) as caught:
        client.add_record("job_code", job_code("secret_rec"), "sess-SECRET-123")
    error = caught.value
    assert error.outcome_unknown is True
    shown = [str(error), repr(error), repr(vars(error)), repr(error.__dict__), repr(error.args)]
    for text in shown:
        assert "sess-SECRET-123" not in text
        assert "secret_rec" not in text
    assert error.__cause__ is None and error.__suppress_context__ is True


def test_kind_table_matches_backend_paths_and_site_flags():
    assert set(KIND_TABLE) == set(writes.KINDS)
    for name, route in KIND_TABLE.items():
        kind = writes.KINDS[name]
        assert route.collection == kind.collection_path, name
        assert route.item_path == kind.item_path, name
        assert route.site_scoped == (kind.scope == "site"), name
        assert route.id_field == kind.key, name


def test_kind_table_payload_keys_match_backend(backend_url):
    """Every kind's payload key really is in its collection's ?with=meta read:
    list_records would fail on a missing key (review R-09)."""
    client = client_for(backend_url)
    for name, route in KIND_TABLE.items():
        result = client.list_records(name, site_id=SITE if route.site_scoped else None)
        assert result["records"], name
        assert all(route.id_field in record for record in result["records"]), name
        assert set(result["meta"]) == {record[route.id_field] for record in result["records"]}, name


# ===================================================== Sender and Reshaper


def test_ids_are_quoted_into_paths():
    assert hsm_client._quoted("a/b?x#y") == "a%2Fb%3Fx%23y"
    _, path = hsm_client._kind_route("employee", "s/1?#")
    assert path == "/labor/sites/s%2F1%3F%23/employees"
    assert hsm_client._kind_route("job_code", "ignored")[1] == "/sales/job-codes"


def test_unknown_kind_and_missing_site_raise_value_error():
    with pytest.raises(ValueError, match="unknown kind"):
        hsm_client._kind_route("menu", None)
    for kind in ("employee", "on_hand"):
        with pytest.raises(ValueError, match="needs a site_id"):
            hsm_client._kind_route(kind, None)


@pytest.mark.parametrize(
    "action, cause",
    [
        ("drop", "RemoteDisconnected"),
        ("hang", "TimeoutError"),
        ("bad_status", "BadStatusLine"),
        ("reset", None),  # ConnectionResetError, or RemoteDisconnected if the reset lands later
        (("cut", 200, b'{"active": tr', 200), "invalid response body"),
        (("raw", 200, b"<html>not json</html>"), "invalid response body"),
        (("raw", 200, b"\xff\xfe\xfa"), "invalid response body"),
    ],
)
def test_each_transport_trigger_is_a_no_answer(fake, action, cause):
    fake.actions = [action]
    client = client_for(fake.url, timeout=0.5)
    with pytest.raises(hsm_client._NoAnswer) as caught:
        client._send("GET", "/sessions/abc")
    if cause is not None:
        assert caught.value.reason == cause
    else:
        assert caught.value.reason in ("ConnectionResetError", "RemoteDisconnected")
    assert len(fake.requests) == 1


def test_refused_connection_is_a_no_answer(refused_url):
    with pytest.raises(hsm_client._NoAnswer) as caught:
        client_for(refused_url)._send("GET", "/sessions/abc")
    assert caught.value.reason == "URLError"


def test_read_without_answer_raises_unavailable_not_unknown(fake):
    fake.actions = ["drop"]
    with pytest.raises(HsmUnavailable) as caught:
        client_for(fake.url)._call("GET", "/sessions/abc")
    error = caught.value
    assert (error.status, error.outcome_unknown, error.request_id, error.retry_deadline) == (0, False, None, None)
    assert error.message == "no answer from HSM: RemoteDisconnected"
    assert len(fake.requests) == 1  # never retried


def test_invalid_url_propagates_unchanged():
    client = HsmClient(mint_token(REGIONAL), base_url="http://127.0.0.1:notaport")
    with pytest.raises(http.client.InvalidURL):
        client._send("GET", "/sessions/abc")
    with pytest.raises(http.client.InvalidURL):
        client._call("GET", "/sessions/abc")


@pytest.mark.parametrize(
    "status, payload, message, problems",
    [
        (
            400,
            b'{"error": "invalid record", "problems": [{"field": "name", "reason": "is required"}]}',
            "invalid record",
            [{"field": "name", "reason": "is required"}],
        ),
        (409, b'{"error": "request id reused", "problems": "not a list"}', "request id reused", []),
        (400, b'{"detail": "no error key"}', '{"detail": "no error key"}', []),
        (400, b'{"error": 7}', '{"error": 7}', []),
        (502, b'["not", "an", "object"]', '["not", "an", "object"]', []),
        (503, b"Service Unavailable \xff", "Service Unavailable �", []),
    ],
)
def test_error_bodies_map_to_api_error(fake, status, payload, message, problems):
    fake.actions = [("raw", status, payload)]
    with pytest.raises(HsmApiError) as caught:
        client_for(fake.url)._call("GET", "/sessions/abc")
    error = caught.value
    assert type(error) is HsmApiError
    assert (error.status, error.message, error.problems) == (status, message, problems)


def test_unreadable_error_body(fake):
    fake.actions = [("cut", 500, b'{"error": "boo', 400)]
    with pytest.raises(HsmApiError) as caught:
        client_for(fake.url)._call("GET", "/sessions/abc")
    assert type(caught.value) is HsmApiError
    assert (caught.value.status, caught.value.message, caught.value.problems) == (500, "unreadable error body", [])


def test_no_active_session_on_a_read_is_plain_api_error(fake):
    fake.actions = [("raw", 401, b'{"error": "no active session"}')]
    with pytest.raises(HsmApiError) as caught:
        client_for(fake.url)._call("GET", "/sessions/abc")
    assert type(caught.value) is HsmApiError and caught.value.status == 401


def _meta(*keys):
    return {key: {"origin": "seeded", "version": 1} for key in keys}


def test_reshape_list_kind_uses_records_as_is():
    payload = {"job_codes": [{"job_code": "jc_a", "title": "A"}], "meta": {"job_code": _meta("jc_a")}}
    result = hsm_client._reshape("job_code", payload)
    assert result == {"records": [{"job_code": "jc_a", "title": "A"}], "meta": _meta("jc_a")}


def test_reshape_recipe_map():
    lines = [{"raw_material_id": "rm_a", "qty": 1, "uom": "ea"}]
    payload = {"recipes": {"mi_a": lines}, "meta": {"recipe": _meta("mi_a")}}
    assert hsm_client._reshape("recipe", payload) == {
        "records": [{"menu_item_id": "mi_a", "lines": lines}],
        "meta": _meta("mi_a"),
    }


@pytest.mark.parametrize("kind, key", [("par_level", "par_levels"), ("reorder_point", "reorder_points")])
def test_reshape_shared_stock_maps(kind, key):
    payload = {key: {"rm_a": 4, "rm_b": 2.5}, "meta": {kind: _meta("rm_a", "rm_b")}}
    assert hsm_client._reshape(kind, payload) == {
        "records": [{"raw_material_id": "rm_a", "qty": 4}, {"raw_material_id": "rm_b", "qty": 2.5}],
        "meta": _meta("rm_a", "rm_b"),
    }


def test_reshape_labor_rules_map():
    rule = {"jurisdiction": "GA", "weekly_ot_threshold_hours": 40}
    payload = {"rules": {"GA": rule}, "meta": {"labor_rule": _meta("GA")}}
    assert hsm_client._reshape("labor_rule", payload) == {"records": [rule], "meta": _meta("GA")}


def test_reshape_on_hand_keeps_only_on_hand():
    payload = {
        "site_id": SITE,
        "on_hand": {"rm_a": 3},
        "par_levels": {"rm_a": 9},
        "reorder_points": {"rm_a": 5},
        "meta": {"on_hand": _meta("rm_a"), "par_level": _meta("rm_a", "x"), "reorder_point": _meta("y")},
    }
    assert hsm_client._reshape("on_hand", payload, SITE) == {
        "records": [{"site_id": SITE, "raw_material_id": "rm_a", "qty": 3}],
        "meta": _meta("rm_a"),
    }


def test_reshape_missing_payload_key_fails_loudly():
    with pytest.raises(KeyError):
        hsm_client._reshape("vendor", {"vendor": []})


@pytest.mark.perf
def test_reshape_1000_entries_within_target():
    payload = {
        "par_levels": {f"rm_{i:04d}": i for i in range(1000)},
        "meta": {"par_level": _meta(*(f"rm_{i:04d}" for i in range(1000)))},
    }
    start = time.perf_counter()
    result = hsm_client._reshape("par_level", payload)
    elapsed = time.perf_counter() - start
    assert len(result["records"]) == 1000
    assert elapsed <= RESHAPE_1000_SECONDS, f"reshape took {elapsed * 1000:.1f} ms (target 50 ms)"


# ================================================= Writer and retry_write

JOB_CODES = "/sales/job-codes"


def start(url, user=REGIONAL):
    """A login session on the real backend (through ``url``)."""
    return client_for(url, user)._call("POST", "/sessions")["session_id"]


def logout(url, session_id, user=REGIONAL):
    return client_for(url, user)._call("POST", f"/sessions/{session_id}/logout")


def add_entries(record_id):
    return [e for e in audit_entries("add") if e["record_id"] == record_id]


def test_first_attempt_dropped_is_retried_identically_once(fake, backend_url):
    session = start(backend_url)
    fake.actions = ["drop", "forward"]
    result = client_for(fake.url)._write("POST", JOB_CODES, {"record": job_code("r1")}, session)
    assert result["record"] == job_code("r1")
    assert len(fake.requests) == 2
    assert fake.requests[0] == fake.requests[1]
    body = last_body(fake)
    assert body["session_id"] == session and len(body["request_id"]) == 32
    assert "jc_r1" in db.JOB_CODES
    assert [e["outcome"] for e in add_entries("jc_r1")] == ["allowed"]


def test_double_drop_is_outcome_unknown(fake, fixed_clock):
    fake.actions = ["drop", "drop"]
    with pytest.raises(HsmUnavailable) as caught:
        client_for(fake.url)._write("POST", JOB_CODES, {"record": job_code("r2")}, "s1")
    error = caught.value
    assert (error.status, error.outcome_unknown) == (0, True)
    assert error.request_id == last_body(fake)["request_id"]
    assert error.retry_deadline == FIXED_NOW + timedelta(minutes=14) == FIXED_NOW + RETRY_WINDOW
    assert error.retry_deadline.tzinfo is not None
    assert error.message == "no answer from HSM: RemoteDisconnected"
    assert len(fake.requests) == 2 and fake.requests[0] == fake.requests[1]
    assert hsm_client._RETRY_STORE[error].data == fake.requests[0][2]


def test_caller_request_id_is_used(fake, backend_url):
    session = start(backend_url)
    client_for(fake.url)._write("POST", JOB_CODES, {"record": job_code("r3")}, session, request_id="my-id-1")
    assert last_body(fake)["request_id"] == "my-id-1"


def test_retry_write_after_stored_attempt_returns_the_stored_201(fake, backend_url, fixed_clock):
    session = start(backend_url)
    stored_before = len(db.JOB_CODES)
    fake.actions = ["forward_drop", "forward_drop"]
    client = client_for(fake.url)
    with pytest.raises(HsmUnavailable) as caught:
        client._write("POST", JOB_CODES, {"record": job_code("r4")}, session)
    logout(backend_url, session)  # the session ends before "Try again"
    fixed_clock(FIXED_NOW + timedelta(minutes=13))
    result = client.retry_write(caught.value)
    assert result["record"] == job_code("r4") and result["meta"]["version"] == 1
    assert fake.requests[0] == fake.requests[1] == fake.requests[2]
    assert "jc_r4" in db.JOB_CODES and len(db.JOB_CODES) == stored_before + 1  # no second record
    assert [e["outcome"] for e in add_entries("jc_r4")] == ["allowed"]  # no second audit entry


def test_retry_write_when_first_attempt_never_arrived_after_logout_is_session_expired(fake, backend_url, fixed_clock):
    session = start(backend_url)
    fake.actions = ["drop", "drop"]
    client = client_for(fake.url)
    with pytest.raises(HsmUnavailable) as caught:
        client._write("POST", JOB_CODES, {"record": job_code("r5")}, session)
    logout(backend_url, session)
    with pytest.raises(SessionExpired) as expired:
        client.retry_write(caught.value)
    assert (expired.value.status, expired.value.message) == (401, "no active session")
    assert "jc_r5" not in db.JOB_CODES


def test_retry_write_after_deadline_sends_nothing(fake, fixed_clock):
    fake.actions = ["drop", "drop"]
    client = client_for(fake.url)
    with pytest.raises(HsmUnavailable) as caught:
        client._write("POST", JOB_CODES, {"record": job_code("r6")}, "sess-SECRET-6")
    fixed_clock(caught.value.retry_deadline + timedelta(microseconds=1))
    with pytest.raises(ValueError, match="retry not allowed for request") as refused:
        client.retry_write(caught.value)
    assert caught.value.request_id in str(refused.value)
    assert "sess-SECRET-6" not in str(refused.value) and "jc_r6" not in str(refused.value)
    assert len(fake.requests) == 2  # nothing more was sent


def test_retry_write_at_the_deadline_is_still_allowed(fake, backend_url, fixed_clock):
    session = start(backend_url)
    fake.actions = ["drop", "drop"]
    client = client_for(fake.url)
    with pytest.raises(HsmUnavailable) as caught:
        client._write("POST", JOB_CODES, {"record": job_code("r7")}, session)
    fixed_clock(caught.value.retry_deadline)
    assert client.retry_write(caught.value)["record"] == job_code("r7")


def test_failed_retry_stays_outcome_unknown_and_can_be_retried(fake, backend_url, fixed_clock):
    session = start(backend_url)
    fake.actions = ["drop", "drop", "hang"]
    client = client_for(fake.url, timeout=0.3)
    with pytest.raises(HsmUnavailable) as first:
        client._write("POST", JOB_CODES, {"record": job_code("r8")}, session)
    fixed_clock(FIXED_NOW + timedelta(minutes=5))
    with pytest.raises(HsmUnavailable) as second:
        client.retry_write(first.value)
    again = second.value
    assert again is not first.value
    assert (again.outcome_unknown, again.request_id, again.retry_deadline) == (
        True,
        first.value.request_id,
        first.value.retry_deadline,
    )
    assert again.message == "no answer from HSM: TimeoutError"
    assert client.retry_write(again)["record"] == job_code("r8")
    assert len({request for request in fake.requests}) == 1 and len(fake.requests) == 4


@pytest.mark.parametrize(
    "error",
    [
        HsmApiError(400, "invalid record"),
        HsmUnavailable("no answer from HSM: TimeoutError"),  # a read: outcome known
        HsmUnavailable("forged", outcome_unknown=True, request_id="x", retry_deadline=FIXED_NOW),  # not in the store
        "not an error",
    ],
)
def test_retry_write_refuses_anything_else(refused_url, error):
    with pytest.raises(ValueError, match="retry not allowed"):
        client_for(refused_url).retry_write(error)


def test_non_json_2xx_on_a_write_is_outcome_unknown(fake):
    fake.actions = [("raw", 201, b"created!"), ("raw", 201, b"created!")]
    with pytest.raises(HsmUnavailable) as caught:
        client_for(fake.url)._write("POST", JOB_CODES, {"record": job_code("r9")}, "s1")
    assert caught.value.outcome_unknown is True
    assert caught.value.message == "no answer from HSM: invalid response body"
    assert len(fake.requests) == 2


def test_non_json_2xx_on_a_read_is_unavailable_not_unknown(fake):
    fake.actions = [("raw", 200, b"ok")]
    with pytest.raises(HsmUnavailable) as caught:
        client_for(fake.url)._call("GET", JOB_CODES)
    assert (caught.value.outcome_unknown, caught.value.request_id) == (False, None)
    assert len(fake.requests) == 1


def test_any_http_answer_on_a_write_is_final(fake):
    fake.actions = [("raw", 500, b'{"error": "internal error"}')]
    with pytest.raises(HsmApiError) as caught:
        client_for(fake.url)._write("POST", JOB_CODES, {"record": job_code("r10")}, "s1")
    assert type(caught.value) is HsmApiError and caught.value.status == 500
    assert len(fake.requests) == 1


def test_write_with_ended_session_is_session_expired(backend_url):
    session = start(backend_url)
    logout(backend_url, session)
    with pytest.raises(SessionExpired) as caught:
        client_for(backend_url)._write("POST", JOB_CODES, {"record": job_code("r11")}, session)
    assert caught.value.status == 401


def test_write_with_expired_token_is_plain_api_error(backend_url, monkeypatch):
    session = start(backend_url)
    real_time = time.time
    monkeypatch.setattr(auth.time, "time", lambda: real_time() - 2 * 3600)
    stale = HsmClient(mint_token(REGIONAL), base_url=backend_url)
    monkeypatch.undo()
    with pytest.raises(HsmApiError) as caught:
        stale._write("POST", JOB_CODES, {"record": job_code("r12")}, session)
    assert type(caught.value) is HsmApiError
    assert (caught.value.status, caught.value.message) == (401, "invalid token: expired")


def test_second_logout_is_plain_api_error(backend_url):
    session = start(backend_url)
    logout(backend_url, session)
    with pytest.raises(HsmApiError) as caught:
        logout(backend_url, session)
    assert type(caught.value) is HsmApiError and caught.value.status == 401


def test_publish_and_submit_are_never_retried(fake):
    fake.default = "drop"
    client = client_for(fake.url)
    with pytest.raises(http.client.RemoteDisconnected):
        client.publish_schedule(SITE, [])
    assert len(fake.requests) == 1
    with pytest.raises(http.client.RemoteDisconnected):
        client.submit_purchase_order("v_x", [], site_id=SITE)
    assert len(fake.requests) == 2


# ========================================================= Public methods


def _record(kind, tag):
    """A valid record per kind; references name the prerequisites below."""
    return {
        "menu_item": {"menu_item_id": f"mi_{tag}", "name": f"Item {tag}", "gl_code": "GL-BEV"},
        "recipe": {"menu_item_id": f"mi_{tag}", "lines": [{"raw_material_id": "rm_w", "qty": 1, "uom": "u_w"}]},
        "raw_material": {"raw_material_id": f"rm_{tag}", "name": f"RM {tag}", "uom": "u_w"},
        "uom": {"uom_id": f"u_{tag}", "name": f"unit {tag}", "base": f"u_{tag}", "factor_to_base": 1},
        "vendor": {
            "vendor_id": f"v_{tag}",
            "name": "Vendor",
            "lead_time_days": 2,
            "price_list": {"rm_w": 1.25},
            "min_order_value": 10,
        },
        "employee": {
            "name": f"Emp {tag}",
            "job_code": "jc_w",
            "hourly_rate": 14.5,
            "max_weekly_hours_preference": 30,
            "available_days": ["Mon", "Wed"],
        },
        "job_code": job_code(tag),
        "on_hand": {"raw_material_id": f"rm_{tag}", "qty": 5},
        "par_level": {"raw_material_id": f"rm_{tag}", "qty": 5},
        "reorder_point": {"raw_material_id": f"rm_{tag}", "qty": 5},
        "labor_rule": {
            "jurisdiction": f"J_{tag}",
            "weekly_ot_threshold_hours": 40,
            "daily_ot_threshold_hours": 8,
            "ot_multiplier": 1.5,
            "max_consecutive_days": 6,
            "min_rest_hours_between_shifts": 10,
            "max_shift_length_hours": 10,
            "note": "Test rule",
        },
    }[kind]


def _changed(kind, record):
    if kind == "recipe":
        return {**record, "lines": [{**record["lines"][0], "qty": 2}]}
    for name, value in (("qty", 7), ("name", "Renamed"), ("title", "Retitled"), ("note", "Changed")):
        if name in record:
            return {**record, name: value}
    raise AssertionError(kind)


@pytest.fixture
def regional(backend_url):
    """A Regional Manager client and session, with the records other kinds refer to."""
    client = client_for(backend_url)
    session = client.start_session()["session_id"]
    for kind, record in (
        ("uom", _record("uom", "w")),
        ("raw_material", _record("raw_material", "w")),
        ("job_code", job_code("w")),
    ):
        client.add_record(kind, record, session)
    return client, session


def test_session_start_status_end(backend_url):
    client = client_for(backend_url, RM)
    started = client.start_session()
    assert set(started) == {"session_id", "user_id", "persona", "idle_timeout_seconds"}
    assert (started["user_id"], started["persona"]) == (RM, "RESTAURANT_MANAGER")
    session = started["session_id"]
    assert client.session_status(session) == {"active": True, "ended_reason": None}
    assert client.end_session(session) == {"active": False, "ended_reason": "logout"}
    assert client.session_status(session) == {"active": False, "ended_reason": "logout"}
    with pytest.raises(HsmApiError) as again:
        client.end_session(session)
    assert type(again.value) is HsmApiError and again.value.status == 401


@pytest.mark.parametrize("kind", sorted(KIND_TABLE))
def test_add_update_delete_every_kind(regional, kind):
    client, session = regional
    route = KIND_TABLE[kind]
    site = SITE if route.site_scoped else None
    if kind == "recipe":
        client.add_record("menu_item", _record("menu_item", "k"), session)
    if kind in ("on_hand", "par_level", "reorder_point"):
        client.add_record("raw_material", _record("raw_material", "k"), session)
    record = _record(kind, "k")

    added = client.add_record(kind, record, session, site_id=site)
    record_id = added["record"][route.id_field]
    assert added["meta"]["origin"] == "dashboard" and added["meta"]["version"] == 1
    listed = client.list_records(kind, site_id=site)
    assert record_id in listed["meta"]
    assert any(r[route.id_field] == record_id for r in listed["records"])

    updated = client.update_record(kind, record_id, _changed(kind, record), 1, session, site_id=site)
    assert updated["meta"]["version"] == 2
    assert updated["record"][route.id_field] == record_id

    deleted = client.delete_record(kind, record_id, 2, session, site_id=site)
    assert deleted == {"deleted": True, "kind": kind, "record_id": record_id}
    assert record_id not in client.list_records(kind, site_id=site)["meta"]


def test_list_records_on_hand_keeps_only_on_hand(regional):
    client, _ = regional
    result = client.list_records("on_hand", site_id=SITE)
    assert {r["raw_material_id"] for r in result["records"]} == set(db.ON_HAND[SITE]) == set(result["meta"])
    assert all(r["site_id"] == SITE for r in result["records"])


def test_list_records_labor_rules(regional):
    client, _ = regional
    result = client.list_records("labor_rule")
    assert result["records"] == [db.LABOR_RULES_BY_JURISDICTION["GA"]]
    assert set(result["meta"]) == {"GA"}


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.list_records("employee"),
        lambda c: c.add_record("on_hand", {"raw_material_id": "rm_x", "qty": 1}, "s"),
        lambda c: c.update_record("employee", "emp_1", {}, 1, "s"),
        lambda c: c.delete_record("on_hand", "rm_x", 1, "s"),
        lambda c: c.bulk_add("employee", [], "f.csv", "s"),
        lambda c: c.csv_template("on_hand"),
        lambda c: c.add_record("menu", {}, "s"),
    ],
)
def test_site_kind_without_site_or_unknown_kind_raises_before_any_request(refused_url, call):
    with pytest.raises(ValueError):
        call(client_for(refused_url))  # a request would have raised HsmUnavailable instead


def test_update_quotes_the_record_id(regional, fake):
    _, session = regional
    with pytest.raises(HsmApiError) as caught:
        client_for(fake.url).update_record("job_code", "a/b?x#y", job_code("q"), 1, session)
    assert fake.requests[-1][1] == "/sales/job-codes/a%2Fb%3Fx%23y"
    assert caught.value.status == 404  # the backend's refusal reaches the caller unchanged


def test_refused_write_status_reaches_caller(backend_url):
    client = client_for(backend_url, RM)
    session = client.start_session()["session_id"]
    with pytest.raises(HsmApiError) as caught:
        client.add_record("job_code", job_code("rm"), session)
    assert type(caught.value) is HsmApiError and caught.value.status == 403


def test_add_with_ended_session_is_session_expired(backend_url):
    client = client_for(backend_url)
    session = client.start_session()["session_id"]
    client.end_session(session)
    with pytest.raises(SessionExpired):
        client.add_record("job_code", job_code("x"), session)


def test_bulk_add_sends_rows_as_given(regional, fake):
    _, session = regional
    rows = [{"row": 1, "record": job_code("b1")}, {"row": 2, "record": job_code("b2")}]
    result = client_for(fake.url).bulk_add("job_code", rows, "codes.csv", session)
    assert result["added"] == 2
    assert [r["record"]["job_code"] for r in result["records"]] == ["jc_b1", "jc_b2"]
    body = last_body(fake)
    assert fake.requests[-1][:2] == ("POST", "/sales/job-codes/bulk")
    assert (body["source"], body["file_name"], body["rows"]) == ("csv", "codes.csv", rows)


def test_bulk_add_with_parse_error_returns_problems(regional):
    client, session = regional
    rows = [{"row": 1, "record": job_code("p1")}, {"row": 2, "parse_error": "unterminated quote"}]
    with pytest.raises(HsmApiError) as caught:
        client.bulk_add("job_code", rows, "bad.csv", session)
    error = caught.value
    assert (type(error), error.status, error.message) == (HsmApiError, 400, "invalid rows")
    assert [p["row"] for p in error.problems] == [2]
    assert "jc_p1" not in db.JOB_CODES


def test_csv_template_shared_and_site_kinds(backend_url):
    client = client_for(backend_url)
    assert client.csv_template("job_code") == {"columns": ["job_code", "title"], "csv": "job_code,title\n"}
    employee = client.csv_template("employee", site_id=SITE)
    assert employee["columns"] == list(writes.KINDS["employee"].csv_columns)
    with pytest.raises(HsmApiError) as caught:
        client_for(backend_url, RM).csv_template("employee", site_id="site_002")
    assert caught.value.status == 403


def test_audit_page_pages_with_before(regional):
    client, session = regional
    rows = [{"row": n, "record": job_code(f"a{n}")} for n in range(1, 56)]
    client.bulk_add("job_code", rows, "many.csv", session)
    first = client.audit_page()
    assert set(first) == {"entries", "next_before", "limit", "total"}
    assert len(first["entries"]) == first["limit"] == 50 and first["next_before"] is not None
    second = client.audit_page(before=first["next_before"])
    ids = [e["entry_id"] for e in first["entries"] + second["entries"]]
    assert len(ids) == len(set(ids)) == first["total"] == 1 + 3 + 55  # login, 3 prerequisites, 55 rows
    assert second["next_before"] is None


def test_existing_methods_unchanged(backend_url):
    client = client_for(backend_url)
    assert client.get_menu_items() == list(db.MENU_ITEMS.values())
    assert client.get_employees(SITE) == [e for e in db.EMPLOYEES.values() if e["site_id"] == SITE]
    assert client.get_labor_rules("GA") == db.LABOR_RULES_BY_JURISDICTION["GA"]
    on_hand = client.get_on_hand(SITE)
    assert "meta" not in on_hand and on_hand["on_hand"] == db.ON_HAND[SITE]
    with pytest.raises(HsmApiError) as caught:
        client.get_site("site_999")
    assert (type(caught.value), caught.value.status, caught.value.problems) == (HsmApiError, 404, [])


def test_existing_method_raises_the_same_type_on_a_dropped_connection(fake):
    fake.default = "drop"
    with pytest.raises(http.client.RemoteDisconnected) as caught:
        client_for(fake.url).get_menu_items()
    assert not isinstance(caught.value, HsmApiError)
    assert len(fake.requests) == 1


def test_ten_threads_share_one_client(backend_url):
    client = client_for(backend_url)
    session = client.start_session()["session_id"]
    stored_before = len(db.JOB_CODES)
    results, errors = [], []

    def worker(n):
        try:
            for i in range(9):
                results.append(client.add_record("job_code", job_code(f"t{n}_{i}"), session))
        except Exception as e:  # noqa: BLE001 -- reported by the assertion below
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len({r["record"]["job_code"] for r in results}) == 90
    assert len(db.JOB_CODES) == stored_before + 90
    assert len(writes._state["requests"][REGIONAL]) == 90  # 90 distinct request ids


def test_write_without_any_answer_raises_after_exactly_two_attempts(fake, fixed_clock):
    fake.default = "hang"
    client = client_for(fake.url, timeout=0.3)
    start_time = time.monotonic()
    with pytest.raises(HsmUnavailable) as caught:
        client.add_record("job_code", job_code("slow"), "s1")
    elapsed = time.monotonic() - start_time
    assert caught.value.outcome_unknown is True
    assert caught.value.message == "no answer from HSM: TimeoutError"
    assert len(fake.requests) == 2
    assert 0.6 <= elapsed < 3, f"took {elapsed:.2f}s for two 0.3s timeouts"


# ============================================ Redone NFR pass (2026-10-02)
# Coverage the redone NFR requirements added or sharpened: session ids in
# paths (NFR1.1), every error path exposing nothing (NFR1.3), both backend
# 503s being final (NFR2.1), a copied error being refused (NFR2.2) and
# concurrent double failures each retried to its own record (NFR4.4).


def test_session_calls_quote_the_session_id(fake):
    session = "s/1?x#y"
    fake.actions = [
        ("raw", 200, b'{"active": true, "ended_reason": null}'),
        ("raw", 200, b'{"active": false, "ended_reason": "logout"}'),
    ]
    client = client_for(fake.url)
    assert client.session_status(session) == {"active": True, "ended_reason": None}
    assert client.end_session(session) == {"active": False, "ended_reason": "logout"}
    assert [request[:2] for request in fake.requests] == [
        ("GET", "/sessions/s%2F1%3Fx%23y"),
        ("POST", "/sessions/s%2F1%3Fx%23y/logout"),
    ]


def _error_status_case(backend_url, fake):
    """A second end_session: 401 from the backend, the session id in the URL."""
    session = start(backend_url)
    client = client_for(backend_url)
    client.end_session(session)
    with pytest.raises(HsmApiError) as caught:
        client.end_session(session)
    assert type(caught.value) is HsmApiError and caught.value.status == 401
    return caught.value, session


def _session_expired_case(backend_url, fake):
    """A data write after logout: the session id in the request body."""
    session = start(backend_url)
    logout(backend_url, session)
    with pytest.raises(SessionExpired) as caught:
        client_for(backend_url).add_record("job_code", job_code("leak_se"), session)
    return caught.value, session


def _read_no_answer_case(backend_url, fake):
    """session_status with no answer: the session id in the URL."""
    session = start(backend_url)
    fake.actions = ["drop"]
    with pytest.raises(HsmUnavailable) as caught:
        client_for(fake.url).session_status(session)
    assert caught.value.outcome_unknown is False
    assert session in fake.requests[-1][1]
    return caught.value, session


def _outcome_unknown_case(backend_url, fake):
    """A data write with no answer twice: the session id in the body."""
    session = start(backend_url)
    fake.actions = ["drop", "drop"]
    with pytest.raises(HsmUnavailable) as caught:
        client_for(fake.url).add_record("job_code", job_code("leak_ou"), session)
    assert caught.value.outcome_unknown is True
    assert last_body(fake)["session_id"] == session
    return caught.value, session


@pytest.mark.parametrize(
    "make_error",
    [
        _error_status_case,
        _session_expired_case,
        _read_no_answer_case,
        _outcome_unknown_case,
    ],
    ids=["error-status", "session-expired", "read-no-answer", "outcome-unknown-write"],
)
def test_every_error_path_exposes_no_session_id(backend_url, fake, make_error):
    error, session = make_error(backend_url, fake)
    assert len(session) >= 16  # a real backend session id, so a leak would be visible
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    shown = {
        "str": str(error),
        "repr": repr(error),
        "vars": repr(vars(error)),
        "traceback": "".join(traceback.format_exception(error)),
    }
    for where, text in shown.items():
        assert session not in text, where


@pytest.mark.parametrize("message", ["audit unavailable", "audit could not record the attempt"])
def test_backend_503_on_a_write_is_final_after_one_request(fake, message):
    fake.default = "drop"  # a second request, if one were sent, would get no answer
    fake.actions = [("raw", 503, json.dumps({"error": message}).encode())]
    with pytest.raises(HsmApiError) as caught:
        client_for(fake.url).add_record("job_code", job_code("a503"), "s1")
    error = caught.value
    assert type(error) is HsmApiError and not isinstance(error, HsmUnavailable)
    assert (error.status, error.message, error.problems) == (503, message, [])
    assert len(fake.requests) == 1


def test_retry_write_refuses_a_copied_error(fake, fixed_clock):
    fake.actions = ["drop", "drop"]
    client = client_for(fake.url)
    with pytest.raises(HsmUnavailable) as caught:
        client.add_record("job_code", job_code("copied"), "s1")
    original = caught.value
    copied = copy.copy(original)
    assert copied is not original
    assert (copied.outcome_unknown, copied.request_id, copied.retry_deadline) == (
        True,
        original.request_id,
        original.retry_deadline,
    )
    with pytest.raises(ValueError, match="retry not allowed for request"):
        client.retry_write(copied)
    assert len(fake.requests) == 2  # nothing more was sent
    assert original in hsm_client._RETRY_STORE  # the original error stays retryable


def test_eight_concurrent_double_failures_each_retry_to_their_own_record(fake, backend_url, fixed_clock):
    session = start(backend_url)
    fake.default = "forward_drop"  # every attempt reaches the backend, but no answer comes back
    shared = client_for(fake.url)  # one client for every thread's failing write
    retrier = client_for(backend_url)  # one client for every thread's retry, against the real backend
    stored_before = len(db.JOB_CODES)
    barrier = threading.Barrier(8, timeout=10)
    errors, results, failures = {}, {}, []

    def worker(n):
        try:
            barrier.wait()  # all eight writes fail together
            try:
                shared.add_record("job_code", job_code(f"c{n}"), session)
            except HsmUnavailable as e:
                errors[n] = e
            barrier.wait()  # all eight retries run together
            results[n] = retrier.retry_write(errors[n])
        except Exception as e:  # noqa: BLE001 -- reported by the assertion below
            failures.append((n, e))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert sorted(errors) == sorted(results) == list(range(8))
    assert len({error.request_id for error in errors.values()}) == 8
    assert len(fake.requests) == 16  # two attempts each, no more
    for n, error in errors.items():
        assert error.outcome_unknown is True
        stored = json.loads(hsm_client._RETRY_STORE[error].data)
        assert (stored["request_id"], stored["record"]) == (error.request_id, job_code(f"c{n}"))
        assert results[n]["record"] == job_code(f"c{n}") and results[n]["meta"]["version"] == 1
        assert [e["outcome"] for e in add_entries(f"jc_c{n}")] == ["allowed"]  # audited once
    assert len(db.JOB_CODES) == stored_before + 8  # no record created twice
