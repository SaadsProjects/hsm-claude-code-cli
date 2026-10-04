"""
Actions and Outcomes: the dashboard's button actions (unit U4).

Every button that calls the backend runs one of these actions inline, where
the button is drawn (``if st.button(...)``), through ``then_rerun``: the
action stores its outcome in session state and ``st.rerun()`` then draws the
banner, the notice and the disabled controls from that state, so the next
completed render shows the outcome (NFR2.3, NFR-design Q2: B). Each backend
action is wrapped by ``guarded``, which turns every ``Exception`` into state,
so an exception never escapes an action and the rest of the page always
renders (security-design.md, Inline writes and one rerun). ``st.rerun()`` is
called outside the guard; its signal is a ``BaseException``, which the guard
never catches (NFR-design review R-03):

    SessionExpired                     log out locally, session-ended notice
    HsmUnavailable, outcome unknown    hold pending_retry (writes)
    HsmUnavailable                     "Can't reach the backend"
    HsmApiError                        the backend's message and problems
    ValueError from retry_write        the expired-retry handling (WF8 step 4)
    anything else                      "Something went wrong: <type>"

Request ids (NFR2.1, NFR2.2): an edit or delete control reuses its stored id
only for an identical body after a success, so a double click is answered
from the backend's stored response; every other case sends a new id. An add
or upload gets a new id after a success, and its form or file picker moves to
a new generation, so a double click (even a stale one that brings the old
values back) finds nothing to send, while the same values entered again on
purpose are a new add. The control's
id is also renewed whenever an unconfirmed write is held or dropped
(Discard, an expired retry, logout, an ended session; functional-design
review R-01). A success drops the other controls' stored successes for the
same kind and site, so a later identical submission cannot replay a stale
success (NFR-design review R-14).

Log out always ends the login at once; a held write is dropped and the
logged-out notice says so (NFR2.4 as amended by NFR-design Q1: B).

After every write outcome the cached reads (the shared cache and this
session's Manage data reads) are cleared and the loaded audit entries
emptied, so every tab shows the latest state (BR3.3). Nothing here draws,
prints or logs; problems are reported through ``notice``.
"""
import contextlib
import functools
import hashlib
import json
import uuid
from datetime import datetime, timezone

import streamlit as st

from agents.hsm_client import HsmApiError, HsmUnavailable, SessionExpired
from dashboard import csv_rows, kind_forms, session

UNREACHABLE = "Can't reach the backend."
SESSION_ENDED = "Your session has ended; log in again."
WRITE_DROPPED = " An unconfirmed write was dropped; reload to check whether it was saved."
LOGGED_OUT = "You logged out."
LOGOUT_WRITE_DROPPED = " An unconfirmed write was dropped; reload after logging in to check whether it was saved."
ENDED_REASONS = {
    "idle": "You were logged out after 15 minutes without a save.",
    "logout": "You logged out.",
}
ENDED_GENERIC = "Your session has ended (the backend may have restarted)."
RETRY_EXPIRED = "We couldn't confirm this write. Reload the data to see whether it was saved."
DISCARDED = "If that write did reach the backend, it is saved; reload to check."
STALE = "this record changed since you opened it; reload and try again"
AUDIT_UNAVAILABLE = "The audit trail is unavailable."
NOTHING_SAVED = "Nothing from the file was saved."


def _now():
    """Aware UTC now; module level so tests can move it."""
    return datetime.now(timezone.utc)


def clear_cached_reads(state=None):
    """Clear every cached read: the existing tabs' shared ``st.cache_data``
    store, so every session's Overview, Labor and Inventory tabs show a
    change (WF5 step 6), and this session's Manage data reads (Q3: B)."""
    st.cache_data.clear()
    session.clear_records(state)


def then_rerun(action, *args, **kwargs):
    """Run a clicked button's action inline, then start a new run that draws
    its outcome (Q2: B). ``st.rerun()`` stays outside ``guarded``: its
    signal is a ``BaseException`` the guard never catches (review R-03)."""
    action(*args, **kwargs)
    st.rerun()


# ------------------------------------------------------------------ notices

def _notice(level, message, problems=None, *, stale=False, note=None):
    return {"level": level, "message": message, "problems": list(problems or []), "stale": stale, "note": note}


def notify(state, level, message, problems=None, **extra):
    session.set_notice(_notice(level, message, problems, **extra), state)


# ------------------------------------------------------------ login session

