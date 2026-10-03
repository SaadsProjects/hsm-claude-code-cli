"""
Business-logic tests for the U1 write service (mock_hsm/writes.py), called
directly: the rights matrix, the check order, references, deletes, versions,
the entry limit, bulk files, request ids, failure paths and sessions.

Every NFR6 item is a named test here: ``test_rights_matrix``,
``test_restaurant_manager_shared_write_is_denied_and_audited``,
``test_out_of_scope_writes_are_refused``,
``test_record_100_is_accepted_and_record_101_refused`` (per persona) and
``test_dev_tester_entries_carry_its_own_user_id``.
"""
import copy
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mock_hsm import audit, db, writes
from mock_hsm.auth import mint_token, verify_token

RM, REGIONAL, DEV = "user_rm_midtown", "user_regional_atl", "user_dev_tester"
PERSONAS = [RM, REGIONAL, DEV]
SITE_KINDS = ["employee", "on_hand"]
ALL_KINDS = list(writes.KINDS)
ALL_SEEING = {"user_id": "test-auditor", "persona": "SYSTEM_ADMIN", "site_ids": [], "region_id": None}
NOT_SAVED = "not saved: other rows in the file failed"


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def set(self, minutes, seconds=0):
        self.now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes, seconds=seconds)


@pytest.fixture
def clock():
    fake = FakeClock()
    writes.set_clock(fake)
    return fake


def _claims(user):
    return verify_token(mint_token(user))


def _entries():
    entries, before = [], None
    while True:
        page = audit.page(ALL_SEEING, before)
        entries += page["entries"]
        before = page["next_before"]
        if before is None:
            return entries[::-1]


def _data_entries():
    return [e for e in _entries() if e["action"] not in ("login", "logout")]


class Session:
    """A persona's login session driving the write service directly."""

    def __init__(self, user):
        self.user = user
        self.claims = _claims(user)
        status, body = writes.start_session(self.claims)
        assert status == 201
        self.id = body["session_id"]

    def body(self, **fields):
        return {"session_id": self.id, "request_id": str(uuid.uuid4()), **fields}

    def add(self, kind, record, site=None):
        return writes.write(kind, "add", self.claims, _site(kind, site), None, self.body(record=record))

    def update(self, kind, key, record, version, site=None):
        return writes.write(kind, "update", self.claims, _site(kind, site), key,
                            self.body(record=record, version=version))

    def delete(self, kind, key, version, site=None):
        return writes.write(kind, "delete", self.claims, _site(kind, site), key, self.body(version=version))

    def bulk(self, kind, records, site=None):
        rows = [{"row": i, "record": r} for i, r in enumerate(records, start=1)]
        return self.bulk_rows(kind, rows, site)

    def bulk_rows(self, kind, rows, site=None):
        return writes.bulk(kind, self.claims, _site(kind, site),
                           self.body(source="csv", file_name="upload.csv", rows=rows))


def _site(kind, site):
    return site or ("site_001" if kind in SITE_KINDS else None)


# ------------------------------------------------------------ record factories

def _uom(uom_id, base=None):
    return {"uom_id": uom_id, "name": f"unit {uom_id}", "base": base or uom_id, "factor_to_base": 1}


def _raw_material(rm_id, uom_id="u_w"):
    return {"raw_material_id": rm_id, "name": f"RM {rm_id}", "uom": uom_id}


def _record(kind, tag):
    return {
        "menu_item": {"menu_item_id": f"mi_{tag}", "name": f"Item {tag}", "gl_code": "GL-FOOD"},
        "recipe": {"menu_item_id": f"mi_{tag}", "lines": [{"raw_material_id": "rm_w", "qty": 1, "uom": "u_w"}]},
        "raw_material": _raw_material(f"rm_{tag}"),
        "uom": _uom(f"u_{tag}"),
        "vendor": {"vendor_id": f"v_{tag}", "name": f"Vendor {tag}", "lead_time_days": 2,
                   "price_list": {"rm_w": 1.25}, "min_order_value": 10},
        "employee": {"name": f"Emp {tag}", "job_code": "jc_w", "hourly_rate": 14.5,
                     "max_weekly_hours_preference": 30, "available_days": ["Mon", "Wed"]},
        "job_code": {"job_code": f"jc_{tag}", "title": f"Title {tag}"},
        "on_hand": {"raw_material_id": f"rm_{tag}", "qty": 5},
        "par_level": {"raw_material_id": f"rm_{tag}", "qty": 5},
        "reorder_point": {"raw_material_id": f"rm_{tag}", "qty": 5},
        "labor_rule": {"jurisdiction": f"J_{tag}", "weekly_ot_threshold_hours": 40, "daily_ot_threshold_hours": 8,
                       "ot_multiplier": 1.5, "max_consecutive_days": 6, "min_rest_hours_between_shifts": 10,
                       "max_shift_length_hours": 10, "note": "Test rule"},
    }[kind]


def _changed(record):
    record = copy.deepcopy(record)
    for name in ("name", "title", "note"):
        if name in record:
            record[name] += " (edited)"
            return record
    if "qty" in record:
        record["qty"] += 1
    else:
        record["lines"][0]["qty"] = 2
    return record


def _world(setup):
    """Dashboard-added basics other records refer to."""
    assert setup.add("uom", _uom("u_w"))[0] == 201
    assert setup.add("raw_material", _raw_material("rm_w"))[0] == 201
    assert setup.add("job_code", {"job_code": "jc_w", "title": "Worker"})[0] == 201


def _prereqs(setup, kind, tag):
    if kind == "recipe":
        assert setup.add("menu_item", _record("menu_item", tag))[0] == 201
    if kind in ("on_hand", "par_level", "reorder_point"):
        assert setup.add("raw_material", _raw_material(f"rm_{tag}"))[0] == 201


def _key(kind, body):
    return body["record"][writes.KINDS[kind].key]


@pytest.fixture
def setup():
    session = Session(REGIONAL)
    _world(session)
    return session


# ================================================================ rights (NFR6)

