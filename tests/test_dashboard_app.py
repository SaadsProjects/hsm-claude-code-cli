"""
Screen tests for the dashboard's write screens (unit U4), plus the
hidden-write check and the timing tests (``perf``).

The app runs under ``streamlit.testing.v1.AppTest`` against the real mock
backend, in process, on an ephemeral port. ``dashboard.session.client_for``
is monkeypatched to point at that server, and the Streamlit data cache is
cleared before each test. tests/conftest.py gives every test its own audit
file and resets the backend's write state afterwards.

Faults are injected per client method: ``"no-answer"`` sends the call to a
closed port, so the client raises its own outcome-unknown HsmUnavailable
with a real stored request that ``retry_write`` can re-send; an exception
instance is raised as is.
"""

import socket
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import pytest
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate_app import gate_app

from agents.hsm_client import HsmApiError, HsmClient
from dashboard import actions, data, kind_forms, manage_tab, markers, session
from dashboard.safe_text import escape_md
from mock_hsm import audit, writes
from mock_hsm.auth import mint_token
from mock_hsm.db import USERS
from mock_hsm.server import Handler

RM, REGIONAL, DEV = "user_rm_midtown", "user_regional_atl", "user_dev_tester"
PERSONAS = (RM, REGIONAL, DEV)
SITE = "site_001"
ALL_SEEING = {"user_id": "test-auditor", "persona": "SYSTEM_ADMIN", "site_ids": [], "region_id": None}
# Relative paths resolve against the calling file, so the app is named absolutely.
APP = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")
TABS = ["Overview", "Labor", "Inventory", "Manage data", "Audit"]


@pytest.fixture
def base_url():
    """The real backend, in process, on an ephemeral port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    # A short poll keeps shutdown() from waiting the default 0.5 s on every test.
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def dead_url():
    """A port nothing listens on: every call to it gets no answer."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def faults():
    """Client method name -> "no-answer" or an exception to raise."""
    return {}


@pytest.fixture
def client_factory(base_url, dead_url, faults, monkeypatch):
    """Point the dashboard's one client factory at the test server (NFR6.2),
    with the faults the test asks for."""

    def factory(user_id):
        client = HsmClient(mint_token(user_id), base_url=base_url)
        for name, fault in faults.items():
            if fault == "no-answer":
                setattr(client, name, getattr(HsmClient(mint_token(user_id), base_url=dead_url, timeout=1), name))
            else:
                setattr(client, name, _raiser(fault))
        return client

    monkeypatch.setattr(session, "client_for", factory)
    return factory


def _raiser(error):
    def raise_it(*args, **kwargs):
        raise error

    return raise_it


@pytest.fixture
def clock():
    """Move the backend's clock; the real clock comes back after the test."""
    yield lambda delta: writes.set_clock(lambda: datetime.now(timezone.utc) + delta)
    writes.set_clock(None)


@pytest.fixture
def app(client_factory, monkeypatch):
    # Through the sign-in gate as the shared fake allowed visitor (AC4.8.1).
    st.cache_data.clear()
    at = gate_app(APP, monkeypatch)
    at.run()
    return at


def _entries():
    entries, before = [], None
    while True:
        page = audit.page(ALL_SEEING, before)
        entries += page["entries"]
        before = page["next_before"]
        if before is None:
            return entries[::-1]


# ---------------------------------------------------------------- helpers


def log_in(at, user_id):
    at.selectbox(key="session-persona").set_value(user_id)
    at.button(key="session-login").click().run()
    assert not at.exception, at.exception
    return at


def pick(at, data_set, kind):
    at.selectbox(key="manage-data-set").set_value(data_set).run()
    at.selectbox(key=f"manage-kind@{data_set}").set_value(kind).run()
    assert not at.exception, at.exception
    return at


def widget(at, key):
    for widgets in (at.text_input, at.number_input, at.selectbox, at.multiselect):
        try:
            return widgets(key)
        except KeyError:
            continue
    raise KeyError(key)


def _add_version(at, kind, site):
    try:
        generation = at.session_state["add_generation"].get((kind, site), 0)
    except KeyError:
        generation = 0
    return f"g{generation}" if generation else None


def fill(at, mode, kind, site, record, version, values):
    if mode == "add" and version is None:
        version = _add_version(at, kind, site)  # the add form's current generation
    for name, value in values.items():
        widget(at, kind_forms.field_key(mode, kind, site, record, version, name)).set_value(value)
    return at


def click(at, key):
    at.button(key=key).click().run()
    assert not at.exception, at.exception
    return at


def notice(at):
    return at.session_state["notice"]


def button_keys(at):
    return {b.key for b in at.button}


def tab_labels(at):
    return [t.label for t in at.tabs]


