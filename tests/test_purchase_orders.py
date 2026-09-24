"""
Scope tests for the mock purchase-order route (mock_hsm/server.py's
/inventory/purchase-orders handler), called directly -- no HTTP server needed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mock_hsm import db
from mock_hsm.auth import mint_token, verify_token
from mock_hsm.server import ApiError, inventory_create_po

LINES = [{"raw_material_id": "rm_ground_beef", "qty": 10}]


@pytest.fixture(autouse=True)
def _empty_po_store(monkeypatch):
    # Successful submits append to the shared in-memory store; keep them out
    # of other tests (and of PO ids, which count the store).
    monkeypatch.setattr(db, "PURCHASE_ORDERS", [])


def _submit(user, **body):
    claims = verify_token(mint_token(user))
    return inventory_create_po({}, claims, {}, {"vendor_id": "vendor_protein_co", "line_items": LINES, **body})


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
    claims = {**verify_token(mint_token("user_regional_atl")), "persona": "SYSTEM_ADMIN"}
    with pytest.raises(ApiError) as exc:
        inventory_create_po({}, claims, {}, {"vendor_id": "vendor_protein_co", "line_items": LINES,
                                             "site_id": "site_001", "region_id": "region_chi"})
    assert exc.value.status == 400
