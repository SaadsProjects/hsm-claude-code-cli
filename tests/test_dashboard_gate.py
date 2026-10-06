"""
The sign-in gate on the running dashboard (unit U3): Screens 1, 2 and 5, the
signed-in frame, sign-out end to end, and the gate's no-I/O and no-waiting
rules.

Every app here is built with tests/gate_app.py, which patches only the
identity seam. The real gate, the real secrets bridge and (when allowed) the
real embedded backend on an ephemeral port run underneath.
"""

import ast
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException, StopException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate_app import ALLOWED_EMAIL, DUMMY_AUTH, SIGNED_OUT, default_secrets, gate_app, identity

from dashboard import auth_gate, markers
from mock_hsm import embedded

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP = str(PROJECT_ROOT / "dashboard" / "app.py")
TITLE = "HSM labor & inventory"
SCREEN_1 = ["Access to this demo is by invitation."]
SCREEN_2 = ["This account doesn't have access."]
SCREEN_5 = ["Sign-in isn't available right now.", "Reload the page or try again later."]
SECRET_ENV = "HSM_SIGNING_SECRET"
STRANGER = "stranger@example.com"


@pytest.fixture(autouse=True)
def holder():
    embedded.reset_for_tests()
    st.cache_data.clear()
    yield
    embedded.reset_for_tests()


@pytest.fixture
def start_spy(monkeypatch):
    """Record any backend start; a refused visitor must never cause one."""
    calls = []

    def spy(port=0):
        calls.append(port)
        return embedded.BackendHandle(
            address="http://127.0.0.1:1",
            host="127.0.0.1",
            port=1,
            started_at=datetime.now(timezone.utc),
            status="failed",
            failure_cause="spy",
        )

    monkeypatch.setattr(embedded, "start", spy)
    return calls


def _run(at):
    at.run()
    assert not at.exception, at.exception
    return at


def _click(at, key):
    at.button(key=key).click().run()
    assert not at.exception, at.exception
    return at


def _block_keys(node):
    keys = set()
    key = getattr(node, "key", None)
    if type(node).__name__ == "Block" and key:
        keys.add(key)
    for child in getattr(node, "children", {}).values():
        keys |= _block_keys(child)
    return keys


def _screen_text(at):
    parts = []
    for group in (at.title, at.markdown, at.text, at.caption, at.error, at.warning, at.info, at.success, at.subheader):
        parts += [str(el.value) for el in group]
    parts += [b.label for b in at.button]
    return "\n".join(parts)


def _assert_gate_screen_only(at, marker, buttons):
    assert [t.value for t in at.title] == [TITLE]
    assert len(at.tabs) == 0 and len(at.selectbox) == 0 and len(at.radio) == 0
    assert len(at.sidebar.children) == 0
    assert {b.key for b in at.button} == buttons
    gate_markers = {markers.SIGN_IN_SCREEN, markers.REFUSAL_SCREEN, markers.UNAVAILABLE_SCREEN}
    assert _block_keys(at._tree) & gate_markers == {marker}


def _cookie_clash():
    secrets = default_secrets()
    secrets["auth"]["cookie_secret"] = os.environ[SECRET_ENV]
    return secrets


def _no_allowlist():
    secrets = default_secrets()
    secrets["HSM_ALLOWED_EMAILS"] = []
    return secrets


def _raise(error):
    def raiser(*args, **kwargs):
        raise error

    return raiser


# ------------------------------------------------------------- Screen 1 (US4.1)


def test_signed_out_shows_only_screen_1_and_sign_in_calls_the_seam(monkeypatch, start_spy):
    at = _run(gate_app(APP, monkeypatch, identity=SIGNED_OUT))
    _assert_gate_screen_only(at, markers.SIGN_IN_SCREEN, {markers.SIGN_IN_BUTTON})
    assert [m.value for m in at.markdown] == SCREEN_1
    assert at.button(key=markers.SIGN_IN_BUTTON).label == "Sign in with Google"
    _click(at, markers.SIGN_IN_BUTTON)
    assert at.seam.calls == ["sign_in"]
    assert start_spy == []