def admin_client(user_id=REGIONAL):
    """A client and session of its own, for test data and for writes the
    dashboard did not make."""
    client = session.client_for(user_id)
    return client, client.start_session()["session_id"]


def records(kind, site=None):
    listing = session.client_for(REGIONAL).list_records(kind, site_id=site)
    key = kind_forms.KIND_FORMS[kind].key
    return {r[key]: (r, listing["meta"][r[key]]) for r in listing["records"]}


def record_frame(at):
    """The Manage data tab's record table (the other tabs draw frames too)."""
    return next(df.value for df in at.dataframe if "origin" in df.value.columns)


def problem_frame(at):
    return next(df.value for df in at.dataframe if "reason" in df.value.columns and "outcome" not in df.value.columns)


def _all_text(node):
    out = []
    proto = getattr(node, "proto", None)
    if proto is not None:
        out.append(str(proto))
    for child in getattr(node, "children", {}).values():
        out += _all_text(child)
    return out


def hold_a_write(at, faults, job_code="jc_held"):
    """Add a job code whose answer never arrives, so the write is held."""
    faults["add_record"] = "no-answer"
    pick(at, "Staff", "job_code")
    fill(at, "add", "job_code", None, None, None, {"job_code": job_code, "title": "Held"})
    click(at, "manage-job_code-add-submit")
    assert at.session_state["pending_retry"] is not None
    faults.clear()
    return at


# ------------------------------------------------------------ hidden write


def test_hidden_shared_write_sent_through_the_client_is_refused_and_audited(client_factory):
    # NFR1.1: the dashboard hides shared-kind controls from the Restaurant
    # Manager, but the backend is what refuses and audits such a write.
    assert not kind_forms.is_region_wide(USERS[RM])
    client = client_factory(RM)
    session_id = client.start_session()["session_id"]
    with pytest.raises(HsmApiError) as refused:
        client.add_record("job_code", {"job_code": "jc_x", "title": "X"}, session_id)
    assert refused.value.status == 403
    violations = [e for e in _entries() if e["outcome"] == "violation"]
    assert len(violations) == 1
    assert (violations[0]["user_id"], violations[0]["kind"], violations[0]["action"]) == (RM, "job_code", "add")


# ---------------------------------------------------------- login (WF1-3)


def test_logged_out_view_shows_only_the_login(app):
    assert tab_labels(app) == []
    assert [i.value for i in app.info] == ["Log in to see the dashboard."]
    assert button_keys(app) == {"session-login", markers.SIGN_OUT_BUTTON}


@pytest.mark.parametrize("user_id", PERSONAS)
def test_login_and_logout_for_each_persona(app, user_id):
    log_in(app, user_id)
    assert tab_labels(app) == TABS
    login = app.session_state["login"]
    assert login["user_id"] == user_id
    name = USERS[user_id]["name"]
    assert f"Acting as {escape_md(name)} ({escape_md(login['persona'])})" in [c.value for c in app.sidebar.caption]
    session_id = login["session_id"]

    click(app, "session-logout")
    assert tab_labels(app) == []
    assert app.session_state["login"] is None
    assert session.client_for(user_id).session_status(session_id)["active"] is False


@pytest.mark.parametrize("user_id", PERSONAS)
def test_no_publish_or_submit_button_for_any_persona(app, user_id):
    # NFR1.2, FR2.9: no publish, submit or draft action anywhere.
    log_in(app, user_id)
    for data_set, kinds in kind_forms.DATA_SETS.items():
        for kind in kinds:
            pick(app, data_set, kind)
            labels = [b.label.lower() for b in app.button]
            assert not any(word in label for label in labels for word in ("publish", "submit", "draft")), labels


# ------------------------------------------------- add, edit, delete (WF5)


def _prepare_on_hand():
    client, session_id = admin_client()
    client.add_record("uom", {"uom_id": "u_p", "name": "piece", "base": "u_p", "factor_to_base": 1}, session_id)
    client.add_record("raw_material", {"raw_material_id": "rm_t", "name": "Test", "uom": "u_p"}, session_id)


LABOR_RULE = {
    "jurisdiction": "TX",
    "weekly_ot_threshold_hours": 40.0,
    "daily_ot_threshold_hours": 8.0,
    "ot_multiplier": 1.5,
    "max_consecutive_days": 6,
    "min_rest_hours_between_shifts": 8.0,
    "max_shift_length_hours": 12.0,
    "note": "test rule",
}

