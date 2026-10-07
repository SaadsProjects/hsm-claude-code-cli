"""Tests for scripts/staging_monitor.py, the scheduled staging monitor (unit U1).

No test here reaches staging or api.github.com, opens a real issue or sleeps
toward a threshold: times are passed in, HTTP boundaries are exercised
against standard-library servers on port 0, and GitHub is a fake sender.
"""

import ast
import json
import re
import socket
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from ci_scripts import load

sm = load("staging_monitor")

STAGING = "https://staging.example.test"
PRACTICE = "https://practice-1.invalid"
T0 = datetime(2026, 10, 7, 3, 7, 0, tzinfo=timezone.utc)


def at(minutes, seconds=0):
    return T0 + timedelta(minutes=minutes, seconds=seconds)


def healthy(key=STAGING, checked=T0, practice=False):
    return sm.OutageState(target_key=key, last_checked_at=checked, last_reason="ok", practice=practice)


def suspected(first=T0, checked=None, key=STAGING, practice=False):
    return sm.OutageState(
        target_key=key,
        first_down_at=first,
        last_checked_at=checked or first,
        last_reason="no-answer",
        practice=practice,
    )


def alerted(first=T0, alerted_at=None, checked=None, number=42, key=STAGING, practice=False, acknowledged=False):
    alerted_at = alerted_at or first + timedelta(minutes=30)
    return sm.OutageState(
        target_key=key,
        first_down_at=first,
        last_checked_at=checked or alerted_at,
        last_reason="no-answer",
        alerted_at=alerted_at,
        issue_number=number,
        acknowledged=acknowledged,
        practice=practice,
    )


# ------------------------------------------------------------- target keys
@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://Staging.Example.TEST", STAGING),
        ("https://staging.example.test/", STAGING),
        ("https://staging.example.test/some/path?q=1#frag", STAGING),
        ("  https://staging.example.test  ", STAGING),
        ("https://staging.example.test:8443/x", "https://staging.example.test:8443"),
    ],
)
def test_target_key_keeps_only_the_lower_case_https_host(url, key):
    assert sm.target_key(url) == key


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://staging.example.test",
        "ftp://staging.example.test",
        "staging.example.test",
        "https://",
        "https://user:pw@staging.example.test",
    ],
)
def test_target_key_refuses_anything_but_an_https_host(url):
    with pytest.raises(ValueError):
        sm.target_key(url)


# --------------------------------------------------------- state consistency
def test_a_consistent_state_has_no_problem():
    for state in (healthy(), suspected(), alerted(), alerted(acknowledged=True)):
        assert sm.state_problem(state, at(60)) is None, state


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(
            sm.OutageState(STAGING, last_checked_at=T0, last_reason="ok", first_down_at=T0, alerted_at=T0),
            id="alerted-without-issue",
        ),
        pytest.param(
            sm.OutageState(STAGING, last_checked_at=T0, last_reason="ok", first_down_at=T0, issue_number=3),
            id="issue-without-alerted",
        ),
        pytest.param(
            sm.OutageState(STAGING, last_checked_at=T0, last_reason="ok", first_down_at=T0, acknowledged=True),
            id="acknowledged-without-alert",
        ),
        pytest.param(
            sm.OutageState(STAGING, last_checked_at=T0, last_reason="ok", alerted_at=T0, issue_number=3),
            id="alerted-without-first-down",
        ),
        pytest.param(
            sm.OutageState(
                STAGING, last_checked_at=T0, last_reason="ok", first_down_at=T0, alerted_at=T0, issue_number=0
            ),
            id="issue-number-zero",
        ),
        pytest.param(sm.OutageState(STAGING, last_checked_at=T0, last_reason="fine"), id="unknown-reason"),
        pytest.param(sm.OutageState("https://Bad.Key/", last_checked_at=T0, last_reason="ok"), id="bad-key"),
    ],
)
def test_an_inconsistent_state_is_named(state):
    assert sm.state_problem(state, at(60))


def test_a_last_check_later_than_this_check_is_out_of_order():
    assert sm.state_problem(healthy(checked=at(10)), at(5)) == "last check is later than this check"


# ------------------------------------------------------------- state file
def test_a_saved_state_reads_back_the_same(tmp_path):
    path = tmp_path / "nested" / "state.json"
    states = {STAGING: alerted(acknowledged=True), PRACTICE: suspected(key=PRACTICE, practice=True)}
    sm.save_state(path, states, at(90))
    loaded, notes = sm.load_state(path)
    assert loaded == states
    assert notes == []


def test_the_state_file_holds_iso_utc_times_and_a_schema_version(tmp_path):
    path = tmp_path / "state.json"
    sm.save_state(path, {STAGING: suspected()}, at(1))
    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert data["written_at"] == "2026-10-07T03:08:00Z"
    entry = data["entries"][STAGING]
    assert entry["first_down_at"] == "2026-10-07T03:07:00Z"
    assert entry["last_checked_at"] == "2026-10-07T03:07:00Z"
    assert entry["alerted_at"] is None


def test_saving_keeps_the_16_most_recently_checked_entries(tmp_path):
    path = tmp_path / "state.json"
    states = {f"https://p{i}.invalid": healthy(f"https://p{i}.invalid", at(i), True) for i in range(20)}
    sm.save_state(path, states, at(30))
    loaded, _ = sm.load_state(path)
    assert sorted(loaded) == sorted(f"https://p{i}.invalid" for i in range(4, 20))


def test_saving_leaves_no_temporary_file_behind(tmp_path):
    folder = tmp_path / "monitor"
    sm.save_state(folder / "state.json", {STAGING: healthy()}, T0)
    assert [p.name for p in folder.iterdir()] == ["state.json"]


def test_a_missing_state_file_reads_as_empty_with_a_note(tmp_path):
    loaded, notes = sm.load_state(tmp_path / "absent.json")
    assert loaded == {}
    assert notes == ["no saved state"]


@pytest.mark.parametrize(
    ("content", "note"),
    [
        pytest.param("{not json", "discarded (not readable JSON)", id="invalid-json"),
        pytest.param("[1, 2]", "discarded (wrong shape)", id="wrong-shape"),
        pytest.param('{"schema_version": 1, "entries": []}', "discarded (wrong shape)", id="entries-not-a-map"),
        pytest.param('{"schema_version": 2, "entries": {}}', "discarded (schema version 2 not understood)", id="v2"),
        pytest.param('{"entries": {}}', "discarded (schema version None not understood)", id="no-version"),
    ],
)
def test_an_unreadable_state_file_reads_as_empty_with_a_note(tmp_path, content, note):
    path = tmp_path / "state.json"
    path.write_text(content)
    loaded, notes = sm.load_state(path)
    assert loaded == {}
    assert notes == [note]


