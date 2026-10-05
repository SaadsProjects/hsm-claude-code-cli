"""
Unit tests for the dashboard's write screens (unit U4) that need no running
app: the pure modules ``kind_forms``, ``safe_text`` and ``csv_rows``, the
button actions in ``actions`` and the per-session Manage data cache in
``session``, run against a fake client with a plain dict standing in for
Streamlit's session state.

tests/conftest.py gives every test its own audit file and resets the
backend's write state afterwards.
"""

import ast
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hsm_client import HsmApiError, HsmUnavailable, SessionExpired
from dashboard import actions, csv_rows, kind_forms, session
from dashboard.safe_text import escape_md
from mock_hsm import db, writes

# ================================================================ KindForms

_INPUT_FOR = {
    "id": kind_forms.TEXT,
    "text": kind_forms.TEXT,
    "ref": kind_forms.REF,
    "number": kind_forms.NUMBER,
    "integer": kind_forms.WHOLE,
    "gl_code": kind_forms.GL_CODE,
    "days": kind_forms.DAYS_INPUT,
    "lines": kind_forms.LINES,
    "price_list": kind_forms.PRICE_LIST,
}


def test_kind_forms_match_the_backend_catalog():
    # Drift guard: same kinds, scope, key, key mode and fields (names, order, input type, referenced kind).
    assert set(kind_forms.KIND_FORMS) == set(writes.KINDS)
    for name, kind in writes.KINDS.items():
        form = kind_forms.KIND_FORMS[name]
        assert (form.scope, form.key, form.key_mode, form.label) == (kind.scope, kind.key, kind.key_mode, kind.label)
        assert [f.name for f in form.fields] == [f.name for f in kind.fields], name
        for form_field, kind_field in zip(form.fields, kind.fields, strict=True):
            assert form_field.input == _INPUT_FOR[kind_field.type], (name, kind_field.name)
            assert form_field.ref == kind_field.ref, (name, kind_field.name)
    assert kind_forms.GL_CODES == db.GL_CODES
    assert kind_forms.DAYS == writes.DAYS
    assert [p.name for p in kind_forms.LINE_PARTS] == [f.name for f in writes._LINE_FIELDS]


def test_data_sets_group_all_eleven_kinds():
    assert kind_forms.DATA_SETS == {
        "Menu": ("menu_item", "recipe"),
        "Ingredients and suppliers": ("raw_material", "uom", "vendor"),
        "Staff": ("employee", "job_code"),
        "Stock levels": ("on_hand", "par_level", "reorder_point"),
        "Labor rules": ("labor_rule",),
    }


@pytest.mark.parametrize(
    ("kind", "values", "expected"),
    [
        (
            "menu_item",
            {"menu_item_id": "mi_x", "name": "X", "gl_code": "GL-FOOD"},
            {"menu_item_id": "mi_x", "name": "X", "gl_code": "GL-FOOD"},
        ),
        (
            "recipe",
            {
                "menu_item_id": "mi_x",
                "lines": [
                    {"raw_material_id": "rm_a", "qty": 1.5, "uom": "u"},
                    {"raw_material_id": None, "qty": None, "uom": None},
                    {"raw_material_id": "rm_b", "qty": None, "uom": None},
                ],
            },
            {
                "menu_item_id": "mi_x",
                "lines": [
                    {"raw_material_id": "rm_a", "qty": 1.5, "uom": "u"},
                    {"raw_material_id": "rm_b", "qty": None, "uom": None},
                ],
            },
        ),
        (
            "raw_material",
            {"raw_material_id": "rm_a", "name": "A", "uom": "u"},
            {"raw_material_id": "rm_a", "name": "A", "uom": "u"},
        ),
        (
            "uom",
            {"uom_id": "u", "name": "unit", "base": "u", "factor_to_base": 1.0},
            {"uom_id": "u", "name": "unit", "base": "u", "factor_to_base": 1.0},
        ),
        (
            "vendor",
            {
                "vendor_id": "v",
                "name": "V",
                "lead_time_days": 2,
                "min_order_value": 50.0,
                "price_list": [
                    {"raw_material_id": "rm_a", "price": 3.0},
                    {"raw_material_id": None, "price": None},
                    {"raw_material_id": None, "price": 4.0},
                ],
            },
            {
                "vendor_id": "v",
                "name": "V",
                "lead_time_days": 2,
                "price_list": {"rm_a": 3.0, "": 4.0},
                "min_order_value": 50.0,
            },
        ),
        (
            "employee",
            {
                "name": "E",
                "job_code": "jc",
                "hourly_rate": 15.0,
                "max_weekly_hours_preference": 30,
                "available_days": ("Mon", "Tue"),
                "employee_id": "ignored",
            },
            {
                "name": "E",
                "job_code": "jc",
                "hourly_rate": 15.0,
                "max_weekly_hours_preference": 30,
                "available_days": ["Mon", "Tue"],
            },
        ),
        ("job_code", {"job_code": "jc", "title": "T"}, {"job_code": "jc", "title": "T"}),
        ("on_hand", {"raw_material_id": "rm_a", "qty": 4.0}, {"raw_material_id": "rm_a", "qty": 4.0}),
        ("par_level", {"raw_material_id": "rm_a", "qty": 4.0}, {"raw_material_id": "rm_a", "qty": 4.0}),
        ("reorder_point", {"raw_material_id": "rm_a", "qty": None}, {"raw_material_id": "rm_a", "qty": None}),
        (
            "labor_rule",
            {
                "jurisdiction": "XX",
                "weekly_ot_threshold_hours": 40.0,
                "daily_ot_threshold_hours": 8.0,
                "ot_multiplier": 1.5,
                "max_consecutive_days": 6,
                "min_rest_hours_between_shifts": 8.0,
                "max_shift_length_hours": 12.0,
                "note": "n",
            },
            {
                "jurisdiction": "XX",
                "weekly_ot_threshold_hours": 40.0,
                "daily_ot_threshold_hours": 8.0,
                "ot_multiplier": 1.5,
                "max_consecutive_days": 6,
                "min_rest_hours_between_shifts": 8.0,
                "max_shift_length_hours": 12.0,
                "note": "n",
            },
        ),
    ],
)
def test_build_record_per_kind(kind, values, expected):
    assert kind_forms.build_record(kind, values) == expected