def end_login(state, message):
    """Drop the login and the session-scoped state, keeping a notice. When an
    unconfirmed write was held, the notice says it was dropped (NFR2.4)."""
    dropped = _drop_held(state)
    session.set_login(None, state)
    session.clear_session_scoped(state)
    notify(state, "warning", message + (WRITE_DROPPED if dropped else ""))


def check_session(state=None):
    """The session check at the top of every rerun (WF2, BR1.2), outside
    any action; it never keeps the session alive. Returns a message to
    show when the check got no usable answer (the login is kept), else None.
    An ended session logs out locally with the backend's reason."""
    state = session.state_of(state)
    login = session.login(state)
    if login is None:
        return None
    try:
        status = session.client_for(login["user_id"]).session_status(login["session_id"])
    except HsmUnavailable:
        return UNREACHABLE
    except HsmApiError as e:
        return e.message
    except Exception as e:  # noqa: BLE001 -- shown in place of the tabs; the login is kept
        return f"Something went wrong: {type(e).__name__}"
    if not status.get("active"):
        end_login(state, ENDED_REASONS.get(status.get("ended_reason"), ENDED_GENERIC))
    return None


# ---------------------------------------------------------------- outcomes

def _after_write_outcome(state):
    """BR3.3: every tab shows the latest state on the next render."""
    clear_cached_reads(state)
    session.set_item("audit", {}, state)


def _hold_retry(state, write, error):
    """Hold the outcome-unknown error itself, never a copy (NFR2.2), and
    renew the control's id: Try again re-sends with the id the error holds,
    so nothing else may send it again (review R-01)."""
    session.set_item("pending_retry", {**write, "error": error}, state)
    renew_request_id(state, write.get("control"))


def _drop_held(state):
    """Drop a held write, renewing its control's id. True if one was held."""
    held = session.pending_retry(state)
    if held is None:
        return False
    renew_request_id(state, held.get("control"))
    session.set_item("pending_retry", None, state)
    return True


def _expire_retry(state):
    """WF8 step 4: stop offering Try again; the control gets a new id."""
    _drop_held(state)
    clear_cached_reads(state)
    notify(state, "warning", RETRY_EXPIRED)


def _refused(state, write, error):
    if write.get("retry"):
        session.set_item("pending_retry", None, state)  # the retry got an answer (WF8 step 2)
    if write:
        _mark(state, write.get("control"), "refused")
        _after_write_outcome(state)
        if write.get("action") == "delete":
            session.set_item("pending_delete", None, state)
    stale = error.status == 409 and error.message == STALE
    note = NOTHING_SAVED if write.get("action") == "bulk" else None
    notify(state, "error", error.message, error.problems, stale=stale, note=note)


def record_outcome(state, write, error):
    """Map one exception from an action to its state change. ``write``
    describes the write the action sent (empty for other actions)."""
    if isinstance(error, SessionExpired):
        if write.get("retry"):
            session.set_item("pending_retry", None, state)  # the backend saw it never landed
        end_login(state, SESSION_ENDED)
    elif isinstance(error, HsmUnavailable) and error.outcome_unknown and write:
        _hold_retry(state, write, error)
    elif isinstance(error, HsmUnavailable):
        notify(state, "error", UNREACHABLE)
    elif isinstance(error, HsmApiError):
        _refused(state, write, error)
    elif isinstance(error, ValueError) and write.get("retry"):
        _expire_retry(state)
    else:
        notify(state, "error", f"Something went wrong: {type(error).__name__}")


def guarded(action):
    """Wrap an action so no ``Exception`` escapes it; a ``BaseException``
    such as Streamlit's rerun signal is never caught. The action is called as
    ``action(state, write, *args)``; it fills ``write`` before it sends a
    write, so the outcome can be mapped. ``state`` is an optional keyword
    (default ``st.session_state``)."""

    @functools.wraps(action)
    def run(*args, state=None, **kwargs):
        state = session.state_of(state)
        write = {}
        try:
            action(state, write, *args, **kwargs)
        except Exception as error:  # noqa: BLE001 -- every outcome becomes state (security-design.md)
            record_outcome(state, write, error)

    return run


# -------------------------------------------------------------- request ids