# ------------------------------------------------------------- Screen 2 (US4.3)


@pytest.mark.parametrize(
    "who",
    [identity(STRANGER), identity(ALLOWED_EMAIL, verified=False), identity(ALLOWED_EMAIL, verified="true")],
    ids=["not-listed", "not-verified", "verified-as-string"],
)
def test_a_refused_visitor_sees_screen_2_with_the_email_and_sign_out(monkeypatch, start_spy, who):
    at = _run(gate_app(APP, monkeypatch, identity=who))
    _assert_gate_screen_only(at, markers.REFUSAL_SCREEN, {markers.SIGN_OUT_BUTTON})
    assert [m.value for m in at.markdown] == SCREEN_2
    assert [t.value for t in at.text] == [f"Signed in as: {who.email}"]
    assert at.button(key=markers.SIGN_OUT_BUTTON).label == "Sign out"
    assert start_spy == []


@pytest.mark.parametrize("email", ["<b>x</b>@example.com", "*a*@example.com"])
def test_a_markup_email_is_shown_as_the_literal_string(monkeypatch, email):
    at = _run(gate_app(APP, monkeypatch, identity=identity(email)))
    assert [t.value for t in at.text] == [f"Signed in as: {email}"]
    assert all(email not in m.value for m in at.markdown)


def test_sign_out_from_screen_2_returns_to_screen_1(monkeypatch, start_spy):
    at = _run(gate_app(APP, monkeypatch, identity=identity(STRANGER)))
    _click(at, markers.SIGN_OUT_BUTTON)
    assert at.seam.calls == ["sign_out"]
    _assert_gate_screen_only(at, markers.SIGN_IN_SCREEN, {markers.SIGN_IN_BUTTON})
    assert start_spy == []


# ------------------------------------------------------------- Screen 5 (US4.4)

SYSTEM_FAILURES = {
    "settings-missing": {"secrets": {}},
    "allowlist-invalid": {"secrets": "no-allowlist"},
    "cookie-clash": {"secrets": "cookie-clash"},
    "short-secret": {"env": "too-short"},
    "missing-secret": {"env": ""},
    "decide-raises": {"decide": RuntimeError("boom")},
}


def _system_failure_app(monkeypatch, name, who=None):
    failure = SYSTEM_FAILURES[name]
    secrets = failure.get("secrets")
    if isinstance(secrets, str):
        secrets = {"no-allowlist": _no_allowlist, "cookie-clash": _cookie_clash}[secrets]()
    if "env" in failure:
        monkeypatch.setenv(SECRET_ENV, failure["env"])
    if "decide" in failure:
        monkeypatch.setattr(auth_gate, "decide", _raise(failure["decide"]))
    return gate_app(APP, monkeypatch, identity=who, secrets=secrets)


@pytest.mark.parametrize("name", SYSTEM_FAILURES)
def test_a_system_failure_shows_screen_5_with_sign_out_when_signed_in(monkeypatch, start_spy, name):
    at = _run(_system_failure_app(monkeypatch, name))
    _assert_gate_screen_only(at, markers.UNAVAILABLE_SCREEN, {markers.SIGN_OUT_BUTTON})
    assert [m.value for m in at.markdown] == SCREEN_5
    assert len(at.text) == 0
    assert start_spy == []


@pytest.mark.parametrize("name", ["settings-missing", "cookie-clash", "allowlist-invalid"])
def test_screen_5_shows_no_sign_out_to_a_signed_out_visitor(monkeypatch, start_spy, name):
    at = _run(_system_failure_app(monkeypatch, name, who=SIGNED_OUT))
    _assert_gate_screen_only(at, markers.UNAVAILABLE_SCREEN, set())
    assert [m.value for m in at.markdown] == SCREEN_5


def test_a_failing_identity_read_shows_screen_5_without_sign_out(monkeypatch, start_spy):
    at = _run(gate_app(APP, monkeypatch, identity=_raise(RuntimeError("provider down"))))
    _assert_gate_screen_only(at, markers.UNAVAILABLE_SCREEN, set())
    assert [m.value for m in at.markdown] == SCREEN_5
    assert start_spy == []


