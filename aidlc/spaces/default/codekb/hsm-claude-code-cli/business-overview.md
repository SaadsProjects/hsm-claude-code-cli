# Business Overview: hsm-claude-code-cli

Commit `825a0f8`, scanned 2026-10-04. Source: developer scan for intent
`261005-dashboard-hosting-readin`.

## Business Domain

HSM is a restaurant back-office system (sites, menu, sales, forecast, labor,
inventory, vendors). This repository does not contain HSM itself. It contains
a **mock HSM backend** and automation around two back-office workflows,
built on Claude Code's own primitives: MCP tools, subagents, slash commands
and hooks.

## Purpose

1. **Show agentic automation of HSM workflows** with a hard split between
   deterministic maths (pure Python functions) and LLM judgment (subagents).
2. **Keep real writes gated.** Publishing a schedule and submitting a purchase
   order are treated as real, irreversible writes and need explicit human
   permission at several layers (see `architecture.md` § Write Gating).
3. **Give people a dashboard** (Streamlit) to look at the same data, manage
   demo records and read the audit trail.

## Key Workflows

| Workflow | Entry point | Persona | Outcome |
|---|---|---|---|
| Labor scheduling | `/schedule-labor <site_id> [--publish]` → `labor-scheduler` subagent | Restaurant Manager (`user_rm_midtown`, site_001) | A week of shifts that the Labor Rules Engine (`validate_schedule`) declares compliant; optionally published |
| Inventory review | `/review-inventory [--submit]` → `inventory-analyst` subagent | Regional Manager (`user_regional_atl`, region_atl, site_001-003) | Usage anomalies explained and consolidated vendor POs drafted; optionally submitted |
| Dashboard viewing | `streamlit run dashboard/app.py` | Any persona picked in-app | Overview, Labor and Inventory tabs (read-only) |
| Demo data management | Dashboard "Manage data" tab, after `POST /sessions` | Any persona, within its scope | Add, edit, delete and CSV bulk-upload 11 kinds of record |
| Audit review | Dashboard "Audit" tab | Any persona, scope-filtered | Pages through every write and every publish/PO attempt |
| Committing project changes | `/commit` → `code-reviewer` subagent + lint hook | Developer | Reviewed, lint-clean commit |

## Personas

Defined in `mock_hsm/db.py` `USERS`:

- `user_rm_midtown`: Restaurant Manager, site_001 only.
- `user_regional_atl`: Regional Manager, region_atl (site_001 to site_003).
- `user_dev_tester`: developer/tester login with the Regional Manager's
  persona and scope, distinguished in the audit trail by its user id.

## Business Rules That Matter

- Never publish a schedule or submit a PO unless the human explicitly asks.
- `validate_schedule` (server-side Labor Rules Engine) is the only authority
  on compliance. Times are strict `HH:MM`; an end at or before the start runs
  past midnight; same-day split shifts are allowed but capped by
  `max_daily_hours` and must not overlap. `daily_ot_threshold_hours` is a
  cost input, not a violation.
- A raw material with a medium/high-severity usage anomaly is never ordered
  above the tool-supplied `suggested_order_qty`.
- Usage variance threshold is 15% (`agents/inventory_agent.py`).
- Dates are site-local and come from the backend (each site has a timezone).
- Some anomalies are planted on purpose (`rm_ground_beef` drift at site_001).

## Current Business Context (intent `dashboard-hosting-readin`)

The dashboard runs only on loopback today, the persona picker is the only
"sign-in", the signing secret is a burned literal, and all demo data is in
memory. The active intent prepares the dashboard for hosting on Streamlit
Community Cloud. The gaps it must close are recorded once in
`code-quality-assessment.md`.