def test_a_state_file_that_cannot_be_read_reads_as_empty(tmp_path):
    loaded, notes = sm.load_state(tmp_path)  # a directory, not a file
    assert loaded == {}
    assert notes == ["discarded (not readable)"]


def _entry(**overrides):
    entry = {
        "target_key": STAGING,
        "first_down_at": "2026-10-07T03:07:00Z",
        "last_checked_at": "2026-10-07T03:37:00Z",
        "last_reason": "no-answer",
        "alerted_at": None,
        "issue_number": None,
        "acknowledged": False,
        "practice": False,
    }
    entry.update(overrides)
    return entry


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(_entry(alerted_at="2026-10-07T03:37:00Z"), id="alerted-without-issue"),
        pytest.param(_entry(first_down_at="yesterday"), id="bad-time"),
        pytest.param(_entry(last_checked_at="2026-10-07T03:37:00"), id="time-without-z"),
        pytest.param(_entry(issue_number="42", alerted_at="2026-10-07T03:37:00Z"), id="issue-number-string"),
        pytest.param(_entry(acknowledged="no"), id="acknowledged-string"),
        pytest.param(_entry(target_key="https://other.example.test"), id="key-mismatch"),
        pytest.param({"target_key": STAGING}, id="missing-fields"),
        pytest.param("not a map", id="not-a-map"),
    ],
)
def test_an_inconsistent_entry_is_dropped_with_a_note(tmp_path, entry):
    path = tmp_path / "state.json"
    good = _entry(target_key=PRACTICE, practice=True)
    data = {
        "schema_version": 1,
        "written_at": "2026-10-07T03:37:00Z",
        "entries": {STAGING: entry, PRACTICE: good},
    }
    path.write_text(json.dumps(data))
    loaded, notes = sm.load_state(path)
    assert list(loaded) == [PRACTICE]
    assert notes == ["discarded an inconsistent entry"]


# -------------------------------------------------------------- classifier
def result(status=None, body="", error_kind="none", content_type="text/plain"):
    return sm.ProbeResult(
        target=STAGING,
        checked_at=T0,
        status=status,
        error_kind=error_kind,
        body_text=body,
        content_type=content_type,
        body_bytes=len(body.encode()),
    )


def outcome(probe_result):
    observation = sm.classify(probe_result, STAGING)
    return observation.outcome, observation.reason


def test_classify_keeps_the_target_time_and_status():
    observation = sm.classify(result(502, "Bad gateway"), STAGING)
    assert observation == sm.Observation(STAGING, T0, "down", "error-status", 502)


@pytest.mark.parametrize(
    ("error_kind", "reason"),
    [("no-answer", "no-answer"), ("timeout", "timeout")],
)
def test_no_http_answer_is_down(error_kind, reason):
    assert outcome(result(error_kind=error_kind)) == ("down", reason)


@pytest.mark.parametrize("wording", ["gone to sleep", "get this app back up", "your app is in the oven", "waking up"])
@pytest.mark.parametrize("status", [200, 303, 404, 503])
def test_sleep_wording_is_asleep_at_any_status(wording, status):
    page = f"<html><body>Zzzz. This app has {wording.upper()}!</body></html>"
    assert outcome(result(status, page, content_type="text/html")) == ("asleep", "asleep")


@pytest.mark.parametrize("body", ["ok", "ok\n", "  ok  ", "\r\nok\t"])
def test_200_with_body_ok_is_up(body):
    assert outcome(result(200, body)) == ("up", "ok")


@pytest.mark.parametrize("body", ["", "OK fine", "<html>Streamlit</html>", "not ok"])
def test_200_with_any_other_body_is_an_unexpected_page(body):
    assert outcome(result(200, body, content_type="text/html")) == ("down", "unexpected-page")


@pytest.mark.parametrize("status", [204, 201])
def test_another_success_status_is_an_unexpected_page_even_with_ok(status):
    assert outcome(result(status, "ok")) == ("down", "unexpected-page")


@pytest.mark.parametrize("status", [301, 303, 307, 308])
def test_a_redirect_is_down_even_with_ok_in_the_body(status):
    assert outcome(result(status, "ok")) == ("down", "redirect")


@pytest.mark.parametrize("status", [404, 500, 502, 503])
def test_an_error_status_is_down(status):
    assert outcome(result(status, "ok")) == ("down", "error-status")


def test_sleep_wording_beats_a_no_answer_only_when_there_was_an_answer():
    # No answer has no body; the error kind decides before any wording check.
    assert outcome(result(error_kind="timeout", body="waking up")) == ("down", "timeout")


# ----------------------------------------------------------------- tracker
def seen(outcome_, minutes, seconds=0, key=STAGING):
    reason = {"up": "ok", "asleep": "asleep", "down": "no-answer"}[outcome_]
    return sm.Observation(key, at(minutes, seconds), outcome_, reason, None)


def issue(number=42, opened=None, key=STAGING, practice=False):
    return sm.OutageIssue(number=number, opened_at=opened or at(30), target_key=key, practice=practice)


def test_healthy_and_up_stays_healthy_and_records_the_check():
    state, decision = sm.decide(healthy(), seen("up", 30), None)
    assert decision.action == "nothing"
    assert not decision.red
    assert state == healthy(checked=at(30))


def test_healthy_and_asleep_stays_healthy():
    state, decision = sm.decide(healthy(), seen("asleep", 30), None)
    assert decision.action == "nothing"
    assert state.first_down_at is None
    assert state.last_reason == "asleep"


def test_the_first_down_sighting_is_remembered_without_an_alert():
    state, decision = sm.decide(healthy(), seen("down", 30), None)
    assert decision.action == "remember"
    assert not decision.red
    assert state.first_down_at == at(30)
    assert state.alerted_at is None


def test_down_with_no_state_at_all_is_a_first_sighting():
    state, decision = sm.decide(None, seen("down", 0), None)
    assert decision.action == "remember"
    assert state == suspected(first=T0)


def test_down_just_under_5_minutes_after_the_first_sighting_sends_nothing():
    state, decision = sm.decide(suspected(), seen("down", 4, 59), None)
    assert decision.action == "nothing"
    assert not decision.red
    assert state.alerted_at is None
    assert state.first_down_at == T0
    assert state.last_checked_at == at(4, 59)


def test_down_at_exactly_5_minutes_opens_one_issue_and_turns_the_run_red():
    state, decision = sm.decide(suspected(), seen("down", 5), None)
    assert decision.action == "open-issue"
    assert decision.red
    assert state.alerted_at == at(5)
    assert state.first_down_at == T0
    # Until the issue exists, the state to keep is the unalerted suspicion.
    assert decision.keep_on_failure == suspected(first=T0, checked=at(5))