def test_a_signed_in_identity_without_email_shows_screen_5_with_sign_out(monkeypatch, start_spy):
    at = _run(gate_app(APP, monkeypatch, identity=identity(email=None)))
    _assert_gate_screen_only(at, markers.UNAVAILABLE_SCREEN, {markers.SIGN_OUT_BUTTON})


@pytest.mark.parametrize("name", SYSTEM_FAILURES)
def test_screen_5_names_no_setting_secret_or_allowlist_entry(monkeypatch, name):
    at = _run(_system_failure_app(monkeypatch, name))
    text = _screen_text(at)
    for leaked in (
        SECRET_ENV,
        "HSM_ALLOWED_EMAILS",
        "cookie_secret",
        "client_id",
        ALLOWED_EMAIL,
        DUMMY_AUTH["cookie_secret"],
        os.environ[SECRET_ENV] or "unset",
        "RuntimeError",
    ):
        assert leaked not in text


class _BreaksOnDisplay:
    """An email that decides normally but fails when Screen 2 draws it."""

    def strip(self):
        return STRANGER

    def __radd__(self, other):
        raise RuntimeError("drawing failed")


def test_an_error_while_drawing_screen_2_leaves_only_screen_5(monkeypatch, start_spy):
    at = _run(gate_app(APP, monkeypatch, identity=identity(_BreaksOnDisplay())))
    _assert_gate_screen_only(at, markers.UNAVAILABLE_SCREEN, {markers.SIGN_OUT_BUTTON})
    assert [m.value for m in at.markdown] == SCREEN_5
    assert start_spy == []


def test_an_error_after_screen_2_drew_sign_out_still_lands_on_screen_5(monkeypatch, start_spy):
    # Screen 2's Sign out button is already registered when the click's
    # unexpected error reaches the gate's boundary; Screen 5 must not register
    # the same widget key again (commit review finding 2).
    at = _run(gate_app(APP, monkeypatch, identity=identity(STRANGER)))
    at.seam.sign_out_error = RuntimeError("provider down")  # the visitor stays signed in
    monkeypatch.setattr(auth_gate, "end_visitor_session", _raise(RuntimeError("unexpected")))
    _click(at, markers.SIGN_OUT_BUTTON)
    assert [m.value for m in at.markdown] == SCREEN_5
    assert _block_keys(at._tree) & {markers.REFUSAL_SCREEN, markers.UNAVAILABLE_SCREEN} == {markers.UNAVAILABLE_SCREEN}
    assert start_spy == []


def test_streamlits_control_exceptions_are_not_exceptions():
    # The gate's one boundary catches Exception; st.stop() and st.rerun()
    # must pass through it (security-design S3).
    assert not issubclass(StopException, Exception)
    assert not issubclass(RerunException, Exception)


def test_a_gate_error_is_logged_with_its_type_only(monkeypatch, caplog):
    at = _system_failure_app(monkeypatch, "decide-raises")
    at.run()
    lines = [r.getMessage() for r in caplog.records if r.name == "dashboard.auth_gate"]
    assert lines == ["sign-in refused: reason=gate_error error=RuntimeError"]
    assert "boom" not in caplog.text and ALLOWED_EMAIL not in caplog.text


# ------------------------------------------------- signed-in frame (US4.6, D11)

RM = "user_rm_midtown"
BACKEND_FAILED = "The demo backend didn't start. Reload the page or try again later."


def _persona_login(at, user_id=RM):
    at.selectbox(key="session-persona").set_value(user_id)
    return _click(at, "session-login")


def _account_block(at):
    first = next(iter(at.sidebar.children.values()))
    assert type(first).__name__ == "Block" and first.key == markers.ACCOUNT_SECTION
    return first


def test_the_sidebar_starts_with_the_account_section_then_the_demo_persona(monkeypatch):
    at = _run(gate_app(APP, monkeypatch))
    account = _account_block(at)
    assert [h.value for h in account.subheader] == ["Account"]
    assert [t.value for t in account.text] == [ALLOWED_EMAIL]
    assert [b.key for b in account.button] == [markers.SIGN_OUT_BUTTON]
    after = list(at.sidebar.children.values())[1:]
    kinds = [type(n).__name__ for n in after]
    assert kinds[:2] == ["Divider", "Subheader"], kinds
    assert after[1].value == "Demo persona"
    assert at.sidebar.selectbox(key="session-persona") is not None


