"""
Deterministic calculation for use case 2 (inventory/COGS + vendor ordering).

As with labor_scheduling_agent.py, only the pure calculation functions
survive here for the Claude Code CLI version -- wrapped by
mcp_server/hsm_tools.py as the `compute_usage_anomalies` and
`compute_reorder_needs` tools. The judgment steps (interpreting an
anomaly, drafting/consolidating purchase orders) are now the
inventory-analyst subagent's own reasoning (see
.claude/agents/inventory-analyst.md) -- there is deliberately no
LLM-calling code left in this file.
"""

VARIANCE_THRESHOLD = 0.15  # 15%, per demo scoping
FORECAST_WINDOW_DAYS = 7


def _vendor_for_material(vendors, rm_id):
    for v in vendors:
        if rm_id in v["price_list"]:
            return v["vendor_id"], v["price_list"][rm_id], v["lead_time_days"], v["min_order_value"]
    return None, None, None, None


def compute_usage_anomalies(site_id, usage, vendors):
    """[deterministic] variance% + threshold flagging."""
    actual, expected = usage["actual_usage"], usage["expected_usage"]
    anomalies = []
    for rm_id, expected_qty in expected.items():
        actual_qty = actual.get(rm_id, 0.0)
        if expected_qty <= 0:
            continue
        variance_pct = (actual_qty - expected_qty) / expected_qty
        if abs(variance_pct) >= VARIANCE_THRESHOLD:
            vendor_id, price, _, _ = _vendor_for_material(vendors, rm_id)
            cost_impact = round((actual_qty - expected_qty) * (price or 0), 2)
            anomalies.append({
                "site_id": site_id, "raw_material_id": rm_id,
                "expected_qty": round(expected_qty, 2), "actual_qty": round(actual_qty, 2),
                "variance_pct": round(variance_pct * 100, 1), "cost_impact": cost_impact,
                "vendor_id": vendor_id,
            })
    return anomalies


def compute_reorder_needs(site_id, forecast, on_hand_data, recipes_by_item, vendors):
    """[deterministic] forecast -> expected daily usage per material -> compare on-hand,
    net of usage expected to occur before the vendor's next delivery, to the reorder point;
    size the order up to par at that point-in-time."""
    daily_usage_by_material = []  # index-aligned with `forecast`
    for day in forecast:
        day_usage = {}
        for item_id, units in day["items"].items():
            for line in recipes_by_item[item_id]:
                rm = line["raw_material_id"]
                day_usage[rm] = day_usage.get(rm, 0.0) + units * line["qty"]
        daily_usage_by_material.append(day_usage)

    all_materials = {rm for day in daily_usage_by_material for rm in day}
    on_hand = on_hand_data["on_hand"]
    par = on_hand_data["par_levels"]
    reorder_point = on_hand_data["reorder_points"]

    needs = []
    for rm_id in all_materials:
        vendor_id, price, lead_time, min_order_value = _vendor_for_material(vendors, rm_id)
        lead_time = lead_time or 1
        usage_until_delivery = sum(day.get(rm_id, 0.0) for day in daily_usage_by_material[:lead_time])
        current = on_hand.get(rm_id, 0.0)
        projected_at_delivery = current - usage_until_delivery
        if projected_at_delivery <= reorder_point.get(rm_id, 0):
            suggested_qty = max(0.0, par.get(rm_id, 0) - projected_at_delivery)
            needs.append({
                "site_id": site_id, "raw_material_id": rm_id, "on_hand": round(current, 1),
                "vendor_lead_time_days": lead_time,
                "projected_qty_at_delivery": round(projected_at_delivery, 1),
                "suggested_order_qty": round(suggested_qty, 1),
                "vendor_id": vendor_id, "unit_price": price,
                "vendor_min_order_value": min_order_value,
            })
    return needs