@pytest.mark.parametrize("persona", PERSONAS)
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_rights_matrix(setup, kind, persona):
    """NFR1.4, NFR6.1: 11 kinds x 3 personas x add, update and delete."""
    actor = Session(persona)
    allowed = kind in SITE_KINDS or persona != RM
    _prereqs(setup, kind, "act")
    status, body = actor.add(kind, _record(kind, "act"))
    if allowed:
        assert status == 201, body
        key, record = _key(kind, body), _record(kind, "act")
    else:
        assert (status, body) == (403, {"error": "persona RESTAURANT_MANAGER cannot write shared data"})
        _prereqs(setup, kind, "own")
        status, body = setup.add(kind, _record(kind, "own"))
        assert status == 201
        key, record = _key(kind, body), _record(kind, "own")
    status, body = actor.update(kind, key, _changed(record), version=1)
    assert status == (200 if allowed else 403), body
    if allowed:
        assert body["meta"]["version"] == 2 and body["meta"]["updated_by"] == persona
    status, body = actor.delete(kind, key, version=2 if allowed else 1)
    assert status == (200 if allowed else 403), body
    assert writes.find(writes.KINDS[kind], _site(kind, None), key)[0] is not allowed


def test_restaurant_manager_shared_write_is_denied_and_audited(setup):
    rm = Session(RM)
    before = dict(db.JOB_CODES)
    status, body = rm.add("job_code", {"job_code": "jc_rm", "title": "Nope"})
    assert (status, body) == (403, {"error": "persona RESTAURANT_MANAGER cannot write shared data"})
    assert before == db.JOB_CODES
    entry = _data_entries()[-1]
    assert {k: entry[k] for k in ("user_id", "persona", "session_id", "source", "action", "outcome", "kind",
                                  "record_id", "reason")} == {
        "user_id": RM, "persona": "RESTAURANT_MANAGER", "session_id": rm.id, "source": "dashboard",
        "action": "add", "outcome": "violation", "kind": "job_code", "record_id": "jc_rm",
        "reason": "persona RESTAURANT_MANAGER cannot write shared data"}


def test_out_of_scope_writes_are_refused(setup):
    rm = Session(RM)
    employee = _record("employee", "x")
    assert rm.add("employee", employee, site="site_002")[0] == 403
    assert rm.add("employee", employee, site="site_404")[0] == 404
    assert rm.add("par_level", {"raw_material_id": "rm_w", "qty": 1})[0] == 403  # shared data
    assert rm.update("employee", "emp_site_001_01", employee, 1)[0] == 403        # seeded record
    assert setup.update("uom", "lb", _uom("lb"), 1)[0] == 403
    # A record at another site is reported as not found through a site_001 path (NFR1.5).
    status, body = setup.add("employee", employee, site="site_002")
    assert status == 201
    other = body["record"]["employee_id"]
    assert rm.update("employee", other, employee, 1, site="site_001")[0] == 404
    assert rm.delete("employee", other, 1, site="site_001")[0] == 404
    assert db.EMPLOYEES[other]["name"] == "Emp x"
    unknown_site = [e for e in _data_entries() if e["outcome"] == "violation" and e["reason"].startswith("unknown")]
    assert unknown_site[0]["site_id"] is None and unknown_site[0]["changes"]["site_id"] == "site_404"


@pytest.mark.parametrize("persona", PERSONAS)
def test_record_100_is_accepted_and_record_101_refused(setup, persona):
    """BR6.1, NFR6.1: per persona; the limit is checked last; a delete frees no slot."""
    actor = Session(persona)
    kind = "employee" if persona == RM else "job_code"

    def record(i):
        return _record("employee", i) if kind == "employee" else {"job_code": f"jc_{persona}_{i}", "title": "T"}

    for i in range(100):
        status, body = actor.add(kind, record(i))
        assert status == 201, (i, body)
    last_key = _key(kind, body) if kind == "job_code" else body["record"]["employee_id"]
    assert actor.add(kind, record(100)) == (429, {"error": f"entry limit reached for {kind}"})
    bad = {**record(101), ("title" if kind == "job_code" else "name"): "<b>"}
    assert actor.add(kind, bad)[0] == 400  # field problems come before the limit
    assert actor.delete(kind, last_key, 1)[0] == 200
    assert actor.add(kind, record(102))[0] == 429
    assert Session(persona).add(kind, record(103))[0] == 201  # a new session starts at zero
    entry = _data_entries()[-2]
    assert (entry["outcome"], entry["reason"]) == ("violation", f"entry limit reached for {kind}")


def test_dev_tester_entries_carry_its_own_user_id(setup):
    dev = Session(DEV)
    assert dev.add("job_code", {"job_code": "jc_dev", "title": "Dev"})[0] == 201
    assert dev.add("job_code", {"job_code": "jc_dev", "title": "Dev"})[0] == 400
    login, *rest = [e for e in _entries() if e["user_id"] == DEV]
    assert (login["action"], login["persona"], login["session_id"]) == ("login", "REGIONAL_MANAGER", dev.id)
    assert [(e["user_id"], e["persona"], e["session_id"], e["outcome"]) for e in rest] == [
        (DEV, "REGIONAL_MANAGER", dev.id, "allowed"), (DEV, "REGIONAL_MANAGER", dev.id, "violation")]
    assert writes.meta_map("job_code")["jc_dev"]["created_by"] == DEV


def test_any_dashboard_record_may_be_updated_within_rights(setup):
    """BR3.2: the developer/tester may update the Regional Manager's record."""
    status, body = Session(DEV).update("job_code", "jc_w", {"title": "Renamed"}, 1)
    assert status == 200 and body["record"] == {"job_code": "jc_w", "title": "Renamed"}


# ================================================================ check order

def test_each_check_step_gives_its_first_failure_status(setup, clock):
    rm, regional = Session(RM), setup
    regional.add("raw_material", _raw_material("rm_used"))
    regional.add("par_level", {"raw_material_id": "rm_used", "qty": 1})
    claims = rm.claims

    def call(action, kind, site, key, **body):
        return writes.write(kind, action, claims, site, key, body)

    rid = {"request_id": "r-" + uuid.uuid4().hex}
    # 2 envelope before session: no session and a list record
    assert call("add", "uom", None, None, record=[])[1]["error"] == "malformed request"
    # session before request id
    assert call("add", "uom", None, None, record={})[0] == 401
    # request id before site
    assert call("add", "employee", "site_404", None, session_id=rm.id, record={})[0] == 400
    # site: unknown 404, then out of scope 403, before rights/fields
    assert call("add", "employee", "site_404", None, session_id=rm.id, record={}, **rid)[0] == 404
    rid = {"request_id": "r-" + uuid.uuid4().hex}
    assert call("add", "employee", "site_002", None, session_id=rm.id, record={}, **rid)[0] == 403
    # record (404) before rights (403)
    assert rm.update("uom", "u_missing", {}, 1)[0] == 404
    # rights before seeded/fields
    assert rm.update("uom", "u_w", {}, 1)[0] == 403
    # seeded before fields and version
    assert regional.update("uom", "lb", {}, 99) == (403, {"error": "seeded records are read-only"})
    # ownership before version
    assert Session(DEV).delete("uom", "u_w", 99) == (403, {"error": "not your record from this session"})
    # fields before version
    assert regional.update("uom", "u_w", {"name": "<x>"}, 99)[0] == 400
    # version before in use
    status, body = regional.delete("raw_material", "rm_used", 99)
    assert (status, body["error"]) == (409, "this record changed since you opened it; reload and try again")
    # in use
    assert regional.delete("raw_material", "rm_used", 1)[1]["error"] == "record is still in use"


