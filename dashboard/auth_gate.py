"""
The sign-in gate in front of the whole dashboard (unit U3, contract C4).

Every rerun decides from scratch whether this browser session may see the
dashboard: nothing about access is cached, so an allowlist or settings change
takes effect on the next interaction. Only a signed-in visitor whose identity
provider reports the email as verified (the boolean ``True``) and whose
trimmed, lower-cased email exactly matches an allowlist entry is let in.

``decide`` and ``parse_allowlist`` are pure, so the access rules are tested
without Streamlit. The identity seam (``current_identity``, ``sign_in``,
``sign_out``) is the only code that touches Streamlit's sign-in API, and it
holds nothing else, so tests replace just those three functions.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

import streamlit as st

from agents.hsm_client import HsmApiError
from dashboard import markers, secrets_bridge, session
from dashboard.secrets_bridge import cookie_secret_conflict
from mock_hsm.auth import SECRET_ENV, SecretMissingError, require_secret
from mock_hsm.embedded import BackendNotRunning

ALLOW, REFUSE_VISITOR, REFUSE_UNAVAILABLE = "allow", "refuse_visitor", "refuse_unavailable"
OK = "ok"
NOT_SIGNED_IN, NOT_VERIFIED, NOT_LISTED = "not_signed_in", "not_verified", "not_listed"
SETTINGS_MISSING, ALLOWLIST_INVALID, GATE_ERROR = "settings_missing", "allowlist_invalid", "gate_error"
PROVIDER = "google"
ALLOWLIST_KEY = "HSM_ALLOWED_EMAILS"
# Fixed screen copy (refined mockups, Screens 1, 2 and 5).
SIGN_IN_TEXT = "Access to this demo is by invitation."
SIGN_IN_LABEL = "Sign in with Google"
REFUSED_TEXT = "This account doesn't have access."
SIGNED_IN_AS = "Signed in as: "
UNAVAILABLE_TEXT = "Sign-in isn't available right now."
RELOAD_TEXT = "Reload the page or try again later."
SIGN_OUT_LABEL = "Sign out"
ACCOUNT_HEADING = "Account"

# Session-state keys of this unit: the refusal reasons already logged, and the
# normalised email of the account this browser session's state belongs to
# (never shown or logged).
REFUSALS_LOGGED = "gate-refusals-logged"
ACCOUNT_BOUND = "gate-account"
# Ending the persona's backend session at sign-out is best effort: these are
# the failures it may meet (HsmApiError covers HsmUnavailable; ValueError is
# mint_token's unknown user). Anything else is re-raised after the clearing.
_BACKEND_END_ERRORS = (BackendNotRunning, HsmApiError, SecretMissingError, KeyError, ValueError)
_INFO_REASONS = frozenset({NOT_VERIFIED, NOT_LISTED})
_LOGGED_REASONS = _INFO_REASONS | {SETTINGS_MISSING, ALLOWLIST_INVALID, GATE_ERROR}

log = logging.getLogger(__name__)
# Visitor refusals are INFO; without this the root default (WARNING) would
# drop them (infrastructure review R-01, D7).
log.setLevel(logging.INFO)

# The five C7 sign-in keys st.login needs, as (table path, key).
AUTH_KEYS = (
    (("auth",), "redirect_uri"),
    (("auth",), "cookie_secret"),
    (("auth", "google"), "client_id"),
    (("auth", "google"), "client_secret"),
    (("auth", "google"), "server_metadata_url"),
)


@dataclass(frozen=True)
class Identity:
    """What the identity provider reports. ``email_verified`` is the raw
    provider value; only the boolean ``True`` counts. The email is kept out
    of ``repr`` so it can't reach a log through one."""

    signed_in: bool
    email: str | None = field(default=None, repr=False)
    email_verified: object = None


@dataclass(frozen=True)
class Decision:
    """One rerun's answer. ``identity`` carries the visitor the decision was
    made on, so the screens can show the email; ``settings`` names (never the
    values of) the settings behind a ``settings_missing`` or
    ``allowlist_invalid`` refusal, for the log. Neither takes part in
    equality."""

    outcome: str
    reason: str
    identity: Identity | None = field(default=None, compare=False, repr=False)
    settings: tuple[str, ...] = field(default=(), compare=False)


class AllowlistInvalidError(ValueError):
    """The allowlist is not a non-empty list of non-blank strings. The message
    never quotes an entry."""


def parse_allowlist(raw) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise AllowlistInvalidError("HSM_ALLOWED_EMAILS must be a non-empty list of email addresses")
    entries = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            raise AllowlistInvalidError("every HSM_ALLOWED_EMAILS entry must be a non-blank string")
        entries.append(entry.strip().lower())
    return tuple(entries)


