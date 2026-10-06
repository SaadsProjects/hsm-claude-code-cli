"""
Unit tests of the sign-in gate's plain functions (dashboard/auth_gate.py,
unit U3): the pure decision core, the markers module, the gate's evaluation
order, refusal logging, sign-out and the account binding.

None of these needs Streamlit to run a script: state is a plain dict, and
hosted secrets are a plain mapping.
"""

import ast
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hsm_client import HsmApiError, HsmUnavailable
from dashboard import auth_gate, session
from dashboard.auth_gate import (
    ALLOW,
    ALLOWLIST_INVALID,
    GATE_ERROR,
    NOT_LISTED,
    NOT_SIGNED_IN,
    NOT_VERIFIED,
    OK,
    REFUSE_UNAVAILABLE,
    REFUSE_VISITOR,
    AllowlistInvalidError,
    Decision,
    Identity,
    decide,
    parse_allowlist,
)
from mock_hsm.auth import SecretMissingError
from mock_hsm.embedded import BackendNotRunning

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"
ALLOWLIST = ("allowed@example.com", "example.com")


def _who(email="allowed@example.com", verified=True, signed_in=True):
    return Identity(signed_in=signed_in, email=email, email_verified=verified)


# ------------------------------------------------------ parse_allowlist (BR2.2)


def test_parse_allowlist_trims_and_lower_cases_each_entry():
    assert parse_allowlist(["  Allowed@Example.COM ", "b@example.com"]) == ("allowed@example.com", "b@example.com")


@pytest.mark.parametrize(
    "raw",
    [None, "allowed@example.com", [], ["ok@example.com", 3], ["ok@example.com", "   "], {"a": 1}, ("a@b.c",)],
    ids=["missing", "plain-string", "empty", "non-string-entry", "blank-entry", "mapping", "tuple"],
)
def test_parse_allowlist_refuses_anything_but_a_non_empty_list_of_non_blank_strings(raw):
    with pytest.raises(AllowlistInvalidError):
        parse_allowlist(raw)


def test_allowlist_error_message_holds_no_entry():
    with pytest.raises(AllowlistInvalidError) as refused:
        parse_allowlist(["secret-entry@example.com", ""])
    assert "secret-entry" not in str(refused.value)


# --------------------------------------------------------------- decide (BR3.x)


def test_decide_allows_a_verified_listed_email():
    assert decide(_who(), ALLOWLIST) == Decision(ALLOW, OK)


def test_decide_refuses_a_visitor_who_is_not_signed_in():
    assert decide(_who(email=None, verified=None, signed_in=False), ALLOWLIST) == Decision(
        REFUSE_VISITOR, NOT_SIGNED_IN
    )


@pytest.mark.parametrize("email", [None, "", "   "], ids=["none", "empty", "blank"])
def test_decide_treats_a_signed_in_identity_without_email_as_a_gate_error(email):
    assert decide(_who(email=email), ALLOWLIST) == Decision(REFUSE_UNAVAILABLE, GATE_ERROR)


@pytest.mark.parametrize(
    "verified", [False, None, "true", "false", 1], ids=["false", "none", "str-true", "str-false", "one"]
)
def test_decide_counts_only_boolean_true_as_verified(verified):
    assert decide(_who(verified=verified), ALLOWLIST) == Decision(REFUSE_VISITOR, NOT_VERIFIED)


def test_decide_refuses_a_missing_verified_claim():
    who = Identity(signed_in=True, email="allowed@example.com")
    assert decide(who, ALLOWLIST) == Decision(REFUSE_VISITOR, NOT_VERIFIED)


def test_decide_refuses_an_unlisted_email():
    assert decide(_who(email="stranger@example.com"), ALLOWLIST) == Decision(REFUSE_VISITOR, NOT_LISTED)


def test_decide_never_matches_a_domain_entry():
    assert decide(_who(email="a@example.com"), ALLOWLIST) == Decision(REFUSE_VISITOR, NOT_LISTED)


def test_decide_matches_after_trimming_and_lower_casing():
    assert decide(_who(email="  Allowed@Example.COM "), ALLOWLIST) == Decision(ALLOW, OK)