def test_n_mixed_attempts_give_n_entries(setup):
    before = len(_data_entries())
    regional = setup
    outcomes = [regional.add("uom", _uom("u_m1"))[0], regional.add("uom", _uom("u_m1"))[0],
                regional.update("uom", "u_m1", _uom("u_m1"), 1)[0], regional.update("uom", "u_m1", _uom("u_m1"), 1)[0],
                regional.delete("uom", "lb", 1)[0], regional.delete("uom", "u_m1", 2)[0],
                writes.write("uom", "add", regional.claims, None, None, [])[0]]
    assert outcomes == [201, 400, 200, 409, 403, 200, 400]
    assert len(_data_entries()) - before == 7


# ================================================================== references

@pytest.mark.parametrize("record, field", [
    (_raw_material("rm_x", "lb"), "uom"),
    (_raw_material("rm_x", "u_missing"), "uom"),
    ({"menu_item_id": "mi_burger", "lines": [{"raw_material_id": "rm_w", "qty": 1, "uom": "u_w"}]}, "menu_item_id"),
])
def test_references_to_seeded_or_missing_records_are_refused(setup, record, field):
    kind = "raw_material" if "raw_material_id" in record else "recipe"
    status, body = setup.add(kind, record)
    assert status == 400
    assert any(p["field"] == field and p["reason"].startswith("must be a dashboard-added") for p in body["problems"])


def test_nested_references_are_checked(setup):
    status, body = setup.add("vendor", {**_record("vendor", "r"), "price_list": {"rm_w": 1, "rm_bun": 2}})
    assert (status, body["problems"]) == (400, [{"field": "price_list",
                                                 "reason": "must be a dashboard-added raw material"}])
    setup.add("menu_item", _record("menu_item", "r"))
    status, body = setup.add("recipe", {"menu_item_id": "mi_r", "lines": [
        {"raw_material_id": "rm_w", "qty": 1, "uom": "oz"}]})
    assert body["problems"] == [{"field": "lines[0].uom", "reason": "must be a dashboard-added unit of measure"}]
    status, body = setup.add("employee", {**_record("employee", "r"), "job_code": "JC-COOK"})
    assert body["problems"] == [{"field": "job_code", "reason": "must be a dashboard-added job code"}]


def test_a_unit_may_be_its_own_base_but_bases_may_not_loop(setup):
    assert setup.add("uom", _uom("u_a"))[0] == 201
    assert setup.add("uom", _uom("u_b", base="u_a"))[0] == 201
    status, body = setup.update("uom", "u_a", _uom("u_a", base="u_b"), 1)
    assert (status, body["problems"]) == (400, [{"field": "base", "reason": "base units may not loop"}])
    assert setup.update("uom", "u_b", _uom("u_b"), 1)[0] == 200


def test_labor_rules_are_added_only_for_new_jurisdictions(setup):
    status, body = setup.add("labor_rule", {**_record("labor_rule", "x"), "jurisdiction": "GA"})
    assert (status, body["problems"]) == (400, [{"field": "jurisdiction", "reason": "already exists"}])
    assert setup.add("labor_rule", _record("labor_rule", "x"))[0] == 201


def test_employee_site_and_jurisdiction_are_derived(setup):
    status, body = setup.add("employee", {**_record("employee", "d"), "site_id": "site_003", "jurisdiction": "XX",
                                          "employee_id": "typed", "extra": "ignored"}, site="site_002")
    assert status == 201
    record = body["record"]
    assert (record["site_id"], record["jurisdiction"], record["employee_id"]) == (
        "site_002", "GA", "emp_site_002_d001")
    assert "extra" not in db.EMPLOYEES["emp_site_002_d001"]


# ======================================================= deletes and versions

def test_deleting_a_record_in_use_names_its_users(setup):
    setup.add("vendor", _record("vendor", "u"))
    status, body = setup.delete("raw_material", "rm_w", 1)
    assert status == 409
    assert body["problems"] == [{"field": "vendor", "reason": "still used by vendor v_u"}]
    assert "rm_w" in db.RAW_MATERIALS
    assert setup.delete("vendor", "v_u", 1)[0] == 200
    assert setup.delete("raw_material", "rm_w", 1)[0] == 200


def test_a_stale_version_is_refused(setup):
    assert setup.update("job_code", "jc_w", {"title": "One"}, 1)[0] == 200
    status, body = setup.update("job_code", "jc_w", {"title": "Two"}, 1)
    assert (status, body["error"]) == (409, "this record changed since you opened it; reload and try again")
    assert db.JOB_CODES["jc_w"]["title"] == "One"


def test_delete_ownership_is_enforced_across_sessions(setup):
    again = Session(REGIONAL)
    assert again.delete("job_code", "jc_w", 1) == (403, {"error": "not your record from this session"})
    assert Session(DEV).delete("job_code", "jc_w", 1)[0] == 403
    assert setup.delete("job_code", "jc_w", 1)[0] == 200


def test_seeded_records_are_unchanged_by_writes(setup):
    seeded = copy.deepcopy({kind.attr: getattr(db, kind.attr) for kind in writes.KINDS.values()})
    setup.add("par_level", {"raw_material_id": "rm_w", "qty": 3})
    setup.update("par_level", "rm_w", {"qty": 4}, 1)
    setup.add("on_hand", {"raw_material_id": "rm_w", "qty": 3}, site="site_002")
    setup.delete("par_level", "rm_w", 2)
    setup.delete("uom", "oz", 1)
    for attr, table in seeded.items():
        current = getattr(db, attr)
        if attr == "ON_HAND":
            assert all(current[s][k] == v for s, t in table.items() for k, v in t.items())
        else:
            assert {k: current[k] for k in table} == table