def test_build_record_sends_missing_values_for_the_backend_to_report():
    # The dashboard does not check values: an empty form becomes a record of empty values.
    assert kind_forms.build_record("menu_item", {}) == {"menu_item_id": None, "name": None, "gl_code": None}
    assert kind_forms.build_record("recipe", {"menu_item_id": "m"}) == {"menu_item_id": "m", "lines": []}


def test_slot_count_never_truncates_a_stored_record():
    assert kind_forms.slot_count() == 10
    assert kind_forms.slot_count(7) == 10
    lines = [{"raw_material_id": f"rm_{i}", "qty": i, "uom": "u"} for i in range(14)]
    form = kind_forms.KIND_FORMS["recipe"]
    stored = kind_forms.stored_slots("recipe", form.field("lines"), {"lines": lines})
    assert len(stored) == 14
    assert kind_forms.slot_count(len(stored)) == 17
    # Every stored line survives a round trip through the slots.
    assert kind_forms.build_record("recipe", {"menu_item_id": "m", "lines": stored})["lines"] == lines


def test_stored_price_list_becomes_slots():
    form = kind_forms.KIND_FORMS["vendor"]
    slots = kind_forms.stored_slots("vendor", form.field("price_list"), {"price_list": {"a": 1, "b": 2}})
    assert slots == [{"raw_material_id": "a", "price": 1}, {"raw_material_id": "b", "price": 2}]
    with pytest.raises(ValueError, match="no line slots"):
        kind_forms.stored_slots("vendor", form.field("name"), {})


@pytest.mark.parametrize(
    ("user_id", "expected"), [("user_rm_midtown", False), ("user_regional_atl", True), ("user_dev_tester", True)]
)
def test_region_wide_detection_for_every_persona(user_id, expected):
    assert kind_forms.is_region_wide(db.USERS[user_id]) is expected


def test_region_wide_detection_handles_missing_entries():
    assert kind_forms.is_region_wide(None) is False
    assert kind_forms.is_region_wide({"region_id": ""}) is False


def test_field_key_is_distinct_across_mode_record_version_and_site():
    keys = {
        kind_forms.field_key("add", "vendor", None, None, None, "name"),
        kind_forms.field_key("edit", "vendor", None, "v1", 1, "name"),
        kind_forms.field_key("edit", "vendor", None, "v1", 2, "name"),
        kind_forms.field_key("edit", "vendor", None, "v2", 1, "name"),
        kind_forms.field_key("edit", "employee", "site_001", "v1", 1, "name"),
        kind_forms.field_key("edit", "employee", "site_002", "v1", 1, "name"),
        # A record key containing the separator characters cannot collide with another field.
        kind_forms.field_key("edit", "vendor", None, 'a","b', 1, "name"),
        kind_forms.field_key("edit", "vendor", None, "a", 1, 'b","name'),
    }
    assert len(keys) == 8
    assert kind_forms.field_key("add", "vendor", "", "", "", "x") == kind_forms.field_key(
        "add", "vendor", None, None, None, "x"
    )


def test_referenced_kinds_and_blank_detection():
    assert kind_forms.referenced_kinds("recipe") == ["menu_item", "raw_material", "uom"]
    assert kind_forms.referenced_kinds("vendor") == ["raw_material"]
    assert kind_forms.referenced_kinds("job_code") == []
    assert kind_forms.is_blank("recipe", {"menu_item_id": None, "lines": [{"raw_material_id": None, "qty": None}]})
    assert not kind_forms.is_blank("recipe", {"menu_item_id": None, "lines": [{"raw_material_id": None, "qty": 1}]})
    assert kind_forms.is_blank("employee", {"name": "", "available_days": []})
    assert not kind_forms.is_blank("employee", {"name": "", "available_days": ["Mon"]})
    assert kind_forms.is_blank("job_code", {"job_code": "jc", "title": ""}, skip=("job_code",))


# ================================================================= SafeText


def test_escape_md_escapes_markdown_html_entities_colour_and_math():
    raw = "**b** <b>x</b> [l](u) :red[x] $m$ &lt; # h"
    assert escape_md(raw) == (r"\*\*b\*\* \<b\>x\</b\> \[l\]\(u\) \:red\[x\] \$m\$ \&lt; \# h")


def test_escape_md_full_set_none_and_plain_text():
    assert escape_md(None) == ""
    assert escape_md("plain text 123") == "plain text 123"
    for ch in "\\`*_{}[]()#+-.!|~><:$&":
        assert escape_md(ch) == "\\" + ch
    assert escape_md(42) == "42"


def test_escape_md_keeps_line_breaks():
    assert escape_md("a\nb\r\nc") == "a\nb\r\nc"


# ================================================================ CsvReader

COLUMNS = ("vendor_id", "name", "price_list")


def _read(text, columns=COLUMNS, encoding="utf-8"):
    return csv_rows.read_upload(text.encode(encoding), columns)


def test_csv_dialect_quotes_commas_doubled_quotes_and_crlf():
    result = _read('vendor_id,name,price_list\r\nv1,"Acme, Inc.","a=1;b=2"\r\nv2,"Say ""hi""",c=3\r\n')
    assert result.refusal is None
    assert result.rows == [
        {"row": 1, "record": {"vendor_id": "v1", "name": "Acme, Inc.", "price_list": "a=1;b=2"}},
        {"row": 2, "record": {"vendor_id": "v2", "name": 'Say "hi"', "price_list": "c=3"}},
    ]