def test_decision_repr_never_shows_the_email():
    who = _who(email="private@example.com")
    assert "private@example.com" not in repr(Decision(ALLOW, OK, identity=who))


# --------------------------------------------------- purity and the seam (S2)


def _functions(path):
    return {n.name: n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.FunctionDef)}


def _st_attributes(node):
    return [
        n.attr
        for n in ast.walk(node)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "st"
    ]


def test_decide_and_parse_allowlist_make_no_streamlit_call():
    functions = _functions(DASHBOARD / "auth_gate.py")
    assert _st_attributes(functions["decide"]) == []
    assert _st_attributes(functions["parse_allowlist"]) == []


def test_only_the_three_seam_functions_touch_the_sign_in_api():
    seam = {"current_identity", "sign_in", "sign_out"}
    offenders = []
    for path in sorted(DASHBOARD.glob("*.py")):
        tree = ast.parse(path.read_text())
        for function in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            if path.name == "auth_gate.py" and function.name in seam:
                continue
            for attr in _st_attributes(function):
                if attr in {"user", "login", "logout"}:
                    offenders.append(f"{path.name}:{function.name}:{attr}")
        top_level = [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        offenders += [
            f"{path.name}:<module>:{a}"
            for n in top_level
            for a in _st_attributes(n)
            if a in {"user", "login", "logout"}
        ]
    assert offenders == []
    functions = _functions(DASHBOARD / "auth_gate.py")
    assert set(_st_attributes(functions["current_identity"])) == {"user"}
    assert _st_attributes(functions["sign_in"]) == ["login"]
    assert _st_attributes(functions["sign_out"]) == ["logout"]


# ------------------------------------------------------------ markers (C6, BR4.7)

MARKER_NAMES = (
    "SIGN_IN_SCREEN",
    "SIGN_IN_BUTTON",
    "REFUSAL_SCREEN",
    "UNAVAILABLE_SCREEN",
    "BACKEND_FAILED_SCREEN",
    "ACCOUNT_SECTION",
    "SIGN_OUT_BUTTON",
    "RESET_BANNER",
    "BUILD_CAPTION",
    "APP_TABS",
)


def test_markers_are_ten_distinct_strings_with_only_a_future_import():
    from dashboard import markers

    values = [getattr(markers, name) for name in MARKER_NAMES]
    assert all(isinstance(v, str) and v for v in values)
    assert len(set(values)) == len(MARKER_NAMES)
    tree = ast.parse((DASHBOARD / "markers.py").read_text())
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert [(n.module, [a.name for a in n.names]) for n in imports] == [("__future__", ["annotations"])]
    assigned = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets}
    assert assigned == set(MARKER_NAMES)


# ------------------------------------------- evaluation order (BR3.6, S3)

SECRET_ENV = "HSM_SIGNING_SECRET"
AUTH_KEYS = ("redirect_uri", "cookie_secret")
GOOGLE_KEYS = ("client_id", "client_secret", "server_metadata_url")


def _hosted():
    return {
        "HSM_ALLOWED_EMAILS": ["allowed@example.com", "example.com"],
        "auth": {
            "redirect_uri": "http://localhost:8501/oauth2callback",
            "cookie_secret": "cookie-secret-placeholder",
            "google": {
                "client_id": "id",
                "client_secret": "secret",
                "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
            },
        },
    }


class _Reader:
    def __init__(self, who=None):
        self.calls = 0
        self.who = who or _who()

    def __call__(self):
        self.calls += 1
        return self.who


def _refused_before_identity(hosted, reason):
    reader = _Reader()
    decision = auth_gate._evaluate(hosted, reader)
    assert decision == Decision(REFUSE_UNAVAILABLE, reason)
    assert reader.calls == 0
    return decision


def test_evaluate_allows_with_valid_settings_and_identity():
    reader = _Reader()
    decision = auth_gate._evaluate(_hosted(), reader)
    assert decision == Decision(ALLOW, OK)
    assert decision.identity == _who() and reader.calls == 1


