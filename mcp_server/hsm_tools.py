"""
MCP server exposing the mock HSM REST API as tools for Claude Code.

Deterministic computations (demand derivation, usage-variance detection,
reorder-point math, labor-rule validation) are computed HERE, server-side,
and returned as data -- the calling agent can only get these numbers by
calling the tool, never by approximating them itself. That's what keeps
the deterministic/LLM split real rather than aspirational: it's enforced
by which operations are exposed as tools with fixed logic vs. left to the
subagent's own reasoning over the results.

Run standalone for a protocol smoke test:
    python3 mcp_server/hsm_tools.py

Registered with Claude Code via .mcp.json in the project root.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from agents.hsm_client import HsmClient
from agents.inventory_agent import compute_reorder_needs as _compute_reorder_needs
from agents.inventory_agent import compute_usage_anomalies as _compute_usage_anomalies
from agents.labor_scheduling_agent import compute_demand
from mock_hsm.auth import mint_token
from mock_hsm.db import RECIPES

mcp = FastMCP("hsm", instructions=(
    "Tools for HSM (restaurant back-office) labor scheduling and inventory/"
    "COGS review. Deterministic calculations (demand, variance, reorder "
    "points, labor-rule validation) are computed by these tools, not by "
    "the calling model -- always call the relevant tool rather than "
    "estimating these numbers yourself. publish_schedule and "
    "submit_purchase_order have real effects and are permission-gated."
))


def _client() -> HsmClient:
    user_id = os.environ.get("HSM_ACTIVE_USER")
    if not user_id:
        raise RuntimeError(
            "HSM_ACTIVE_USER is not set. Export it to the demo user acting as "
            "this session's persona, e.g. HSM_ACTIVE_USER=user_rm_midtown."
        )
    return HsmClient(mint_token(user_id))


# --------------------------------------------------------------- Read-only
@mcp.tool()
def get_forecast(site_id: str, start_offset_days: int = 0, days: int = 7) -> dict:
    """AI/ML sales forecast for a site (normally BigQuery-backed). Returns
    per-day projected units by menu item."""
    return {"site_id": site_id, "forecast": _client().get_forecast(site_id, start_offset_days, days)}


@mcp.tool()
def get_employees(site_id: str) -> dict:
    """Employee roster for a site: id, name, job_code, hourly_rate,
    jurisdiction, max_weekly_hours_preference, available_days."""
    return {"site_id": site_id, "employees": _client().get_employees(site_id)}


@mcp.tool()
def get_labor_rules(jurisdiction: str) -> dict:
    """Labor Rules Engine ruleset for a jurisdiction (overtime thresholds,
    max shift length, max consecutive days, min rest between shifts)."""
    return _client().get_labor_rules(jurisdiction)


@mcp.tool()
def get_vendors() -> dict:
    """Vendor list with price lists, lead times, and minimum order values."""
    return {"vendors": _client().get_vendors()}


@mcp.tool()
def get_on_hand(site_id: str) -> dict:
    """Current on-hand raw-material inventory, par levels, and reorder points for a site."""
    return _client().get_on_hand(site_id)


# ------------------------------------------------------- Deterministic calc
@mcp.tool()
def compute_labor_demand(site_id: str, start_offset_days: int = 7, days: int = 7) -> dict:
    """DETERMINISTIC. Forecast -> covers -> role-hours-needed per day, via
    fixed staffing ratios. Call this instead of estimating staffing demand
    yourself from a raw forecast."""
    forecast = _client().get_forecast(site_id, start_offset_days, days)
    today = datetime.now().astimezone().date()  # site-local calendar date
    dates = [today + timedelta(days=start_offset_days + i) for i in range(days)]
    return {"site_id": site_id, "demand": compute_demand(forecast, dates)}


@mcp.tool()
def validate_schedule(jurisdiction: str, shifts: list) -> dict:
    """DETERMINISTIC / AUTHORITATIVE. Calls the (mock) Labor Rules Engine to
    check a draft schedule for violations (overtime, max shift length, max
    consecutive days, minimum rest between shifts). This is the only
    authoritative source of truth on rule compliance -- never assert a
    schedule is compliant without calling this, and never treat your own
    judgment as a substitute for its result.

    shifts: list of {employee_id, date (YYYY-MM-DD), role, start_time
    (HH:MM), end_time (HH:MM)}."""
    return _client().validate_schedule(jurisdiction, shifts)


@mcp.tool()
def compute_usage_anomalies(site_id: str) -> dict:
    """DETERMINISTIC. Actual vs. recipe-expected raw-material usage over the
    past 7 days, flagged where variance exceeds 15%. Returns the numeric
    anomalies only -- interpreting likely cause/severity/action is your job,
    not this tool's."""
    client = _client()
    usage = client.get_usage(site_id, start_offset_days=-7, days=7)
    anomalies = _compute_usage_anomalies(site_id, usage, client.get_vendors())
    return {"site_id": site_id, "anomalies": anomalies}


@mcp.tool()
def compute_reorder_needs(site_id: str) -> dict:
    """DETERMINISTIC. Projects usage over the next 7 days from the sales
    forecast, compares on-hand inventory (net of usage expected before each
    vendor's next delivery) to the reorder point, and sizes a suggested
    order quantity up to par. Returns raw needs only -- deciding how to
    consolidate into purchase orders, and whether to cap any item under
    anomaly investigation, is your job, not this tool's."""
    client = _client()
    forecast = client.get_forecast(site_id, start_offset_days=0, days=7)
    on_hand_data = client.get_on_hand(site_id)
    needs = _compute_reorder_needs(site_id, forecast, on_hand_data, RECIPES, client.get_vendors())
    return {"site_id": site_id, "reorder_needs": needs}


# --------------------------------------------------------- Gated write ops
@mcp.tool()
def publish_schedule(site_id: str, shifts: list) -> dict:
    """WRITE / GATED. Publishes a schedule. Permission-gated in
    .claude/settings.json and additionally re-validated by a PreToolUse
    hook that blocks this call if any labor-rule violation remains --
    do not call this until validate_schedule has returned zero violations
    for this exact shift list, and only when the user has explicitly asked
    you to publish."""
    return _client().publish_schedule(site_id, shifts)


@mcp.tool()
def submit_purchase_order(vendor_id: str, line_items: list, site_id: str | None = None, region_id: str | None = None) -> dict:
    """WRITE / GATED. Submits a purchase order to a vendor. Permission-gated
    in .claude/settings.json. Only call this when the user has explicitly
    asked you to submit, and never for a line item you have reason to
    believe is still under active usage-anomaly investigation."""
    return _client().submit_purchase_order(vendor_id, line_items, site_id=site_id, region_id=region_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")