CRUD_CASES = [
    (
        "Menu",
        "menu_item",
        None,
        None,
        {"menu_item_id": "mi_t", "name": "Taco", "gl_code": "GL-FOOD"},
        {"name": "Tacos"},
    ),
    (
        "Ingredients and suppliers",
        "uom",
        None,
        None,
        {"uom_id": "u_t", "name": "unit", "base": kind_forms.SELF_BASE, "factor_to_base": 1.0},
        {"name": "units"},
    ),
    ("Staff", "job_code", None, None, {"job_code": "jc_t", "title": "Cook"}, {"title": "Head cook"}),
    ("Stock levels", "on_hand", SITE, _prepare_on_hand, {"raw_material_id": "rm_t", "qty": 5.0}, {"qty": 7.5}),
    ("Labor rules", "labor_rule", None, None, LABOR_RULE, {"note": "changed"}),
]


@pytest.mark.parametrize(
    ("data_set", "kind", "site", "prepare", "values", "change"), CRUD_CASES, ids=[case[1] for case in CRUD_CASES]
)
def test_add_edit_and_delete_one_kind_in_each_data_set(app, data_set, kind, site, prepare, values, change):
    if prepare:
        prepare()
    form = kind_forms.KIND_FORMS[kind]
    key = values[form.key]
    log_in(app, REGIONAL)
    pick(app, data_set, kind)

    fill(app, "add", kind, site, None, None, values)
    click(app, f"manage-{kind}-add-submit")
    assert notice(app)["level"] == "success", notice(app)
    stored, meta = records(kind, site)[key]
    assert (meta["origin"], meta["created_by"], meta["version"]) == ("dashboard", REGIONAL, 1)
    added_key = session.added_key(kind, site, form.site_scoped)
    assert app.session_state["added"][added_key] == [key]
    table = record_frame(app)
    assert {"added by", "changed by", "origin", "version"} <= set(table.columns)
    assert key in set(table[form.key])

    app.selectbox(key=f"manage-{kind}-edit-pick@{site or ''}").set_value(key).run()
    fill(app, "edit", kind, site, key, 1, change)
    click(app, f"manage-{kind}-edit-submit")
    assert notice(app)["level"] == "success", notice(app)
    stored, meta = records(kind, site)[key]
    assert meta["version"] == 2 and meta["updated_by"] == REGIONAL
    for name, value in change.items():
        assert stored[name] == value

    click(app, f"manage-{kind}-delete-{key}")
    assert [w.value for w in app.warning] == [f"Delete {escape_md(key)}?"]
    click(app, f"manage-{kind}-delete-confirm")
    assert notice(app)["level"] == "success", notice(app)
    assert key not in records(kind, site)
    assert app.session_state["added"][added_key] == []
    assert app.session_state["pending_delete"] is None


def test_delete_cancel_keeps_the_record(app):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_c", "title": "Keep"})
    click(app, "manage-job_code-add-submit")
    click(app, "manage-job_code-delete-jc_c")
    click(app, "manage-job_code-delete-cancel")
    assert app.session_state["pending_delete"] is None
    assert "jc_c" in records("job_code")


def test_delete_offered_only_for_this_sessions_records(app):
    client, session_id = admin_client()
    client.add_record("job_code", {"job_code": "jc_other", "title": "Other"}, session_id)
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    assert not any(key.startswith("manage-job_code-delete") for key in button_keys(app) if key)
    # Records added in another session are still editable; seeded ones are not.
    assert app.selectbox(key="manage-job_code-edit-pick@").options == ["jc_other"]


def test_stale_edit_shows_the_reload_message(app):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_s", "title": "First"})
    click(app, "manage-job_code-add-submit")
    app.selectbox(key="manage-job_code-edit-pick@").set_value("jc_s").run()
    client, session_id = admin_client()
    client.update_record("job_code", "jc_s", {"title": "Elsewhere"}, 1, session_id)

    fill(app, "edit", "job_code", None, "jc_s", 1, {"title": "Mine"})
    click(app, "manage-job_code-edit-submit")
    assert notice(app)["stale"] is True
    assert [e.value for e in app.error] == [escape_md(actions.STALE)]
    assert records("job_code")["jc_s"][0]["title"] == "Elsewhere"

    click(app, "notice-reload")
    assert app.session_state["notice"] is None
    # The reloaded form is keyed by the new version and filled from it.
    key = kind_forms.field_key("edit", "job_code", None, "jc_s", 2, "title")
    assert app.text_input(key=key).value == "Elsewhere"


def test_restaurant_manager_sees_shared_data_read_only(app):
    log_in(app, RM)
    for data_set, kinds in kind_forms.DATA_SETS.items():
        for kind in kinds:
            pick(app, data_set, kind)
            form = kind_forms.KIND_FORMS[kind]
            if form.site_scoped:
                assert f"manage-{kind}-add-submit" in button_keys(app)
            else:
                assert escape_md(manage_tab.READ_ONLY_NOTE) in [i.value for i in app.info]
                assert not any(key and key.startswith(f"manage-{kind}") for key in button_keys(app))
                assert len(record_frame(app)) > 0  # the seeded records are still shown