def decide(identity: Identity, allowlist: tuple[str, ...]) -> Decision:
    if not identity.signed_in:
        return Decision(REFUSE_VISITOR, NOT_SIGNED_IN)
    email = (identity.email or "").strip().lower()
    if not email:
        # The provider signed someone in without an address: not their fault.
        return Decision(REFUSE_UNAVAILABLE, GATE_ERROR)
    # An identity check, so "true", 1 and a missing claim all refuse.
    if identity.email_verified is not True:
        return Decision(REFUSE_VISITOR, NOT_VERIFIED)
    # Exact match only: an entry such as "example.com" is never a domain rule.
    if email not in allowlist:
        return Decision(REFUSE_VISITOR, NOT_LISTED)
    return Decision(ALLOW, OK)


# ---------------------------------------------------------------- evaluation
def _table(hosted, path):
    table = hosted
    for name in path:
        table = table.get(name) if isinstance(table, Mapping) else None
    return table if isinstance(table, Mapping) else {}


def _missing_settings(hosted) -> tuple[str, ...]:
    missing = []
    for path, key in AUTH_KEYS:
        value = _table(hosted, path).get(key)
        if not isinstance(value, str) or not value.strip():
            missing.append(".".join((*path, key)))
    return tuple(missing)


def _evaluate(hosted, identity_reader) -> Decision:
    """W1 steps 2-6 in their fixed order (BR3.6): the signing secret, the
    sign-in settings, the allowlist, and only then the identity, so a broken
    configuration never reaches the identity provider."""
    try:
        require_secret()
    except SecretMissingError:
        return Decision(REFUSE_UNAVAILABLE, SETTINGS_MISSING, settings=(SECRET_ENV,))
    if cookie_secret_conflict(os.environ.get(SECRET_ENV), _table(hosted, ("auth",)).get("cookie_secret")):
        return Decision(REFUSE_UNAVAILABLE, SETTINGS_MISSING, settings=(SECRET_ENV, "auth.cookie_secret"))
    missing = _missing_settings(hosted)
    if missing:
        return Decision(REFUSE_UNAVAILABLE, SETTINGS_MISSING, settings=missing)
    try:
        allowlist = parse_allowlist(hosted.get(ALLOWLIST_KEY))
    except AllowlistInvalidError:
        return Decision(REFUSE_UNAVAILABLE, ALLOWLIST_INVALID, settings=(ALLOWLIST_KEY,))
    identity = identity_reader()
    decision = decide(identity, allowlist)
    return Decision(decision.outcome, decision.reason, identity=identity)


# ------------------------------------------------------------------- logging
def _log_refusal_once(decision, state, error_type=None, settings=()) -> None:
    """One line per refusal reason per browser session (BR6.2), built only
    from constants, the error type and setting names: never an email, a
    secret, a setting value or an allowlist entry (BR6.1, BR6.3)."""
    if decision.reason not in _LOGGED_REASONS:
        return
    logged = state.setdefault(REFUSALS_LOGGED, set())
    if decision.reason in logged:
        return
    logged.add(decision.reason)
    message = f"sign-in refused: reason={decision.reason}"
    if error_type:
        message += f" error={error_type}"
    if settings:
        message += " settings=" + ",".join(settings)
    log.log(logging.INFO if decision.reason in _INFO_REASONS else logging.WARNING, message)


# --------------------------------------------------------- visitor session
def _state(state):
    return st.session_state if state is None else state


def _clear_visitor_state(state) -> None:
    owned = {session.LOGIN, session.NOTICE, REFUSALS_LOGGED, ACCOUNT_BOUND, *session.SCOPED_DEFAULTS}
    for key in list(state.keys()):
        if key in owned or (isinstance(key, str) and key.startswith(session.FORM_KEY_PREFIX)):
            del state[key]


def end_visitor_session(state=None) -> None:
    """Sign-out's own part, outside the seam (BR5.1): end the persona's
    backend session, best effort, then clear every dashboard key of this
    browser session. It doesn't reuse the persona Log out action, which
    leaves a "You logged out." notice behind."""
    state = _state(state)
    login = session.login(state)
    try:
        if login is not None:
            session.client_for(login["user_id"]).end_session(login["session_id"])
    except _BACKEND_END_ERRORS as exc:
        log.warning("backend session end failed at sign-out: %s", type(exc).__name__)
    finally:
        _clear_visitor_state(state)


def _bind_account(identity, state) -> None:
    """A persona login belongs to the account that opened it: a different
    allowed account starts with none (BR5.2), even after a session that
    expired without Sign out."""
    email = (identity.email or "").strip().lower()
    bound = state.get(ACCOUNT_BOUND)
    if bound is not None and bound != email:
        end_visitor_session(state)
    state[ACCOUNT_BOUND] = email


# ------------------------------------------------------------------- screens