def test_csv_quoted_line_break_is_one_row_and_numbering_continues():
    result = _read('vendor_id,name,price_list\nv1,"two\nlines",a=1\nv2,n,b=2\n')
    assert [r["row"] for r in result.rows] == [1, 2]
    assert result.rows[0]["record"]["name"] == "two\nlines"


def test_csv_blank_record_skipped_but_keeps_its_number():
    result = _read("vendor_id,name,price_list\nv1,a,x\n\nv2,b,y\n")
    assert [r["row"] for r in result.rows] == [1, 3]


def test_csv_wrong_cell_count_becomes_a_parse_error_row_and_cells_are_untrimmed():
    result = _read("vendor_id,name,price_list\nv1,a,x,\nv2\n  v3 , b , y \n")
    assert result.rows == [
        {"row": 1, "parse_error": "expected 3 values, found 4"},  # a trailing empty cell counts
        {"row": 2, "parse_error": "expected 3 values, found 1"},
        {"row": 3, "record": {"vendor_id": "  v3 ", "name": " b ", "price_list": " y "}},
    ]


def test_csv_bom_accepted_and_header_trimmed():
    result = csv_rows.read_upload(b"\xef\xbb\xbf vendor_id , name,price_list\nv1,a,x\n", COLUMNS)
    assert result.refusal is None and len(result.rows) == 1


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", csv_rows.EMPTY),
        (b"\r\n\n", csv_rows.EMPTY),
        (b"vendor_id,name,price_list\n\xff\xfe,x,y\n", csv_rows.NOT_UTF8),
        (b"vendor_id,name\nv1,a\n", "The header must be: vendor_id,name,price_list."),
        (b"Vendor_id,name,price_list\nv1,a,x\n", "The header must be: vendor_id,name,price_list."),
        (b"name,vendor_id,price_list\nv1,a,x\n", "The header must be: vendor_id,name,price_list."),
        (b'vendor_id,name,price_list\nv1,"open,x\n', "The file could not be read as CSV: unexpected end of data."),
    ],
)
def test_csv_local_refusals(data, message):
    result = csv_rows.read_upload(data, COLUMNS)
    assert result == (None, message)


def test_csv_header_only_file_gives_no_rows():
    # Sent as is: the backend refuses a file with no rows and audits the refusal.
    assert _read("vendor_id,name,price_list\n").rows == []


def test_csv_raw_size_over_the_limit_is_refused_before_parsing(monkeypatch):
    def no_parse(*args, **kwargs):
        raise AssertionError("parsed an oversized file")

    monkeypatch.setattr(csv_rows.csv, "reader", no_parse)
    data = b"vendor_id,name,price_list\n" + b"x" * csv_rows.MAX_BULK_BYTES
    assert csv_rows.read_upload(data, COLUMNS) == (None, csv_rows.TOO_LARGE)


def _rows_of_size(target, cell_char="a"):
    """Rows whose encoded bulk body is exactly ``target`` bytes (one big name cell, padded)."""
    rows = [{"row": 1, "record": {"vendor_id": "v", "name": "", "price_list": "x"}}]
    base = csv_rows.encoded_bulk_size(rows, "f.csv")
    per_char = (
        csv_rows.encoded_bulk_size([{"row": 1, "record": {**rows[0]["record"], "name": cell_char}}], "f.csv") - base
    )
    count, rest = divmod(target - base, per_char)
    rows[0]["record"]["name"] = cell_char * count + "a" * rest
    return rows


def test_encoded_size_just_under_and_just_over_the_limit():
    under = _rows_of_size(csv_rows.MAX_BULK_BYTES - 1024)  # 959 KiB
    exact = _rows_of_size(csv_rows.MAX_BULK_BYTES)
    over = _rows_of_size(csv_rows.MAX_BULK_BYTES + 1024)  # 961 KiB
    assert csv_rows.encoded_bulk_size(under, "f.csv") == csv_rows.MAX_BULK_BYTES - 1024
    assert csv_rows.fits(under, "f.csv") and csv_rows.fits(exact, "f.csv")
    assert csv_rows.encoded_bulk_size(over, "f.csv") == csv_rows.MAX_BULK_BYTES + 1024
    assert not csv_rows.fits(over, "f.csv")


def test_encoded_size_matches_the_client_encoding_with_real_ids():
    import json

    rows = [{"row": 1, "record": {"vendor_id": "v", "name": "Café", "price_list": "x"}}]
    session_id, request_id = "s" * 43, "r" * 32
    body = {"session_id": session_id, "request_id": request_id, "source": "csv", "file_name": "f.csv", "rows": rows}
    assert csv_rows.encoded_bulk_size(rows, "f.csv", session_id, request_id) == len(json.dumps(body).encode())
    assert csv_rows.encoded_bulk_size(rows, "f.csv") == len(json.dumps(body).encode())  # placeholders, same length


def test_non_ascii_file_under_the_raw_limit_can_exceed_the_encoded_limit():
    # "é" is 2 bytes of UTF-8 but 6 bytes once JSON-escaped (é).
    cell = "é" * 200_000
    data = ("vendor_id,name,price_list\nv1," + cell + ",x\n").encode()
    assert len(data) < csv_rows.MAX_BULK_BYTES
    result = csv_rows.read_upload(data, COLUMNS)
    assert result.refusal is None
    assert not csv_rows.fits(result.rows, "f.csv")


# ===================================================== Actions and Outcomes

SITE = "site_001"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
LOGIN = {"session_id": "sid-secret-1", "user_id": "user_regional_atl", "persona": "REGIONAL_MANAGER"}


