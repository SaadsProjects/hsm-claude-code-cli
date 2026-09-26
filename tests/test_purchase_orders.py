"""
Scope tests for the mock purchase-order route (mock_hsm/server.py's
/inventory/purchase-orders handler), called directly -- no HTTP server needed.
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hsm_client import HsmApiError, HsmClient
from mock_hsm import db
from mock_hsm.auth import mint_token, verify_token
from mock_hsm.server import ApiError, Handler, ThreadingHTTPServer, inventory_create_po

LINES = [{"raw_material_id": "rm_ground_beef", "qty": 10}]


@pytest.fixture(autouse=True)
def _empty_po_store(monkeypatch):
    # Successful submits append to the shared in-memory store; keep them out
    # of other tests (and of PO ids, which count the store).
    monkeypatch.setattr(db, "PURCHASE_ORDERS", [])


def _submit(user, **body):
    claims = verify_token(mint_token(user))
    return inventory_create_po({}, claims, {}, {"vendor_id": "vendor_protein_co", "line_items": LINES, **body})


def _admin_claims():
    # No admin user is seeded, so derive admin claims from a real token.
    return {**verify_token(mint_token("user_regional_atl")), "persona": "SYSTEM_ADMIN"}


def _status(user, **body):
    with pytest.raises(ApiError) as exc:
        _submit(user, **body)
    return exc.value.status


def test_regional_manager_can_order_for_own_region():
    status, po = _submit("user_regional_atl", region_id="region_atl")
    assert status == 201 and po["region_id"] == "region_atl"


def test_regional_manager_cannot_order_for_another_region(monkeypatch):
    monkeypatch.setitem(db.REGIONS, "region_chi", {"region_id": "region_chi", "name": "Chicago",
                                                   "org_id": "org_001"})
    assert _status("user_regional_atl", region_id="region_chi") == 403


def test_regional_manager_cannot_order_for_unknown_region():
    assert _status("user_regional_atl", region_id="region_xyz") == 404


def test_region_po_requires_regional_persona():
    assert _status("user_rm_midtown", region_id="region_atl") == 403


def test_site_po_cannot_claim_a_region_outside_scope():
    assert _status("user_rm_midtown", site_id="site_001", region_id="region_atl") == 403


def test_site_po_outside_scope_denied():
    assert _status("user_rm_midtown", site_id="site_002") == 403


def test_site_po_in_scope_allowed():
    status, po = _submit("user_rm_midtown", site_id="site_001")
    assert status == 201 and po["site_id"] == "site_001"


def test_po_needs_site_or_region():
    assert _status("user_regional_atl") == 400


def test_regional_manager_site_po_with_own_region_allowed():
    status, po = _submit("user_regional_atl", site_id="site_002", region_id="region_atl")
    assert status == 201 and (po["site_id"], po["region_id"]) == ("site_002", "region_atl")


def test_site_po_region_must_contain_the_site(monkeypatch):
    # An admin can reach any site and region, so only the containment check stops this.
    monkeypatch.setitem(db.REGIONS, "region_chi", {"region_id": "region_chi", "name": "Chicago",
                                                   "org_id": "org_001"})
    claims = _admin_claims()
    with pytest.raises(ApiError) as exc:
        inventory_create_po({}, claims, {}, {"vendor_id": "vendor_protein_co", "line_items": LINES,
                                             "site_id": "site_001", "region_id": "region_chi"})
    assert exc.value.status == 400


def test_site_po_with_unknown_region_not_found():
    assert _status("user_regional_atl", site_id="site_001", region_id="region_xyz") == 404


def test_admin_can_place_region_po():
    status, po = inventory_create_po({}, _admin_claims(), {}, {"vendor_id": "vendor_protein_co",
                                                               "line_items": LINES, "region_id": "region_atl"})
    assert status == 201 and po["region_id"] == "region_atl"


@pytest.mark.parametrize("body", [{"region_id": ["region_atl"]}, {"site_id": 1}])
def test_non_string_ids_rejected(body):
    assert _status("user_regional_atl", **body) == 400


@pytest.fixture
def http_client():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # ephemeral port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield lambda user: HsmClient(mint_token(user), base_url=base_url)
    server.shutdown()
    server.server_close()


def test_scope_enforced_over_http(http_client, monkeypatch):
    monkeypatch.setitem(db.REGIONS, "region_chi", {"region_id": "region_chi", "name": "Chicago",
                                                   "org_id": "org_001"})
    client = http_client("user_regional_atl")
    assert client.submit_purchase_order("vendor_protein_co", LINES, region_id="region_atl")["status"] == "SUBMITTED"
    for kwargs, status in [({"region_id": "region_chi"}, 403), ({"region_id": "region_xyz"}, 404), ({}, 400)]:
        with pytest.raises(HsmApiError) as exc:
            client.submit_purchase_order("vendor_protein_co", LINES, **kwargs)
        assert exc.value.status == status