def _fingerprint(body):
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def request_id_for(state, control, kind, site, body):
    """The id to send for ``body`` from ``control`` (NFR2.1): the stored id
    when the body is identical and the last answer was a success, else new."""
    ids = session.request_ids(state)
    fingerprint = _fingerprint(body)
    entry = ids.get(control)
    if entry is not None and entry["fingerprint"] == fingerprint and entry["last"] == "ok":
        return entry["id"]
    ids[control] = {"id": uuid.uuid4().hex, "fingerprint": fingerprint, "last": None, "kind": kind, "site": site}
    return ids[control]["id"]


def renew_request_id(state, control):
    """Give ``control`` a fresh id that no request has carried; its next
    submission is checked afresh whatever its body (NFR2.2)."""
    entry = session.request_ids(state).get(control)
    if entry is not None:
        entry.update(id=uuid.uuid4().hex, fingerprint=None, last=None)


def _mark(state, control, last):
    entry = session.request_ids(state).get(control)
    if entry is None:
        return
    entry["last"] = last
    if last == "ok":
        # R-14: another control's stored success for the same kind and site
        # is stale now; its next identical submission must be checked afresh.
        ids = session.request_ids(state)
        for other in [c for c, e in ids.items() if c != control and e["last"] == "ok"
                      and (e["kind"], e["site"]) == (entry["kind"], entry["site"])]:
            del ids[other]


# ------------------------------------------------------------------ writes

def _login_or_raise(state):
    login = session.login(state)
    if login is None:
        raise SessionExpired()
    return login


def _site_arg(kind, site):
    return site if kind_forms.KIND_FORMS[kind].site_scoped else None


def _added_list(state, kind, site):
    form = kind_forms.KIND_FORMS[kind]
    return session.added(state).setdefault(session.added_key(kind, site, form.site_scoped), [])


def _succeeded(state, write, result):
    """A write's success (also a Try again that found it landed)."""
    _mark(state, write.get("control"), "ok")
    kind, site, action = write["kind"], write["site"], write["action"]
    form = kind_forms.KIND_FORMS[kind]
    added = _added_list(state, kind, site)
    label = form.label
    if action == "add":
        key = result["record"][form.key]
        if key not in added:
            added.append(key)
        message = f"Added {label} {key}."
        _clear_add_form(state, kind, site)
        # A new form generation stops a repeat click, even one that brings
        # the old values back from the browser; a fresh id makes a deliberate
        # second add with the same values a new request, so a second
        # identical employee is really added (final review R-03).
        session.next_add_generation(kind, site, state)
        renew_request_id(state, write.get("control"))
    elif action == "update":
        message = f"Saved {label} {write['record_id']}."
    elif action == "delete":
        if write["record_id"] in added:
            added.remove(write["record_id"])
        session.set_item("pending_delete", None, state)
        message = f"Deleted {label} {write['record_id']}."
    else:  # bulk
        for item in result.get("records", []):
            key = item["record"][form.key]
            if key not in added:
                added.append(key)
        message = f"Added {result.get('added', 0)} records from {write['file_name']}."
        # Empty the picker and renew the id, as for a single add.
        session.next_upload_generation(kind, site, state)
        renew_request_id(state, write.get("control"))
    _after_write_outcome(state)
    notify(state, "success", message)


def _clear_add_form(state, kind, site):
    """After an add succeeds its form starts empty (security-design, Request ids)."""
    prefix = kind_forms.form_key_prefix("add", kind, site, None, session.add_form_version(kind, site, state))
    for key in [k for k in list(state.keys()) if isinstance(k, str) and k.startswith(prefix)]:
        del state[key]


def form_values(state, mode, kind, site, record, version, slots=None):
    """Read a form's widget values from state (security-design, Form values).
    ``slots`` maps a line-slot field to how many slots were drawn."""
    form = kind_forms.KIND_FORMS[kind]
    values = {}
    for fld in form.fields:
        if fld.input in kind_forms.SLOT_PARTS:
            count = (slots or {}).get(fld.name, kind_forms.slot_count())
            values[fld.name] = [
                {part.name: state.get(kind_forms.field_key(
                    mode, kind, site, record, version, kind_forms.slot_field(fld.name, i, part.name)))
                 for part in kind_forms.SLOT_PARTS[fld.input]}
                for i in range(count)]
        else:
            values[fld.name] = state.get(kind_forms.field_key(mode, kind, site, record, version, fld.name))
    return values


def _send(state, write, body, send):
    """Pick the request id, send, and handle a success."""
    write["control_body"] = body
    request_id = request_id_for(state, write["control"], write["kind"], write["site"], body)
    result = send(request_id)
    _succeeded(state, write, result)


