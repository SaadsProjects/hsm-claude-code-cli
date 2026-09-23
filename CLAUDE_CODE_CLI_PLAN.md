# Automating HSM Workflows with the Claude Code CLI — Detailed Plan

This is the detailed design plan for automating two HSM (restaurant
back-office) use cases — labor scheduling, and inventory/COGS + vendor
ordering — as a project built **on the Claude Code CLI itself**:
subagents, MCP tools, slash commands, hooks, and permissions handle the
orchestration, rather than a bespoke script that calls the Anthropic API
directly.

Orchestration lives in **Claude Code's own agent loop** rather than a
hand-written control-flow loop: subagents call MCP tools for anything
deterministic (demand calculation, rule validation, anomaly detection,
reorder math) so those numbers can't be "reasoned around," and reason over
the results themselves for anything judgment-based (schedule drafts,
anomaly interpretation, PO sizing). The human-approval gate on any write
(publishing a schedule, submitting a purchase order) is a real Claude Code
permission rule and `PreToolUse` hook, enforced by the platform rather
than application code.

This exercises the actual Claude Code product surface end to end:
subagents, MCP servers, hooks, permissions, and headless (`-p`) scripting.

---

## 1. Key architectural decisions

| Concern | Approach |
|---|---|
| Who orchestrates | Claude Code's agent loop, driven by a slash command + subagent prompt |
| How HSM is reached | REST calls wrapped as **MCP tools** the agent invokes |
| Deterministic math (demand, variance, reorder point, rule validation) | Lives **inside MCP tool implementations** — the agent can only get these numbers by calling the tool, never by "reasoning" them, so they stay authoritative |
| LLM judgment steps | The subagent's own reasoning, using tool results as context — no separate API call to manage |
| Approval gate | Claude Code **permission rule** / **PreToolUse hook** on the `publish_schedule` / `submit_purchase_order` tools — the platform enforces the pause, not application code |
| Persona scoping | Token minted by the MCP server from an env var / slash-command argument naming the acting persona; enforcement is server-side, every call |
| Running it | `claude "/schedule-labor site_001"` (interactive) or `claude -p "/schedule-labor site_001" --output-format json` (headless/scripted) |

The mock HSM server (`mock_hsm/server.py`) is a plain REST API, which is
exactly what an MCP server needs to wrap.

---

## 2. Project layout

```
hsm-claude-code/
├── CLAUDE.md                        # project-level instructions Claude Code loads automatically
├── mock_hsm/                        # mock HSM REST backend + persona-scoped auth
│   ├── db.py
│   ├── auth.py
│   └── server.py
├── mcp_server/
│   └── hsm_tools.py                 # MCP server: wraps mock_hsm REST API as tools
├── .mcp.json                        # registers hsm_tools.py as a project MCP server
├── .claude/
│   ├── agents/
│   │   ├── labor-scheduler.md       # subagent: use case 1
│   │   └── inventory-analyst.md     # subagent: use case 2
│   ├── commands/
│   │   ├── schedule-labor.md        # slash command: /schedule-labor <site_id>
│   │   └── review-inventory.md      # slash command: /review-inventory
│   ├── hooks/
│   │   └── require_no_violations.py # PreToolUse hook guarding publish/submit tools
│   └── settings.json                # permission rules + hook registration
└── tests/
    └── test_mcp_tools.py            # protocol-level smoke tests against the MCP layer
```

---

## 3. The MCP server: where the deterministic logic lives

This is the load-bearing piece. Every deterministic step (`compute_demand`,
`compute_usage_anomalies`, `compute_reorder_needs`, schedule rule
validation) lives in a **tool implementation** the agent calls *as part
of* its own reasoning. That's the key architectural principle: in Claude
Code, "deterministic vs. judgment" isn't enforced by which function an
orchestration script happens to call next — it's enforced by which
operations are exposed as tools with fixed server-side logic (can't be
talked out of) versus left to the model's own reasoning over tool results.

