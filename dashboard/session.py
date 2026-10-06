"""
ClientFactory and SessionState for the dashboard (unit U4).

``client_for`` is the one place the dashboard builds an ``HsmClient``: every
read and write, the existing tabs' included, goes through it, so the screen
tests point the whole dashboard at their own backend with one monkeypatch
(NFR6.2). Callers reach it as ``session.client_for(...)`` so that patch
reaches them all (NFR-design review R-13).

The SessionState accessors read and write one browser session's state.
Every function takes an optional ``state`` mapping and falls back to
``st.session_state``, so the unit tests use a plain dict. The session id
lives only in ``login``; nothing here prints, logs or shows it (NFR1.4).

``records`` is the Manage data tab's per-session read cache (NFR-design Q3:
B): each ``list_records`` answer is stamped with its fetch time from the
injectable clock ``_now`` and reused for ``RECORDS_TTL``. It is cleared after
this session's write outcomes, by Refresh data and with the login.
"""

from datetime import datetime, timedelta, timezone

import streamlit as st

from agents.hsm_client import HsmClient
from mock_hsm import embedded
from mock_hsm.auth import mint_token

# login: None when logged out, else {session_id, user_id, persona}. notice:
# the last outcome message. Both survive clear_session_scoped(); the rest
# belong to one login session (functional-spec, Session State).
LOGIN, NOTICE = "login", "notice"
SCOPED_DEFAULTS = {
    "added": dict,  # added_key(kind, site) -> [record keys this login added]
    "pending_delete": lambda: None,
    "pending_retry": lambda: None,
    "audit": dict,  # {entries, next_before, total}, or {} when it must be reloaded
    "request_ids": dict,  # control -> {id, fingerprint, last, kind, site}
    "templates": dict,  # (kind, site) -> {columns, csv}
    "records": dict,  # (user_id, kind, site) -> {fetched, listing}: the Manage data cache
}
RECORDS_TTL = timedelta(seconds=60)
# Widget keys of the record forms (kind_forms.field_key), cleared with a login.
FORM_KEY_PREFIX = "form:"


def _now():
    """Aware UTC now; module level so tests can move the cache's clock."""
    return datetime.now(timezone.utc)


def client_for(user_id):
    """An HsmClient carrying ``user_id``'s token, addressed to the backend
    running in this process (``mock_hsm.embedded``), never ``HSM_BASE_URL``.

    The address is read from the live instance on every call, because a
    replaced backend listens on a new port. With no live backend this raises
    ``BackendNotRunning``; it never starts one (the start belongs to the
    render, before any screen reads data)."""
    backend = embedded.current()
    if backend is None:
        raise embedded.BackendNotRunning("the embedded backend is not running")
    return HsmClient(mint_token(user_id), base_url=backend.address)


def state_of(state=None):
    return st.session_state if state is None else state


def _get(name, state):
    state = state_of(state)
    if name not in state:
        state[name] = SCOPED_DEFAULTS[name]()
    return state[name]


def login(state=None):
    return state_of(state).get(LOGIN)


def set_login(value, state=None):
    state_of(state)[LOGIN] = value


def notice(state=None):
    return state_of(state).get(NOTICE)


def set_notice(value, state=None):
    state_of(state)[NOTICE] = value


def added(state=None):
    return _get("added", state)


def pending_delete(state=None):
    return _get("pending_delete", state)


def pending_retry(state=None):
    return _get("pending_retry", state)


def audit(state=None):
    return _get("audit", state)


def request_ids(state=None):
    return _get("request_ids", state)


def uploader_key(kind, site, state=None):
    """The CSV picker's widget key. A successful upload moves it to a new
    generation, so the picker starts empty and a repeat click sends nothing.
    The counter is never reset, so a stale file can't come back after logout."""
    generations = state_of(state).setdefault("upload_generation", {})
    return f"manage-{kind}-file@{site or ''}#{generations.get((kind, site), 0)}"


def add_form_version(kind, site, state=None):
    """The ``version`` part of the add form's field keys. A successful add
    moves the form to a new generation, so values a stale double click
    brings back from the browser land on keys no longer drawn, and the
    second click finds the form blank (commit review, finding 2).
    Generation 0 keeps the plain keys. Never reset, like the upload picker."""
    generation = state_of(state).setdefault("add_generation", {}).get((kind, site), 0)
    return f"g{generation}" if generation else None


def next_add_generation(kind, site, state=None):
    generations = state_of(state).setdefault("add_generation", {})
    generations[(kind, site)] = generations.get((kind, site), 0) + 1


def next_upload_generation(kind, site, state=None):
    generations = state_of(state).setdefault("upload_generation", {})
    generations[(kind, site)] = generations.get((kind, site), 0) + 1


def templates(state=None):
    return _get("templates", state)


def records(state=None):
    return _get("records", state)


def records_for(user_id, kind, site, state=None):
    """``{records, meta}`` of one kind: this session's cached answer while it
    is younger than ``RECORDS_TTL``, else a fresh ``list_records`` read. A
    failed read is not cached; its error reaches the caller."""
    cache = records(state)
    key = (user_id, kind, site)
    entry = cache.get(key)
    now = _now()
    if entry is not None and now - entry["fetched"] < RECORDS_TTL:
        return entry["listing"]
    listing = client_for(user_id).list_records(kind, site_id=site)
    cache[key] = {"fetched": now, "listing": listing}
    return listing


def clear_records(state=None):
    """Drop this session's cached Manage data reads."""
    state_of(state)["records"] = {}


def set_item(name, value, state=None):
    """Set one session-scoped item (``pending_delete``, ``audit``, ...)."""
    if name not in SCOPED_DEFAULTS:
        raise KeyError(name)
    state_of(state)[name] = value


def added_key(kind, site, site_scoped):
    """``added`` is keyed by kind, and site kinds also by their site."""
    return f"{kind}@{site}" if site_scoped else kind


def clear_session_scoped(state=None):
    """Reset everything except ``login`` and ``notice``: the scoped items
    and the record forms' widget values."""
    state = state_of(state)
    for name, default in SCOPED_DEFAULTS.items():
        state[name] = default()
    for key in [k for k in list(state.keys()) if isinstance(k, str) and k.startswith(FORM_KEY_PREFIX)]:
        del state[key]