@pytest.mark.parametrize("value", ["", "too-short"], ids=["missing", "short"])
def test_evaluate_refuses_an_unusable_signing_secret(monkeypatch, value):
    monkeypatch.setenv(SECRET_ENV, value)
    decision = _refused_before_identity(_hosted(), auth_gate.SETTINGS_MISSING)
    assert decision.settings == (SECRET_ENV,)


def test_evaluate_refuses_a_signing_secret_equal_to_the_cookie_secret(monkeypatch):
    hosted = _hosted()
    hosted["auth"]["cookie_secret"] = auth_gate.os.environ[SECRET_ENV]
    decision = _refused_before_identity(hosted, auth_gate.SETTINGS_MISSING)
    assert decision.settings == (SECRET_ENV, "auth.cookie_secret")


@pytest.mark.parametrize("key", AUTH_KEYS + GOOGLE_KEYS)
@pytest.mark.parametrize("bad", ["missing", "", "   ", 42], ids=["missing", "empty", "blank", "not-string"])
def test_evaluate_refuses_each_missing_or_blank_sign_in_key(key, bad):
    hosted = _hosted()
    table = hosted["auth"] if key in AUTH_KEYS else hosted["auth"]["google"]
    if bad == "missing":
        del table[key]
    else:
        table[key] = bad
    decision = _refused_before_identity(hosted, auth_gate.SETTINGS_MISSING)
    assert decision.settings == ((f"auth.{key}",) if key in AUTH_KEYS else (f"auth.google.{key}",))


@pytest.mark.parametrize("section", ["auth", "google"])
def test_evaluate_refuses_a_missing_section(section):
    hosted = _hosted()
    if section == "auth":
        del hosted["auth"]
    else:
        del hosted["auth"]["google"]
    _refused_before_identity(hosted, auth_gate.SETTINGS_MISSING)


@pytest.mark.parametrize(
    "raw", ["missing", [], "a@example.com", ["ok@example.com", ""]], ids=["missing", "empty", "string", "blank"]
)
def test_evaluate_refuses_an_invalid_allowlist(raw):
    hosted = _hosted()
    if raw == "missing":
        del hosted["HSM_ALLOWED_EMAILS"]
    else:
        hosted["HSM_ALLOWED_EMAILS"] = raw
    decision = _refused_before_identity(hosted, ALLOWLIST_INVALID)
    assert decision.settings == ("HSM_ALLOWED_EMAILS",)


def test_evaluate_checks_the_secret_before_the_settings_and_the_allowlist(monkeypatch):
    monkeypatch.setenv(SECRET_ENV, "")
    hosted = _hosted()
    del hosted["auth"]
    hosted["HSM_ALLOWED_EMAILS"] = []
    assert auth_gate._evaluate(hosted, _Reader()).settings == (SECRET_ENV,)


def test_evaluate_checks_the_settings_before_the_allowlist():
    hosted = _hosted()
    del hosted["auth"]["google"]["client_id"]
    hosted["HSM_ALLOWED_EMAILS"] = []
    assert auth_gate._evaluate(hosted, _Reader()).reason == auth_gate.SETTINGS_MISSING


def test_evaluate_passes_the_identity_on_for_a_visitor_refusal():
    who = _who(email="stranger@example.com")
    decision = auth_gate._evaluate(_hosted(), _Reader(who))
    assert decision == Decision(REFUSE_VISITOR, NOT_LISTED) and decision.identity == who


# ---------------------------------------------- refusal logging (BR6.x, S7, D7)

LOGGER = "dashboard.auth_gate"
VISITOR_REASONS = (NOT_VERIFIED, NOT_LISTED)
SYSTEM_REASONS = (auth_gate.SETTINGS_MISSING, ALLOWLIST_INVALID, GATE_ERROR)


def _decision(reason):
    outcome = REFUSE_VISITOR if reason in (*VISITOR_REASONS, NOT_SIGNED_IN) else REFUSE_UNAVAILABLE
    return Decision(outcome, reason, identity=_who(email="private@example.com"))


def _records(caplog):
    return [r for r in caplog.records if r.name == LOGGER]