def test_down_30_minutes_after_the_first_sighting_opens_an_issue():
    _, decision = sm.decide(suspected(), seen("down", 30), None)
    assert decision.action == "open-issue"


@pytest.mark.parametrize("outcome_", ["up", "asleep"])
def test_a_single_failed_check_followed_by_up_or_asleep_sends_nothing(outcome_):
    state, decision = sm.decide(suspected(), seen(outcome_, 30), None)
    assert decision.action == "nothing"
    assert not decision.red
    assert state.first_down_at is None
    assert state.alerted_at is None


def test_a_stale_suspicion_restarts_at_this_check():
    old = suspected(first=T0, checked=T0)
    state, decision = sm.decide(old, seen("down", 91), None)
    assert decision.action == "remember"
    assert state.first_down_at == at(91)
    assert "stale suspicion forgotten" in decision.notes


def test_a_suspicion_checked_exactly_90_minutes_ago_is_not_stale():
    _, decision = sm.decide(suspected(), seen("down", 90), None)
    assert decision.action == "open-issue"


def test_an_alerted_outage_older_than_90_minutes_is_not_stale():
    old = alerted(first=T0, alerted_at=at(5), checked=at(5))
    state, decision = sm.decide(old, seen("down", 300), issue(opened=at(5)))
    assert decision.action == "leave-open"
    assert state.first_down_at == T0
    assert state.issue_number == 42


def test_further_down_runs_while_the_issue_is_open_do_not_alert_again():
    state, decision = sm.decide(alerted(), seen("down", 60), issue())
    assert decision.action == "leave-open"
    assert not decision.red
    assert state == alerted(checked=at(60))


def test_a_real_issue_closed_by_hand_during_the_outage_is_an_acknowledgement():
    state, decision = sm.decide(alerted(), seen("down", 60), None)
    assert decision.action == "acknowledge"
    assert not decision.red
    assert state.acknowledged
    assert state.issue_number == 42


def test_a_practice_issue_closed_by_hand_ends_the_drill_and_this_run_starts_the_next():
    # BR2.4 / functional-spec W2 step 4: the run that finds the practice issue
    # closed is the first sighting of a fresh drill, not a wasted run.
    practice_state = alerted(key=PRACTICE, practice=True)
    check = seen("down", 60, key=PRACTICE)
    state, decision = sm.decide(practice_state, check, None, practice=True)
    assert decision.action == "remember"
    assert not decision.red
    assert state.practice
    assert state.first_down_at == check.checked_at
    assert (state.alerted_at, state.issue_number, state.acknowledged) == (None, None, False)


def test_the_next_practice_run_after_the_drill_starts_a_new_one():
    state, decision = sm.decide(None, seen("down", 70, key=PRACTICE), None, practice=True)
    assert decision.action == "remember"
    assert state.practice


def test_a_repeat_drill_with_the_same_address_takes_two_runs():
    # Drill 1: remember, open; the owner closes the issue by hand.
    state, decision = sm.decide(None, seen("down", 0, key=PRACTICE), None, practice=True)
    assert decision.action == "remember"
    state, decision = sm.decide(state, seen("down", 6, key=PRACTICE), None, practice=True)
    assert decision.action == "open-issue"
    state = replace(state, issue_number=7)
    # Drill 2 with the same address, after the issue was closed: two runs again.
    state, decision = sm.decide(state, seen("down", 60, key=PRACTICE), None, practice=True)
    assert decision.action == "remember"
    state, decision = sm.decide(state, seen("down", 66, key=PRACTICE), None, practice=True)
    assert decision.action == "open-issue"
    assert decision.red


def test_acknowledged_and_still_down_stays_quiet_and_is_not_acknowledged_again():
    quiet = alerted(acknowledged=True)
    state, decision = sm.decide(quiet, seen("down", 90), None)
    assert decision.action == "nothing"
    assert not decision.red
    assert state.acknowledged


@pytest.mark.parametrize("outcome_", ["up", "asleep"])
def test_acknowledged_and_back_up_returns_to_healthy_without_touching_github(outcome_):
    state, decision = sm.decide(alerted(acknowledged=True), seen(outcome_, 90), None)
    assert decision.action == "nothing"
    assert state.first_down_at is None
    assert state.issue_number is None
    assert not state.acknowledged


@pytest.mark.parametrize("outcome_", ["up", "asleep"])
def test_the_first_success_after_an_alert_closes_the_outage(outcome_):
    state, decision = sm.decide(alerted(), seen(outcome_, 60), issue())
    assert decision.action == "close-issue"
    assert decision.issue_number == 42
    assert not decision.red
    assert state.first_down_at is None
    assert state.issue_number is None
    # If the close fails, the outage stays remembered so the next run retries.
    kept = decision.keep_on_failure
    assert (kept.issue_number, kept.alerted_at, kept.first_down_at) == (42, at(30), T0)
    assert kept.last_checked_at == at(60)


def test_lost_state_with_an_open_issue_and_down_adopts_it():
    state, decision = sm.decide(None, seen("down", 60), issue(opened=at(30)))
    assert decision.action == "adopt-issue"
    assert decision.adopted
    assert not decision.red
    assert (state.issue_number, state.alerted_at, state.first_down_at) == (42, at(30), at(30))


def test_a_suspicion_with_an_open_issue_adopts_it_instead_of_opening_a_second():
    state, decision = sm.decide(suspected(), seen("down", 60), issue(opened=at(30)))
    assert decision.action == "adopt-issue"
    assert state.first_down_at == T0
    assert state.issue_number == 42


@pytest.mark.parametrize("outcome_", ["up", "asleep"])
def test_lost_state_with_an_open_issue_and_up_adopts_it_then_closes_it(outcome_):
    state, decision = sm.decide(None, seen(outcome_, 60), issue(opened=at(30)))
    assert decision.action == "close-issue"
    assert decision.adopted
    assert decision.issue_number == 42
    assert state.issue_number is None
    assert decision.keep_on_failure.issue_number == 42


def test_inconsistent_state_is_discarded_and_treated_as_healthy():
    broken = sm.OutageState(STAGING, last_checked_at=T0, last_reason="ok", first_down_at=T0, alerted_at=T0)
    state, decision = sm.decide(broken, seen("down", 30), None)
    assert decision.action == "remember"
    assert state.first_down_at == at(30)
    assert any(note.startswith("discarded") for note in decision.notes)


def test_out_of_order_state_is_discarded():
    future = suspected(first=at(100), checked=at(100))
    state, decision = sm.decide(future, seen("down", 30), None)
    assert decision.action == "remember"
    assert state.first_down_at == at(30)
    assert "discarded (last check is later than this check)" in decision.notes