# ===================================================================== input

@pytest.mark.parametrize("name", ["Fresh & Co.", "O'Brien's", "x" * 100])
def test_ordinary_names_are_accepted(setup, name):
    status, body = setup.add("vendor", {**_record("vendor", "ok"), "name": name})
    assert status == 201 and body["record"]["name"] == name


@pytest.mark.parametrize("name", ["<script>alert(1)</script>", "a<b>c", "line\nbreak", "x" * 101])
def test_injection_and_overlong_text_are_refused_and_change_nothing(setup, name):
    before = dict(db.VENDORS)
    status, body = setup.add("vendor", {**_record("vendor", "bad"), "name": name})
    assert status == 400 and body["problems"][0]["field"] == "name"
    assert before == db.VENDORS


def test_formula_cells_are_refused_in_files(setup):
    status, body = setup.bulk("job_code", [{"job_code": "jc_f", "title": "=SUM(A1)"}])
    assert (status, body["problems"]) == (400, [{"row": 1, "field": "title",
                                                 "reason": "not allowed: a cell may not start with =, +, - or @"}])
    assert setup.add("job_code", {"job_code": "jc_f", "title": "=SUM(A1)"})[0] == 201  # a form is not a file


def test_nan_in_a_record_is_a_field_problem_and_audited(setup):
    status, body = setup.add("par_level", {"raw_material_id": "rm_w", "qty": float("nan")})
    assert (status, body["problems"]) == (400, [{"field": "qty", "reason": "must be a finite number"}])
    assert _data_entries()[-1]["changes"]["record"]["qty"] == "nan"


# ===================================================================== bulk

def test_a_bulk_file_is_all_or_nothing_and_every_row_is_audited(setup):
    before = dict(db.JOB_CODES)
    status, body = setup.bulk("job_code", [{"job_code": "jc_b1", "title": "A"}, {"job_code": "jc_b2", "title": ""},
                                           {"job_code": "jc_b3", "title": "C"}])
    assert (status, body) == (400, {"error": "invalid rows",
                                    "problems": [{"row": 2, "field": "title", "reason": "is required"}]})
    assert before == db.JOB_CODES
    rows = _data_entries()[-3:]
    assert [(e["file_row"], e["action"], e["outcome"], e["reason"]) for e in rows] == [
        (1, "bulk_row", "violation", NOT_SAVED), (2, "bulk_row", "violation", "title: is required"),
        (3, "bulk_row", "violation", NOT_SAVED)]
    assert len({e["entry_id"] for e in rows}) == 3


def test_an_accepted_file_adds_every_row_with_one_entry_each(setup):
    status, body = setup.bulk("job_code", [{"job_code": f"jc_ok{i}", "title": "T"} for i in range(3)])
    assert status == 201 and body["added"] == 3
    assert [r["record"]["job_code"] for r in body["records"]] == ["jc_ok0", "jc_ok1", "jc_ok2"]
    assert [(e["file_row"], e["outcome"], e["record_id"]) for e in _data_entries()[-3:]] == [
        (1, "allowed", "jc_ok0"), (2, "allowed", "jc_ok1"), (3, "allowed", "jc_ok2")]
    assert writes._state["quota"][(setup.id, "job_code")] == 4


def test_a_501_row_file_gets_one_entry(setup):
    before = len(_data_entries())
    status, body = setup.bulk("job_code", [{"job_code": f"jc_{i}", "title": "T"} for i in range(501)])
    assert (status, body["error"]) == (400, "file must hold 1 to 500 rows")
    entries = _data_entries()[before:]
    assert len(entries) == 1 and entries[0]["file_row"] is None
    assert setup.bulk("job_code", [])[0] == 400
    assert len(_data_entries()) - before == 2


def test_an_expired_session_with_three_rows_gets_three_entries(setup, clock):
    session = Session(REGIONAL)
    clock.set(minutes=20)
    before = len(_data_entries())
    status, body = session.bulk("job_code", [{"job_code": f"jc_e{i}", "title": "T"} for i in range(3)])
    assert (status, body) == (401, {"error": "no active session", "problems": [{"reason": "no active session"}]})
    entries = _data_entries()[before:]
    assert [(e["user_id"], e["session_id"], e["file_row"]) for e in entries] == [
        ("unknown", None, 1), ("unknown", None, 2), ("unknown", None, 3)]


def test_a_parse_error_row_is_a_problem_row(setup):
    rows = [{"row": 1, "record": {"job_code": "jc_p1", "title": "T"}}, {"row": 2, "parse_error": "wrong column count"}]
    status, body = setup.bulk_rows("job_code", rows)
    assert (status, body["problems"]) == (400, [{"row": 2, "reason": "could not read line: wrong column count"}])
    assert [e["reason"] for e in _data_entries()[-2:]] == [NOT_SAVED, "could not read line: wrong column count"]
    assert _data_entries()[-1]["changes"] == {"parse_error": "wrong column count"}


def test_rows_repeating_an_id_are_refused(setup):
    status, body = setup.bulk("job_code", [{"job_code": "jc_r", "title": "A"}, {"job_code": "jc_r", "title": "B"}])
    assert status == 400
    assert body["problems"] == [{"row": 2, "field": "job_code", "reason": "repeats row 1"}]


def test_recipe_rows_are_grouped_by_menu_item(setup):
    setup.add("menu_item", _record("menu_item", "g1"))
    setup.add("menu_item", _record("menu_item", "g2"))
    line = {"raw_material_id": "rm_w", "qty": "0.5", "uom": "u_w"}
    status, body = setup.bulk("recipe", [{"menu_item_id": "mi_g1", **line}, {"menu_item_id": "mi_g2", **line},
                                         {"menu_item_id": "mi_g1", **line, "qty": "2"}])
    assert status == 201 and body["added"] == 2
    assert db.RECIPES["mi_g1"] == [{"raw_material_id": "rm_w", "qty": 0.5, "uom": "u_w"},
                                   {"raw_material_id": "rm_w", "qty": 2, "uom": "u_w"}]
    assert [(e["file_row"], e["record_id"]) for e in _data_entries()[-3:]] == [(1, "mi_g1"), (2, "mi_g2"),
                                                                              (3, "mi_g1")]
    assert writes._state["quota"][(setup.id, "recipe")] == 2  # the limit counts recipes