def test_empty_reference_lists_disable_the_submit_with_the_reason(app):
    log_in(app, REGIONAL)
    pick(app, "Menu", "recipe")
    captions = [c.value for c in app.caption]
    for label in ("menu item", "raw material", "unit of measure"):
        assert f"Add a {escape_md(label)} first" in captions
    assert app.button(key="manage-recipe-add-submit").disabled

    click(app, "session-logout")
    log_in(app, RM)
    pick(app, "Staff", "employee")
    assert "No dashboard-added job code exists yet; a regional role must add one first" in [
        c.value for c in app.caption
    ]
    assert app.button(key="manage-employee-add-submit").disabled


def test_reference_options_list_only_dashboard_added_records(app):
    client, session_id = admin_client()
    client.add_record("job_code", {"job_code": "jc_ref", "title": "Ref"}, session_id)
    log_in(app, RM)
    pick(app, "Staff", "employee")
    options = widget(
        app, kind_forms.field_key("add", "employee", SITE, None, _add_version(app, "employee", SITE), "job_code")
    ).options
    assert options == ["jc_ref"]  # the seeded JC-* codes are not offered
    assert not app.button(key="manage-employee-add-submit").disabled

    fill(
        app,
        "add",
        "employee",
        SITE,
        None,
        None,
        {
            "name": "Kim",
            "job_code": "jc_ref",
            "hourly_rate": 15.0,
            "max_weekly_hours_preference": 30,
            "available_days": ["Mon"],
        },
    )
    click(app, "manage-employee-add-submit")
    assert notice(app)["level"] == "success", notice(app)
    (employee_id,) = app.session_state["added"][f"employee@{SITE}"]
    assert records("employee", SITE)[employee_id][0]["name"] == "Kim"


def test_refusal_shows_the_message_and_problems(app):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_bad", "title": "X <b>"})
    click(app, "manage-job_code-add-submit")
    assert [e.value for e in app.error] == [escape_md("invalid record")]
    problems = problem_frame(app)
    assert list(problems.columns) == ["field", "reason"]
    assert problems.iloc[0]["field"] == "title"


# ------------------------------------------------------- bulk upload (WF6)


def _uploader_key(at, kind, site=None):
    try:
        generation = at.session_state["upload_generation"].get((kind, site), 0)
    except KeyError:
        generation = 0
    return f"manage-{kind}-file@{site or ''}#{generation}"


def _upload(at, kind, text, file_name="jobs.csv", site=None):
    at.file_uploader(key=_uploader_key(at, kind, site)).set_value((file_name, text.encode(), "text/csv"))
    return click(at, f"manage-{kind}-upload")


def test_accepted_upload_adds_every_row(app):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    assert app.session_state["templates"][("job_code", None)]["columns"] == ["job_code", "title"]
    _upload(app, "job_code", 'job_code,title\njc_a,A\n\njc_b,"B, the second"\n')
    assert notice(app)["message"] == "Added 2 records from jobs.csv."
    assert app.session_state["added"]["job_code"] == ["jc_a", "jc_b"]
    assert records("job_code")["jc_b"][0]["title"] == "B, the second"


def test_refused_upload_lists_problem_rows_and_saves_nothing(app):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    _upload(app, "job_code", "job_code,title\njc_a,A\n,B\njc_c\n")
    assert notice(app)["level"] == "error"
    assert actions.NOTHING_SAVED in [c.value for c in app.caption] or escape_md(actions.NOTHING_SAVED) in [
        c.value for c in app.caption
    ]
    problems = problem_frame(app)
    assert list(problems.columns) == ["row", "field", "reason"]
    assert set(problems["row"]) >= {2, 3}
    assert not {"jc_a", "jc_c"} & set(records("job_code"))


def test_upload_refused_locally_sends_nothing(app):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    before = len(_entries())
    _upload(app, "job_code", "code,title\njc_a,A\n")
    assert notice(app)["message"] == "The header must be: job_code,title."
    assert len(_entries()) == before


# ---------------------------------------- unconfirmed writes (WF7, WF8)


def test_no_answer_write_shows_the_banner_in_the_same_run_and_try_again_saves_once(app, faults):
    log_in(app, REGIONAL)
    hold_a_write(app, faults, "jc_r")
    # Same run: the banner is drawn and every write control is disabled (NFR2.3).
    assert any("We couldn't confirm this was saved" in w.value for w in app.warning)
    assert {"notice-try-again", "notice-discard"} <= button_keys(app)
    assert app.button(key="manage-job_code-add-submit").disabled
    assert app.button(key="manage-job_code-upload").disabled
    assert escape_md(manage_tab.HELD_NOTE) in [c.value for c in app.caption]
    assert "jc_r" not in records("job_code")

    click(app, "notice-try-again")
    assert notice(app)["message"] == "Added job code jc_r."
    assert app.session_state["pending_retry"] is None
    assert not app.button(key="manage-job_code-add-submit").disabled
    allowed = [e for e in _entries() if e["kind"] == "job_code" and e["outcome"] == "allowed"]
    assert [e["record_id"] for e in allowed] == ["jc_r"]
    assert app.session_state["added"]["job_code"] == ["jc_r"]