@guarded
def submit_add(state, write, kind, site, slots=None, version=None):
    login = _login_or_raise(state)
    values = form_values(state, "add", kind, site, None, version, slots)
    if kind_forms.is_blank(kind, values):
        return  # a second click on a form that was cleared after its success (R-11)
    record = kind_forms.build_record(kind, values)
    site_arg = _site_arg(kind, site)
    write.update(control=("add", kind, site), kind=kind, site=site, action="add", describe=f"add {kind}")
    client = session.client_for(login["user_id"])
    _send(state, write, {"action": "add", "kind": kind, "site": site_arg, "record": record},
          lambda rid: client.add_record(kind, record, login["session_id"], site_id=site_arg, request_id=rid))


@guarded
def submit_edit(state, write, kind, site, record_id, version, slots=None):
    login = _login_or_raise(state)
    values = form_values(state, "edit", kind, site, record_id, version, slots)
    form = kind_forms.KIND_FORMS[kind]
    if form.key_mode != "generated":
        values[form.key] = record_id  # the key cannot be changed
    record = kind_forms.build_record(kind, values)
    site_arg = _site_arg(kind, site)
    write.update(control=("edit", kind, site, record_id, version), kind=kind, site=site, action="update",
                 record_id=record_id, describe=f"edit {kind} {record_id}")
    client = session.client_for(login["user_id"])
    body = {"action": "update", "kind": kind, "site": site_arg, "record_id": record_id, "version": version,
            "record": record}
    _send(state, write, body, lambda rid: client.update_record(
        kind, record_id, record, version, login["session_id"], site_id=site_arg, request_id=rid))


def ask_delete(kind, site, record_id, version, state=None):
    """The first Delete click: ask "Delete <record>?" (Q4). No backend call."""
    session.set_item("pending_delete", {"kind": kind, "site": site, "record_id": record_id, "version": version},
                     state)


def cancel_delete(state=None):
    session.set_item("pending_delete", None, state)


@guarded
def confirm_delete(state, write):
    login = _login_or_raise(state)
    pending = session.pending_delete(state)
    if pending is None:
        return  # a repeat Confirm after the first one resolved
    kind, site, record_id, version = pending["kind"], pending["site"], pending["record_id"], pending["version"]
    site_arg = _site_arg(kind, site)
    write.update(control=("delete", kind, site, record_id), kind=kind, site=site, action="delete",
                 record_id=record_id, describe=f"delete {kind} {record_id}")
    client = session.client_for(login["user_id"])
    body = {"action": "delete", "kind": kind, "site": site_arg, "record_id": record_id, "version": version}
    _send(state, write, body, lambda rid: client.delete_record(
        kind, record_id, version, login["session_id"], site_id=site_arg, request_id=rid))


@guarded
def upload(state, write, kind, site, uploader_key):
    """Read the picked file, refuse it locally or send it in one bulk
    request (WF6, BR4.2, NFR1.6). A local refusal sends nothing."""
    login = _login_or_raise(state)
    picked = state.get(uploader_key)
    template = session.templates(state).get((kind, site))
    if picked is None or template is None:
        notify(state, "error", "Pick a .csv file first.")
        return
    data, file_name = picked.getvalue(), picked.name
    read = csv_rows.read_upload(data, template["columns"])
    if read.refusal is not None:
        notify(state, "error", read.refusal)
        return
    site_arg = _site_arg(kind, site)
    control = ("upload", kind, site)
    body = {"action": "bulk", "kind": kind, "site": site_arg, "file_name": file_name, "rows": read.rows}
    request_id = request_id_for(state, control, kind, site, body)
    if not csv_rows.fits(read.rows, file_name, login["session_id"], request_id):
        notify(state, "error", csv_rows.TOO_LARGE)
        return
    write.update(control=control, kind=kind, site=site, action="bulk", file_name=file_name,
                 describe=f"upload {file_name}")
    client = session.client_for(login["user_id"])
    result = client.bulk_add(kind, read.rows, file_name, login["session_id"], site_id=site_arg,
                             request_id=request_id)
    _succeeded(state, write, result)


# ---------------------------------------------------------- pending retry

def retry_expired(state=None):
    """True when the held write is past its retry deadline. Checked when the
    banner is drawn; it then clears the retry (WF8 step 4)."""
    held = session.pending_retry(state)
    if held is None or held["error"].retry_deadline is None or _now() <= held["error"].retry_deadline:
        return False
    _expire_retry(session.state_of(state))
    return True