def test_a_recipe_group_problem_is_reported_on_each_of_its_rows(setup):
    line = {"raw_material_id": "rm_w", "qty": 1, "uom": "u_w"}
    status, body = setup.bulk("recipe", [{"menu_item_id": "mi_burger", **line}, {"menu_item_id": "mi_burger", **line}])
    assert status == 400
    group = [{"field": "menu_item_id", "reason": "must be a dashboard-added menu item"},
             {"field": "menu_item_id", "reason": "already exists"}]
    assert body["problems"] == [{"row": row, **p} for row in (1, 2) for p in group]


def test_a_unit_file_may_refer_to_units_added_by_earlier_rows(setup):
    status, _ = setup.bulk("uom", [_uom("u_f1"), _uom("u_f2", base="u_f1")])
    assert status == 201 and db.UOM["u_f2"]["base"] == "u_f1"
    status, body = setup.bulk("uom", [_uom("u_g2", base="u_g1"), _uom("u_g1")])
    assert body["problems"] == [{"row": 1, "field": "base", "reason": "must be a dashboard-added unit of measure"}]


def test_a_file_over_the_entry_limit_is_refused_whole_after_row_checks(setup):
    for i in range(97):  # setup already added one job code
        setup.add("job_code", {"job_code": f"jc_q{i}", "title": "T"})
    rows = [{"job_code": f"jc_z{i}", "title": "T"} for i in range(3)]
    status, body = setup.bulk("job_code", rows)
    assert (status, body["problems"]) == (429, [{"reason": "file over the entry limit"}])
    assert [e["reason"] for e in _data_entries()[-3:]] == ["file over the entry limit"] * 3
    assert setup.bulk("job_code", rows[:2])[0] == 201


def test_bulk_employees_take_ids_in_row_order_from_the_path_site(setup):
    rows = [{**_record("employee", i), "available_days": "Mon|Tue", "hourly_rate": "13",
             "max_weekly_hours_preference": "20", "site_id": "site_001"} for i in range(3)]
    status, body = setup.bulk("employee", rows, site="site_003")
    assert status == 201
    assert [r["record"]["employee_id"] for r in body["records"]] == [
        "emp_site_003_d001", "emp_site_003_d002", "emp_site_003_d003"]
    assert {db.EMPLOYEES[r["record"]["employee_id"]]["site_id"] for r in body["records"]} == {"site_003"}


# ================================================================ request ids

def test_a_repeated_request_id_replays_the_original_response(setup):
    body = setup.body(record=_uom("u_rep"))
    first = writes.write("uom", "add", setup.claims, None, None, body)
    before = len(_data_entries())
    assert writes.write("uom", "add", setup.claims, None, None, copy.deepcopy(body)) == first
    assert len(_data_entries()) == before and writes._state["quota"][(setup.id, "uom")] == 2


def test_a_refusal_is_replayed_too(setup):
    body = setup.body(record={"uom_id": "u_x"})
    first = writes.write("uom", "add", setup.claims, None, None, body)
    assert first[0] == 400
    before = len(_data_entries())
    assert writes.write("uom", "add", setup.claims, None, None, body) == first
    assert len(_data_entries()) == before