def test_the_persona_caption_reads_acting_as(monkeypatch):
    from dashboard.safe_text import escape_md
    from mock_hsm.db import USERS

    at = _persona_login(_run(gate_app(APP, monkeypatch)))
    captions = [c.value for c in at.sidebar.caption]
    persona = at.session_state["login"]["persona"]
    assert f"Acting as {escape_md(USERS[RM]['name'])} ({escape_md(persona)})" in captions
    assert not any(c.startswith("Logged in as") for c in captions)
    assert len(at.tabs) == 5


def test_screen_4_shows_the_account_section_and_no_persona_section(monkeypatch, start_spy):
    at = _run(gate_app(APP, monkeypatch))
    assert start_spy == [0]
    account = _account_block(at)
    assert [t.value for t in account.text] == [ALLOWED_EMAIL]
    assert [m.value for m in at.markdown] == [BACKEND_FAILED]
    assert len(at.selectbox) == 0 and len(at.tabs) == 0
    assert {b.key for b in at.button} == {markers.SIGN_OUT_BUTTON}
    assert "Demo persona" not in [h.value for h in at.subheader]


# ------------------------------------------------ sign-out end to end (BR5.x)


def _state_keys(at):
    return set(at.session_state.keys())


def test_sign_out_after_a_persona_login_ends_everything(monkeypatch):
    from dashboard import session

    at = _persona_login(_run(gate_app(APP, monkeypatch)))
    session_id = at.session_state["login"]["session_id"]
    _click(at, markers.SIGN_OUT_BUTTON)
    assert at.seam.calls == ["sign_out"]
    keys = _state_keys(at)
    owned = {
        session.LOGIN,
        session.NOTICE,
        auth_gate.REFUSALS_LOGGED,
        auth_gate.ACCOUNT_BOUND,
        *session.SCOPED_DEFAULTS,
    }
    assert keys & owned == set()
    assert not [k for k in keys if k.startswith(session.FORM_KEY_PREFIX)]
    # The fake provider signed the visitor out, so this rerun is Screen 1.
    _assert_gate_screen_only(at, markers.SIGN_IN_SCREEN, {markers.SIGN_IN_BUTTON})
    assert session.client_for(RM).session_status(session_id)["active"] is False


def test_a_failing_provider_sign_out_is_a_gate_error_and_the_state_stays_cleared(monkeypatch, caplog):
    at = _persona_login(_run(gate_app(APP, monkeypatch)))
    at.seam.sign_out_error = RuntimeError("provider settings broken")
    _click(at, markers.SIGN_OUT_BUTTON)
    assert "login" not in _state_keys(at) or at.session_state["login"] is None
    lines = [r.getMessage() for r in caplog.records if r.name == "dashboard.auth_gate"]
    assert "sign-out failed: reason=gate_error error=RuntimeError" in lines
    assert "provider settings broken" not in caplog.text


def test_a_different_allowed_account_starts_with_no_persona(monkeypatch):
    secrets = default_secrets()
    secrets["HSM_ALLOWED_EMAILS"] = [ALLOWED_EMAIL, "other@example.com"]
    at = _persona_login(_run(gate_app(APP, monkeypatch, secrets=secrets)))
    at.seam.identity = identity("ALLOWED@Example.com")
    _run(at)
    assert at.session_state["login"] is not None and len(at.tabs) == 5
    at.seam.identity = identity("other@example.com")
    _run(at)
    assert "login" not in _state_keys(at) or at.session_state["login"] is None
    assert len(at.tabs) == 0
    assert [t.value for t in _account_block(at).text] == ["other@example.com"]


# ---------------------------------------- no I/O, no waiting, timing (P1-P3)