def test_try_again_that_gets_no_answer_keeps_the_banner(app, faults):
    log_in(app, REGIONAL)
    hold_a_write(app, faults)
    faults["retry_write"] = "no-answer"
    click(app, "notice-try-again")
    assert app.session_state["pending_retry"] is not None
    assert "notice-try-again" in button_keys(app)


def test_discard_drops_the_held_write(app, faults):
    log_in(app, REGIONAL)
    hold_a_write(app, faults)
    click(app, "notice-discard")
    assert app.session_state["pending_retry"] is None
    assert notice(app)["message"] == actions.DISCARDED
    assert "notice-try-again" not in button_keys(app)
    assert not app.button(key="manage-job_code-add-submit").disabled


def test_after_discard_the_next_submit_carries_a_new_request_id(app, faults):
    # NFR2.2: the held request's id is never sent again from the form.
    log_in(app, REGIONAL)
    hold_a_write(app, faults, "jc_n2")
    held_id = app.session_state["pending_retry"]["error"].request_id
    click(app, "notice-discard")
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_n2", "title": "Held"})
    click(app, "manage-job_code-add-submit")
    assert notice(app)["message"] == "Added job code jc_n2."
    assert app.session_state["request_ids"][("add", "job_code", None)]["id"] != held_id
    assert "jc_n2" in records("job_code")


def test_one_logout_click_with_a_held_write_logs_out_and_says_it_was_dropped(app, faults):
    # NFR2.4 as amended (NFR-design Q1: B): no prompt.
    log_in(app, REGIONAL)
    session_id = app.session_state["login"]["session_id"]
    hold_a_write(app, faults)
    click(app, "session-logout")
    assert app.session_state["login"] is None
    assert app.session_state["pending_retry"] is None
    assert tab_labels(app) == []
    assert button_keys(app) == {"session-login", markers.SIGN_OUT_BUTTON}
    assert [w.value for w in app.warning] == [escape_md(actions.LOGGED_OUT + actions.LOGOUT_WRITE_DROPPED)]
    assert session.client_for(REGIONAL).session_status(session_id)["active"] is False


def test_unexpected_client_error_still_renders_the_page(app, faults):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    faults["add_record"] = RuntimeError("boom")
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_u", "title": "U"})
    click(app, "manage-job_code-add-submit")
    assert notice(app)["message"] == "Something went wrong: RuntimeError"
    assert tab_labels(app) == TABS
    assert app.session_state["login"] is not None

    # A failing read is shown in place of the Manage data tab; the rest renders.
    # Refresh data empties both caches, this session's Manage data reads included.
    faults["list_records"] = RuntimeError("boom")
    app.button[[b.label for b in app.button].index("Refresh data")].click().run()
    assert not app.exception, app.exception
    assert not app.exception
    assert f"Something went wrong: {escape_md('RuntimeError')}" in [e.value for e in app.error]
    assert tab_labels(app) == TABS


# ---------------------------------------------------- session end (WF2)


def test_session_ended_by_the_clock_logs_out_with_the_reason(app, clock):
    log_in(app, REGIONAL)
    clock(timedelta(minutes=16))
    app.run()
    assert app.session_state["login"] is None
    assert notice(app)["message"] == actions.ENDED_REASONS["idle"]
    assert tab_labels(app) == []
    assert "session-login" in button_keys(app)


def test_session_ended_with_a_held_write_says_it_was_dropped(app, faults, clock):
    log_in(app, REGIONAL)
    hold_a_write(app, faults)
    clock(timedelta(minutes=16))
    app.run()
    assert app.session_state["login"] is None
    assert notice(app)["message"] == actions.ENDED_REASONS["idle"] + actions.WRITE_DROPPED
    assert app.session_state["pending_retry"] is None


def test_unreachable_session_check_keeps_the_login_and_the_banner(app, faults):
    log_in(app, REGIONAL)
    hold_a_write(app, faults)
    faults["session_status"] = "no-answer"
    app.run()
    assert app.session_state["login"] is not None
    assert escape_md(actions.UNREACHABLE) in [e.value for e in app.error]
    assert tab_labels(app) == []
    assert "notice-try-again" in button_keys(app)


# --------------------------------------------------------- audit (WF9)


def _audit_frame(at):
    return next(df.value for df in at.dataframe if "outcome" in df.value.columns)