class FakeClient:
    """Stands in for HsmClient. Each method records its call and runs the
    behaviour scripted in ``self.script`` (a callable, or an exception to
    raise), falling back to a plausible success."""

    def __init__(self):
        self.calls = []
        self.script = {}

    def _run(self, name, default, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        behaviour = self.script.get(name)
        if isinstance(behaviour, list):
            behaviour = behaviour.pop(0)
        if isinstance(behaviour, BaseException):
            raise behaviour
        if callable(behaviour):
            return behaviour(*args, **kwargs)
        return default if behaviour is None else behaviour

    def names(self):
        return [name for name, _, _ in self.calls]

    def start_session(self):
        return self._run("start_session", {"session_id": "sid-new", "persona": "REGIONAL_MANAGER"})

    def end_session(self, session_id):
        return self._run("end_session", {"active": False, "ended_reason": "logout"}, session_id)

    def session_status(self, session_id):
        return self._run("session_status", {"active": True, "ended_reason": None}, session_id)

    def add_record(self, kind, record, session_id, site_id=None, request_id=None):
        return self._run(
            "add_record",
            {"record": record, "meta": {}},
            kind,
            record,
            session_id,
            site_id=site_id,
            request_id=request_id,
        )

    def update_record(self, kind, record_id, record, version, session_id, site_id=None, request_id=None):
        return self._run(
            "update_record",
            {"record": record, "meta": {}},
            kind,
            record_id,
            record,
            version,
            session_id,
            site_id=site_id,
            request_id=request_id,
        )

    def delete_record(self, kind, record_id, version, session_id, site_id=None, request_id=None):
        return self._run(
            "delete_record",
            {"deleted": True},
            kind,
            record_id,
            version,
            session_id,
            site_id=site_id,
            request_id=request_id,
        )

    def bulk_add(self, kind, rows, file_name, session_id, site_id=None, request_id=None):
        key = kind_forms.KIND_FORMS[kind].key
        records = [{"record": {key: row["record"].get(key, f"gen{row['row']}")}} for row in rows]
        return self._run(
            "bulk_add",
            {"added": len(rows), "records": records},
            kind,
            rows,
            file_name,
            session_id,
            site_id=site_id,
            request_id=request_id,
        )

    def retry_write(self, error):
        return self._run("retry_write", {"record": {"job_code": "jc1"}, "meta": {}}, error)

    def audit_page(self, before=None):
        return self._run("audit_page", {"entries": [{"id": "e2"}], "next_before": "e2", "total": 2}, before=before)


class Upload:
    def __init__(self, name, data):
        self.name, self._data = name, data

    def getvalue(self):
        return self._data


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(session, "client_for", lambda user_id: client)
    return client


@pytest.fixture
def cleared(monkeypatch):
    """Counts cache clears instead of touching Streamlit's cache."""
    counter = {"n": 0}
    monkeypatch.setattr(actions, "clear_cached_reads", lambda state=None: counter.__setitem__("n", counter["n"] + 1))
    return counter


@pytest.fixture
def state(fake, cleared):
    """A logged-in session state as a plain dict."""
    state = {}
    session.set_login(dict(LOGIN), state)
    session.clear_session_scoped(state)
    return state


def _unknown(deadline=NOW + timedelta(minutes=14)):
    return HsmUnavailable(
        "no answer from HSM: TimeoutError", outcome_unknown=True, request_id="r-held", retry_deadline=deadline
    )


def _fill_job_code_add(state, job_code="jc1", title="Cook"):
    state[kind_forms.field_key("add", "job_code", None, None, None, "job_code")] = job_code
    state[kind_forms.field_key("add", "job_code", None, None, None, "title")] = title


def _fill_job_code_edit(state, title, version=1):
    state[kind_forms.field_key("edit", "job_code", None, "jc1", version, "title")] = title


def _sent_ids(fake, name):
    return [kwargs["request_id"] for call, _, kwargs in fake.calls if call == name]


# ------------------------------------------------------------ exception table


def test_session_expired_logs_out_with_the_session_ended_notice(state, fake):
    fake.script["add_record"] = SessionExpired()
    _fill_job_code_add(state)
    actions.submit_add("job_code", None, state=state)
    assert session.login(state) is None
    assert session.notice(state)["message"] == actions.SESSION_ENDED
    assert session.request_ids(state) == {} and session.added(state) == {}


def test_outcome_unknown_write_holds_the_retry_and_renews_the_id(state, fake, cleared):
    error = _unknown()
    fake.script["add_record"] = error
    _fill_job_code_add(state)
    actions.submit_add("job_code", None, state=state)
    held = session.pending_retry(state)
    assert held["error"] is error and held["action"] == "add" and held["control"] == ("add", "job_code", None)
    assert session.login(state) == LOGIN and cleared["n"] == 0
    # R-01: while the write is held, the control's stored id is no longer the one that was sent.
    (sent,) = _sent_ids(fake, "add_record")
    entry = session.request_ids(state)[("add", "job_code", None)]
    assert entry["id"] != sent and entry["last"] is None and entry["fingerprint"] is None


def test_no_answer_on_a_read_shows_cant_reach_the_backend(state, fake):
    fake.script["audit_page"] = HsmUnavailable("no answer")
    session.set_item("audit", {"entries": [], "next_before": "e1", "total": 3}, state)
    actions.audit_load_older(state=state)
    assert session.notice(state)["message"] == actions.UNREACHABLE
    assert session.pending_retry(state) is None


def test_refusal_shows_message_and_problems_and_refreshes(state, fake, cleared):
    problems = [{"field": "title", "reason": "is required"}]
    fake.script["add_record"] = HsmApiError(400, "invalid record", problems)
    session.set_item("audit", {"entries": [1], "next_before": None, "total": 1}, state)
    _fill_job_code_add(state)
    actions.submit_add("job_code", None, state=state)
    notice = session.notice(state)
    assert (notice["level"], notice["message"], notice["problems"], notice["stale"]) == (
        "error",
        "invalid record",
        problems,
        False,
    )
    assert cleared["n"] == 1 and session.audit(state) == {}


def test_stale_record_refusal_offers_reload(state, fake, cleared):
    fake.script["update_record"] = HsmApiError(409, actions.STALE)
    _fill_job_code_edit(state, "Chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    assert session.notice(state)["stale"] is True
    actions.reload(state=state)
    assert session.notice(state) is None and cleared["n"] == 2


def test_value_error_from_retry_write_is_the_expired_retry(state, fake, cleared):
    session.set_item(
        "pending_retry",
        {"control": ("add", "job_code", None), "kind": "job_code", "site": None, "action": "add", "error": _unknown()},
        state,
    )
    session.request_ids(state)[("add", "job_code", None)] = {
        "id": "r-held",
        "fingerprint": "f",
        "last": "unknown",
        "kind": "job_code",
        "site": None,
    }
    fake.script["retry_write"] = ValueError("retry not allowed")
    actions.try_again(state=state)
    assert session.pending_retry(state) is None
    assert session.notice(state)["message"] == actions.RETRY_EXPIRED
    assert session.request_ids(state)[("add", "job_code", None)]["id"] != "r-held" and cleared["n"] == 1


def test_unexpected_error_keeps_the_login_and_never_escapes(state, fake):
    fake.script["add_record"] = RuntimeError("boom")
    _fill_job_code_add(state)
    actions.submit_add("job_code", None, state=state)  # does not raise
    assert session.login(state) == LOGIN
    assert session.notice(state)["message"] == "Something went wrong: RuntimeError"


# ---------------------------------------------------------- request-id rule


def test_same_id_reused_only_for_an_identical_body_after_a_success(state, fake):
    _fill_job_code_edit(state, "Chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    actions.submit_edit("job_code", None, "jc1", 1, state=state)  # double click: identical body
    _fill_job_code_edit(state, "Head chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)  # changed body
    first, repeat, changed = _sent_ids(fake, "update_record")
    assert first == repeat and changed != first


def test_new_id_after_a_refusal(state, fake):
    fake.script["update_record"] = [HsmApiError(403, "nope"), None]
    _fill_job_code_edit(state, "Chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    first, second = _sent_ids(fake, "update_record")
    assert first != second


def test_new_id_after_discard_and_after_expiry(state, fake, monkeypatch):
    fake.script["update_record"] = [_unknown(), None, _unknown(), None]
    _fill_job_code_edit(state, "Chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    actions.discard(state=state)
    assert session.notice(state)["message"] == actions.DISCARDED
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    _fill_job_code_edit(state, "Chef", version=2)
    actions.submit_edit("job_code", None, "jc1", 2, state=state)  # no answer again, then expires
    monkeypatch.setattr(actions, "_now", lambda: NOW + timedelta(minutes=15))
    assert actions.retry_expired(state) is True
    assert session.pending_retry(state) is None
    actions.submit_edit("job_code", None, "jc1", 2, state=state)
    ids = _sent_ids(fake, "update_record")
    assert len(ids) == 4 and len(set(ids)) == 4


def test_new_id_after_the_session_ended(state, fake):
    _fill_job_code_edit(state, "Chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    fake.script["session_status"] = lambda sid: {"active": False, "ended_reason": "idle"}
    actions.check_session(state)
    session.set_login(dict(LOGIN), state)  # logged in again
    _fill_job_code_edit(state, "Chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    first, second = _sent_ids(fake, "update_record")
    assert first != second


def test_stale_success_dropped_after_another_success_on_the_same_kind_and_site(state, fake):
    _fill_job_code_edit(state, "Chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    edit_control = ("edit", "job_code", None, "jc1", 1)
    assert session.request_ids(state)[edit_control]["last"] == "ok"
    _fill_job_code_add(state, "jc2", "Host")
    actions.submit_add("job_code", None, state=state)  # another success, same kind and site
    assert edit_control not in session.request_ids(state)
    actions.submit_edit("job_code", None, "jc1", 1, state=state)  # identical body, checked afresh
    first, again = _sent_ids(fake, "update_record")
    assert first != again


def test_double_submit_of_a_cleared_add_form_sends_once(state, fake):
    _fill_job_code_add(state)
    actions.submit_add("job_code", None, state=state)
    assert not any(k.startswith(kind_forms.form_key_prefix("add", "job_code", None, None, None)) for k in state)
    actions.submit_add("job_code", None, state=state)  # second callback reads an empty form
    assert fake.names().count("add_record") == 1


def test_a_stale_double_click_that_brings_old_values_back_sends_nothing(state, fake):
    # Commit review, finding 2: a second click can reach the server before
    # the cleared form reaches the browser, carrying the old values under the
    # old keys. The add form moves to a new generation after a success, so
    # those values land on keys no longer drawn and the form reads as blank.
    _fill_job_code_add(state)
    actions.submit_add("job_code", None, state=state)
    _fill_job_code_add(state)  # the browser's stale values
    version = session.add_form_version("job_code", None, state)
    assert version is not None
    actions.submit_add("job_code", None, None, version, state=state)  # what the redrawn form submits
    assert fake.names().count("add_record") == 1


# ------------------------------------------------------- logout and retries


def test_logout_with_a_held_write_logs_out_at_once_and_says_it_was_dropped(state, fake, cleared):
    # NFR2.4 as amended (NFR-design Q1: B): no prompt; one click ends the login.
    session.set_item(
        "pending_retry",
        {"control": ("add", "job_code", None), "kind": "job_code", "site": None, "action": "add", "error": _unknown()},
        state,
    )
    actions.log_out(state=state)
    assert session.login(state) is None and session.pending_retry(state) is None
    assert fake.names() == ["end_session"] and cleared["n"] == 1
    notice = session.notice(state)
    assert (notice["level"], notice["message"]) == ("warning", actions.LOGGED_OUT + actions.LOGOUT_WRITE_DROPPED)
    assert "confirm_logout" not in state and not hasattr(session, "confirm_logout")


def test_logout_without_a_held_write_says_only_you_logged_out(state, fake):
    actions.log_out(state=state)
    assert session.login(state) is None
    notice = session.notice(state)
    assert (notice["level"], notice["message"]) == ("info", actions.LOGGED_OUT)


def test_new_id_after_logout_with_a_held_write(state, fake):
    fake.script["update_record"] = [_unknown(), None]
    _fill_job_code_edit(state, "Chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    actions.log_out(state=state)
    session.set_login(dict(LOGIN), state)  # logged in again
    _fill_job_code_edit(state, "Chef")
    actions.submit_edit("job_code", None, "jc1", 1, state=state)
    first, second = _sent_ids(fake, "update_record")
    assert first != second


@pytest.mark.parametrize("failure", [HsmApiError(401, "unknown or ended session"), HsmUnavailable("no answer")])
def test_logout_always_ends_the_login(state, fake, failure):
    fake.script["end_session"] = failure
    fake.script["session_status"] = HsmUnavailable("no answer")
    actions.log_out(state=state)
    assert session.login(state) is None
    expected = ["end_session", "session_status"] if isinstance(failure, HsmUnavailable) else ["end_session"]
    assert fake.names() == expected


def test_try_again_that_lands_records_the_add(state, fake):
    session.set_item(
        "pending_retry",
        {"control": ("add", "job_code", None), "kind": "job_code", "site": None, "action": "add", "error": _unknown()},
        state,
    )
    actions.try_again(state=state)
    assert session.added(state) == {"job_code": ["jc1"]}
    assert session.notice(state)["message"] == "Added job code jc1."


def test_try_again_passes_the_held_error_object_itself(state, fake):
    held_error = _unknown()
    session.set_item(
        "pending_retry",
        {"control": ("add", "job_code", None), "kind": "job_code", "site": None, "action": "add", "error": held_error},
        state,
    )
    actions.try_again(state=state)
    ((_, args, _),) = [call for call in fake.calls if call[0] == "retry_write"]
    assert args[0] is held_error  # never a copy (NFR2.2)
    assert session.pending_retry(state) is None


def test_try_again_without_an_answer_keeps_offering_it(state, fake):
    again = _unknown()
    fake.script["retry_write"] = again
    session.set_item(
        "pending_retry",
        {"control": ("add", "job_code", None), "kind": "job_code", "site": None, "action": "add", "error": _unknown()},
        state,
    )
    actions.try_again(state=state)
    assert session.pending_retry(state)["error"] is again


def test_session_ended_with_a_held_write_says_it_was_dropped(state, fake):
    session.set_item("pending_retry", {"control": ("add", "job_code", None), "error": _unknown()}, state)
    fake.script["session_status"] = lambda sid: {"active": False, "ended_reason": "idle"}
    assert actions.check_session(state) is None
    assert session.login(state) is None
    assert session.notice(state)["message"] == ENDED_IDLE + actions.WRITE_DROPPED


ENDED_IDLE = actions.ENDED_REASONS["idle"]


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        ("idle", actions.ENDED_REASONS["idle"]),
        ("logout", actions.ENDED_REASONS["logout"]),
        (None, actions.ENDED_GENERIC),
    ],
)
def test_session_check_reasons_without_a_held_write(state, fake, reason, message):
    fake.script["session_status"] = lambda sid: {"active": False, "ended_reason": reason}
    actions.check_session(state)
    assert session.notice(state)["message"] == message


def test_session_check_without_an_answer_keeps_the_login(state, fake):
    fake.script["session_status"] = HsmUnavailable("no answer")
    assert actions.check_session(state) == actions.UNREACHABLE
    assert session.login(state) == LOGIN


# ------------------------------------------------------------ added updates


def test_added_updates_after_add_upload_and_delete(state, fake):
    _fill_job_code_add(state, "jc1", "Cook")
    actions.submit_add("job_code", None, state=state)
    session.templates(state)[("job_code", None)] = {"columns": ["job_code", "title"]}
    state["up"] = Upload("codes.csv", b"job_code,title\njc2,Host\njc3,Runner\n")
    actions.upload("job_code", None, "up", state=state)
    assert session.notice(state)["message"] == "Added 2 records from codes.csv."
    assert session.added(state) == {"job_code": ["jc1", "jc2", "jc3"]}
    actions.ask_delete("job_code", None, "jc2", 1, state=state)
    actions.confirm_delete(state=state)
    assert session.added(state) == {"job_code": ["jc1", "jc3"]} and session.pending_delete(state) is None


def test_site_kind_added_keys_carry_their_site(state, fake):
    fake.script["add_record"] = lambda kind, record, *a, **k: {"record": {**record, "employee_id": "emp_x"}}
    state[kind_forms.field_key("add", "employee", SITE, None, None, "name")] = "Ann"
    actions.submit_add("employee", SITE, state=state)
    assert session.added(state) == {"employee@site_001": ["emp_x"]}
    assert fake.calls[0][2]["site_id"] == SITE


def test_upload_refused_locally_sends_nothing(state, fake):
    session.templates(state)[("job_code", None)] = {"columns": ["job_code", "title"]}
    state["up"] = Upload("codes.csv", b"code,title\njc2,Host\n")
    actions.upload("job_code", None, "up", state=state)
    assert session.notice(state)["message"] == "The header must be: job_code,title."
    state["up"] = Upload(
        "big.csv", b"job_code,title\n" + ("jc,é" * 1).encode() + b"\n" + ("jc9," + "é" * 200_000 + "\n").encode()
    )
    actions.upload("job_code", None, "up", state=state)
    assert session.notice(state)["message"] == csv_rows.TOO_LARGE
    assert "bulk_add" not in fake.names()


def test_refused_upload_lists_problems_and_says_nothing_was_saved(state, fake):
    problems = [{"row": 1, "field": "title", "reason": "is required"}]
    fake.script["bulk_add"] = HsmApiError(400, "invalid rows", problems)
    session.templates(state)[("job_code", None)] = {"columns": ["job_code", "title"]}
    state["up"] = Upload("codes.csv", b"job_code,title\njc2,\n")
    actions.upload("job_code", None, "up", state=state)
    notice = session.notice(state)
    assert notice["problems"] == problems and notice["note"] == actions.NOTHING_SAVED
    assert session.added(state) == {}


# --------------------------------------------------------- login and audit


def test_log_in_starts_one_session_and_clears_scoped_state(fake, cleared):
    state = {"added": {"x": ["y"]}, "notice": {"message": "old"}}
    actions.log_in("user_dev_tester", state=state)
    assert session.login(state) == {
        "session_id": "sid-new",
        "user_id": "user_dev_tester",
        "persona": "REGIONAL_MANAGER",
    }
    assert session.added(state) == {} and session.notice(state) is None and fake.names() == ["start_session"]


def test_failed_log_in_stays_logged_out(fake, cleared):
    fake.script["start_session"] = HsmApiError(503, "audit unavailable")
    state = {}
    actions.log_in("user_rm_midtown", state=state)
    assert session.login(state) is None and session.notice(state)["message"] == "audit unavailable"


def test_audit_paging_load_older_appends_from_the_last_entry(state, fake):
    fake.script["audit_page"] = [
        {"entries": [{"id": "e3", "session_id": "sid-x"}], "next_before": "e3", "total": 3},
        {"entries": [{"id": "e2"}], "next_before": None, "total": 3},
    ]
    assert actions.load_audit(state) is None
    actions.audit_load_older(state=state)
    assert [e["id"] for e in session.audit(state)["entries"]] == ["e3", "e2"]
    assert all("session_id" not in e for e in session.audit(state)["entries"])
    assert session.audit(state)["next_before"] is None
    actions.audit_load_older(state=state)  # no older page: no call
    assert [kwargs["before"] for name, _, kwargs in fake.calls] == [None, "e3"]


def test_refused_load_older_keeps_the_loaded_entries(state, fake):
    # U2 BR4.3: no purge branch; any refusal is an ordinary notice.
    fake.script["audit_page"] = [
        {"entries": [{"id": "e3"}], "next_before": "e3", "total": 3},
        HsmApiError(400, "invalid before"),
    ]
    actions.load_audit(state)
    actions.audit_load_older(state=state)
    assert [e["id"] for e in session.audit(state)["entries"]] == ["e3"]
    assert session.notice(state)["message"] == "invalid before"


def test_audit_unavailable_message(state, fake):
    fake.script["audit_page"] = HsmApiError(503, "audit unavailable")
    assert actions.load_audit(state) == actions.AUDIT_UNAVAILABLE


# ================================================= inline actions and rerun


class _Signal(BaseException):
    """Stands in for Streamlit's rerun signal, a BaseException."""


def test_rerun_signal_is_a_base_exception_the_guard_never_catches(state):
    from streamlit.runtime.scriptrunner_utils.exceptions import RerunException

    assert not issubclass(RerunException, Exception)

    @actions.guarded
    def action(state, write):
        raise _Signal()

    with pytest.raises(_Signal):
        action(state=state)
    assert session.notice(state) is None


def test_then_rerun_reruns_after_the_guarded_action_even_when_it_failed(state, fake, monkeypatch):
    order = []
    monkeypatch.setattr(actions.st, "rerun", lambda: order.append("rerun"))
    fake.script["add_record"] = RuntimeError("boom")
    _fill_job_code_add(state)
    real = actions.submit_add
    monkeypatch.setattr(actions, "submit_add", lambda *a, **k: (order.append("action"), real(*a, **k)))
    actions.then_rerun(actions.submit_add, "job_code", None, state=state)
    assert order == ["action", "rerun"]
    assert session.notice(state)["message"] == "Something went wrong: RuntimeError"


def test_then_rerun_passes_the_rerun_signal_through(monkeypatch):
    def rerun():
        raise _Signal()

    monkeypatch.setattr(actions.st, "rerun", rerun)
    with pytest.raises(_Signal):
        actions.then_rerun(lambda: None)


# ======================================== per-session Manage data cache (Q3)


def _listing(n):
    return {"records": [{"job_code": f"jc{n}"}], "meta": {}}


def test_records_are_reused_within_60_seconds(state, fake, monkeypatch):
    fake.list_records = lambda kind, site_id=None: fake._run("list_records", _listing(len(fake.calls)), kind)
    monkeypatch.setattr(session, "_now", lambda: NOW)
    first = session.records_for("u", "job_code", None, state)
    monkeypatch.setattr(session, "_now", lambda: NOW + timedelta(seconds=59))
    assert session.records_for("u", "job_code", None, state) is first
    assert fake.names() == ["list_records"]


def test_records_are_read_again_once_60_seconds_old(state, fake, monkeypatch):
    fake.list_records = lambda kind, site_id=None: fake._run("list_records", _listing(len(fake.calls)), kind)
    monkeypatch.setattr(session, "_now", lambda: NOW)
    first = session.records_for("u", "job_code", None, state)
    monkeypatch.setattr(session, "_now", lambda: NOW + timedelta(seconds=60))
    second = session.records_for("u", "job_code", None, state)
    assert second != first and fake.names() == ["list_records", "list_records"]


def test_records_are_keyed_by_user_kind_and_site(state, fake):
    fake.list_records = lambda kind, site_id=None: fake._run("list_records", _listing(len(fake.calls)), kind)
    session.records_for("u", "employee", "site_001", state)
    session.records_for("u", "employee", "site_002", state)
    session.records_for("v", "employee", "site_001", state)
    session.records_for("u", "employee", "site_001", state)
    assert fake.names().count("list_records") == 3


def test_a_failed_read_is_not_cached(state, fake):
    calls = []

    def list_records(kind, site_id=None):
        calls.append(kind)
        if len(calls) == 1:
            raise HsmApiError(503, "busy")
        return _listing(1)

    fake.list_records = list_records
    with pytest.raises(HsmApiError):
        session.records_for("u", "job_code", None, state)
    assert session.records_for("u", "job_code", None, state) == _listing(1) and len(calls) == 2


_real_clear = actions.clear_cached_reads  # captured before the ``cleared`` fixture replaces it


def test_write_outcomes_refresh_and_logout_clear_the_session_cache(state, fake, monkeypatch):
    monkeypatch.setattr(actions.st.cache_data, "clear", lambda: None)
    monkeypatch.setattr(actions, "clear_cached_reads", _real_clear)
    for clear in (
        lambda: (_fill_job_code_add(state), actions.submit_add("job_code", None, state=state)),
        lambda: actions.clear_cached_reads(state),  # Refresh data
        lambda: actions.log_out(state=state),
    ):
        session.set_login(dict(LOGIN), state)
        session.records(state)[("u", "job_code", None)] = {"fetched": NOW, "listing": _listing(0)}
        clear()
        assert session.records(state) == {}


# ============================================================ Source scans

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"
NEW_MODULES = ("safe_text", "kind_forms", "csv_rows", "session", "actions", "manage_tab", "audit_tab")
# The functions app.py gained for the login, banner and notice (unit U4); the
# rest of app.py is the unchanged read-only dashboard.
NEW_APP_FUNCTIONS = ("_login_panel", "_session_panel", "_banner", "_notice_panel", "_guarded_tab")
MARKDOWN_CALLS = {"markdown", "error", "warning", "info", "success", "caption"}
MIN_CHECKED = 26  # every Markdown-capable call and label in the U4 screens; selectbox options are plain text and no longer counted (final review R-02)
FORBIDDEN_NAMES = {"unsafe_allow_html", "html", "write", "toast", "metric", "table", "exception"}


def _new_code():
    """``(where, AST)`` for every new module and every new app.py function."""
    trees = [(f"{name}.py", ast.parse((DASHBOARD / f"{name}.py").read_text())) for name in NEW_MODULES]
    app = ast.parse((DASHBOARD / "app.py").read_text())
    functions = {node.name: node for node in app.body if isinstance(node, ast.FunctionDef)}
    missing = set(NEW_APP_FUNCTIONS) - set(functions)
    assert not missing, missing
    return trees + [(f"app.py:{name}", functions[name]) for name in NEW_APP_FUNCTIONS]


def _is_escape(node):
    return isinstance(node, ast.Call) and (
        getattr(node.func, "id", None) == "escape_md" or getattr(node.func, "attr", None) == "escape_md"
    )


def _safe_text(node, where):
    """A string constant, a direct escape_md(...) call, or an f-string whose
    every interpolated value is a direct escape_md(...) call."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if _is_escape(node):
        return True
    if isinstance(node, ast.JoinedStr):
        return all(
            isinstance(part, ast.Constant) or (isinstance(part, ast.FormattedValue) and _is_escape(part.value))
            for part in node.values
        )
    return False


def _function_results(name, tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return [n.value for n in ast.walk(node) if isinstance(n, ast.Return) and n.value is not None]
    return None


def test_no_click_callbacks_in_the_write_screens():
    # NFR-design Q2: B: every button's action runs inline, then st.rerun().
    for where, tree in _new_code():
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword):
                assert node.arg != "on_click", (where, node.lineno)


def test_dashboard_listens_on_this_machine_by_default():
    # NFR1.3: the settings file and the documented start command both bind
    # 127.0.0.1, and the README says how to open it up on purpose. NFR1.6:
    # Streamlit itself refuses uploads over 2 MB.
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    config = tomllib.loads((DASHBOARD.parent / ".streamlit" / "config.toml").read_text())
    assert config["server"]["address"] == "127.0.0.1" and config["server"]["maxUploadSize"] == 2
    readme = (DASHBOARD / "README.md").read_text()
    assert "streamlit run dashboard/app.py --server.address 127.0.0.1" in readme
    assert "--server.address 0.0.0.0" in readme


def test_no_publish_or_submit_anywhere_in_the_dashboard():
    # NFR1.2: no dashboard module publishes a schedule or submits a purchase order.
    for path in DASHBOARD.glob("*.py"):
        text = path.read_text()
        for name in ("publish_schedule", "submit_purchase_order", "/schedules/publish", "/inventory/purchase-orders"):
            assert name not in text, (path.name, name)


def test_new_code_uses_no_forbidden_streamlit_calls_and_no_print_or_logging():
    for where, tree in _new_code():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_NAMES, (where, node.attr, node.lineno)
            if isinstance(node, ast.keyword):
                assert node.arg != "unsafe_allow_html", (where, node.lineno)
            if isinstance(node, ast.Name):
                assert node.id not in {"print", "logging"}, (where, node.id, node.lineno)
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = [alias.name for alias in node.names] + [getattr(node, "module", None) or ""]
                assert "logging" not in names, (where, node.lineno)


def test_markdown_capable_calls_take_only_fixed_or_escaped_text():
    # NFR1.5: every Markdown-capable call and label passes the rule.
    # Selectbox options (format_func results) are plain text in Streamlit
    # 1.64, so they must NOT be escaped, or the backslashes show on screen
    # (final review R-02).
    checked = 0
    for where, tree in _new_code():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None)
            if name in MARKDOWN_CALLS:
                text = node.args[0] if node.args else next(k.value for k in node.keywords if k.arg == "body")
                assert _safe_text(text, where), (where, name, node.lineno, ast.unparse(text))
                checked += 1
            for keyword in node.keywords:
                if keyword.arg == "label":
                    assert _safe_text(keyword.value, where), (where, node.lineno, ast.unparse(keyword.value))
                    checked += 1
                if keyword.arg == "format_func":
                    assert "escape_md" not in ast.unparse(keyword.value), (where, node.lineno)
    assert checked >= MIN_CHECKED, checked


def test_markdown_rule_catches_unescaped_text():
    tree = ast.parse("st.error(message)\nst.error(f'x {escape_md(a)} {b}')\nst.error(escape_md(a))\nst.error('ok')")
    verdicts = [_safe_text(node.value.args[0], "t") for node in tree.body]
    assert verdicts == [False, False, True, True]