def _sign_out_button(state, drawn=None) -> None:
    # Widget keys are registered per run, not per placeholder: once Screen 2
    # has drawn Sign out, a Screen 5 drawn over it after an error must not
    # register the key again, or Streamlit raises instead of showing Screen 5.
    # The reload line stays its way out (BR4.3).
    if drawn is not None:
        if markers.SIGN_OUT_BUTTON in drawn:
            return
        drawn.add(markers.SIGN_OUT_BUTTON)
    if st.button(SIGN_OUT_LABEL, key=markers.SIGN_OUT_BUTTON):
        _sign_out_clicked(state)


def _sign_out_clicked(state) -> None:
    try:
        end_visitor_session(state)
    finally:
        # Even when ending the session fails unexpectedly, the visitor is
        # signed out of Google, or the next rerun would let them straight back in.
        try:
            sign_out()
        except Exception as exc:  # noqa: BLE001 -- the state is already cleared; the next rerun shows Screen 1 or 5
            # Logged directly, not through the refusal marks, so the cleared state stays empty.
            log.warning("sign-out failed: reason=%s error=%s", GATE_ERROR, type(exc).__name__)
    st.rerun()


def _render_sign_in(placeholder) -> None:
    with placeholder.container(key=markers.SIGN_IN_SCREEN):
        st.markdown(SIGN_IN_TEXT)
        if st.button(SIGN_IN_LABEL, key=markers.SIGN_IN_BUTTON):
            sign_in()


def _render_refusal(placeholder, identity, state, drawn) -> None:
    with placeholder.container(key=markers.REFUSAL_SCREEN):
        st.markdown(REFUSED_TEXT)
        # st.text never interprets Markdown or HTML, so the email shows as typed (D3).
        st.text(SIGNED_IN_AS + identity.email)
        _sign_out_button(state, drawn)


def _render_unavailable(placeholder, state, drawn) -> None:
    """Screen 5. The identity is read here in its own guarded call, on every
    path, so a signed-in visitor keeps Sign out as a way out (BR4.3)."""
    with placeholder.container(key=markers.UNAVAILABLE_SCREEN):
        st.markdown(UNAVAILABLE_TEXT)
        st.markdown(RELOAD_TEXT)
        try:
            signed_in = current_identity().signed_in
        except Exception as exc:  # noqa: BLE001 -- no Sign out then; the reload line stays the way out
            _log_refusal_once(Decision(REFUSE_UNAVAILABLE, GATE_ERROR), state, error_type=type(exc).__name__)
            signed_in = False
        if signed_in:
            _sign_out_button(state, drawn)


def _render_screen(placeholder, decision, state, drawn) -> None:
    if decision.reason == NOT_SIGNED_IN:
        _render_sign_in(placeholder)
    elif decision.outcome == REFUSE_VISITOR:
        _render_refusal(placeholder, decision.identity, state, drawn)
    else:
        _render_unavailable(placeholder, state, drawn)


def render_account_section(identity, state=None) -> None:
    """The sidebar's first block on Screens 3 and 4 (BR4.6): the account the
    visitor signed in with, as literal text, and Sign out."""
    with st.container(key=markers.ACCOUNT_SECTION):
        st.subheader(ACCOUNT_HEADING)
        st.text(identity.email)
        _sign_out_button(_state(state))


def gate(state=None) -> Decision:
    """W1 steps 1-8 on every rerun. Renders Screen 1, 2 or 5 for a refusal
    and returns the decision; the caller renders nothing else unless the
    outcome is ``allow`` (C4 caller rule). Every gate screen is drawn into one
    placeholder, so Screen 5 replaces anything a failure left half-drawn."""
    state = _state(state)
    placeholder = st.empty()
    drawn = set()  # widget keys this run has registered on a gate screen
    try:
        hosted = secrets_bridge.read_hosted_secrets()
        secrets_bridge.bridge_signing_secret(hosted)
        decision = _evaluate(hosted, current_identity)
        _log_refusal_once(decision, state, settings=decision.settings)
        if decision.outcome == ALLOW:
            _bind_account(decision.identity, state)
        else:
            _render_screen(placeholder, decision, state, drawn)
        return decision
    except Exception as exc:  # noqa: BLE001 -- any gate failure must become Screen 5, never the persona picker
        decision = Decision(REFUSE_UNAVAILABLE, GATE_ERROR)
        _log_refusal_once(decision, state, error_type=type(exc).__name__)
        _render_unavailable(placeholder, state, drawn)
        return decision


# ------------------------------------------------------------- identity seam
def current_identity() -> Identity:
    user = st.user
    return Identity(
        signed_in=bool(user.is_logged_in),
        email=user.get("email"),
        email_verified=user.get("email_verified"),
    )


def sign_in() -> None:
    st.login(PROVIDER)


def sign_out() -> None:
    st.logout()