def test_audit_tab_pages_filters_and_shows_an_entrys_changes(app):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    base = app.session_state["audit"]["total"]
    rows = "".join(f"jc_{i:02d},Job {i}\n" for i in range(60))
    _upload(app, "job_code", "job_code,title\n" + rows)
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_v", "title": "X <b>"})
    click(app, "manage-job_code-add-submit")
    total = app.session_state["audit"]["total"]
    assert total == base + 61
    assert f"Showing {escape_md(50)} of {escape_md(total)} entries" in [c.value for c in app.caption]

    click(app, "audit-load-older")
    assert f"Showing {escape_md(total)} of {escape_md(total)} entries" in [c.value for c in app.caption]
    assert "audit-load-older" not in button_keys(app)

    app.selectbox(key="audit-outcome").set_value("violation").run()
    violations = _audit_frame(app)
    assert list(violations["outcome"]) == ["violation"]
    app.selectbox(key="audit-outcome").set_value("All").run()
    app.selectbox(key="audit-kind").set_value("job_code").run()
    assert len(_audit_frame(app)) == 61

    entry_id = app.session_state["audit"]["entries"][0]["entry_id"]
    app.selectbox(key="audit-entry").set_value(entry_id).run()
    changes = app.dataframe[-1].value
    assert list(changes.columns) == ["change", "value"]
    assert "record.title" in set(changes["change"])

    click(app, "audit-refresh")
    assert len(app.session_state["audit"]["entries"]) == 50


def test_audit_reloads_after_every_write_outcome(app):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    before = app.session_state["audit"]["total"]
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_w", "title": "W"})
    click(app, "manage-job_code-add-submit")
    assert app.session_state["audit"]["total"] == before + 1


# ------------------------------------------------ escaping and secrets


def test_notices_are_escaped_but_options_are_shown_as_is(app):
    # Notices render Markdown, so they are escaped (NFR1.5). Selectbox options
    # are plain text in Streamlit, so escaping them would show stray
    # backslashes (final review R-02).
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    _upload(app, "job_code", "job_code,title\njc_a-b_c,A\n", file_name="**b**_[l](u).csv")
    message = "Added 1 records from **b**_[l](u).csv."
    assert [s.value for s in app.success] == [escape_md(message)]
    assert app.selectbox(key="manage-job_code-edit-pick@").options == ["jc_a-b_c"]


def test_no_element_shows_the_session_id(app):
    log_in(app, REGIONAL)
    session_id = app.session_state["login"]["session_id"]
    pick(app, "Staff", "job_code")
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_n", "title": "N"})
    click(app, "manage-job_code-add-submit")
    _upload(app, "job_code", "job_code,title\njc_m,M\n")
    app.selectbox(key="audit-entry").set_value(app.session_state["audit"]["entries"][0]["entry_id"]).run()
    text = "\n".join(_all_text(app._tree))
    assert session_id not in text


def test_a_repeat_click_after_a_success_sends_nothing_and_a_re_entered_add_is_new(app, monkeypatch):
    # NFR2.1: a click on the cleared form sends nothing (R-11). Values typed
    # in again after a success are a new add with a new request id, so they
    # are checked afresh rather than answered from the stored response
    # (final review R-03); for a job code that is a refusal.
    sent = []
    add_record = HsmClient.add_record

    def counted(self, *args, **kwargs):
        sent.append(kwargs["request_id"])
        return add_record(self, *args, **kwargs)

    monkeypatch.setattr(HsmClient, "add_record", counted)
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    values = {"job_code": "jc_d", "title": "Twice"}
    fill(app, "add", "job_code", None, None, None, values)
    click(app, "manage-job_code-add-submit")
    assert notice(app)["message"] == "Added job code jc_d."
    click(app, "manage-job_code-add-submit")
    assert len(sent) == 1  # the cleared form sends nothing
    fill(app, "add", "job_code", None, None, None, values)
    click(app, "manage-job_code-add-submit")
    assert len(sent) == 2 and sent[0] != sent[1]
    assert notice(app)["level"] == "error"  # jc_d already exists
    allowed = [e for e in _entries() if e["kind"] == "job_code" and e["outcome"] == "allowed"]
    assert len(allowed) == 1
    assert app.session_state["added"]["job_code"] == ["jc_d"]


def test_two_identical_employee_adds_create_two_employees(app):
    # Final review R-03: the backend generates employee ids, so the same
    # values entered twice are two people, not a replay.
    client, session_id = admin_client()
    client.add_record("job_code", {"job_code": "jc_twin", "title": "Twin"}, session_id)
    log_in(app, RM)
    pick(app, "Staff", "employee")
    values = {
        "name": "Alex",
        "job_code": "jc_twin",
        "hourly_rate": 15.0,
        "max_weekly_hours_preference": 40,
        "available_days": ["Mon"],
    }
    for _ in range(2):
        fill(app, "add", "employee", SITE, None, None, values)
        click(app, "manage-employee-add-submit")
        assert notice(app)["level"] == "success", notice(app)
    added = app.session_state["added"][f"employee@{SITE}"]
    assert len(set(added)) == 2
    assert all(records("employee", SITE)[e][0]["name"] == "Alex" for e in added)


def test_a_successful_upload_empties_the_picker_so_a_repeat_click_sends_nothing(app, monkeypatch):
    sent = []
    bulk_add = HsmClient.bulk_add

    def counted(self, *args, **kwargs):
        sent.append(kwargs["request_id"])
        return bulk_add(self, *args, **kwargs)

    monkeypatch.setattr(HsmClient, "bulk_add", counted)
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    _upload(app, "job_code", "job_code,title\njc_up,Up\n")
    assert notice(app)["level"] == "success"
    assert app.file_uploader(key=_uploader_key(app, "job_code")).value is None
    click(app, "manage-job_code-upload")
    assert len(sent) == 1
    assert notice(app)["message"] == "Pick a .csv file first."


def test_no_element_shows_the_session_id_or_a_traceback(app, faults, clock):
    # NFR1.7: after a refused write, an unconfirmed write and an expired session.
    log_in(app, REGIONAL)
    session_id = app.session_state["login"]["session_id"]

    def shown():
        return "\n".join(_all_text(app._tree))

    pick(app, "Staff", "job_code")
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_bad", "title": "X <b>"})
    click(app, "manage-job_code-add-submit")
    assert notice(app)["level"] == "error"
    assert session_id not in shown() and "Traceback" not in shown()

    hold_a_write(app, faults, "jc_t2")
    assert session_id not in shown() and "Traceback" not in shown()

    clock(timedelta(minutes=16))
    app.run()
    assert app.session_state["login"] is None
    assert session_id not in shown() and "Traceback" not in shown()


def test_identical_resubmission_after_a_refusal_sends_a_new_id(app):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    values = {"job_code": "jc_bad", "title": "X <b>"}
    fill(app, "add", "job_code", None, None, None, values)
    click(app, "manage-job_code-add-submit")
    first = app.session_state["request_ids"][("add", "job_code", None)]["id"]
    fill(app, "add", "job_code", None, None, None, values)
    click(app, "manage-job_code-add-submit")
    assert app.session_state["request_ids"][("add", "job_code", None)]["id"] != first
    assert len([e for e in _entries() if e["outcome"] == "violation"]) == 2


# ------------------------------------- per-session Manage data cache (Q3)


@pytest.fixture
def list_reads(monkeypatch):
    """Count the dashboard's ``list_records`` reads, as (kind, site)."""
    seen = []
    list_records = HsmClient.list_records

    def counted(self, kind, site_id=None):
        seen.append((kind, site_id))
        return list_records(self, kind, site_id=site_id)

    monkeypatch.setattr(HsmClient, "list_records", counted)
    return seen


def test_a_refresh_without_a_write_makes_no_repeat_manage_data_read(app, list_reads):
    # NFR4.3: a plain rerun is served from this session's cache.
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    assert ("job_code", None) in list_reads
    list_reads.clear()
    app.run()
    app.run()
    assert list_reads == []


def test_manage_data_reads_expire_after_60_seconds(app, list_reads, monkeypatch):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    list_reads.clear()
    later = datetime.now(timezone.utc) + timedelta(seconds=61)
    monkeypatch.setattr(session, "_now", lambda: later)
    app.run()
    assert ("job_code", None) in list_reads


def test_a_write_outcome_reloads_the_manage_data_reads(app, list_reads):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    list_reads.clear()
    fill(app, "add", "job_code", None, None, None, {"job_code": "jc_rr", "title": "R"})
    click(app, "manage-job_code-add-submit")
    assert ("job_code", None) in list_reads
    assert "jc_rr" in set(record_frame(app)["job_code"])


# ========================================================= timing (NFR4)


@pytest.fixture
def calls(monkeypatch):
    """Count every HTTP call the dashboard's clients make, as (method, path)."""
    seen = []
    send, request = HsmClient._send, HsmClient._request

    def counted_send(self, method, path, *args, **kwargs):
        seen.append((method, unquote(path)))
        return send(self, method, path, *args, **kwargs)

    def counted_request(self, method, path, *args, **kwargs):
        seen.append((method, unquote(path)))
        return request(self, method, path, *args, **kwargs)

    monkeypatch.setattr(HsmClient, "_send", counted_send)
    monkeypatch.setattr(HsmClient, "_request", counted_request)
    return seen


