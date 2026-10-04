"""
Route and integration tests for the U1 dashboard data writes over HTTP, with
an in-process server on an ephemeral port: sessions, every kind's add /
update / delete / bulk / template routes, dispatcher hardening, unchanged
read payloads, ``?with=meta``, and data reach into the reorder calculation
and the employee roster. The ``perf`` tests measure the NFR4 targets and
the NFR1.7 concurrency result with in-process calls; each failure message
carries the measured value next to its target.
"""
import http.client
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.inventory_agent import compute_reorder_needs
from mock_hsm import audit, db, writes
from mock_hsm.auth import mint_token, verify_token
from mock_hsm.server import Handler, ThreadingHTTPServer, inventory_raw_materials

RM, REGIONAL, DEV = "user_rm_midtown", "user_regional_atl", "user_dev_tester"
ALL_SEEING = {"user_id": "test-auditor", "persona": "SYSTEM_ADMIN", "site_ids": [], "region_id": None}

# Targets (NFR4.1-NFR4.3). Never relax these to make a test pass.
SINGLE_WRITE_P95_SECONDS = 0.200
BULK_FILE_SECONDS = 2.0
READ_SLOWDOWN_P95_SECONDS = 0.050


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # ephemeral port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _call(base_url, user, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base_url + path, data=data, method=method)
    request.add_header("Authorization", f"Bearer {mint_token(user)}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _entries():
    entries, before = [], None
    while True:
        page = audit.page(ALL_SEEING, before)
        entries += page["entries"]
        before = page["next_before"]
        if before is None:
            return entries[::-1]


class Client:
    """One persona with a login session, over HTTP."""

    def __init__(self, base_url, user):
        self.base_url, self.user = base_url, user
        status, body = self.call("POST", "/sessions")
        assert status == 201, body
        self.session = body["session_id"]

    def call(self, method, path, body=None):
        return _call(self.base_url, self.user, method, path, body)

    def send(self, method, path, **fields):
        return self.call(method, path, {"session_id": self.session, "request_id": str(uuid.uuid4()), **fields})


def _paths(kind_name, site_id="site_001"):
    kind = writes.KINDS[kind_name]
    return kind.collection_path.format(site_id=site_id), kind.item_path.replace("{site_id}", site_id)


def _uom(uom_id, base=None):
    return {"uom_id": uom_id, "name": f"unit {uom_id}", "base": base or uom_id, "factor_to_base": 1}


def _record(kind, tag):
    return {
        "menu_item": {"menu_item_id": f"mi_{tag}", "name": f"Item {tag}", "gl_code": "GL-BEV"},
        "recipe": {"menu_item_id": f"mi_{tag}", "lines": [{"raw_material_id": "rm_w", "qty": 1, "uom": "u_w"}]},
        "raw_material": {"raw_material_id": f"rm_{tag}", "name": f"RM {tag}", "uom": "u_w"},
        "uom": _uom(f"u_{tag}"),
        "vendor": {"vendor_id": f"v_{tag}", "name": "Vendor", "lead_time_days": 2, "price_list": {"rm_w": 1.25},
                   "min_order_value": 10},
        "employee": {"name": f"Emp {tag}", "job_code": "jc_w", "hourly_rate": 14.5,
                     "max_weekly_hours_preference": 30, "available_days": ["Mon", "Wed"]},
        "job_code": {"job_code": f"jc_{tag}", "title": "Title"},
        "on_hand": {"raw_material_id": f"rm_{tag}", "qty": 5},
        "par_level": {"raw_material_id": f"rm_{tag}", "qty": 5},
        "reorder_point": {"raw_material_id": f"rm_{tag}", "qty": 5},
        "labor_rule": {"jurisdiction": f"J_{tag}", "weekly_ot_threshold_hours": 40, "daily_ot_threshold_hours": 8,
                       "ot_multiplier": 1.5, "max_consecutive_days": 6, "min_rest_hours_between_shifts": 10,
                       "max_shift_length_hours": 10, "note": "Test rule"},
    }[kind]


def _csv_row(kind, tag):
    """The same record as the dashboard sends a CSV row: list fields as cell text."""
    record = {k: str(v) if isinstance(v, int | float) else v for k, v in _record(kind, tag).items()}
    if kind == "vendor":
        record["price_list"] = "rm_w=1.25"
    if kind == "employee":
        record["available_days"] = "Mon|Wed"
    if kind == "recipe":
        record = {"menu_item_id": f"mi_{tag}", "raw_material_id": "rm_w", "qty": "1", "uom": "u_w"}
    return record


def _prereqs(client, kind, tag):
    if kind == "recipe":
        assert client.send("POST", _paths("menu_item")[0], record=_record("menu_item", tag))[0] == 201
    if kind in ("on_hand", "par_level", "reorder_point"):
        assert client.send("POST", _paths("raw_material")[0], record=_record("raw_material", tag))[0] == 201


@pytest.fixture
def regional(base_url):
    client = Client(base_url, REGIONAL)
    for kind, record in (("uom", _uom("u_w")), ("raw_material", _record("raw_material", "w")),
                         ("job_code", {"job_code": "jc_w", "title": "Worker"})):
        assert client.send("POST", _paths(kind)[0], record=record)[0] == 201
    return client


# =================================================================== sessions

def test_session_start_logout_and_status(base_url):
    client = Client(base_url, DEV)
    path = f"/sessions/{client.session}"
    assert client.call("GET", path) == (200, {"active": True, "ended_reason": None})
    assert _call(base_url, REGIONAL, "GET", path)[0] == 403
    assert _call(base_url, REGIONAL, "POST", path + "/logout")[0] == 403
    assert client.call("POST", path + "/logout") == (200, {"active": False, "ended_reason": "logout"})
    assert client.call("GET", path) == (200, {"active": False, "ended_reason": "logout"})
    assert client.call("POST", path + "/logout")[0] == 401
    assert client.call("GET", "/sessions/nope") == (200, {"active": False, "ended_reason": None})
    assert client.call("POST", "/sessions/nope/logout")[0] == 401


def test_session_start_returns_the_contract_shape(base_url):
    status, body = _call(base_url, RM, "POST", "/sessions")
    assert status == 201
    assert set(body) == {"session_id", "user_id", "persona", "idle_timeout_seconds"}
    assert (body["user_id"], body["persona"], body["idle_timeout_seconds"]) == (RM, "RESTAURANT_MANAGER", 900)


def test_a_bad_token_gets_401_before_any_route(base_url):
    request = urllib.request.Request(base_url + "/sessions", data=b"{}", method="POST")
    request.add_header("Authorization", "Bearer forged.token")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=10)
    assert exc.value.code == 401
    assert _entries() == []


# ============================================================ per-kind routes

@pytest.mark.parametrize("kind", list(writes.KINDS))
def test_each_kinds_routes_work(regional, kind):
    collection, item = _paths(kind)
    status, body = regional.call("GET", collection + "/template")
    assert (status, body["columns"]) == (200, list(writes.KINDS[kind].csv_columns))
    _prereqs(regional, kind, "one")
    status, body = regional.send("POST", collection, record=_record(kind, "one"))
    assert status == 201, body
    key = body["record"]["employee_id" if kind == "employee" else writes.KINDS[kind].key]
    status, body = regional.send("PUT", item.format(record_id=key), record=_record(kind, "one"), version=1)
    assert (status, body["meta"]["version"]) == (200, 2), body
    _prereqs(regional, kind, "two")
    status, body = regional.send("POST", collection + "/bulk", source="csv", file_name="f.csv",
                                 rows=[{"row": 1, "record": _csv_row(kind, "two")}])
    assert (status, body["added"]) == (201, 1), body
    bulk_key = body["records"][0]["record"]["employee_id" if kind == "employee" else writes.KINDS[kind].key]
    assert regional.send("DELETE", item.format(record_id=key), version=2)[0] == 200
    read_path = "/labor/rules?with=meta" if kind == "labor_rule" else collection + "?with=meta"
    status, body = regional.call("GET", read_path)
    assert status == 200 and key not in body["meta"][kind] and bulk_key in body["meta"][kind]


def test_site_kinds_take_their_site_from_the_path(regional):
    status, body = regional.send("POST", "/inventory/sites/site_003/on-hand",
                                 record={"raw_material_id": "rm_w", "qty": 4, "site_id": "site_001"})
    assert status == 201 and body["record"] == {"site_id": "site_003", "raw_material_id": "rm_w", "qty": 4}
    assert db.ON_HAND["site_003"]["rm_w"] == 4 and "rm_w" not in db.ON_HAND["site_001"]
    status, body = regional.send("POST", "/labor/sites/site_002/employees/bulk", source="csv", file_name="e.csv",
                                 rows=[{"row": 1, "record": {**_csv_row("employee", "s"), "site_id": "site_001"}}])
    assert status == 201 and body["records"][0]["record"]["site_id"] == "site_002"
    status, body = regional.call("GET", "/inventory/sites/site_404/on-hand/template")
    assert status == 404


def test_the_restaurant_manager_is_held_to_its_site_over_http(regional, base_url):
    rm = Client(base_url, RM)
    assert rm.send("POST", "/labor/sites/site_002/employees", record=_record("employee", "x"))[0] == 403
    assert rm.send("POST", "/sales/job-codes", record={"job_code": "jc_rm", "title": "T"})[0] == 403
    assert rm.send("POST", "/labor/sites/site_001/employees", record=_record("employee", "x"))[0] == 201


def test_the_recipe_template_route_does_not_collide_with_the_item_route(regional):
    status, body = regional.call("GET", "/inventory/recipes/template")
    assert (status, body["csv"]) == (200, "menu_item_id,raw_material_id,qty,uom\n")
    status, body = regional.call("GET", "/inventory/recipes/mi_soda")
    assert (status, body) == (200, {"menu_item_id": "mi_soda", "lines": db.RECIPES["mi_soda"]})
    assert regional.send("PUT", "/inventory/recipes/template", record={}, version=1)[0] == 404
    assert regional.send("POST", "/sales/job-codes", record={"job_code": "bulk", "title": "T"})[0] == 400


def test_refusals_carry_error_and_problems(regional):
    status, body = regional.send("POST", "/inventory/vendors", record={"vendor_id": "v_bad", "name": "<b>"})
    assert status == 400 and body["error"] == "invalid record"
    assert {p["field"] for p in body["problems"]} == {"name", "lead_time_days", "price_list", "min_order_value"}


# ================================================================ reads (C6)

def test_existing_get_payloads_are_unchanged(regional):
    """NFR4.4: the same keys and values as before, for seeded data."""
    expected = {
        "/catalog/menu-items": {"menu_items": list(db.MENU_ITEMS.values())},
        "/inventory/uom": {"uom": list(db.UOM.values())},
        "/inventory/raw-materials": {"raw_materials": list(db.RAW_MATERIALS.values())},
        "/inventory/vendors": {"vendors": list(db.VENDORS.values())},
        "/sales/job-codes": {"job_codes": list(db.JOB_CODES.values())},
        "/sales/gl-codes": {"gl_codes": ["GL-BEV", "GL-FOOD"]},
        "/inventory/recipes/mi_burger": {"menu_item_id": "mi_burger", "lines": db.RECIPES["mi_burger"]},
        "/labor/rules?jurisdiction=GA": db.LABOR_RULES_BY_JURISDICTION["GA"],
        "/inventory/sites/site_002/on-hand": {"site_id": "site_002", "on_hand": db.ON_HAND["site_002"],
                                              "par_levels": db.PAR_LEVELS, "reorder_points": db.REORDER_POINTS},
        "/labor/sites/site_003/employees": {"site_id": "site_003", "employees": [
            e for e in db.EMPLOYEES.values() if e["site_id"] == "site_003"]},
    }
    for path, payload in expected.items():
        status, body = regional.call("GET", path)
        assert status == 200 and set(body) == set(payload), path
        assert body == payload, path
    assert regional.call("GET", "/labor/rules?jurisdiction=XX")[0] == 404


def test_new_collection_reads(regional):
    assert regional.call("GET", "/inventory/recipes")[1] == {"recipes": db.RECIPES}
    assert regional.call("GET", "/inventory/par-levels")[1] == {"par_levels": db.PAR_LEVELS}
    assert regional.call("GET", "/inventory/reorder-points")[1] == {"reorder_points": db.REORDER_POINTS}


def test_with_meta_returns_the_documented_shapes(regional):
    status, body = regional.call("GET", "/inventory/sites/site_001/on-hand?with=meta")
    assert status == 200 and set(body) == {"site_id", "on_hand", "par_levels", "reorder_points", "meta"}
    assert set(body["meta"]) == {"on_hand", "par_level", "reorder_point"}
    assert set(body["meta"]["on_hand"]) == set(body["on_hand"])
    assert body["meta"]["par_level"]["rm_bun"]["origin"] == "seeded"
    status, body = regional.call("GET", "/catalog/menu-items?with=meta")
    assert set(body["meta"]) == {"menu_item"} and body["meta"]["menu_item"]["mi_burger"]["created_by"] == "system"
    assert set(body["meta"]["menu_item"]["mi_burger"]) == set(writes.WIRE_META_FIELDS)
    status, body = regional.call("GET", "/labor/sites/site_002/employees?with=meta")
    assert set(body["meta"]["employee"]) == {e["employee_id"] for e in body["employees"]}
    status, body = regional.call("GET", "/labor/rules?with=meta")
    assert body == {"rules": db.LABOR_RULES_BY_JURISDICTION,
                    "meta": {"labor_rule": {"GA": writes.meta_map("labor_rule")["GA"]}}}
    status, body = regional.call("GET", "/labor/rules?jurisdiction=GA&with=meta")
    assert body == {**db.LABOR_RULES_BY_JURISDICTION["GA"], "meta": {"labor_rule": {"GA": body["meta"]["labor_rule"]["GA"]}}}
    assert regional.call("GET", "/labor/rules?jurisdiction=XX&with=meta")[0] == 404
    assert regional.session not in json.dumps(regional.call("GET", "/inventory/raw-materials?with=meta")[1])


def test_reads_keep_working_while_the_audit_trail_is_down(regional, monkeypatch):
    monkeypatch.setattr(audit, "_write_all", lambda fd, data: (_ for _ in ()).throw(OSError("ro")))
    assert regional.send("POST", "/sales/job-codes", record={"job_code": "jc_down", "title": "T"})[0] == 503
    assert regional.call("GET", "/sales/job-codes")[0] == 200
    assert regional.call("GET", "/inventory/raw-materials?with=meta")[0] == 200


# ================================================================ dispatcher

def _raw(base_url, method, path, headers, body=b""):
    host, port = base_url.removeprefix("http://").split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=30)
    conn.putrequest(method, path, skip_accept_encoding=True)
    conn.putheader("Authorization", f"Bearer {mint_token(REGIONAL)}")
    for name, value in headers.items():
        conn.putheader(name, value)
    conn.endheaders()
    if body:
        conn.send(body)
    response = conn.getresponse()
    result = response.status, json.loads(response.read())
    conn.close()
    return result


def test_a_missing_content_length_works_for_get(base_url):
    assert _raw(base_url, "GET", "/sales/job-codes", {})[0] == 200


@pytest.mark.parametrize("value", ["abc", "-1", "1.5", "+5", "1_0", ""])
def test_an_invalid_content_length_gets_400(base_url, value):
    assert _raw(base_url, "POST", "/sessions", {"Content-Length": value}) == (
        400, {"error": "invalid Content-Length"})


def test_a_2_mib_body_is_drained_and_gets_400(base_url):
    body = b" " * (2 * 1024 * 1024)
    assert _raw(base_url, "POST", "/sales/job-codes", {"Content-Length": str(len(body))}, body) == (
        400, {"error": "request too large"})
    assert _entries() == []


def test_a_body_over_8_mib_is_refused_without_reading(base_url):
    assert _raw(base_url, "POST", "/sales/job-codes", {"Content-Length": str(9 * 1024 * 1024)})[0] == 400


@pytest.mark.parametrize("body", [b'{"record": ' + b"9" * 5000 + b"}", b"[" * 200000 + b"]" * 200000,
                                  b"{not json", b'"\xff"'])
def test_unparseable_bodies_get_an_unaudited_400(base_url, body):
    assert _raw(base_url, "POST", "/sales/job-codes", {"Content-Length": str(len(body))}, body) == (
        400, {"error": "invalid JSON body"})
    assert _entries() == []


def test_put_and_delete_reach_the_dispatcher(regional):
    assert regional.call("PUT", "/nowhere", {})[0] == 404
    assert regional.call("DELETE", "/sales/job-codes/jc_w", {})[1]["error"] == "malformed request"


# ================================================================ data reach

def test_added_raw_material_with_stock_and_vendor_reaches_reorder_needs(regional):
    """BR11.1: the reorder calculation sees dashboard-added records."""
    regional.send("POST", "/inventory/raw-materials", record={"raw_material_id": "rm_new", "name": "New", "uom": "u_w"})
    regional.send("POST", "/inventory/sites/site_001/on-hand", record={"raw_material_id": "rm_new", "qty": 1})
    regional.send("POST", "/inventory/reorder-points", record={"raw_material_id": "rm_new", "qty": 5})
    regional.send("POST", "/inventory/par-levels", record={"raw_material_id": "rm_new", "qty": 20})
    regional.send("POST", "/inventory/vendors", record={"vendor_id": "v_new", "name": "New Co.", "lead_time_days": 1,
                                                        "price_list": {"rm_new": 2.5}, "min_order_value": 0})
    forecast = regional.call("GET", "/forecast/sites/site_001/sales?start_offset_days=0&days=7")[1]["forecast"]
    on_hand = regional.call("GET", "/inventory/sites/site_001/on-hand")[1]
    items = {item for day in forecast for item in day["items"]}
    recipes = {item: regional.call("GET", f"/inventory/recipes/{item}")[1]["lines"] for item in items}
    vendors = regional.call("GET", "/inventory/vendors")[1]["vendors"]
    needs = {n["raw_material_id"]: n for n in compute_reorder_needs("site_001", forecast, on_hand, recipes, vendors)}
    assert needs["rm_new"]["vendor_id"] == "v_new" and needs["rm_new"]["suggested_order_qty"] == 19.0


def test_an_added_employee_appears_in_the_site_roster(regional, base_url):
    rm = Client(base_url, RM)
    status, body = rm.send("POST", "/labor/sites/site_001/employees", record=_record("employee", "roster"))
    roster = rm.call("GET", "/labor/sites/site_001/employees")[1]["employees"]
    assert status == 201 and roster[-1] == body["record"]
    assert len(roster) == 7


# =========================================================== perf (NFR4, NFR1.7)

def _claims(user):
    return verify_token(mint_token(user))


def _p95(samples):
    return statistics.quantiles(samples, n=20, method="inclusive")[18]


def _session(user):
    return writes.start_session(_claims(user))[1]["session_id"]


def _add(user_claims, session_id, kind, record):
    body = {"session_id": session_id, "request_id": str(uuid.uuid4()), "record": record}
    return writes.write(kind, "add", user_claims, None, None, body)


@pytest.mark.perf
def test_nfr4_1_single_write_p95_within_200_ms():
    claims = _claims(REGIONAL)
    setup = _session(REGIONAL)
    assert _add(claims, setup, "uom", _uom("u_perf"))[0] == 201
    session, samples = _session(REGIONAL), []
    for i in range(200):
        kind, record = (("raw_material", {"raw_material_id": f"rm_p{i}", "name": "P", "uom": "u_perf"}) if i < 100
                        else ("job_code", {"job_code": f"jc_p{i}", "title": "P"}))
        start = time.perf_counter()
        status, _ = _add(claims, session, kind, record)
        samples.append(time.perf_counter() - start)
        assert status == 201
    p95 = _p95(samples)
    print(f"\n[perf] NFR4.1 single write p95 = {p95 * 1000:.2f} ms (target <= 200 ms)")
    assert p95 <= SINGLE_WRITE_P95_SECONDS, f"p95 {p95 * 1000:.2f} ms > target 200 ms"


def _recipe_rows(bad=False):
    rows, n = [], 0
    for r in range(100):
        for line in range(5):
            n += 1
            rows.append({"row": n, "record": {"menu_item_id": f"mi_p{r}", "raw_material_id": f"rm_p{line + r % 95}",
                                              "qty": "0.5", "uom": f"u_p{line}"}})
    if bad:
        rows[250]["record"]["qty"] = "-1"
    return rows


@pytest.mark.perf
def test_nfr4_2_a_500_line_recipe_file_within_2_seconds():
    claims = _claims(REGIONAL)
    units, materials, items = _session(REGIONAL), _session(REGIONAL), _session(REGIONAL)
    for i in range(100):
        assert _add(claims, units, "uom", _uom(f"u_p{i}"))[0] == 201
        assert _add(claims, materials, "raw_material", {"raw_material_id": f"rm_p{i}", "name": "P",
                                                        "uom": f"u_p{i}"})[0] == 201
        assert _add(claims, items, "menu_item", {"menu_item_id": f"mi_p{i}", "name": "P", "gl_code": "GL-FOOD"})[0] == 201
    timings = {}
    for label, bad, expected in (("refused", True, 400), ("accepted", False, 201)):
        body = {"session_id": _session(REGIONAL), "request_id": str(uuid.uuid4()), "source": "csv",
                "file_name": "recipes.csv", "rows": _recipe_rows(bad)}
        start = time.perf_counter()
        status, payload = writes.bulk("recipe", claims, None, body)
        timings[label] = time.perf_counter() - start
        assert status == expected, payload.get("problems", payload)[:3]
    assert len([r for r in db.RECIPES if r.startswith("mi_p")]) == 100
    print(f"\n[perf] NFR4.2 500-line file: refused {timings['refused']:.3f} s, "
          f"accepted {timings['accepted']:.3f} s (target <= 2 s each)")
    for label, seconds in timings.items():
        assert seconds <= BULK_FILE_SECONDS, f"{label} file took {seconds:.3f} s > target 2 s"


def _read_samples(count):
    claims, samples = _claims(REGIONAL), []
    for _ in range(count):
        start = time.perf_counter()
        status, _ = inventory_raw_materials({}, claims, {}, {})
        samples.append(time.perf_counter() - start)
        assert status == 200
    return samples


@pytest.mark.perf
def test_nfr4_3_reads_slow_by_at_most_50_ms_under_single_writes():
    claims = _claims(REGIONAL)
    assert _add(claims, _session(REGIONAL), "uom", _uom("u_rw"))[0] == 201
    alone = _p95(_read_samples(200))
    stop, writer_errors, added = threading.Event(), [], [0]

    def writer():
        session, n = _session(REGIONAL), 0
        while not stop.is_set():
            if n and n % 100 == 0:
                session = _session(REGIONAL)
            status, _ = _add(claims, session, "raw_material", {"raw_material_id": f"rm_w{n}", "name": "W",
                                                               "uom": "u_rw"})
            if status != 201:
                writer_errors.append(status)
            n += 1
        added[0] = n

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        time.sleep(0.05)  # let the writer get going
        loaded = _p95(_read_samples(200))
    finally:
        stop.set()
        thread.join()
    slowdown = loaded - alone
    print(f"\n[perf] NFR4.3 read p95 alone {alone * 1000:.2f} ms, with writer {loaded * 1000:.2f} ms, "
          f"slowdown {slowdown * 1000:.2f} ms (target <= 50 ms; writer made {added[0]} adds)")
    assert writer_errors == [] and added[0] > 0
    assert slowdown <= READ_SLOWDOWN_P95_SECONDS, f"slowdown {slowdown * 1000:.2f} ms > target 50 ms"


@pytest.mark.perf
def test_nfr1_7_ten_threads_add_200_records_with_210_entries():
    claims = _claims(REGIONAL)
    assert _add(claims, _session(REGIONAL), "uom", _uom("u_c"))[0] == 201
    before, raw_before = len(_entries()), set(db.RAW_MATERIALS)
    errors, stop = [], threading.Event()

    def adder(t):
        session = _session(REGIONAL)
        for i in range(20):
            status, body = _add(claims, session, "raw_material", {"raw_material_id": f"rm_c{t}_{i}", "name": "C",
                                                                  "uom": "u_c"})
            if status != 201:
                errors.append(body)

    def reader():
        while not stop.is_set():
            try:
                inventory_raw_materials({}, claims, {"with": ["meta"]}, {})
            except Exception as e:  # noqa: BLE001 -- recorded and asserted on below
                errors.append(repr(e))

    reading = threading.Thread(target=reader)
    reading.start()
    threads = [threading.Thread(target=adder, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    reading.join()
    assert errors == []
    added = set(db.RAW_MATERIALS) - raw_before
    entries = _entries()[before:]
    assert len(added) == 200 and len(entries) == 210
    assert sorted(e["record_id"] for e in entries if e["action"] == "add") == sorted(added)
    assert len({e["entry_id"] for e in entries}) == 210


# ============================================ code-review fixes (iteration 1)

def test_a_401_is_not_stored_so_a_retry_after_relogin_works(base_url):
    # Review R-01: a 401 is never stored under its request id.
    client = Client(base_url, REGIONAL)
    request_id = str(uuid.uuid4())
    record = {"job_code": "jc_relogin", "title": "T"}
    assert client.call("POST", f"/sessions/{client.session}/logout")[0] == 200
    dead = {"session_id": client.session, "request_id": request_id, "record": record}
    assert client.call("POST", "/sales/job-codes", dead)[0] == 401
    fresh = Client(base_url, REGIONAL)
    live = {"session_id": fresh.session, "request_id": request_id, "record": record}
    assert fresh.call("POST", "/sales/job-codes", live)[0] == 201


def test_a_typed_id_cannot_forge_an_audit_log_line(regional, monkeypatch, capsys):
    # Review R-02: U2's own ERROR line strips control characters from the id.
    monkeypatch.setattr(audit, "_write_all", lambda fd, data: (_ for _ in ()).throw(OSError("ro")))
    forged = "jc\n[mock-hsm] ERROR audit: FORGED"
    regional.send("POST", "/sales/job-codes", record={"job_code": forged, "title": "T"})
    err = capsys.readouterr().err
    assert "\n[mock-hsm] ERROR audit: FORGED" not in err
    assert all(line.startswith("[mock-hsm] ") for line in err.splitlines() if line)


@pytest.mark.parametrize("text, expected", [("10", 10), ("12.5", 12.5), (".5", 0.5),
                                            ("1000000000", 1000000000)])
def test_cell_numbers_accept_plain_ascii_decimals_exactly(text, expected):
    # Review R-03: whole numbers are read exactly, decimals as plain ASCII.
    # Values above writes.MAX_NUMBER are refused (see test_writes_core).
    assert writes._number(text, cell=True, integer=isinstance(expected, int)) == (expected, None)


@pytest.mark.parametrize("text", ["1_0", "١٢", "-0", "1e3", "0x10", "1,000", "inf", "nan", ""])
def test_cell_numbers_refuse_other_forms(text):
    assert writes._number(text, cell=True, integer=False)[1] is not None


def test_a_zero_padded_content_length_is_read_as_its_value(base_url):
    # Review R-05: leading zeros don't make a small body "too large".
    body = b'{"x": 1}'
    status, _ = _raw(base_url, "POST", "/labor/rules/validate",
                     {"Content-Length": "0" * 12 + str(len(body))}, body)
    assert status == 404  # parsed and routed: no jurisdiction given, not "request too large"


def test_seeded_payloads_are_pinned_and_validate_returns_a_copy(regional):
    # Review R-06: literal seeded values, independent of the live db objects.
    status, menu = regional.call("GET", "/catalog/menu-items")
    assert status == 200
    assert {"menu_item_id": "mi_burger", "name": "Classic Burger", "gl_code": "GL-FOOD"} in menu["menu_items"]
    assert regional.call("GET", "/inventory/recipes/mi_soda") == (
        200, {"menu_item_id": "mi_soda", "lines": [{"raw_material_id": "rm_soda_syrup", "qty": 4, "uom": "oz"}]})
    assert regional.call("GET", "/sales/gl-codes") == (200, {"gl_codes": ["GL-BEV", "GL-FOOD"]})
    status, result = regional.call("POST", "/labor/rules/validate", {"jurisdiction": "GA", "shifts": []})
    assert status == 200 and result["violations"] == []
    assert result["rules"]["max_shift_length_hours"] == 10 and result["rules"]["jurisdiction"] == "GA"
    result["rules"]["max_shift_length_hours"] = 99  # the response is a copy, never the live rules
    assert db.LABOR_RULES_BY_JURISDICTION["GA"]["max_shift_length_hours"] == 10
