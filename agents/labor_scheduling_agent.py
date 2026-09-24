"""
Deterministic calculation for use case 1 (labor scheduling).

This is the piece of the original standalone-demo orchestration that is
still useful in the Claude Code CLI version: the pure demand-derivation
math, wrapped by mcp_server/hsm_tools.py as the `compute_labor_demand`
tool. The judgment steps (draft a schedule, resolve rule violations) that
used to be hand-coded LLM calls here are now just the labor-scheduler
subagent's own reasoning (see .claude/agents/labor-scheduler.md) -- there
is deliberately no LLM-calling code left in this file.
"""
from datetime import date

STAFFING_RATIO = {"JC-COOK": 25.0, "JC-SERVER": 25.0, "JC-CASHIER": 50.0}  # covers per labor-hour
LEAD_HOURS_PER_DAY = 8.0


def _weekday_abbr(d: date) -> str:
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]


def compute_demand(forecast):
    """[deterministic] covers-per-day -> role-hours-per-day via fixed staffing ratios.
    Dates come from the forecast rows (site-local), not from this host's clock."""
    demand = []
    for day_row in forecast:
        d = date.fromisoformat(day_row["date"])
        covers = sum(day_row["items"].values())
        role_hours = {jc: round(covers / ratio, 1) for jc, ratio in STAFFING_RATIO.items()}
        role_hours["JC-LEAD"] = LEAD_HOURS_PER_DAY
        demand.append({"date": d.isoformat(), "weekday": _weekday_abbr(d), "covers": round(covers, 1),
                        "role_hours_needed": role_hours})
    return demand