def test_every_decided_run_records_its_check_time_and_reason():
    for before, observation, found in [
        (healthy(), seen("down", 30), None),
        (suspected(), seen("down", 3), None),
        (alerted(), seen("down", 60), issue()),
        (alerted(acknowledged=True), seen("down", 60), None),
    ]:
        state, _ = sm.decide(before, observation, found)
        assert (state.last_checked_at, state.last_reason) == (observation.checked_at, observation.reason)


def test_only_open_issue_turns_a_run_red():
    reds = {
        sm.decide(*args)[1].action
        for args in [
            (healthy(), seen("down", 30), None),
            (suspected(), seen("down", 5), None),
            (alerted(), seen("down", 60), issue()),
            (alerted(), seen("up", 60), issue()),
            (alerted(), seen("down", 60), None),
        ]
        if sm.decide(*args)[1].red
    }
    assert reds == {"open-issue"}


# ------------------------------------------------- probe (local server, port 0)
@contextmanager
def serve(status=200, body=b"ok", headers=None, delay=0.0):
    """A one-answer HTTP server on 127.0.0.1, port 0. Yields its base URL and
    the list of requests it received (method, path, headers)."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(("GET", self.path, dict(self.headers)))
            if delay:
                time.sleep(delay)  # a slow server, against a much shorter client timeout
            self.send_response(status)
            for name, value in (headers or {"Content-Type": "text/plain"}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_POST = do_PATCH = do_GET

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", received
    finally:
        server.shutdown()
        server.server_close()


def closed_port_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def test_the_probe_sends_one_plain_get_of_the_health_path():
    with serve(200, b"ok") as (base, received):
        got = sm.probe(base + "/ignored/path", T0, timeout=2)
    assert got.status == 200
    assert got.error_kind == "none"
    assert got.body_text == "ok"
    assert got.checked_at == T0
    assert len(received) == 1
    method, path, headers = received[0]
    assert (method, path) == ("GET", sm.HEALTH_PATH)
    lowered = {name.lower() for name in headers}
    assert "authorization" not in lowered
    assert "cookie" not in lowered
    assert headers.get("User-Agent") == sm.USER_AGENT
    assert sm.classify(got, STAGING).outcome == "up"


def test_the_probe_does_not_follow_a_redirect():
    with serve(303, b"", {"Location": "/elsewhere"}) as (base, received):
        got = sm.probe(base, T0, timeout=2)
    assert got.status == 303
    assert len(received) == 1
    assert sm.classify(got, STAGING).reason == "redirect"


def test_the_sleep_page_is_asleep():
    page = b"<html><body>Zzzz. This app has gone to sleep due to inactivity.</body></html>"
    with serve(503, page, {"Content-Type": "text/html"}) as (base, _):
        got = sm.probe(base, T0, timeout=2)
    assert (got.status, got.content_type) == (503, "text/html")
    assert sm.classify(got, STAGING).outcome == "asleep"


def test_the_host_wrapper_page_is_an_unexpected_page():
    shell = b"<!doctype html><html><head><title>Streamlit</title></head><body></body></html>"
    with serve(200, shell, {"Content-Type": "text/html"}) as (base, _):
        got = sm.probe(base, T0, timeout=2)
    assert sm.classify(got, STAGING).reason == "unexpected-page"


@pytest.mark.parametrize("status", [404, 502])
def test_an_error_status_comes_back_as_its_status(status):
    with serve(status, b"nope") as (base, _):
        got = sm.probe(base, T0, timeout=2)
    assert got.status == status
    assert sm.classify(got, STAGING).reason == "error-status"


def test_a_slow_answer_is_a_timeout():
    with serve(200, b"ok", delay=1.0) as (base, _):
        got = sm.probe(base, T0, timeout=0.2)
    assert (got.status, got.error_kind) == (None, "timeout")


def test_a_closed_port_is_no_answer():
    got = sm.probe(closed_port_url(), T0, timeout=1)
    assert (got.status, got.error_kind) == (None, "no-answer")


def test_a_host_that_cannot_be_encoded_is_no_answer_not_a_crash():
    # A DNS label over 63 characters passes target_key but fails IDNA encoding
    # inside urllib; the probe promises never to raise.
    target = sm.target_key("https://" + "a" * 64 + ".example.test")
    got = sm.probe(target, T0, timeout=1)
    assert (got.status, got.error_kind) == (None, "no-answer")


def test_the_probe_keeps_only_the_first_64_kib_of_the_body():
    with serve(200, b"x" * (100 * 1024)) as (base, _):
        got = sm.probe(base, T0, timeout=2)
    assert got.body_bytes == sm.BODY_LIMIT_BYTES == 65536
    assert len(got.body_text) == 65536


def test_the_probe_and_github_time_out_after_20_seconds_by_default():
    assert sm.REQUEST_TIMEOUT_SECONDS == 20


# ------------------------------------------------------------- GitHub client
class _CapturingOpener:
    def __init__(self, answer=b"[]"):
        self.requests, self.answer = [], answer

    def open(self, request, timeout=None):
        self.requests.append((request, timeout))
        return _Answer(self.answer)


class _Answer:
    status = 200

    def __init__(self, body):
        self.body = body

    def read(self, limit=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_github_requests_go_only_to_the_api_host_with_the_token():
    request = sm.github_request("POST", "/repos/o/r/issues", "tkn-123", {"title": "x"})
    assert request.full_url == "https://api.github.com/repos/o/r/issues"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer tkn-123"
    assert json.loads(request.data) == {"title": "x"}


@pytest.mark.parametrize("path", ["repos/o/r", "@evil.example/x", "https://evil.example/x"])
def test_github_request_refuses_a_path_that_could_leave_the_api_host(path):
    with pytest.raises(ValueError):
        sm.github_request("GET", path, "tkn-123")


def test_the_sender_builds_repository_paths_on_the_api_host():
    opener = _CapturingOpener(b'[{"number": 1}]')
    sender = sm.make_sender("tkn-123", "owner/repo", opener=opener)
    assert sender("GET", "/issues?state=open") == [{"number": 1}]
    request, timeout = opener.requests[0]
    assert request.full_url == "https://api.github.com/repos/owner/repo/issues?state=open"
    assert request.get_header("Authorization") == "Bearer tkn-123"
    assert timeout == sm.REQUEST_TIMEOUT_SECONDS


@pytest.mark.parametrize("repository", ["", "owner", "owner/repo/extra", "own er/repo", "../x/y"])
def test_the_sender_refuses_a_malformed_repository(repository):
    with pytest.raises(ValueError):
        sm.make_sender("tkn-123", repository)


def test_a_github_redirect_is_not_followed_so_the_token_is_never_resent():
    with serve(307, b"", {"Location": "/somewhere-else"}) as (base, received):
        request = urllib.request.Request(base + "/repos/o/r/issues", headers={"Authorization": "Bearer tkn-123"})
        with pytest.raises(sm.GitHubError) as caught:
            sm.send_json(request, timeout=2)
    assert caught.value.status == 307
    assert len(received) == 1


def test_a_github_error_status_is_reported_by_status_only():
    with serve(502, b"upstream says https://evil.example/secret") as (base, _), pytest.raises(sm.GitHubError) as caught:
        sm.send_json(urllib.request.Request(base + "/x"), timeout=2)
    assert caught.value.status == 502
    assert "evil" not in str(caught.value)


def test_no_answer_from_github_is_a_github_error_without_status():
    with pytest.raises(sm.GitHubError) as caught:
        sm.send_json(urllib.request.Request(closed_port_url() + "/x"), timeout=1)
    assert caught.value.status is None


# ------------------------------------------------------------------- issues
class FakeSender:
    """Stands in for GitHub: records every call; never touches the network."""

    def __init__(self, listing=(), created=77, fail=()):
        self.listing, self.created, self.fail = list(listing), created, set(fail)
        self.calls = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        operation = {"GET": "list", "POST": "comment" if path.endswith("/comments") else "open", "PATCH": "close"}
        if operation[method] in self.fail:
            raise sm.GitHubError(502)
        if method == "GET":
            return self.listing
        if operation[method] == "open":
            return {"number": self.created}
        return {}


def gh_issue(number=42, author=sm.BOT_AUTHOR, key=STAGING, label=sm.REAL_LABEL, title=None, **extra):
    data = {
        "number": number,
        "state": "open",
        "title": title or f"Staging is down: {key}",
        "user": {"login": author},
        "labels": [{"name": label}],
        "body": f"Some text\n\n{sm.marker(key)}\n",
        "created_at": "2026-10-07T03:37:00Z",
    }
    data.update(extra)
    return data


RUN_LINK = "https://github.com/owner/repo/actions/runs/123"


def test_finds_the_monitors_own_open_issue_for_the_target():
    sender = FakeSender([gh_issue(42)])
    found = sm.find_open_issue(sender, STAGING, practice=False)
    assert found == sm.OutageIssue(42, at(30), STAGING, False)
    method, path, _ = sender.calls[0]
    assert method == "GET"
    assert path.startswith("/issues?")
    assert "state=open" in path
    assert f"labels={sm.REAL_LABEL}" in path


def test_practice_issues_are_looked_up_under_the_practice_label():
    sender = FakeSender([gh_issue(5, key=PRACTICE, label=sm.PRACTICE_LABEL)])
    assert sm.find_open_issue(sender, PRACTICE, practice=True).number == 5
    assert f"labels={sm.PRACTICE_LABEL}" in sender.calls[0][1]


@pytest.mark.parametrize(
    "lookalike",
    [
        pytest.param(gh_issue(7, author="someone"), id="wrong-author"),
        pytest.param(gh_issue(7, body="Staging is down, trust me"), id="no-marker"),
        pytest.param(gh_issue(7, key="https://other.example.test"), id="other-target"),
        pytest.param(gh_issue(7, labels=[{"name": "bug"}]), id="label-missing"),
        pytest.param(gh_issue(7, pull_request={"url": "x"}), id="pull-request"),
        pytest.param(gh_issue(7, user=None), id="no-user"),
        pytest.param(gh_issue(7, body=None), id="no-body"),
        pytest.param(gh_issue(7, created_at="later"), id="bad-time"),
        pytest.param("not an issue", id="not-a-map"),
    ],
)
def test_look_alike_issues_are_ignored(lookalike):
    assert sm.find_open_issue(FakeSender([lookalike]), STAGING, practice=False) is None


def test_the_oldest_own_issue_wins_when_there_are_several():
    sender = FakeSender([gh_issue(50), gh_issue(42), gh_issue(7, author="someone")])
    assert sm.find_open_issue(sender, STAGING, practice=False).number == 42


def test_an_unexpected_listing_is_a_github_error():
    with pytest.raises(sm.GitHubError):
        sm.find_open_issue(lambda method, path, body=None: {"message": "x"}, STAGING, practice=False)


def _observation(reason="no-answer", status=None):
    return sm.Observation(STAGING, at(5), "down", reason, status)


def test_opening_an_issue_uses_the_fixed_template_and_the_real_label():
    sender = FakeSender(created=77)
    number = sm.open_outage_issue(sender, STAGING, False, T0, _observation("error-status", 502), RUN_LINK)
    assert number == 77
    method, path, body = sender.calls[0]
    assert (method, path) == ("POST", "/issues")
    assert body["title"] == f"Staging is down: {STAGING}"
    assert body["labels"] == [sm.REAL_LABEL]
    text = body["body"]
    assert "2026-10-07T03:07:00Z" in text  # first seen
    assert "2026-10-07T03:12:00Z" in text  # last checked
    assert "error-status" in text
    assert "HTTP 502" in text
    assert RUN_LINK in text
    assert "docs/staging-app.md" in text
    assert text.rstrip().endswith(sm.marker(STAGING))


def test_a_practice_issue_says_so_and_uses_the_practice_label():
    sender = FakeSender()
    observation = sm.Observation(PRACTICE, at(5), "down", "no-answer", None)
    sm.open_outage_issue(sender, PRACTICE, True, T0, observation, RUN_LINK)
    body = sender.calls[0][2]
    assert body["title"] == f"Practice: {PRACTICE} is down"
    assert body["labels"] == [sm.PRACTICE_LABEL]
    assert "practice" in body["body"].lower()
    assert body["body"].rstrip().endswith(sm.marker(PRACTICE))


def test_without_a_run_link_the_issue_says_so_instead_of_inventing_one():
    sender = FakeSender()
    sm.open_outage_issue(sender, STAGING, False, T0, _observation(), None)
    assert "https://github.com" not in sender.calls[0][2]["body"]


def test_closing_comments_with_the_time_back_and_the_outage_length_then_closes():
    sender = FakeSender()
    sm.close_outage_issue(sender, 42, at(65, 30), T0)
    (m1, p1, b1), (m2, p2, b2) = sender.calls
    assert (m1, p1) == ("POST", "/issues/42/comments")
    assert "2026-10-07T04:12:30Z" in b1["body"]
    assert "65 minutes" in b1["body"]
    assert (m2, p2) == ("PATCH", "/issues/42")
    assert b2["state"] == "closed"


def test_a_failed_comment_does_not_close_the_issue():
    sender = FakeSender(fail={"comment"})
    with pytest.raises(sm.GitHubError):
        sm.close_outage_issue(sender, 42, at(60), T0)
    assert [method for method, _, _ in sender.calls] == ["POST"]


URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")


@pytest.mark.parametrize(("key", "practice"), [(STAGING, False), (PRACTICE, True)])
def test_every_rendered_text_holds_only_the_target_and_the_run_link(key, practice):
    observation = sm.Observation(key, at(5), "down", "redirect", 303)
    texts = [
        sm.issue_title(key, practice),
        sm.issue_body(key, practice, T0, observation, RUN_LINK),
        sm.recovery_comment(at(60), T0),
    ]
    for text in texts:
        assert set(URL_PATTERN.findall(text)) <= {key, RUN_LINK}, text
        # The runbook is a plain repository path, never a link.
        assert "](docs/" not in text
        assert "blob/" not in text


def test_the_body_names_the_runbook_as_a_plain_path():
    body = sm.issue_body(STAGING, False, T0, _observation(), RUN_LINK)
    assert "`docs/staging-app.md`" in body


@pytest.mark.parametrize(
    ("env", "link"),
    [
        (
            {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "9"},
            "https://github.com/o/r/actions/runs/9",
        ),
        ({"GITHUB_SERVER_URL": "https://ghe.example.test", "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "9"}, None),
        ({"GITHUB_SERVER_URL": "http://github.com", "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "9"}, None),
        ({"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "o/r?x=1", "GITHUB_RUN_ID": "9"}, None),
        ({"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "9a"}, None),
        ({}, None),
    ],
)
def test_the_run_link_is_only_ever_this_repositorys_run_on_github_com(env, link):
    assert sm.run_link(env) == link


# ------------------------------------------------------------- command line
STAGING_ENV = {
    "STAGING_URL": STAGING,
    "GITHUB_TOKEN": "fake-gh-token",
    "GITHUB_REPOSITORY": "owner/repo",
    "GITHUB_RUN_ID": "123",
    "GITHUB_SERVER_URL": "https://github.com",
}


class FakeProbe:
    """Answers every check with one canned result; records what was checked."""

    def __init__(self, status=None, body="", error_kind="none", content_type="text/plain"):
        self.answer = dict(status=status, body_text=body, error_kind=error_kind, content_type=content_type)
        self.calls = []

    def __call__(self, target, checked_at):
        self.calls.append((target, checked_at))
        return sm.ProbeResult(
            target=target, checked_at=checked_at, body_bytes=len(self.answer["body_text"]), **self.answer
        )


UP_PROBE = dict(status=200, body="ok")
DOWN_PROBE = dict(error_kind="no-answer")


def run(tmp_path, *, env=None, now=T0, probe=None, sender=None, state=None, argv=None):
    path = tmp_path / "monitor" / "state.json"
    if state is not None:
        sm.save_state(path, state, now)
    code = sm.main(
        ["--state", str(path)] if argv is None else argv,
        env=dict(STAGING_ENV if env is None else env),
        clock=lambda: now,
        probe_fn=probe or FakeProbe(**UP_PROBE),
        sender=sender if sender is not None else FakeSender(),
    )
    return code, path


def lines(capsys):
    captured = capsys.readouterr()
    return captured.out.splitlines(), captured.err


@pytest.mark.parametrize(
    "env",
    [
        pytest.param({k: v for k, v in STAGING_ENV.items() if k != "STAGING_URL"}, id="missing"),
        pytest.param({**STAGING_ENV, "STAGING_URL": ""}, id="empty"),
        pytest.param({**STAGING_ENV, "STAGING_URL": "http://hidden-host.example.test"}, id="not-https"),
        pytest.param({**STAGING_ENV, "STAGING_URL": "https://user:pw@hidden-host.example.test"}, id="credentials"),
    ],
)
def test_a_missing_or_bad_staging_url_is_bad_usage_naming_only_the_variable(tmp_path, capsys, env):
    probe = FakeProbe(**UP_PROBE)
    code, path = run(tmp_path, env=env, probe=probe)
    out, err = lines(capsys)
    assert code == sm.EXIT_USAGE == 2
    assert "STAGING_URL" in err
    assert "hidden-host" not in err + "\n".join(out)
    assert "pw" not in err
    assert probe.calls == []
    assert not path.exists()


@pytest.mark.parametrize(
    "address",
    ["https://staging.example.test", "http://practice-1.invalid", "https://invalid", "https://x.invalid.example"],
)
def test_a_practice_address_outside_invalid_is_bad_usage(tmp_path, capsys, address):
    probe = FakeProbe(**UP_PROBE)
    code, _ = run(tmp_path, env={**STAGING_ENV, "PRACTICE_ADDRESS": address}, probe=probe)
    _, err = lines(capsys)
    assert code == sm.EXIT_USAGE
    assert "PRACTICE_ADDRESS" in err
    assert probe.calls == []


@pytest.mark.parametrize("missing", ["GITHUB_TOKEN", "GITHUB_REPOSITORY"])
def test_without_github_settings_the_real_sender_cannot_be_built(tmp_path, capsys, missing):
    env = {k: v for k, v in STAGING_ENV.items() if k != missing}
    path = tmp_path / "state.json"
    code = sm.main(["--state", str(path)], env=env, clock=lambda: T0, probe_fn=FakeProbe(**UP_PROBE))
    _, err = lines(capsys)
    assert code == sm.EXIT_USAGE
    assert missing in err
    assert "fake-gh-token" not in err


def test_an_unknown_option_is_bad_usage(tmp_path, capsys):
    code, _ = run(tmp_path, argv=["--bogus"])
    assert code == sm.EXIT_USAGE
    assert "usage:" in capsys.readouterr().err


def test_the_help_lists_the_exit_codes(capsys):
    with pytest.raises(SystemExit):
        sm.main(["--help"])
    assert "exit codes: 0" in capsys.readouterr().out


def test_happy_path_up_prints_one_check_and_one_decision_and_saves_state(tmp_path, capsys):
    code, path = run(tmp_path, probe=FakeProbe(**UP_PROBE))
    out, _ = lines(capsys)
    assert code == sm.EXIT_OK == 0
    checks = [line for line in out if line.startswith("check:")]
    decisions = [line for line in out if line.startswith("decision:")]
    assert checks == [f"check: target={STAGING} at=2026-10-07T03:07:00Z outcome=up reason=ok status=200"]
    assert decisions == ["decision: nothing"]
    loaded, _ = sm.load_state(path)
    assert loaded[STAGING].last_reason == "ok"


def test_the_probe_is_given_the_canonical_target(tmp_path):
    probe = FakeProbe(**UP_PROBE)
    run(tmp_path, env={**STAGING_ENV, "STAGING_URL": "https://Staging.Example.test/app/"}, probe=probe)
    assert probe.calls == [(STAGING, T0)]


def test_a_first_down_sighting_is_remembered_and_the_run_stays_green(tmp_path, capsys):
    code, path = run(tmp_path, probe=FakeProbe(**DOWN_PROBE))
    out, _ = lines(capsys)
    assert code == sm.EXIT_OK
    assert "decision: remember (first sighting)" in out
    assert sm.load_state(path)[0][STAGING].first_down_at == T0


def test_a_confirmed_outage_opens_an_issue_and_turns_the_run_red(tmp_path, capsys):
    sender = FakeSender(created=77)
    code, path = run(tmp_path, now=at(30), probe=FakeProbe(**DOWN_PROBE), sender=sender, state={STAGING: suspected()})
    out, _ = lines(capsys)
    assert code == sm.EXIT_FAIL == 1
    assert "decision: open-issue #77" in out
    posted = [body for method, path_, body in sender.calls if method == "POST"]
    assert posted[0]["labels"] == [sm.REAL_LABEL]
    assert "https://github.com/owner/repo/actions/runs/123" in posted[0]["body"]
    saved = sm.load_state(path)[0][STAGING]
    assert (saved.issue_number, saved.alerted_at, saved.first_down_at) == (77, at(30), T0)


def test_a_failed_open_keeps_the_suspicion_so_the_next_run_retries(tmp_path, capsys):
    sender = FakeSender(fail={"open"})
    code, path = run(tmp_path, now=at(30), probe=FakeProbe(**DOWN_PROBE), sender=sender, state={STAGING: suspected()})
    out, _ = lines(capsys)
    assert code == sm.EXIT_FAIL
    assert "error: open issue failed (HTTP 502)" in out
    saved = sm.load_state(path)[0][STAGING]
    assert (saved.first_down_at, saved.alerted_at, saved.issue_number) == (T0, None, None)
    assert saved.last_checked_at == at(30)
    # The next run confirms again and opens the issue.
    code, path = run(tmp_path, now=at(60), probe=FakeProbe(**DOWN_PROBE), sender=FakeSender(created=78))
    assert code == sm.EXIT_FAIL
    assert sm.load_state(path)[0][STAGING].issue_number == 78


def test_recovery_closes_the_issue_and_the_run_stays_green(tmp_path, capsys):
    sender = FakeSender([gh_issue(42)])
    code, path = run(tmp_path, now=at(60), sender=sender, state={STAGING: alerted()})
    out, _ = lines(capsys)
    assert code == sm.EXIT_OK
    assert "decision: close-issue #42" in out
    assert [(m, p) for m, p, _ in sender.calls[1:]] == [("POST", "/issues/42/comments"), ("PATCH", "/issues/42")]
    assert sm.load_state(path)[0][STAGING].issue_number is None


def test_a_failed_close_keeps_the_alerted_state_and_turns_the_run_red(tmp_path, capsys):
    sender = FakeSender([gh_issue(42)], fail={"close"})
    code, path = run(tmp_path, now=at(60), sender=sender, state={STAGING: alerted()})
    out, _ = lines(capsys)
    assert code == sm.EXIT_FAIL
    assert "error: close issue failed (HTTP 502)" in out
    saved = sm.load_state(path)[0][STAGING]
    assert (saved.issue_number, saved.alerted_at, saved.first_down_at) == (42, at(30), T0)


def test_lost_state_and_an_open_issue_on_recovery_adopts_then_closes_it(tmp_path, capsys):
    sender = FakeSender([gh_issue(42)])
    code, _ = run(tmp_path, now=at(60), sender=sender)
    out, _ = lines(capsys)
    assert code == sm.EXIT_OK
    assert "decision: close-issue #42 (adopted)" in out


def test_a_failed_issue_listing_saves_the_state_and_turns_the_run_red(tmp_path, capsys):
    sender = FakeSender(fail={"list"})
    code, path = run(tmp_path, now=at(30), probe=FakeProbe(**DOWN_PROBE), sender=sender, state={STAGING: suspected()})
    out, _ = lines(capsys)
    assert code == sm.EXIT_FAIL
    assert "error: list issues failed (HTTP 502)" in out
    assert not any(line.startswith("decision:") and "open-issue" in line for line in out)
    assert [m for m, _, _ in sender.calls] == ["GET"]
    assert sm.load_state(path)[0] == {STAGING: suspected()}


def test_unreadable_state_is_noted_and_the_run_continues(tmp_path, capsys):
    path = tmp_path / "monitor" / "state.json"
    path.parent.mkdir()
    path.write_text("{garbage")
    code, _ = run(tmp_path, probe=FakeProbe(**DOWN_PROBE))
    out, _ = lines(capsys)
    assert code == sm.EXIT_OK
    assert "state: discarded (not readable JSON)" in out
    assert "decision: remember (first sighting)" in out


def test_a_state_that_cannot_be_saved_turns_the_run_red(tmp_path, capsys):
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the state folder should be")
    code = sm.main(
        ["--state", str(blocked / "state.json")],
        env=STAGING_ENV,
        clock=lambda: T0,
        probe_fn=FakeProbe(**UP_PROBE),
        sender=FakeSender(),
    )
    out, _ = lines(capsys)
    assert code == sm.EXIT_FAIL
    assert "error: save state failed" in out


@pytest.mark.parametrize(
    ("answer", "detail"),
    [
        (dict(status=303, body=""), True),
        (dict(status=200, body="<html>Streamlit</html>", content_type="text/html"), True),
        (dict(status=502, body="bad"), False),
        (dict(error_kind="no-answer"), False),
        (dict(status=200, body="ok"), False),
    ],
)
def test_check_detail_is_printed_only_for_redirects_and_unexpected_pages(tmp_path, capsys, answer, detail):
    run(tmp_path, probe=FakeProbe(**answer))
    out, _ = lines(capsys)
    details = [line for line in out if line.startswith("check-detail:")]
    if detail:
        status = answer["status"]
        size = len(answer["body"])
        kind = answer.get("content_type", "text/plain")
        assert details == [f"check-detail: status={status} content-type={kind} body-bytes={size}"]
    else:
        assert details == []


def test_no_line_ever_holds_the_token_or_exception_text(tmp_path, capsys):
    def exploding(method, path, body=None):
        raise RuntimeError("boom at https://evil.example.test with fake-gh-token")

    code, _ = run(tmp_path, now=at(30), probe=FakeProbe(**DOWN_PROBE), sender=exploding, state={STAGING: suspected()})
    out, err = lines(capsys)
    text = "\n".join(out) + err
    assert code == sm.EXIT_FAIL
    assert "error: list issues failed (unexpected error)" in out
    assert "fake-gh-token" not in text
    assert "evil" not in text
    assert "boom" not in text


def test_every_output_line_holds_only_the_target_url(tmp_path, capsys):
    run(tmp_path, now=at(30), probe=FakeProbe(**DOWN_PROBE), sender=FakeSender(), state={STAGING: suspected()})
    out, err = lines(capsys)
    assert set(URL_PATTERN.findall("\n".join(out) + err)) <= {STAGING}


def test_github_is_reached_only_through_the_injected_sender(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("the monitor opened a connection of its own")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    sender = FakeSender(created=9)
    code, _ = run(tmp_path, now=at(30), probe=FakeProbe(**DOWN_PROBE), sender=sender, state={STAGING: suspected()})
    assert code == sm.EXIT_FAIL
    assert [m for m, _, _ in sender.calls] == ["GET", "POST"]


def test_a_practice_drill_opens_a_practice_issue_and_leaves_staging_alone(tmp_path, capsys):
    env = {**STAGING_ENV, "PRACTICE_ADDRESS": PRACTICE}
    staging_state = {STAGING: healthy()}
    probe = FakeProbe(**DOWN_PROBE)
    code, path = run(tmp_path, env=env, now=at(1), probe=probe, state=staging_state)
    assert code == sm.EXIT_OK
    assert probe.calls == [(PRACTICE, at(1))]
    sender = FakeSender(created=5)
    code, path = run(tmp_path, env=env, now=at(7), probe=FakeProbe(**DOWN_PROBE), sender=sender)
    assert code == sm.EXIT_FAIL
    assert f"labels={sm.PRACTICE_LABEL}" in sender.calls[0][1]
    assert sender.calls[1][2]["labels"] == [sm.PRACTICE_LABEL]
    loaded = sm.load_state(path)[0]
    assert loaded[STAGING] == healthy()
    assert loaded[PRACTICE].practice
    assert loaded[PRACTICE].issue_number == 5


def test_the_happy_path_with_the_real_probe_against_a_local_server(tmp_path, capsys):
    # target_key insists on https, so the real probe is aimed at a local http server.
    with serve(200, b"ok") as (base, received):
        code, _ = run(tmp_path, probe=lambda target, checked_at: sm.probe(base, checked_at, timeout=2))
    out, _ = lines(capsys)
    assert code == sm.EXIT_OK
    assert len(received) == 1
    assert "decision: nothing" in out


# ------------------------------------------------- read-only by construction
SCRIPT = Path(sm.__file__)
WRITE_TOOLS = ("publish_schedule", "submit_purchase_order")
SIGN_IN_WORDS = ("login", "logout", "sign_in", "signin", "sign_out", "signout")
CREDENTIAL_WORDS = ("secret", "password", "passwd", "credential", "token", "cookie", "api_key", "storage_state")
# The only string allowed to name a credential: the environment variable GitHub sets.
ALLOWED_CREDENTIAL_STRINGS = {"GITHUB_TOKEN"}
WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
# Only these functions talk to GitHub's write endpoints or attach the token.
ISSUE_WRITERS = {"open_outage_issue", "close_outage_issue"}
TOKEN_HOLDER = "github_request"


def _call_name(node):
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _docstring_ids(tree):
    nodes = [tree, *(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef)))]
    return {id(n.body[0].value) for n in nodes if ast.get_docstring(n) is not None}


def _strings_by_function(tree):
    """(enclosing top-level function name or None, string constant) pairs, docstrings skipped."""
    skip = _docstring_ids(tree)
    for node in tree.body:
        owner = node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else None
        for inner in ast.walk(node):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str) and id(inner) not in skip:
                yield owner, inner.value


def read_only_violations(source):
    """Every way ``source`` could sign in, write to the target, hold a
    credential outside the GitHub client or call a gated write tool."""
    tree = ast.parse(source)
    problems = []
    for owner, text in _strings_by_function(tree):
        lowered = text.lower()
        problems += [f"write tool {text!r}" for w in WRITE_TOOLS if w in lowered]
        if text not in ALLOWED_CREDENTIAL_STRINGS:
            problems += [f"credential word in {text!r}" for w in CREDENTIAL_WORDS if w in lowered]
        if text in WRITE_METHODS and owner not in ISSUE_WRITERS:
            problems.append(f"{text} outside the issue writers ({owner})")
        if text == "Authorization" and owner != TOKEN_HOLDER:
            problems.append(f"Authorization header outside {TOKEN_HOLDER} ({owner})")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and any(w in node.id.lower() for w in WRITE_TOOLS):
            problems.append(f"write tool {node.id}")
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if any(word in name.lower() for word in SIGN_IN_WORDS):
                problems.append(f"sign-in call {name}()")
            if name in ("click", "press"):
                problems.append(f"input call {name}()")
    for func in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "probe"):
        for call in (n for n in ast.walk(func) if isinstance(n, ast.Call) and _call_name(n) == "Request"):
            keywords = {k.arg: k.value for k in call.keywords}
            method = keywords.get("method")
            if not (isinstance(method, ast.Constant) and method.value == "GET") or "data" in keywords:
                problems.append("the probe's request is not a plain GET")
    return problems


@pytest.mark.parametrize(
    "snippet",
    [
        pytest.param("TOOL = 'mcp__hsm__publish_schedule'\n", id="publish"),
        pytest.param("def f(c):\n    submit_purchase_order(c)\n", id="submit-po"),
        pytest.param("def f(st):\n    st.login('google')\n", id="login"),
        pytest.param("def f(page):\n    page.click()\n", id="click"),
        pytest.param("HEADER = 'Cookie'\n", id="cookie"),
        pytest.param("NAME = 'API_TOKEN'\n", id="other-token"),
        pytest.param("def probe(t):\n    return Request(t, method='POST')\n", id="probe-post"),
        pytest.param("def probe(t):\n    return Request(t, method='GET', data=b'x')\n", id="probe-body"),
        pytest.param("def find(s):\n    return s('PATCH', '/x')\n", id="patch-elsewhere"),
        pytest.param("def probe(t):\n    return {'Authorization': t}\n", id="auth-in-probe"),
    ],
)
def test_the_scan_catches_each_forbidden_pattern(snippet):
    assert read_only_violations(snippet)


def test_the_scan_allows_the_github_client_its_token_and_writes():
    allowed = (
        "def github_request(token):\n    return {'Authorization': token}\n"
        "def close_outage_issue(s):\n    s('PATCH', '/x')\n"
        "NAME = 'GITHUB_TOKEN'\n"
        "def probe(t):\n    return Request(t, method='GET')\n"
    )
    assert read_only_violations(allowed) == []


def test_the_monitor_is_read_only_towards_the_app_by_construction():
    assert read_only_violations(SCRIPT.read_text()) == []


def test_the_monitor_uses_only_the_standard_library():
    tree = ast.parse(SCRIPT.read_text())
    imported = {alias.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported
