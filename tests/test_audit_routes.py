"""
Endpoint and integration tests for the audit trail: auditing inside the gated
publish and PO routes (called directly and over HTTP), and the read-only
GET /audit view over HTTP.
"""
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mock_hsm import audit, db
from mock_hsm.auth import mint_token, verify_token
from mock_hsm.server import ApiError, Handler, ThreadingHTTPServer, inventory_create_po, labor_publish_schedule

LINES = [{"raw_material_id": "rm_ground_beef", "qty": 10}]
SHIFTS = [{"employee_id": "emp_site_001_01", "date": "2026-10-05", "role": "JC-COOK",
           "start_time": "09:00", "end_time": "17:00"}]
ALL_SEEING = {"user_id": "test-auditor", "persona": "SYSTEM_ADMIN", "site_ids": [], "region_id": None}


@pytest.fixture(autouse=True)
def _empty_write_stores(monkeypatch):
    monkeypatch.setattr(db, "PURCHASE_ORDERS", [])
    monkeypatch.setattr(db, "SCHEDULES", {})


def _claims(user):
    return verify_token(mint_token(user))


def _admin_claims():
    return {**_claims("user_regional_atl"), "persona": "SYSTEM_ADMIN"}


def _entries():
    """Every stored entry, oldest first."""
    entries, before = [], None
    while True:
        page = audit.page(ALL_SEEING, before)
        entries += page["entries"]
        before = page["next_before"]
        if before is None:
            return entries[::-1]


def _publish(claims, site_id="site_001", body=None):
    return labor_publish_schedule({"site_id": site_id}, claims, {}, {"shifts": SHIFTS} if body is None else body)


def _po(claims, **body):
    return inventory_create_po({}, claims, {}, {"vendor_id": "vendor_protein_co", "line_items": LINES, **body})


def _break_appends(monkeypatch):
    def broken_write(fd, data):
        raise OSError("read-only file system")

    monkeypatch.setattr(audit, "_write_all", broken_write)


# ------------------------------------------------- gated routes, direct calls

def test_allowed_publish_is_audited_once():
    status, body = _publish(_claims("user_rm_midtown"))
    assert (status, body) == (200, {"site_id": "site_001", "status": "PUBLISHED", "shift_count": 1,
                                    "published_by": "user_rm_midtown"})
    [entry] = _entries()
    assert {k: entry[k] for k in ("user_id", "persona", "session_id", "source", "action", "outcome", "kind",
                                  "record_id", "site_id", "reason")} == {
        "user_id": "user_rm_midtown", "persona": "RESTAURANT_MANAGER", "session_id": None,
        "source": "claude_code_workflow", "action": "publish_schedule", "outcome": "allowed",
        "kind": "schedule", "record_id": "site_001", "site_id": "site_001", "reason": None}
    assert entry["changes"] == {"shift_count": 1, "shifts": SHIFTS}


@pytest.mark.parametrize("user, site_id, body, status, message, site_field", [
    ("user_rm_midtown", "site_404", None, 404, "unknown site site_404", None),
    ("user_rm_midtown", "site_002", None, 403, "persona RESTAURANT_MANAGER not scoped to site site_002", "site_002"),
    ("admin", "site_001", None, 403, "persona cannot publish schedules", "site_001"),
    ("user_rm_midtown", "site_001", {"shifts": "all of them"}, 400, "shifts must be a list", "site_001"),
])
def test_refused_publish_is_audited_as_violation(user, site_id, body, status, message, site_field):
    claims = _admin_claims() if user == "admin" else _claims(user)
    with pytest.raises(ApiError) as exc:
        _publish(claims, site_id, body)
    assert (exc.value.status, exc.value.message) == (status, message)  # response unchanged
    [entry] = _entries()
    assert (entry["outcome"], entry["reason"], entry["record_id"], entry["site_id"]) == (
        "violation", message, site_id, site_field)
    assert db.SCHEDULES == {}


@pytest.mark.parametrize("user, body, status, site_field", [
    ("user_regional_atl", {"site_id": 1}, 400, None),
    ("user_regional_atl", {}, 400, None),
    ("user_regional_atl", {"region_id": "region_xyz"}, 404, None),
    ("user_rm_midtown", {"site_id": "site_002"}, 403, "site_002"),
    ("user_rm_midtown", {"region_id": "region_atl"}, 403, None),
    ("user_regional_atl", {"site_id": "site_001", "vendor_id": "vendor_nope"}, 400, "site_001"),
])
def test_refused_po_is_audited_as_violation(user, body, status, site_field):
    with pytest.raises(ApiError) as exc:
        _po(_claims(user), **body)
    assert exc.value.status == status
    [entry] = _entries()
    assert (entry["action"], entry["outcome"], entry["reason"]) == (
        "submit_purchase_order", "violation", exc.value.message)
    assert (entry["kind"], entry["record_id"], entry["site_id"]) == ("purchase_order", None, site_field)
    assert entry["changes"]["vendor_id"] == body.get("vendor_id", "vendor_protein_co")
    assert db.PURCHASE_ORDERS == []


def test_site_not_in_region_po_is_audited(monkeypatch):
    # Review R-11: the containment 400 is audited like every other refusal.
    monkeypatch.setitem(db.REGIONS, "region_chi", {"region_id": "region_chi", "name": "Chicago", "org_id": "org_001"})
    with pytest.raises(ApiError) as exc:
        _po(_admin_claims(), site_id="site_001", region_id="region_chi")
    assert exc.value.status == 400
    [entry] = _entries()
    assert (entry["action"], entry["outcome"]) == ("submit_purchase_order", "violation")  # BR3.1
    assert entry["reason"] == "site site_001 is not in region region_chi"
    assert entry["changes"]["region_id"] == "region_chi"
    assert db.PURCHASE_ORDERS == []


def test_direct_po_call_is_audited_with_its_po_id():
    status, po = _po(_claims("user_regional_atl"), region_id="region_atl")
    assert status == 201
    [entry] = _entries()
    assert (entry["action"], entry["outcome"], entry["record_id"], entry["site_id"]) == (
        "submit_purchase_order", "allowed", po["po_id"], None)  # region-level PO: no site
    assert entry["changes"] == {"vendor_id": "vendor_protein_co", "site_id": None, "region_id": "region_atl",
                                "line_items": LINES}

    _, site_po = _po(_claims("user_rm_midtown"), site_id="site_001")
    assert (_entries()[-1]["record_id"], _entries()[-1]["site_id"]) == (site_po["po_id"], "site_001")
    assert site_po["po_id"] != po["po_id"]


def test_oversized_refusal_is_still_audited_with_its_usual_response():
    with pytest.raises(ApiError) as exc:
        _po(_claims("user_regional_atl"), site_id="site_001", vendor_id="v" * 40_000)
    assert exc.value.status == 400 and exc.value.message == f"unknown vendor {'v' * 40_000}"
    [entry] = _entries()
    assert entry["reason"].endswith("...(truncated)") and len(entry["reason"]) < 1100
    assert entry["changes"]["truncated"] is True


def test_unwritable_audit_store_refuses_and_applies_nothing(monkeypatch):
    _break_appends(monkeypatch)
    for call in (lambda: _publish(_claims("user_rm_midtown")),
                 lambda: _po(_claims("user_rm_midtown"), site_id="site_001"),
                 lambda: _publish(_claims("user_rm_midtown"), "site_002")):  # a refusal becomes 503 too
        with pytest.raises(ApiError) as exc:
            call()
        assert (exc.value.status, exc.value.message) == (503, "audit unavailable")
    assert db.SCHEDULES == {} and db.PURCHASE_ORDERS == []


class _BrokenSchedules(dict):
    def setdefault(self, *args):
        raise RuntimeError("schedule store offline")


class _BrokenOrders(list):
    def append(self, item):
        raise RuntimeError("PO store offline")


def test_failure_after_audit_adds_a_compensating_entry(monkeypatch):
    monkeypatch.setattr(db, "SCHEDULES", _BrokenSchedules())
    monkeypatch.setattr(db, "PURCHASE_ORDERS", _BrokenOrders())
    with pytest.raises(RuntimeError, match="schedule store offline"):
        _publish(_claims("user_rm_midtown"))
    with pytest.raises(RuntimeError, match="PO store offline"):
        _po(_claims("user_rm_midtown"), site_id="site_001")
    assert [(e["action"], e["outcome"], e["reason"]) for e in _entries()] == [
        ("publish_schedule", "allowed", None),
        ("publish_schedule", "violation", "failed after audit: schedule store offline"),
        ("submit_purchase_order", "allowed", None),
        ("submit_purchase_order", "violation", "failed after audit: PO store offline"),
    ]
    assert _entries()[2]["record_id"] == _entries()[3]["record_id"] == "po_0001"


def test_failed_compensating_entry_is_logged(monkeypatch, capsys):
    monkeypatch.setattr(db, "SCHEDULES", _BrokenSchedules())
    real_append = audit.append

    def append_then_break(entry):
        entry_id = real_append(entry)
        _break_appends(monkeypatch)  # the allowed entry lands; the compensating one cannot
        return entry_id

    monkeypatch.setattr(audit, "append", append_then_break)
    with pytest.raises(RuntimeError):
        _publish(_claims("user_rm_midtown"))
    err = capsys.readouterr().err
    assert "[mock-hsm] ERROR audit: compensating entry failed for publish_schedule site_001" in err


# --------------------------------------------------------------- over HTTP

@pytest.fixture
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # ephemeral port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _http(base_url, method, path, user=None, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base_url + path, data=data, method=method)
    if user:
        req.add_header("Authorization", f"Bearer {mint_token(user)}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, None


def test_entry_count_matches_attempt_count_over_http(base_url):
    attempts = [
        ("POST", "/labor/sites/site_001/schedules/publish", "user_rm_midtown", {"shifts": SHIFTS}, 200),
        ("POST", "/labor/sites/site_002/schedules/publish", "user_rm_midtown", {"shifts": SHIFTS}, 403),
        ("POST", "/labor/sites/site_nope/schedules/publish", "user_regional_atl", {"shifts": SHIFTS}, 404),
        ("POST", "/labor/sites/site_002/schedules/publish", "user_regional_atl", {"shifts": {}}, 400),
        ("POST", "/inventory/purchase-orders", "user_regional_atl",
         {"vendor_id": "vendor_protein_co", "line_items": LINES, "region_id": "region_atl"}, 201),
        ("POST", "/inventory/purchase-orders", "user_rm_midtown",
         {"vendor_id": "vendor_protein_co", "line_items": LINES, "region_id": "region_atl"}, 403),
        ("POST", "/inventory/purchase-orders", "user_rm_midtown", {"vendor_id": "x", "site_id": "site_001"}, 400),
    ]
    for method, path, user, body, status in attempts:
        assert _http(base_url, method, path, user, body)[0] == status

    # Rejected by the dispatcher before any route runs: never audited (BR3.1).
    assert _http(base_url, "POST", "/inventory/purchase-orders", None, {"vendor_id": "x"})[0] == 401
    assert _http(base_url, "POST", "/labor/sites/site_001/schedules/publish", "user_rm_midtown",
                 raw=b"{not json")[0] == 400

    entries = _entries()
    assert len(entries) == len(attempts)
    assert [e["outcome"] for e in entries] == ["allowed" if s < 300 else "violation" for *_, s in attempts]


def test_unwritable_audit_store_gives_503_over_http(base_url, monkeypatch):
    _break_appends(monkeypatch)
    status, body = _http(base_url, "POST", "/labor/sites/site_001/schedules/publish", "user_rm_midtown",
                         {"shifts": SHIFTS})
    assert (status, body) == (503, {"error": "audit unavailable"})
    assert _http(base_url, "GET", "/labor/sites/site_001/schedules", "user_rm_midtown") == (
        200, {"site_id": "site_001", "published": []})
    assert _http(base_url, "GET", "/audit", "user_regional_atl") == (503, {"error": "audit unavailable"})


def test_unreadable_trail_refuses_audited_operations_but_not_reads(base_url, audit_path):
    audit.append({"user_id": "u", "source": "dashboard", "action": "add", "outcome": "allowed"})
    with open(audit_path, "ab") as f:
        f.write(b"{corrupt\n")
    audit.append({"user_id": "u", "source": "dashboard", "action": "add", "outcome": "allowed"})
    audit.configure()  # restart finds the corrupt middle line

    assert _http(base_url, "POST", "/inventory/purchase-orders", "user_regional_atl",
                 {"vendor_id": "vendor_protein_co", "line_items": LINES, "region_id": "region_atl"})[0] == 503
    assert _http(base_url, "GET", "/audit", "user_regional_atl")[0] == 503
    assert _http(base_url, "GET", "/admin/sites", "user_regional_atl")[0] == 200
    assert db.PURCHASE_ORDERS == []


def _plant_view_entries():
    for site, user in [("site_001", "user_rm_midtown"), ("site_002", "user_regional_atl"),
                       ("site_003", "user_regional_atl"), (None, "user_regional_atl")]:
        audit.append({"user_id": user, "source": "dashboard", "action": "update", "outcome": "allowed",
                      "kind": "on_hand", "record_id": "rm_bun", "site_id": site})
    # "unknown" entries (no session): one about site_001 data, one about shared
    # data (no site), one about another site's data.
    for kind, site in [("on_hand", "site_001"), ("uom", None), ("on_hand", "site_002")]:
        audit.append({"user_id": "unknown", "source": "dashboard", "action": "update", "outcome": "violation",
                      "reason": "no session", "kind": kind, "record_id": "rm_bun", "site_id": site})


@pytest.mark.parametrize("query", ["", "?site_id=site_002", "?region_id=region_atl", "?persona=SYSTEM_ADMIN",
                                   "?user_id=unknown&site_ids=site_002", "?limit=500"])
def test_restaurant_manager_view_cannot_be_widened(base_url, query):
    _plant_view_entries()
    status, page = _http(base_url, "GET", f"/audit{query}", "user_rm_midtown")
    assert status == 200
    # BR4.2 / NFR4.3: its own site's entries, including the "unknown" one about
    # site_001 data; never shared data or another site, whatever the query.
    assert [(e["site_id"], e["user_id"]) for e in page["entries"]] == [
        ("site_001", "unknown"), ("site_001", "user_rm_midtown")]
    assert (page["total"], page["limit"], page["next_before"]) == (2, 50, None)


def test_regional_view_sees_everything_and_pages_over_http(base_url):
    _plant_view_entries()
    for _ in range(55):
        _publish(_claims("user_regional_atl"), "site_002")
    status, first = _http(base_url, "GET", "/audit", "user_regional_atl")
    assert status == 200 and first["total"] == 62 and len(first["entries"]) == 50
    assert {e["user_id"] for e in _entries()} == {"user_rm_midtown", "user_regional_atl", "unknown"}
    status, second = _http(base_url, "GET", f"/audit?before={first['next_before']}", "user_regional_atl")
    assert status == 200 and len(second["entries"]) == 12 and second["next_before"] is None
    assert second["entries"][-1]["entry_id"] == "000000000001"

    for before in ("nope", second["entries"][0]["entry_id"][:-1], "00000000001x"):
        assert _http(base_url, "GET", f"/audit?before={before}", "user_regional_atl")[0] == 400
    assert _http(base_url, "GET", "/audit", None)[0] == 401


def test_any_well_formed_before_is_accepted_over_http(base_url):
    # BR4.3: a cursor is only a position. An id never assigned (or purged) is
    # accepted; it can't reveal whether a hidden or purged entry exists.
    _plant_view_entries()
    status, page = _http(base_url, "GET", "/audit?before=000000000999", "user_regional_atl")
    assert status == 200 and len(page["entries"]) == page["total"] == 7
    status, page = _http(base_url, "GET", "/audit?before=000000000004", "user_regional_atl")
    assert status == 200 and [e["entry_id"] for e in page["entries"]] == [
        "000000000003", "000000000002", "000000000001"]
    status, page = _http(base_url, "GET", "/audit?before=000000000002", "user_rm_midtown")  # a hidden id
    assert (status, [e["entry_id"] for e in page["entries"]], page["total"]) == (200, ["000000000001"], 2)


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_audit_view_accepts_no_other_method(base_url, audit_path, method):
    audit.append({"user_id": "u", "source": "dashboard", "action": "add", "outcome": "allowed"})
    before = audit_path.read_bytes()
    status, _ = _http(base_url, method, "/audit", "user_regional_atl", {"entry_id": "000000000001"})
    assert status in (404, 501)  # no route (POST) or no handler for the method at all
    assert audit_path.read_bytes() == before


# Review R-01: json.loads accepts NaN/Infinity; the audit trail must still record
# the attempt and the route must keep its usual response.
def test_non_finite_numbers_in_an_accepted_publish_are_audited():
    body = {"shifts": [{**SHIFTS[0], "x": float("nan")}]}
    status, _ = _publish(_claims("user_rm_midtown"), body=body)
    assert status == 200
    [entry] = _entries()
    assert entry["outcome"] == "allowed" and entry["changes"]["shifts"][0]["x"] == "nan"


def test_non_finite_numbers_in_a_refused_attempt_keep_their_status():
    with pytest.raises(ApiError) as exc:
        _publish(_claims("user_rm_midtown"), site_id="site_002", body={"shifts": float("inf")})
    assert exc.value.status == 403
    with pytest.raises(ApiError) as exc:
        _po(_claims("user_rm_midtown"), site_id="site_002", line_items=[{"qty": float("-inf")}])
    assert exc.value.status == 403
    assert [e["outcome"] for e in _entries()] == ["violation", "violation"]


def _deeply_nested(depth):
    value = []
    for _ in range(depth):
        value = [value]
    return value


# Review R-04: a body nested past the recursion limit is still audited, with a
# marker in place of the values, and keeps its usual response.
def test_deeply_nested_body_is_audited_with_a_marker():
    status, _ = _publish(_claims("user_rm_midtown"), body={"shifts": [_deeply_nested(1500)]})
    assert status == 200
    with pytest.raises(ApiError) as exc:
        _publish(_claims("user_rm_midtown"), site_id="site_002", body={"shifts": _deeply_nested(1500)})
    assert exc.value.status == 403
    entries = _entries()
    assert [e["outcome"] for e in entries] == ["allowed", "violation"]
    assert all(e["changes"] == {"truncated": True, "unserializable": True} for e in entries)


# Review R-05: any failure of the compensating append is logged, and the
# original apply error still propagates.
def test_unexpected_compensating_failure_keeps_the_original_error(monkeypatch, capsys):
    monkeypatch.setattr(db, "SCHEDULES", _BrokenSchedules())
    real_append = audit.append
    calls = []

    def append_then_raise(entry):
        calls.append(entry)
        if len(calls) == 1:
            return real_append(entry)
        raise RecursionError("too deep")

    monkeypatch.setattr(audit, "append", append_then_raise)
    with pytest.raises(RuntimeError, match="schedule store offline"):
        _publish(_claims("user_rm_midtown"))
    assert "compensating entry failed for publish_schedule" in capsys.readouterr().err