@pytest.mark.parametrize("reason", VISITOR_REASONS + SYSTEM_REASONS)
def test_each_refusal_reason_is_logged_once_per_session(caplog, reason):
    state = {}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        for _ in range(3):
            auth_gate._log_refusal_once(_decision(reason), state)
    records = _records(caplog)
    assert len(records) == 1
    assert reason in records[0].getMessage()
    assert records[0].levelno == (logging.INFO if reason in VISITOR_REASONS else logging.WARNING)


@pytest.mark.parametrize("reason", [NOT_SIGNED_IN, OK])
def test_not_signed_in_and_allow_are_never_logged(caplog, reason):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        auth_gate._log_refusal_once(Decision(ALLOW if reason == OK else REFUSE_VISITOR, reason), {})
    assert _records(caplog) == []


def test_a_gate_error_line_names_only_the_error_type(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        auth_gate._log_refusal_once(_decision(GATE_ERROR), {}, error_type="ZeroDivisionError")
    message = _records(caplog)[0].getMessage()
    assert "ZeroDivisionError" in message and "private@example.com" not in message


def test_a_cookie_clash_line_names_both_settings_and_neither_value(caplog):
    secret = auth_gate.os.environ[SECRET_ENV]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        auth_gate._log_refusal_once(
            _decision(auth_gate.SETTINGS_MISSING), {}, settings=(SECRET_ENV, "auth.cookie_secret")
        )
    message = _records(caplog)[0].getMessage()
    assert SECRET_ENV in message and "auth.cookie_secret" in message
    assert secret not in message


def test_no_refusal_line_carries_an_email_secret_or_allowlist_entry(caplog):
    secret = auth_gate.os.environ[SECRET_ENV]
    state = {}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        for reason in VISITOR_REASONS + SYSTEM_REASONS:
            auth_gate._log_refusal_once(
                _decision(reason), state, error_type="KeyError", settings=("HSM_ALLOWED_EMAILS",)
            )
    text = "\n".join(r.getMessage() for r in _records(caplog))
    for leaked in ("private@example.com", secret, "allowed@example.com", "cookie-secret-placeholder"):
        assert leaked not in text
    assert len(_records(caplog)) == 5


def test_a_reason_is_logged_again_after_the_marks_are_cleared(caplog):
    state = {}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        auth_gate._log_refusal_once(_decision(NOT_LISTED), state)
        state.pop(auth_gate.REFUSALS_LOGGED)
        auth_gate._log_refusal_once(_decision(NOT_LISTED), state)
    assert len(_records(caplog)) == 2


def test_the_logger_emits_info_without_any_root_configuration(caplog):
    # No caplog.at_level here: the module sets its own logger to INFO (D7).
    assert logging.getLogger(LOGGER).level == logging.INFO
    auth_gate._log_refusal_once(_decision(NOT_VERIFIED), {})
    assert [r.levelno for r in _records(caplog)] == [logging.INFO]


# ------------------------------------------ sign-out and binding (BR5.x, S6, D2, D5)

SESSION_ID = "sess-do-not-log-1234"


def _visitor_state():
    state = {
        session.LOGIN: {"session_id": SESSION_ID, "user_id": "user_rm_midtown", "persona": "RESTAURANT_MANAGER"},
        session.NOTICE: {"level": "info", "message": "hi"},
        "form:add:job_code::title": "x",
        auth_gate.REFUSALS_LOGGED: {NOT_LISTED},
        auth_gate.ACCOUNT_BOUND: "allowed@example.com",
        "unrelated-widget": 1,
    }
    for name, default in session.SCOPED_DEFAULTS.items():
        state[name] = default()
    return state


def _assert_cleared(state):
    leftover = set(state) & (
        {session.LOGIN, session.NOTICE, auth_gate.REFUSALS_LOGGED, auth_gate.ACCOUNT_BOUND}
        | set(session.SCOPED_DEFAULTS)
    )
    assert leftover == set()
    assert not [k for k in state if k.startswith(session.FORM_KEY_PREFIX)]


class _Client:
    def __init__(self, error=None):
        self.error, self.ended = error, []

    def end_session(self, session_id):
        if self.error is not None:
            raise self.error
        self.ended.append(session_id)


def test_end_visitor_session_ends_the_backend_session_and_clears_the_state(monkeypatch):
    client = _Client()
    monkeypatch.setattr(session, "client_for", lambda user_id: client)
    state = _visitor_state()
    auth_gate.end_visitor_session(state)
    assert client.ended == [SESSION_ID]
    _assert_cleared(state)
    assert state["unrelated-widget"] == 1


def test_end_visitor_session_without_a_persona_login_only_clears(monkeypatch):
    monkeypatch.setattr(session, "client_for", _raise_on_call)
    state = _visitor_state()
    del state[session.LOGIN]
    auth_gate.end_visitor_session(state)
    _assert_cleared(state)


def _raise_on_call(*args):
    raise AssertionError("no backend call expected")


@pytest.mark.parametrize(
    "error",
    [
        HsmUnavailable("no answer"),
        HsmApiError(401, "session ended"),
        BackendNotRunning("not running"),
        SecretMissingError("missing"),
        ValueError("unknown user_id user_rm_midtown"),
    ],
    ids=["unavailable", "api-error", "not-running", "secret-missing", "unknown-user"],
)
def test_a_failing_backend_end_still_clears_and_is_logged_without_the_session_id(monkeypatch, caplog, error):
    monkeypatch.setattr(session, "client_for", lambda user_id: _Client(error))
    state = _visitor_state()
    with caplog.at_level(logging.INFO, logger=LOGGER):
        auth_gate.end_visitor_session(state)
    _assert_cleared(state)
    assert type(error).__name__ in caplog.text
    assert SESSION_ID not in caplog.text and "user_rm_midtown" not in caplog.text


def test_an_unexpected_error_still_clears_the_state_and_is_re_raised(monkeypatch):
    monkeypatch.setattr(session, "client_for", lambda user_id: _Client(ZeroDivisionError("boom")))
    state = _visitor_state()
    with pytest.raises(ZeroDivisionError, match="boom"):
        auth_gate.end_visitor_session(state)
    _assert_cleared(state)


def test_sign_out_still_signs_out_of_google_when_ending_the_session_fails_unexpectedly(monkeypatch):
    # Otherwise the visitor stays signed in to Google and the next rerun lets
    # them straight back in (commit review finding 3).
    monkeypatch.setattr(session, "client_for", lambda user_id: _Client(ZeroDivisionError("boom")))
    calls = []
    monkeypatch.setattr(auth_gate, "sign_out", lambda: calls.append("sign_out"))
    state = _visitor_state()
    with pytest.raises(ZeroDivisionError, match="boom"):
        auth_gate._sign_out_clicked(state)
    assert calls == ["sign_out"]
    _assert_cleared(state)


def test_the_first_allow_only_binds_the_account(monkeypatch):
    monkeypatch.setattr(session, "client_for", _raise_on_call)
    state = _visitor_state()
    del state[auth_gate.ACCOUNT_BOUND]
    auth_gate._bind_account(_who(email="  Allowed@Example.com "), state)
    assert state[auth_gate.ACCOUNT_BOUND] == "allowed@example.com"
    assert state[session.LOGIN]["session_id"] == SESSION_ID


def test_a_case_change_is_the_same_account(monkeypatch):
    monkeypatch.setattr(session, "client_for", _raise_on_call)
    state = _visitor_state()
    auth_gate._bind_account(_who(email="ALLOWED@example.com"), state)
    assert state[session.LOGIN]["session_id"] == SESSION_ID


def test_a_different_allowed_account_clears_the_persona_then_binds(monkeypatch):
    client = _Client()
    monkeypatch.setattr(session, "client_for", lambda user_id: client)
    state = _visitor_state()
    auth_gate._bind_account(_who(email="other@example.com"), state)
    assert client.ended == [SESSION_ID]
    assert session.LOGIN not in state
    assert state[auth_gate.ACCOUNT_BOUND] == "other@example.com"