```python
# mcp_server/hsm_tools.py  (sketch)
from mcp.server.fastmcp import FastMCP
from agents.hsm_client import HsmClient
from mock_hsm.auth import mint_token
import os

mcp = FastMCP("hsm")

def _client():
    user_id = os.environ["HSM_ACTIVE_USER"]     # set per slash-command invocation
    return HsmClient(mint_token(user_id))

@mcp.tool()
def get_forecast(site_id: str, start_offset_days: int = 0, days: int = 7) -> list:
    """AI/ML sales forecast for a site (normally BigQuery-backed)."""
    return _client().get_forecast(site_id, start_offset_days, days)

@mcp.tool()
def compute_labor_demand(site_id: str, start_offset_days: int = 7, days: int = 7) -> list:
    """Deterministic: forecast -> covers -> role-hours-needed per day.
    Ratios and rounding live HERE, server-side -- not left for the model to
    approximate."""
    from agents.labor_scheduling_agent import compute_demand
    from datetime import date, timedelta
    forecast = _client().get_forecast(site_id, start_offset_days, days)
    dates = [date.today() + timedelta(days=start_offset_days + i) for i in range(days)]
    return compute_demand(forecast, dates)

@mcp.tool()
def get_employees(site_id: str) -> list:
    return _client().get_employees(site_id)

@mcp.tool()
def get_labor_rules(jurisdiction: str) -> dict:
    return _client().get_labor_rules(jurisdiction)

@mcp.tool()
def validate_schedule(jurisdiction: str, shifts: list) -> dict:
    """Deterministic: calls the (mock) Labor Rules Engine. Authoritative --
    the agent must call this rather than assert a schedule is compliant."""
    return _client().validate_schedule(jurisdiction, shifts)

@mcp.tool()
def publish_schedule(site_id: str, shifts: list) -> dict:
    """Writes the schedule. Gated -- see .claude/settings.json permission
    rule and the PreToolUse hook, both of which must pass before this runs."""
    return _client().publish_schedule(site_id, shifts)

@mcp.tool()
def compute_usage_anomalies(site_id: str) -> list:
    from agents.inventory_agent import compute_usage_anomalies as _calc
    client = _client()
    usage = client.get_usage(site_id, -7, 7)
    return _calc(site_id, usage, client.get_vendors())

@mcp.tool()
def compute_reorder_needs(site_id: str) -> list:
    from agents.inventory_agent import compute_reorder_needs as _calc
    from mock_hsm.db import RECIPES
    client = _client()
    forecast = client.get_forecast(site_id, 0, 7)
    on_hand = client.get_on_hand(site_id)
    return _calc(site_id, forecast, on_hand, RECIPES, client.get_vendors())

@mcp.tool()
def submit_purchase_order(vendor_id: str, line_items: list, site_id: str = None, region_id: str = None) -> dict:
    """Gated the same way as publish_schedule."""
    return _client().submit_purchase_order(vendor_id, line_items, site_id, region_id)

if __name__ == "__main__":
    mcp.run()
```

```json
// .mcp.json
{
  "mcpServers": {
    "hsm": {
      "command": "python3",
      "args": ["mcp_server/hsm_tools.py"],
      "env": { "HSM_BASE_URL": "http://127.0.0.1:8770" }
    }
  }
}
```

Note what's *not* an MCP tool: the actual schedule-drafting judgment
("assign these employees to these shifts") and the actual anomaly/PO
judgment. Those stay as reasoning the subagent does itself, over the
outputs of `compute_labor_demand`, `get_employees`, `get_labor_rules`,
`compute_usage_anomalies`, and `compute_reorder_needs`. That's the
deterministic/LLM split, expressed as "which things are tools vs. which
things are left to the model."

---

## 4. Subagents

Each subagent is scoped to only the tools its domain needs (via `tools:`
in frontmatter), which is itself a form of persona-appropriate least
privilege — a labor-scheduling subagent has no path to touch inventory or
vendor data at all, independent of the HSM-level persona scoping.