def test_a_concurrent_replay_gives_one_change_and_one_entry(setup):
    body = setup.body(record=_uom("u_conc"))
    before = len(_data_entries())
    results, barrier = [], threading.Barrier(2)

    def send():
        barrier.wait()
        results.append(writes.write("uom", "add", setup.claims, None, None, copy.deepcopy(body)))

    threads = [threading.Thread(target=send) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results[0] == results[1] and results[0][0] == 201
    assert len(_data_entries()) - before == 1
    assert writes._state["quota"][(setup.id, "uom")] == 2


def test_a_reused_request_id_gets_409_and_keeps_the_stored_record(setup):
    body = setup.body(record=_uom("u_one"))
    first = writes.write("uom", "add", setup.claims, None, None, body)
    other = {**body, "record": _uom("u_two")}
    assert writes.write("uom", "add", setup.claims, None, None, other) == (409, {"error": "request id reused"})
    assert "u_two" not in db.UOM
    assert _data_entries()[-1]["reason"] == "request id reused"
    assert writes.write("uom", "add", setup.claims, None, None, body) == first


def test_a_missing_request_id_is_never_stored(setup):
    before = len(_data_entries())
    for _ in range(2):
        body = {"session_id": setup.id, "record": _uom("u_noid")}
        assert writes.write("uom", "add", setup.claims, None, None, body) == (
            400, {"error": "missing or malformed request id"})
    assert len(_data_entries()) - before == 2
    assert all(None not in log and "" not in log for log in writes._state["requests"].values())
    too_long = {"session_id": setup.id, "request_id": "r" * 101, "record": _uom("u_noid")}
    assert writes.write("uom", "add", setup.claims, None, None, too_long)[0] == 400
    assert "r" * 101 not in writes._state["requests"][REGIONAL]


# ============================================================== malformed

def _nested(levels):
    value = {}
    for _ in range(levels - 2):
        value = {"a": value}
    return value


@pytest.mark.parametrize("levels", [64, 600])
def test_a_deeply_nested_record_gets_400_and_one_marker_entry(setup, levels):
    before = len(_data_entries())
    body = setup.body(record=_nested(levels))
    status, payload = writes.write("uom", "add", setup.claims, None, None, body)
    assert (status, payload["error"]) == (400, "malformed request")
    [entry] = _data_entries()[before:]
    assert entry["changes"] == {"truncated": True, "unserializable": True}
    assert (entry["user_id"], entry["session_id"]) == ("unknown", setup.id)


@pytest.mark.parametrize("body", [[1, 2], {"request_id": ["r"], "record": {}}, {"session_id": 5, "record": {}},
                                  "text"])
def test_a_malformed_envelope_gets_400_and_one_entry(setup, body):
    before = len(_data_entries())
    assert writes.write("uom", "add", setup.claims, None, None, body)[1]["error"] == "malformed request"
    [entry] = _data_entries()[before:]
    assert (entry["outcome"], entry["user_id"]) == ("violation", "unknown")
    assert entry["reason"].startswith("malformed request")


def test_a_malformed_request_records_only_a_session_id_naming_a_session(setup):
    """BR8.3: a session id that matches no session is not recorded."""
    for session_id, recorded in ((setup.id, setup.id), ("s" * 100, None), ("s" * 101, None)):
        writes.write("uom", "add", setup.claims, None, None, {"session_id": session_id, "record": "x"})
        assert _data_entries()[-1]["session_id"] == recorded


def test_another_users_live_session_id_is_never_recorded(setup):
    """BR8.3: a session id is recorded only when it belongs to the caller."""
    other = Session(DEV)
    writes.write("uom", "add", setup.claims, None, None, {"session_id": other.id, "record": "x"})
    assert _data_entries()[-1]["session_id"] is None
    status, _ = writes.write("uom", "add", setup.claims, None, None,
                             {"session_id": other.id, "request_id": str(uuid.uuid4()), "record": {}})
    assert status == 401
    assert _data_entries()[-1]["session_id"] is None
    assert other.id in writes._state["sessions"]  # the other user's session is untouched


def test_a_malformed_bulk_envelope_gets_one_entry(setup):
    before = len(_data_entries())
    status, body = writes.bulk("job_code", setup.claims, None, setup.body(rows="not a list"))
    assert (status, body["error"]) == (400, "malformed request")
    assert len(_data_entries()) - before == 1


# ============================================================== failure paths

def _break_appends(monkeypatch):
    monkeypatch.setattr(audit, "_write_all", lambda fd, data: (_ for _ in ()).throw(OSError("read-only")))


def test_an_unwritable_audit_gives_503_and_changes_nothing(setup, monkeypatch, audit_path, capsys):
    before = (dict(db.EMPLOYEES), dict(writes._state["quota"]), dict(writes._state["id_counters"]))
    _break_appends(monkeypatch)
    capsys.readouterr()
    status, body = setup.add("employee", _record("employee", "u"))
    assert (status, body) == (503, {"error": "audit unavailable"})
    assert (dict(db.EMPLOYEES), dict(writes._state["quota"]), dict(writes._state["id_counters"])) == before
    lines = [line for line in capsys.readouterr().err.splitlines() if line.startswith("[mock-hsm] ERROR writes:")]
    # The key is the one the failed entry carried: the id allocated, then given back.
    assert lines == ["[mock-hsm] ERROR writes: audit unavailable for add employee/emp_site_001_d001"]
    assert setup.id not in "".join(lines)
    # The trail stays failed closed: logins and logouts get 503 too.
    assert writes.start_session(setup.claims) == (503, {"error": "audit unavailable"})
    assert writes.end_session(setup.claims, setup.id) == (503, {"error": "session ended, audit unavailable"})
    monkeypatch.undo()
    audit.configure(audit_path)  # the operator restarts the audit
    retry = Session(REGIONAL)
    assert retry.add("employee", _record("employee", "u"))[1]["record"]["employee_id"] == "emp_site_001_d001"


def test_a_503_names_the_record_key_in_its_log_line(setup, monkeypatch, capsys):
    _break_appends(monkeypatch)
    capsys.readouterr()
    assert setup.add("job_code", {"job_code": "jc_log\x07", "title": "T"})[0] == 503
    err = capsys.readouterr().err
    assert "[mock-hsm] ERROR writes: audit unavailable for add job_code/jc_log\n" in err


def test_a_forced_apply_failure_gives_500_and_a_compensating_entry(setup, monkeypatch, capsys):
    def explode(*args):
        raise KeyError("boom")

    monkeypatch.setattr(writes, "build_stored", explode)
    capsys.readouterr()
    status, body = setup.add("job_code", {"job_code": "jc_fail", "title": "T"})
    assert (status, body) == (500, {"error": "failed after audit"})
    assert "jc_fail" not in db.JOB_CODES and writes._state["quota"][(setup.id, "job_code")] == 1
    allowed, compensating = _data_entries()[-2:]
    assert (allowed["outcome"], compensating["outcome"]) == ("allowed", "violation")
    assert compensating["reason"] == "failed after audit: KeyError"
    assert compensating["record_id"] == allowed["record_id"] == "jc_fail"
    assert "apply failed after audit for add job_code/jc_fail (KeyError)" in capsys.readouterr().err


def test_a_failed_compensating_entry_is_logged(setup, monkeypatch, capsys):
    real_batch = audit.append_batch

    def explode(*args):
        monkeypatch.setattr(audit, "append_batch", lambda entries: (_ for _ in ()).throw(
            audit.AuditUnavailable("down")))
        raise RuntimeError("boom")

    monkeypatch.setattr(writes, "build_stored", explode)
    capsys.readouterr()
    assert setup.add("job_code", {"job_code": "jc_c", "title": "T"})[0] == 500
    assert "compensating entry failed for job_code/jc_c" in capsys.readouterr().err
    assert audit.append_batch is not real_batch


def test_a_double_invalid_entry_gives_a_distinct_503(setup, monkeypatch, capsys):
    def refuse(entry):
        raise audit.InvalidEntry("nope")

    monkeypatch.setattr(audit, "append", refuse)
    capsys.readouterr()
    status, body = setup.add("job_code", {"job_code": "jc_inv", "title": "T"})
    assert (status, body) == (503, {"error": "audit could not record the attempt"})
    assert "jc_inv" not in db.JOB_CODES
    assert "audit could not record add job_code/jc_inv" in capsys.readouterr().err


@pytest.mark.parametrize("error", [audit.InvalidEntry("nope"), RecursionError()])
def test_an_entry_refused_once_is_not_retried(setup, monkeypatch, error):
    """BR8.2: no retry with the marker; 503, nothing applied, one append call."""
    calls = []

    def refuse(entry):
        calls.append(entry)
        raise error

    monkeypatch.setattr(audit, "append", refuse)
    status, body = setup.add("job_code", {"job_code": "jc_m", "title": "T"})
    assert (status, body) == (503, {"error": "audit could not record the attempt"})
    assert "jc_m" not in db.JOB_CODES and writes._state["quota"][(setup.id, "job_code")] == 1
    assert len(calls) == 1 and calls[0]["changes"] == {"record": {"job_code": "jc_m", "title": "T"}}
    monkeypatch.undo()
    assert setup.add("job_code", {"job_code": "jc_m", "title": "T"})[0] == 201  # nothing was stored for it


def test_an_invalid_bulk_batch_is_refused_whole_without_retry(setup, monkeypatch):
    calls = []

    def refuse(entries):
        calls.append(entries)
        raise audit.InvalidEntry("nope")

    monkeypatch.setattr(audit, "append_batch", refuse)
    before = dict(db.JOB_CODES)
    status, body = setup.bulk("job_code", [{"job_code": f"jc_ib{i}", "title": "T"} for i in range(3)])
    assert (status, body) == (503, {"error": "audit could not record the attempt"})
    assert before == db.JOB_CODES and len(calls) == 1 and len(calls[0]) == 3


def test_a_failed_login_append_never_activates_the_session(setup, monkeypatch):
    _break_appends(monkeypatch)
    sessions = set(writes._state["sessions"])
    assert writes.start_session(_claims(DEV))[0] == 503
    assert set(writes._state["sessions"]) == sessions


# =================================================================== sessions

def test_login_and_logout_are_audited_with_the_session_id():
    session = Session(DEV)
    assert writes.end_session(session.claims, session.id) == (200, {"active": False, "ended_reason": "logout"})
    login, logout = _entries()[-2:]
    assert [(e["action"], e["outcome"], e["user_id"], e["session_id"], e["source"]) for e in (login, logout)] == [
        ("login", "allowed", DEV, session.id, "dashboard"), ("logout", "allowed", DEV, session.id, "dashboard")]
    assert writes.session_status(session.claims, session.id) == (200, {"active": False, "ended_reason": "logout"})
    assert writes.end_session(session.claims, session.id)[0] == 401


def test_only_the_sessions_own_persona_may_check_or_end_it():
    session = Session(REGIONAL)
    other = _claims(DEV)
    assert writes.session_status(other, session.id)[0] == 403
    assert writes.end_session(other, session.id)[0] == 403
    assert writes.session_status(session.claims, session.id) == (200, {"active": True, "ended_reason": None})
    assert writes.session_status(other, "unknown-id") == (200, {"active": False, "ended_reason": None})
    assert writes.end_session(other, "unknown-id")[0] == 401


def test_the_idle_timeline(setup, clock):
    """NFR7.1: reads never refresh; 14:59 idle is fine; 15:00 is not."""
    a, b = Session(REGIONAL), Session(REGIONAL)
    assert a.add("job_code", {"job_code": "jc_a0", "title": "T"})[0] == 201
    assert b.add("job_code", {"job_code": "jc_b0", "title": "T"})[0] == 201
    clock.set(minutes=10)
    assert writes.session_status(a.claims, a.id)[1]["active"] and writes.session_status(b.claims, b.id)[1]["active"]
    writes.meta_map("job_code")
    clock.set(minutes=14)
    assert writes.session_status(a.claims, a.id)[1]["active"]
    clock.set(minutes=14, seconds=59)
    assert a.add("job_code", {"job_code": "jc_a1", "title": "T"})[0] == 201
    clock.set(minutes=15)
    assert b.add("job_code", {"job_code": "jc_b1", "title": "T"})[0] == 401
    assert writes.session_status(b.claims, b.id) == (200, {"active": False, "ended_reason": "idle"})
    clock.set(minutes=29, seconds=58)
    assert a.add("job_code", {"job_code": "jc_a2", "title": "T"})[0] == 201  # refreshed at 14:59


def test_a_bulk_write_refreshes_the_session(setup, clock):
    clock.set(minutes=14)
    assert setup.bulk("job_code", [{"job_code": "jc_bk", "title": "T"}])[0] == 201
    clock.set(minutes=28)
    assert setup.add("job_code", {"job_code": "jc_bk2", "title": "T"})[0] == 201


def test_a_refused_write_also_refreshes_the_session(setup, clock):
    clock.set(minutes=14)
    assert setup.add("job_code", {"job_code": "jc_w", "title": "dup"})[0] == 400
    clock.set(minutes=28)
    assert setup.add("job_code", {"job_code": "jc_new", "title": "T"})[0] == 201


def test_a_session_used_with_a_foreign_token_gets_401_audited_as_unknown(setup):
    before = dict(db.JOB_CODES)
    body = setup.body(record={"job_code": "jc_foreign", "title": "T"})
    status, payload = writes.write("job_code", "add", _claims(DEV), None, None, body)
    assert (status, payload) == (401, {"error": "no active session"})
    assert before == db.JOB_CODES
    entry = _data_entries()[-1]
    assert (entry["user_id"], entry["persona"], entry["session_id"]) == ("unknown", None, None)


def test_session_ids_never_appear_in_meta(setup):
    meta = writes.meta_map("job_code")["jc_w"]
    assert setup.id not in str(meta) and set(meta) == set(writes.WIRE_META_FIELDS)


# ======================================================== audit entry shape
# BR8.3 (FD Q8), BR2.3, BR8.6, NFR2.7: what each entry records in ``changes``.

ENTRY_FIELDS = ("user_id", "persona", "session_id", "source", "action", "kind", "record_id", "site_id",
                "changes", "file_row")
MARKER_TEXT = "...(truncated)"


def _last_for(kind):
    return [e for e in _data_entries() if e["kind"] == kind][-1]


def test_an_allowed_add_records_the_submitted_record(setup):
    record = {"job_code": "jc_add", "title": "Cook", "unknown_field": "kept as submitted"}
    assert setup.add("job_code", record)[0] == 201
    assert _last_for("job_code")["changes"] == {"record": record}
    # A site kind records the record alone: the site is the entry's own field.
    employee = _record("employee", "add")
    status, body = setup.add("employee", employee)
    assert status == 201
    entry = _last_for("employee")
    assert (entry["changes"], entry["site_id"]) == ({"record": employee}, "site_001")
    assert entry["record_id"] == body["record"]["employee_id"]


def test_an_allowed_update_records_only_the_changed_fields(setup):
    vendor = _record("vendor", "up")
    assert setup.add("vendor", vendor)[0] == 201
    assert setup.update("vendor", "v_up", {**vendor, "name": "Renamed"}, 1)[0] == 200
    assert _last_for("vendor")["changes"] == {"before": {"name": "Vendor up"}, "after": {"name": "Renamed"}}
    assert setup.update("vendor", "v_up", {**vendor, "name": "Renamed"}, 2)[0] == 200  # nothing changed
    assert _last_for("vendor")["changes"] == {"before": {}, "after": {}}


@pytest.mark.parametrize("kind", ["on_hand", "recipe", "employee"])
def test_an_allowed_update_of_each_record_shape_records_the_change(setup, kind):
    _prereqs(setup, kind, "sh")
    status, body = setup.add(kind, _record(kind, "sh"))
    assert status == 201
    key = body["record"][writes.KINDS[kind].key]
    assert setup.update(kind, key, _changed(_record(kind, "sh")), 1)[0] == 200
    changes = _last_for(kind)["changes"]
    expected = {
        "on_hand": ({"qty": 5}, {"qty": 6}),
        "recipe": ({"lines": [{"raw_material_id": "rm_w", "qty": 1, "uom": "u_w"}]},
                   {"lines": [{"raw_material_id": "rm_w", "qty": 2, "uom": "u_w"}]}),
        "employee": ({"name": "Emp sh"}, {"name": "Emp sh (edited)"}),
    }[kind]
    assert (changes["before"], changes["after"]) == expected


def test_an_allowed_delete_records_the_deleted_record(setup):
    assert setup.add("job_code", {"job_code": "jc_del", "title": "Gone"})[0] == 201
    assert setup.delete("job_code", "jc_del", 1)[0] == 200
    assert _last_for("job_code")["changes"] == {"record": {"job_code": "jc_del", "title": "Gone"}}
    _prereqs(setup, "on_hand", "del")
    assert setup.add("on_hand", _record("on_hand", "del"))[0] == 201
    assert setup.delete("on_hand", "rm_del", 1)[0] == 200
    assert _last_for("on_hand")["changes"] == {"record": {"site_id": "site_001", "raw_material_id": "rm_del",
                                                          "qty": 5}}


def test_a_refused_write_records_what_was_submitted(setup):
    assert setup.add("job_code", {"job_code": "jc_w", "title": "dup"})[0] == 400
    assert _last_for("job_code")["changes"] == {"record": {"job_code": "jc_w", "title": "dup"}}
    assert setup.update("job_code", "jc_w", {"title": "Stale"}, 7)[0] == 409
    assert _last_for("job_code")["changes"] == {"record": {"title": "Stale"}}  # no version, no previous values
    assert setup.delete("job_code", "jc_w", 7)[0] == 409
    assert _last_for("job_code")["changes"] == {"version": 7}
    # An in-scope site write keeps the site out of changes.
    assert setup.add("employee", {**_record("employee", "r"), "name": ""})[0] == 400
    assert "site_id" not in _last_for("employee")["changes"]


def test_unknown_and_out_of_scope_sites_are_kept_in_changes(setup):
    rm = Session(RM)
    employee = _record("employee", "site")
    assert rm.add("employee", employee, site="site_404")[0] == 404
    unknown = _last_for("employee")
    assert (unknown["site_id"], unknown["changes"]) == (None, {"record": employee, "site_id": "site_404"})
    assert rm.add("employee", employee, site="site_002")[0] == 403
    out_of_scope = _last_for("employee")
    assert (out_of_scope["site_id"], out_of_scope["changes"]) == (
        "site_002", {"record": employee, "site_id": "site_002"})
    assert rm.update("employee", "emp_x", employee, 1, site="site_404")[0] == 404
    assert _last_for("employee")["changes"] == {"record": employee, "site_id": "site_404"}
    assert rm.delete("employee", "emp_x", 1, site="site_002")[0] == 403
    assert _last_for("employee")["changes"] == {"version": 1, "site_id": "site_002"}


def test_bulk_rows_record_their_row_and_a_refused_file_keeps_the_site(setup):
    assert setup.bulk("job_code", [{"job_code": "jc_br", "title": "T"}])[0] == 201
    assert _last_for("job_code")["changes"] == {"record": {"job_code": "jc_br", "title": "T"}}
    rm = Session(RM)
    employee = _record("employee", "bulk")
    assert rm.bulk("employee", [employee], site="site_003")[0] == 403
    entry = _last_for("employee")
    assert (entry["file_row"], entry["changes"]) == (1, {"record": employee, "site_id": "site_003"})


def test_a_whole_file_entry_records_its_name_and_row_count(setup):
    assert setup.bulk("job_code", [])[0] == 400
    assert _data_entries()[-1]["changes"] == {"file_name": "upload.csv", "row_count": 0}


def test_a_refused_5000_character_name_is_recorded_cut_to_1024(setup):
    name = "n" * 5_000
    assert setup.add("vendor", {**_record("vendor", "long"), "name": name})[0] == 400
    recorded = _last_for("vendor")["changes"]["record"]["name"]
    assert len(recorded) == 1_024 and recorded.endswith(MARKER_TEXT) and recorded.startswith("n" * 1_000)


def test_long_reason_and_record_id_are_cut_but_identity_fields_never(setup):
    key = "k" * 5_000
    status, body = setup.update("job_code", key, {"title": "T"}, 1)
    assert (status, body["error"]) == (404, f"no job code {key}")
    entry = _last_for("job_code")
    assert len(entry["record_id"]) == len(entry["reason"]) == 1_024
    assert entry["record_id"].endswith(MARKER_TEXT) and entry["reason"].startswith("no job code kkk")
    assert (entry["user_id"], entry["persona"], entry["session_id"]) == (REGIONAL, "REGIONAL_MANAGER", setup.id)


def test_a_compensating_entry_repeats_every_field_of_the_allowed_entry(setup, monkeypatch):
    """BR8.6, for an update (the add case is covered above)."""
    vendor = _record("vendor", "comp")
    assert setup.add("vendor", vendor)[0] == 201

    def explode(*args):
        raise KeyError("boom")

    monkeypatch.setattr(writes, "build_stored", explode)
    assert setup.update("vendor", "v_comp", {**vendor, "name": "New"}, 1) == (500, {"error": "failed after audit"})
    allowed, compensating = _data_entries()[-2:]
    assert allowed["changes"] == {"before": {"name": "Vendor comp"}, "after": {"name": "New"}}
    assert {k: compensating[k] for k in ENTRY_FIELDS} == {k: allowed[k] for k in ENTRY_FIELDS}
    assert (compensating["outcome"], compensating["reason"]) == ("violation", "failed after audit: KeyError")
    assert db.VENDORS["v_comp"]["name"] == "Vendor comp"


def test_compensating_bulk_entries_repeat_each_rows_entry(setup, monkeypatch):
    def explode(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(writes, "build_stored", explode)
    assert setup.bulk("job_code", [{"job_code": f"jc_cb{i}", "title": "T"} for i in range(2)])[0] == 500
    entries = _data_entries()[-4:]
    allowed, compensating = entries[:2], entries[2:]
    for a, c in zip(allowed, compensating, strict=True):
        assert {k: c[k] for k in ENTRY_FIELDS} == {k: a[k] for k in ENTRY_FIELDS}
        assert (a["outcome"], c["outcome"]) == ("allowed", "violation")
