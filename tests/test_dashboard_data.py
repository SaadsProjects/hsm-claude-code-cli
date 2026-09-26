"""
Tests for the read-only dashboard: the schedule GET route, the Streamlit-free
loaders in dashboard/data.py, and a smoke render of dashboard/app.py via
Streamlit's AppTest -- all against a mock server on an ephemeral port.
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hsm_client import HsmApiError, HsmClient
from dashboard import data
from mock_hsm import db
from mock_hsm.auth import mint_token
from mock_hsm.server import Handler, ThreadingHTTPServer

APP_PATH = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
SHIFTS = [
    {"employee_id": "emp_site_001_02", "date": "2026-01-05", "role": "JC-COOK", "start_time": "09:00",
     "end_time": "17:00"},
    {"employee_id": "emp_site_001_01", "date": "2026-01-05", "role": "JC-LEAD", "start_time": "22:00",
     "end_time": "06:00"},
]


@pytest.fixture(autouse=True)
def _empty_write_stores(monkeypatch):
    monkeypatch.setattr(db, "SCHEDULES", {})
    monkeypatch.setattr(db, "PURCHASE_ORDERS", [])


@pytest.fixture
def fresh_app_cache():
    # st.cache_data is process-wide and AppTest doesn't reset it: without this, a test
    # reusing a persona would be served an earlier test's data (from another server).
    import streamlit as st

    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # ephemeral port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _client(user, base_url):
    return HsmClient(mint_token(user), base_url=base_url)


def test_published_schedule_round_trip_and_scope(base_url):
    rm = _client("user_rm_midtown", base_url)
    assert rm.get_published_schedule("site_001") == []
    rm.publish_schedule("site_001", SHIFTS)
    assert rm.get_published_schedule("site_001") == SHIFTS
    with pytest.raises(HsmApiError) as exc:
        rm.get_published_schedule("site_002")
    assert exc.value.status == 403


def test_shift_hours_handles_overnight():
    assert data.shift_hours("09:00", "17:00") == 8
    assert data.shift_hours("22:00", "06:00") == 8
    assert data.shift_hours("08:00", "08:00") == 24


def test_schedule_frame_joins_roster_and_costs():
    employees = [e for e in db.EMPLOYEES.values() if e["site_id"] == "site_001"]
    frame = data.schedule_frame(SHIFTS, employees)
    assert list(frame["hours"]) == [8, 8]
    cook = frame[frame["employee_id"] == "emp_site_001_02"].iloc[0]
    assert cook["est_cost"] == 8 * 16.0


def test_schedule_frame_tolerates_unparseable_times():
    frame = data.schedule_frame([{**SHIFTS[0], "start_time": "9am"}], [])
    assert frame["hours"].isna().all() and frame["est_cost"].isna().all()


def test_schedule_frame_tolerates_missing_fields():
    frame = data.schedule_frame([{}, {"employee_id": "emp_unknown"}, SHIFTS[0]], [])
    assert len(frame) == 3
    # The complete shift sorts first; the incomplete ones keep what they have, with blank hours.
    assert frame.loc[0, "employee_id"] == SHIFTS[0]["employee_id"] and frame.loc[0, "hours"] == 8
    assert frame.loc[1, "employee_id"] == "emp_unknown" and frame.loc[1, "name"] == "?"
    assert frame.loc[1:, "hours"].isna().all() and frame.loc[1:, "date"].isna().all()


def test_loaders_surface_planted_anomaly(base_url):
    client = _client("user_regional_atl", base_url)
    anomalies = data.usage_anomalies(client, "site_001")
    assert "rm_ground_beef" in {a["raw_material_id"] for a in anomalies}
    assert len(data.labor_demand(client, "site_001")) == 7
    rollup = data.region_rollup(client, client.get_sites(region_id="region_atl"))
    assert list(rollup["site_id"]) == ["site_001", "site_002", "site_003"]
    assert (rollup["usage_anomalies"] >= 1).all()
    on_hand = data.on_hand_frame(client.get_on_hand("site_001"), client.get_raw_materials())
    assert len(on_hand) == len(db.RAW_MATERIALS)


def _run_app(base_url, monkeypatch, user):
    from streamlit.testing.v1 import AppTest

    # HsmClient binds its default base URL at import time; point it at this test's server.
    monkeypatch.setattr(HsmClient.__init__, "__defaults__", (base_url, 15))
    monkeypatch.setenv("HSM_ACTIVE_USER", user)
    app = AppTest.from_file(str(APP_PATH), default_timeout=30)
    app.run()
    return app


@pytest.mark.parametrize("user", ["user_regional_atl", "user_rm_midtown"])
def test_app_renders(base_url, monkeypatch, fresh_app_cache, user):
    _client(user, base_url).publish_schedule("site_001", SHIFTS)
    app = _run_app(base_url, monkeypatch, user)
    assert not app.exception, app.exception
    assert not app.error and not app.warning, (app.error, app.warning)
    expected_sites = ["site_001", "site_002", "site_003"] if user == "user_regional_atl" else ["site_001"]
    assert [label.split("(")[-1].rstrip(")") for label in app.sidebar.selectbox[1].options] == expected_sites
    assert any("Region roll-up" in h.value for h in app.subheader) == (user == "user_regional_atl")
    assert any("no violations" in s.value for s in app.success)


def test_app_survives_unvalidatable_schedule(base_url, monkeypatch, fresh_app_cache):
    # Published straight through the API (bypassing the publish hook) with a non-HH:MM time.
    _client("user_rm_midtown", base_url).publish_schedule("site_001", [{**SHIFTS[0], "start_time": "9am"}])
    app = _run_app(base_url, monkeypatch, "user_rm_midtown")
    assert not app.exception, app.exception
    assert not app.warning, app.warning
    assert any("could not validate" in e.value for e in app.error)
    assert any("On hand vs par" in h.value for h in app.subheader)  # the rest of the page still renders


def test_app_keeps_incomplete_shifts_in_per_employee_table(base_url, monkeypatch, fresh_app_cache):
    # No role and no times: the shift must still be counted, with hours and cost left blank.
    _client("user_rm_midtown", base_url).publish_schedule("site_001", [SHIFTS[0], {"employee_id": "emp_x"}])
    app = _run_app(base_url, monkeypatch, "user_rm_midtown")
    assert not app.exception, app.exception
    per_emp = next(df.value for df in app.dataframe if "shifts" in df.value.columns)
    assert set(per_emp["employee_id"]) == {SHIFTS[0]["employee_id"], "emp_x"}
    unknown = per_emp[per_emp["employee_id"] == "emp_x"].iloc[0]
    assert unknown["shifts"] == 1 and unknown[["hours", "est_cost"]].isna().all()


def test_app_cache_does_not_leak_between_tests(base_url, monkeypatch, fresh_app_cache):
    # Same persona as test_app_renders, but nothing published on this test's server.
    app = _run_app(base_url, monkeypatch, "user_rm_midtown")
    assert any("No schedule has been published" in i.value for i in app.info)