```markdown
---
# .claude/agents/labor-scheduler.md
name: labor-scheduler
description: Builds and iterates a compliant weekly labor schedule for one HSM site.
tools: mcp__hsm__get_forecast, mcp__hsm__compute_labor_demand, mcp__hsm__get_employees,
       mcp__hsm__get_labor_rules, mcp__hsm__validate_schedule, mcp__hsm__publish_schedule
---

You build next week's labor schedule for a single restaurant site.

Process:
1. Call compute_labor_demand to get role-hours needed per day (already
   forecast-derived — do not recompute this yourself).
2. Call get_employees and get_labor_rules for the site's jurisdiction.
3. Draft a full week of shifts: one entry per {employee_id, date, role,
   start_time, end_time}. Only assign an employee to a role matching
   their job_code. Respect max_weekly_hours_preference as a soft target.
4. Call validate_schedule with your draft. If it returns violations,
   revise the schedule to resolve them -- prefer reassigning hours to
   another qualified employee over just deleting shifts -- and validate
   again. Repeat up to 3 times.
5. Report the final draft, any coverage gaps against the original demand
   (be explicit about days/roles left short and why -- e.g. "only one
   cashier on staff, cannot legally work all 7 days"), and the projected
   labor cost including overtime premiums.
6. Do NOT call publish_schedule unless the user's instruction to you
   explicitly says to publish AND no violations remain. If violations
   remain, report them and stop -- do not publish a non-compliant schedule
   under any circumstances.
```

```markdown
---
# .claude/agents/inventory-analyst.md
name: inventory-analyst
description: Reviews COGS/usage anomalies across sites and drafts vendor purchase orders.
tools: mcp__hsm__compute_usage_anomalies, mcp__hsm__compute_reorder_needs,
       mcp__hsm__submit_purchase_order
---

You review inventory usage anomalies and draft purchase orders for a set
of sites in a region.

Process:
1. For each site, call compute_usage_anomalies and compute_reorder_needs.
2. For each anomaly, infer a likely cause (portioning drift, prep waste,
   spoilage, recipe/yield mismatch, possible theft, one-off event), a
   severity (low/medium/high), and a specific recommended action --
   grounded only in the numbers given, never invented.
3. Draft purchase orders from the reorder needs, one per vendor,
   consolidating across sites when that clears the vendor's minimum order
   value more efficiently than separate per-site orders. For any raw
   material that also has a medium/high-severity anomaly, cap its order
   quantity at the supplied suggested_order_qty and note it is under
   investigation -- do not increase it, so we don't compound a possible
   waste/theft problem with a bigger order.
4. Report the anomalies, drafts, and total spend per vendor.
5. Do NOT call submit_purchase_order unless the user's instruction to you
   explicitly says to submit.
```

---

## 5. Slash commands

```markdown
---
# .claude/commands/schedule-labor.md
description: Build next week's labor schedule for a site
---
Use the labor-scheduler subagent to build next week's schedule for site
$ARGUMENTS. Draft only -- do not publish unless I separately say to.
```

```markdown
---
# .claude/commands/review-inventory.md
description: Review usage anomalies and draft vendor POs across the region
---
Use the inventory-analyst subagent to review usage anomalies and draft
purchase orders across all sites in region_atl. Draft only -- do not
submit unless I separately say to.
```

Usage:

```bash
export HSM_ACTIVE_USER=user_rm_midtown      # persona for this session
claude "/schedule-labor site_001"

export HSM_ACTIVE_USER=user_regional_atl
claude "/review-inventory"

# Headless / scriptable form, e.g. for a scheduled job:
claude -p "/schedule-labor site_001" --output-format json > schedule_run.json
```

---

## 6. Enforcing the approval gate with permissions + a hook

Rather than trusting the model's own restraint, Claude Code's permission
system and hooks enforce the gate at the platform layer.

**Permission rule** (`.claude/settings.json`) — require explicit approval
on the two write tools regardless of what the subagent decides:

```json
{
  "permissions": {
    "ask": [
      "mcp__hsm__publish_schedule",
      "mcp__hsm__submit_purchase_order"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__hsm__publish_schedule",
        "hooks": [{ "type": "command", "command": "python3 .claude/hooks/require_no_violations.py" }]
      }
    ]
  }
}
```

