"""
Read-only loaders behind the Streamlit dashboard (dashboard/app.py).

Everything goes through agents.hsm_client.HsmClient, so the persona token's
site/region scope is enforced by the backend exactly as it is for the MCP
tools. Derived numbers (demand, usage variance, reorder needs) come from the
same deterministic functions in agents/ that the MCP tools call -- nothing
here re-implements that math. No function in this module writes: the only
POST it makes is the side-effect-free /labor/rules/validate.

Kept free of Streamlit so it can be tested directly.
"""
from datetime import datetime, timedelta

import pandas as pd

from agents.hsm_client import HsmClient
from agents.inventory_agent import compute_reorder_needs, compute_usage_anomalies
from agents.labor_scheduling_agent import compute_demand


def labor_demand(client: HsmClient, site_id, start_offset=7, days=7):
    """Per-day covers and role-hours-needed (same as the compute_labor_demand tool)."""
    return compute_demand(client.get_forecast(site_id, start_offset, days))


def usage_anomalies(client: HsmClient, site_id):
    """Past-7-day usage variance (same inputs as the compute_usage_anomalies tool)."""
    usage = client.get_usage(site_id, start_offset_days=-7, days=7)
    return compute_usage_anomalies(site_id, usage, client.get_vendors())


def reorder_needs(client: HsmClient, site_id):
    """Next-7-day reorder needs (same fetch sequence as the compute_reorder_needs tool)."""
    forecast = client.get_forecast(site_id, start_offset_days=0, days=7)
    on_hand_data = client.get_on_hand(site_id)
    menu_item_ids = {item_id for day in forecast for item_id in day["items"]}
    recipes = {item_id: client.get_recipe(item_id) for item_id in menu_item_ids}
    return compute_reorder_needs(site_id, forecast, on_hand_data, recipes, client.get_vendors())


def on_hand_frame(on_hand_data, raw_materials):
    """One row per material: on hand, reorder point, par, and whether it's at/below the reorder point."""
    names = {rm["raw_material_id"]: rm for rm in raw_materials}
    on_hand, par, rop = on_hand_data["on_hand"], on_hand_data["par_levels"], on_hand_data["reorder_points"]
    rows = []
    for rm_id in sorted(set(on_hand) | set(par) | set(rop)):
        rm = names.get(rm_id, {})
        qty = on_hand.get(rm_id, 0.0)
        rows.append({
            "raw_material_id": rm_id, "name": rm.get("name", rm_id), "uom": rm.get("uom", ""),
            "on_hand": qty, "reorder_point": rop.get(rm_id, 0), "par": par.get(rm_id, 0),
            "below_reorder_point": qty <= rop.get(rm_id, 0),
        })
    return pd.DataFrame(rows)


def sales_vs_forecast(client: HsmClient, site_id, days=7):
    """Total units per day over the past `days`: actual POS sales vs what was forecast."""
    def totals(rows):
        return {row["date"]: round(sum(row["items"].values()), 1) for row in rows}

    actual = totals(client.get_actual_sales(site_id, start_offset_days=-days, days=days))
    forecast = totals(client.get_forecast(site_id, start_offset_days=-days, days=days))
    return pd.DataFrame([{"date": d, "actual": actual.get(d), "forecast": forecast.get(d)}
                         for d in sorted(set(actual) | set(forecast))])


def shift_hours(start_time, end_time):
    """Hours in an HH:MM shift. An end at or before the start runs past midnight,
    matching the Labor Rules Engine's convention."""
    start = datetime.strptime(start_time, "%H:%M")  # noqa: DTZ007 -- wall-clock times, no date/zone
    end = datetime.strptime(end_time, "%H:%M")  # noqa: DTZ007
    if end <= start:
        end += timedelta(days=1)
    return (end - start).total_seconds() / 3600


def schedule_frame(shifts, employees):
    """Published shifts joined to the roster, with hours and estimated straight-time cost per shift."""
    roster = {e["employee_id"]: e for e in employees}
    rows = []
    for s in shifts:
        emp = roster.get(s["employee_id"], {})
        try:
            hours = round(shift_hours(s["start_time"], s["end_time"]), 2)
        except (TypeError, ValueError):
            hours = None  # not HH:MM -- the validator reports it; show the shift without hours
        rate = emp.get("hourly_rate")
        rows.append({
            "date": s["date"], "employee_id": s["employee_id"], "name": emp.get("name", "?"),
            "role": s.get("role", emp.get("job_code")), "start_time": s["start_time"], "end_time": s["end_time"],
            "hours": hours, "est_cost": round(hours * rate, 2) if hours is not None and rate is not None else None,
        })
    columns = ["date", "employee_id", "name", "role", "start_time", "end_time", "hours", "est_cost"]
    return pd.DataFrame(rows, columns=columns).sort_values(["date", "start_time", "employee_id"], ignore_index=True)


def region_rollup(client: HsmClient, sites):
    """One row per site in scope: anomaly count, anomaly cost impact, and items needing reorder."""
    rows = []
    for site in sites:
        anomalies = usage_anomalies(client, site["site_id"])
        needs = reorder_needs(client, site["site_id"])
        rows.append({
            "site_id": site["site_id"], "site": site["name"],
            "usage_anomalies": len(anomalies),
            "anomaly_cost_impact": round(sum(a["cost_impact"] for a in anomalies), 2),
            "items_to_reorder": len(needs),
            "suggested_order_value": round(sum(n["suggested_order_qty"] * (n["unit_price"] or 0) for n in needs), 2),
        })
    return pd.DataFrame(rows)