@guarded
def try_again(state, write):
    """Re-send the exact request behind pending_retry with its original id
    (WF8). Any answer resolves the retry and is handled as WF7 says."""
    held = session.pending_retry(state)
    if held is None:
        return
    login = _login_or_raise(state)
    write.update({k: v for k, v in held.items() if k != "error"}, retry=True)
    # No answer again: guarded holds the new error. A refusal, an ended
    # session or a passed deadline resolves the retry in record_outcome.
    result = session.client_for(login["user_id"]).retry_write(held["error"])
    session.set_item("pending_retry", None, state)
    _succeeded(state, write, result)


def discard(state=None):
    """Drop the held write; the control that sent it gets a new id."""
    state = session.state_of(state)
    _drop_held(state)
    clear_cached_reads(state)
    notify(state, "warning", DISCARDED)


def reload(state=None):
    """Reload after a stale-record refusal: clear the cached reads."""
    clear_cached_reads(state)
    session.set_notice(None, state)


# ----------------------------------------------------------------- login

@guarded
def log_in(state, write, user_id):
    """Start a session for the picked persona (WF1). Only this action ever
    starts one (NFR7.1); a failure leaves the user logged out."""
    started = session.client_for(user_id).start_session()
    session.set_login({"session_id": started["session_id"], "user_id": user_id,
                       "persona": started.get("persona")}, state)
    session.clear_session_scoped(state)
    session.set_notice(None, state)
    clear_cached_reads(state)


@guarded
def log_out(state, write):
    """Log out at once (WF3, BR1.4; NFR2.4 as amended by Q1: B). End the
    session on the backend; whatever the answer, end the login. With no
    answer, ask for the status once (the session ends by itself after 15
    idle minutes if the logout never landed). A held write is dropped, its
    control's id renewed, and the logged-out notice says so."""
    login = session.login(state)
    try:
        if login is not None:
            client = session.client_for(login["user_id"])
            try:
                client.end_session(login["session_id"])
            except HsmUnavailable:
                with contextlib.suppress(HsmApiError):  # no answer again: nothing more to learn
                    client.session_status(login["session_id"])
            except HsmApiError:
                pass  # e.g. 401: the session had already ended
    finally:
        dropped = _drop_held(state)
        session.set_login(None, state)
        session.clear_session_scoped(state)
        clear_cached_reads(state)
        if dropped:
            notify(state, "warning", LOGGED_OUT + LOGOUT_WRITE_DROPPED)
        else:
            notify(state, "info", LOGGED_OUT)


# ----------------------------------------------------------------- audit

def load_audit(state=None):
    """Load the newest audit page when ``audit`` is empty (WF9 step 1).
    Returns a message to show in the tab when the page is refused or gets no
    answer, else None. Not a button action: the Audit tab calls it as it draws."""
    state = session.state_of(state)
    if session.audit(state):
        return None
    login = session.login(state)
    if login is None:
        return None
    try:
        page = session.client_for(login["user_id"]).audit_page()
    except HsmUnavailable:
        return UNREACHABLE
    except HsmApiError as e:
        return AUDIT_UNAVAILABLE if e.status == 503 else e.message
    session.set_item("audit", {"entries": _shown_entries(page), "next_before": page.get("next_before"),
                               "total": page.get("total", 0)}, state)
    return None


def _shown_entries(page):
    """A page's entries without their session ids, which are never shown (NFR1.4)."""
    return [{k: v for k, v in entry.items() if k != "session_id"} for entry in page["entries"]]


@guarded
def audit_load_older(state, write):
    """Append the next page, paged from the last loaded entry's id (the
    page's ``next_before``). The backend pages from any well-formed marker,
    a purged one included (U2 BR4.3), so there is no purge case."""
    loaded = session.audit(state)
    login = _login_or_raise(state)
    if not loaded or loaded.get("next_before") is None:
        return
    try:
        page = session.client_for(login["user_id"]).audit_page(before=loaded["next_before"])
    except HsmApiError as e:
        if e.status == 503:
            notify(state, "error", AUDIT_UNAVAILABLE)
            return
        raise
    session.set_item("audit", {"entries": loaded["entries"] + _shown_entries(page),
                               "next_before": page.get("next_before"), "total": page.get("total", 0)}, state)


def audit_refresh(state=None):
    session.set_item("audit", {}, state)
