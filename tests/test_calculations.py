"""
Unit tests for the deterministic calculations behind the MCP tools
(agents/inventory_agent.py, agents/labor_scheduling_agent.py) and the mock
forecast they consume.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.inventory_agent import compute_reorder_needs, compute_usage_anomalies
from agents.labor_scheduling_agent import compute_demand
from mock_hsm import db

VENDORS = [{"vendor_id": "v1", "price_list": {"rm_a": 2.0, "rm_b": 1.0}, "lead_time_days": 1,
            "min_order_value": 0}]


def test_usage_with_nothing_expected_is_flagged():
    usage = {"expected_usage": {"rm_a": 10.0}, "actual_usage": {"rm_a": 10.0, "rm_b": 4.0}}
    anomalies = compute_usage_anomalies("site_x", usage, VENDORS)
    assert [(a["raw_material_id"], a["variance_pct"]) for a in anomalies] == [("rm_b", None)]
    assert anomalies[0]["cost_impact"] == 4.0


def test_usage_within_threshold_not_flagged():
    usage = {"expected_usage": {"rm_a": 10.0}, "actual_usage": {"rm_a": 11.0}}
    assert compute_usage_anomalies("site_x", usage, VENDORS) == []


def test_material_below_reorder_point_with_no_forecast_use_is_reordered():
    forecast = [{"items": {"mi_x": 1}}]
    recipes = {"mi_x": [{"raw_material_id": "rm_a", "qty": 1}]}
    on_hand = {"on_hand": {"rm_a": 100, "rm_b": 2},
               "par_levels": {"rm_a": 100, "rm_b": 20},
               "reorder_points": {"rm_a": 10, "rm_b": 5}}
    needs = compute_reorder_needs("site_x", forecast, on_hand, recipes, VENDORS)
    assert [(n["raw_material_id"], n["suggested_order_qty"]) for n in needs] == [("rm_b", 18)]


def test_forecast_dates_are_site_local_and_weekend_is_real_fri_sat():
    forecast = db.get_forecast("site_001", 0, 14)
    today = db.site_today("site_001")
    assert [row["date"] for row in forecast] == [(today + timedelta(days=i)).isoformat() for i in range(14)]

    demand = compute_demand(forecast)
    for row in demand:
        assert row["weekday"] == date.fromisoformat(row["date"]).strftime("%a")
    # The 25% Fri/Sat bump outweighs the +/-7.5% noise, so every Fri/Sat
    # must be busier than every other day.
    weekend = [row["covers"] for row in demand if row["weekday"] in ("Fri", "Sat")]
    weekdays = [row["covers"] for row in demand if row["weekday"] not in ("Fri", "Sat")]
    assert min(weekend) > max(weekdays)