def _bulk_job_codes(count, prefix):
    """``count`` dashboard-added job codes, 100 per session (the entry limit)."""
    client = session.client_for(REGIONAL)
    for start in range(0, count, 100):
        session_id = client.start_session()["session_id"]
        rows = [
            {"row": i + 1, "record": {"job_code": f"{prefix}{start + i:04d}", "title": f"Job {start + i}"}}
            for i in range(min(100, count - start))
        ]
        client.bulk_add("job_code", rows, "seed.csv", session_id)


@pytest.mark.perf
def test_nfr4_1_drawing_a_kind_of_300_records_takes_at_most_2_seconds(app):
    _bulk_job_codes(300 - len(records("job_code")), "jc_p")
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    assert len(record_frame(app)) == 300
    started = time.perf_counter()
    app.run()  # every read served from the cache
    elapsed = time.perf_counter() - started
    assert not app.exception
    print(f"NFR4.1 warm run with 300 records: {elapsed:.3f} s (target 2 s)")
    assert elapsed <= 2.0, f"NFR4.1: warm run took {elapsed:.3f} s (target 2 s)"


@pytest.mark.perf
def test_nfr4_2_a_500_row_upload_shows_its_result_within_5_seconds(app, monkeypatch):
    # The backend accepts 100 adds per kind per session (BR6.1), so a single
    # accepted 500-row file needs the limit raised for this test only. The
    # measured path (read, send, answer, redraw) is unchanged.
    monkeypatch.setattr(writes, "ENTRY_LIMIT", 500)
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    rows = "".join(f"jc_{i:04d},Job {i}\n" for i in range(500))
    app.file_uploader(key=_uploader_key(app, "job_code")).set_value(
        ("big.csv", ("job_code,title\n" + rows).encode(), "text/csv")
    )
    app.button(key="manage-job_code-upload").click()
    started = time.perf_counter()
    app.run()
    elapsed = time.perf_counter() - started
    assert notice(app)["message"] == "Added 500 records from big.csv."
    print(f"NFR4.2 500-row upload run: {elapsed:.3f} s (target 5 s)")
    assert elapsed <= 5.0, f"NFR4.2: upload run took {elapsed:.3f} s (target 5 s)"


@pytest.mark.perf
def test_nfr4_3_reruns_make_only_the_session_check(app, calls):
    log_in(app, REGIONAL)
    pick(app, "Staff", "job_code")
    app.run()
    session_id = app.session_state["login"]["session_id"]
    calls.clear()
    app.run()
    app.run()
    assert calls == [("GET", f"/sessions/{session_id}")] * 2


def _existing_reads(client, user, site_id):
    """The reads the existing tabs made before U4, per refresh: load_sites,
    load_site_bundle and load_region in dashboard/app.py, unchanged by U4."""
    sites = client.get_sites()
    site = client.get_site(site_id)
    client.get_employees(site_id)
    shifts = client.get_published_schedule(site_id)
    if shifts and isinstance(shifts, list):
        client.validate_schedule(site["jurisdiction"], shifts)
    data.labor_demand(client, site_id, start_offset=7)
    data.sales_vs_forecast(client, site_id)
    client.get_labor_rules(site["jurisdiction"])
    data.on_hand_frame(client.get_on_hand(site_id), client.get_raw_materials())
    data.usage_anomalies(client, site_id)
    data.reorder_needs(client, site_id)
    client.get_vendors()
    client.get_purchase_orders(site_id=site_id)
    if user["region_id"]:
        data.region_rollup(client, client.get_sites(region_id=user["region_id"]))
        client.get_purchase_orders(region_id=user["region_id"])
    return sites


U4_PREFIXES = ("/sessions", "/audit")


@pytest.mark.perf
def test_nfr4_4_a_logged_in_refresh_makes_the_same_overview_reads_as_before(app, calls):
    log_in(app, REGIONAL)
    calls.clear()
    app.button[[b.label for b in app.button].index("Refresh data")].click().run()
    assert not app.exception
    refreshed = list(calls)

    calls.clear()
    _existing_reads(session.client_for(REGIONAL), USERS[REGIONAL], SITE)
    expected = Counter(calls)

    # Take away the Manage data tab's own reads (the default kind and the
    # kinds it references), the session check, the template and the audit page.
    kind = kind_forms.DATA_SETS["Menu"][0]
    list_reads = Counter()
    calls.clear()
    for name in [kind, *kind_forms.referenced_kinds(kind)]:
        session.client_for(REGIONAL).list_records(name)
    list_reads.update(calls)
    existing = Counter(refreshed) - list_reads
    existing = Counter(
        {
            call: n
            for call, n in existing.items()
            if not call[1].startswith(U4_PREFIXES) and not call[1].endswith("/template")
        }
    )
    assert existing == expected