**Hook** — a hard backstop that blocks publish even if a human fat-fingers
"yes" on a schedule that still has violations, by re-validating server-side
before allowing the call through:

```python
# .claude/hooks/require_no_violations.py
import json, sys
from agents.hsm_client import HsmClient
from mock_hsm.auth import mint_token
import os

payload = json.load(sys.stdin)
shifts = payload["tool_input"]["shifts"]
site_id = payload["tool_input"]["site_id"]
jurisdiction = os.environ.get("HSM_JURISDICTION", "GA")

client = HsmClient(mint_token(os.environ["HSM_ACTIVE_USER"]))
result = client.validate_schedule(jurisdiction, shifts)
if result["violations"]:
    print(json.dumps({"decision": "block",
                       "reason": f"{len(result['violations'])} unresolved labor-rule violation(s)"}))
    sys.exit(0)
print(json.dumps({"decision": "approve"}))
```

The same pattern applies to `submit_purchase_order` if you want a hard
rule like "never auto-submit an order whose total exceeds $X" or "never
submit if any line item is under high-severity anomaly investigation" --
express it as a hook rather than relying on the subagent's prompt.

---

## 7. Persona scoping in this architecture

HSM's real scoping (Restaurant Manager -> one site, Regional Manager ->
one region) maps onto Claude Code as: **the persona is a property of the
session/invocation, not of the model**. `HSM_ACTIVE_USER` (or a
slash-command argument, if you want to switch personas within one Claude
Code session) tells the MCP server which token to mint; the mock server
enforces scope exactly as before, per call. The subagent itself never sees
raw credentials -- it only ever calls tools, and the tools are the only
thing that touches auth.

---

## 8. Component inventory

**Foundational (backend + client, not agent-specific):**
- `mock_hsm/db.py`, `mock_hsm/auth.py`, `mock_hsm/server.py` — the mock backend and persona-scoped auth
- `agents/hsm_client.py` — the REST client
- The pure calculation functions (`compute_demand`, `compute_usage_anomalies`, `compute_reorder_needs`) in `agents/labor_scheduling_agent.py` / `agents/inventory_agent.py` — called directly from MCP tool bodies

**New work specific to this architecture:**
- `mcp_server/hsm_tools.py` — the MCP wrapper (Section 3)
- `.claude/agents/*.md` — the two subagent definitions (Section 4)
- `.claude/commands/*.md` — the two slash commands (Section 5)
- `.claude/settings.json` + `.claude/hooks/require_no_violations.py` — the approval gate (Section 6)
- `CLAUDE.md` — a short project-level brief so Claude Code understands the architecture and the deterministic/LLM split without it being re-explained every session (a few paragraphs pointing at this plan and naming the non-negotiable rules: never publish/submit without explicit instruction, never treat a model-asserted "no violations" as authoritative -- always call validate_schedule)

---

## 9. Suggested build order

1. Set up `mock_hsm/` (backend + persona-scoped auth) and `agents/hsm_client.py` (REST client); confirm the mock server runs on its own before wiring up MCP.
2. Write `mcp_server/hsm_tools.py` and `.mcp.json`; verify each tool independently (a quick Python script calling the MCP server directly, or `claude mcp list` / a scratch session with all tools exposed at the top level, no subagents yet).
3. Write the two subagent files and slash commands; run them in draft-only mode (no permission rules yet) and sanity-check the drafts against the seeded data by hand -- the demand and variance numbers should match what `compute_demand`/`compute_usage_anomalies` compute directly.
4. Add the permission rule and hook; deliberately try to get the agent to publish a schedule with a manufactured violation, and confirm the hook blocks it.
5. Wire up headless invocation (`claude -p ...`) and, if you want a truly "automated" version rather than a manually-triggered demo, a scheduled task that runs `/schedule-labor` weekly per site and `/review-inventory` daily per region.
6. Write `CLAUDE.md` last, once the architecture is settled, so it accurately documents the non-negotiable rules rather than aspirational ones.