def test_the_gate_opens_no_connection_on_allowed_or_refused_runs(monkeypatch, start_spy):
    attempts = []

    def refuse(*args, **kwargs):
        attempts.append(args[1:2] or kwargs)
        raise OSError("the gate must not connect")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    # One at a time: each gate_app call re-patches the module-level seam.
    runs = [
        {},  # allowed; the backend start is the stub
        {"identity": SIGNED_OUT},
        {"identity": identity(STRANGER)},
        {"secrets": {}},
    ]
    for options in runs:
        _run(gate_app(APP, monkeypatch, **options))
    assert attempts == []
    assert start_spy == [0]


def _gate_sources():
    return [PROJECT_ROOT / "dashboard" / name for name in ("auth_gate.py", "secrets_bridge.py")]


def test_the_gate_never_waits_or_retries():
    offenders = []
    for path in _gate_sources():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.While):
                offenders.append(f"{path.name}:{node.lineno}:while")
            if isinstance(node, ast.For) and any(isinstance(n, ast.Try) for n in ast.walk(node)):
                offenders.append(f"{path.name}:{node.lineno}:for-with-try")
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name == "sleep":
                    offenders.append(f"{path.name}:{node.lineno}:sleep")
    assert offenders == []


@pytest.mark.perf
def test_gate_p95_is_under_50_ms_with_a_50_entry_allowlist(monkeypatch, start_spy):
    secrets = default_secrets()
    secrets["HSM_ALLOWED_EMAILS"] = [f"user{i}@example.com" for i in range(49)] + [ALLOWED_EMAIL]
    timings, real_gate = [], auth_gate.gate

    def timed_gate(*args, **kwargs):
        started = time.perf_counter()
        try:
            return real_gate(*args, **kwargs)
        finally:
            timings.append(time.perf_counter() - started)

    monkeypatch.setattr(auth_gate, "gate", timed_gate)
    at = gate_app(APP, monkeypatch, secrets=secrets)
    for _ in range(50):
        _run(at)
    assert len(timings) == 50
    p95 = statistics.quantiles(timings, n=20)[-1]
    assert p95 <= 0.050, f"gate p95 {p95 * 1000:.1f} ms"


# ------------------------------------------- secrets example (AC10.1.3, D9)


EXAMPLE = PROJECT_ROOT / ".streamlit" / "secrets.toml.example"
DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10, as in test_dashboard_units.py
    import tomli as tomllib


def _placeholder(value):
    return value == DISCOVERY_URL or (value.startswith("<") and value.endswith(">"))


def test_the_secrets_example_sets_no_signing_secret_line():
    # A line scan, so this also runs on Python 3.10 (no tomllib).
    lines = EXAMPLE.read_text().splitlines()
    assert not [line for line in lines if re.match(r"\s*HSM_SIGNING_SECRET\s*=", line)]
    assert any(line.lstrip().startswith("#") and "HSM_SIGNING_SECRET" in line for line in lines)


def test_the_secrets_example_has_every_key_with_placeholders_only():
    example = tomllib.loads(EXAMPLE.read_text())
    assert SECRET_ENV not in example
    assert set(example) == {"HSM_ALLOWED_EMAILS", "auth"}
    assert set(example["auth"]) == {"redirect_uri", "cookie_secret", "google"}
    assert set(example["auth"]["google"]) == {"client_id", "client_secret", "server_metadata_url"}
    values = [example["auth"]["redirect_uri"], example["auth"]["cookie_secret"], *example["auth"]["google"].values()]
    values += example["HSM_ALLOWED_EMAILS"]
    assert all(isinstance(v, str) and _placeholder(v) for v in values), values


def test_a_copy_of_the_example_reaches_screen_1(monkeypatch, start_spy):
    at = _run(gate_app(APP, monkeypatch, identity=SIGNED_OUT, secrets=tomllib.loads(EXAMPLE.read_text())))
    _assert_gate_screen_only(at, markers.SIGN_IN_SCREEN, {markers.SIGN_IN_BUTTON})


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_gitignore_ignores_the_real_secrets_file_but_not_the_example():
    def ignored(path):
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", path], cwd=PROJECT_ROOT, check=False, capture_output=True
        )
        return result.returncode == 0

    assert ignored(".streamlit/secrets.toml")
    assert not ignored(".streamlit/secrets.toml.example")
