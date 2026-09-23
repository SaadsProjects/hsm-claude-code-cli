# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# HSM Agentic Automation — Claude Code CLI project

This project automates two HSM (restaurant back-office) workflows using
Claude Code's own primitives — MCP tools, subagents, slash commands, and
hooks — rather than a bespoke orchestration script. See
`CLAUDE_CODE_CLI_PLAN.md` for the full design rationale.

## Non-negotiable rules

- **Never call `publish_schedule` or `submit_purchase_order` unless the
  user's instruction explicitly asks for it.** These are real writes
  (simulated here, but treat them as if they weren't) and are
  permission-gated in `.claude/settings.json` for exactly this reason.
- **Never treat your own judgment as a substitute for `validate_schedule`.**
  It is the Labor Rules Engine call, and it is the only authoritative
  answer on whether a schedule is compliant. If you haven't called it on
  the *exact* shift list you're about to publish, you don't know it's
  compliant.
- **Never increase a purchase-order quantity for a raw material with a
  medium/high-severity usage anomaly.** Cap it at the tool-supplied
  `suggested_order_qty` and say so in the order notes.
- The demand, variance, and reorder-point numbers come from
  `compute_labor_demand`, `compute_usage_anomalies`, and
  `compute_reorder_needs` — call these rather than estimating the
  underlying math yourself.

## Commands

```bash
pip install -r requirements.txt          # Python 3.10+; mcp pinned <2 (code uses 1.x FastMCP API)
python3 -m mock_hsm.server &             # mock backend on 127.0.0.1:8770 (or scripts/start_mock_server.sh)
python3 -m pytest tests/ -q              # all tests; they start their own mock servers (:8772, :8773)
python3 -m pytest tests/test_labor_rules.py -k overnight  # a single test
ruff check .                             # lint (same check the commit hook runs; rules pinned in ruff.toml)
python3 mcp_server/hsm_tools.py          # run the MCP server standalone over stdio
mcp dev mcp_server/hsm_tools.py          # MCP Inspector (needs the mcp[cli] extra)
```

`test_labor_rules.py` calls the validator handler directly; `test_hooks.py`
pipes JSON into the publish hook as Claude Code does (the hung-backend case
takes ~5s by design). `tests/test_mcp_tools.py` is one sequential scenario
(`_run()`) wrapped in a single pytest test, so the first failed assertion
stops the run; it can also be run directly with `python3 tests/test_mcp_tools.py`. Adding a new
MCP tool means adding its name to the `expected` set there.

If the `hsm` MCP server fails to connect, check that `mcp` is installed for
the `python3` on PATH. If `ruff` isn't installed, the lint hook fails
**open** (commits go through unchecked).

## Running the workflows

The mock backend must be running, and `HSM_ACTIVE_USER` must be exported
**before** starting `claude` — the MCP server reads it to mint a scoped
token per call:

```bash
export HSM_ACTIVE_USER=user_rm_midtown      # Restaurant Manager, site_001 only
export HSM_ACTIVE_USER=user_regional_atl    # Regional Manager, region_atl (site_001–003)
```

- `/schedule-labor <site_id> [--publish]` — needs a Restaurant Manager
  scoped to that site.
- `/review-inventory [--submit]` — needs the Regional Manager.
- `/commit <message>` — see below.

## Architecture

Request path for every tool call:
subagent → `mcp__hsm__*` tool (`mcp_server/hsm_tools.py`) → `_client()`
mints an HMAC token from `HSM_ACTIVE_USER` (`mock_hsm/auth.py`) →
`agents/hsm_client.HsmClient` (stdlib urllib, base URL from `HSM_BASE_URL`)
→ `mock_hsm/server.py`, which verifies the token and enforces
site/region scope per route (403 outside the persona's scope).

The deterministic/LLM split is enforced by what's exposed as a tool:

- **Deterministic math** lives as pure functions in
  `agents/labor_scheduling_agent.py` (`compute_demand`) and
  `agents/inventory_agent.py` (`compute_usage_anomalies`,
  `compute_reorder_needs`, 15% variance threshold). The MCP tools just
  fetch data and call these. Anything else in those modules that calls an
  LLM is legacy and unused. New calculations belong there, not inline in
  a tool.
- **Rule validation** happens server-side in the mock's
  `/labor/rules/validate` route (`labor_rules_validate` in
  `mock_hsm/server.py`).
- **Judgment** (building shifts, anomaly cause/severity, PO consolidation)
  is left to the subagents in `.claude/agents/`. Each subagent's `tools:`
  frontmatter allowlists exactly the `mcp__hsm__*` tools it may use, so a
  new tool must be added there before a subagent can use it.

Gating of writes is layered:
1. `permissions.ask` in `.claude/settings.json` prompts before either write tool.
2. The `PreToolUse` hook `.claude/hooks/require_no_violations.py`
   independently re-runs validation on the exact `shifts` passed to
   `publish_schedule` and denies if any violation remains — or if it can't
   validate at all, since a crashed or timed-out hook fails open. It uses
   `HSM_JURISDICTION` (default `GA`), not the site's jurisdiction.
3. Hooks only ever deny or fall through (`{}`); they never grant `allow`.

A new gated write tool needs an `ask` rule in `settings.json`, in the same
way as the existing two.

Mock backend state (`mock_hsm/db.py`) is in-memory: published schedules and
POs reset when the server restarts. Forecast/usage data comes from seeded
RNG and is deterministic. Some anomalies are planted on purpose (e.g. the
`rm_ground_beef` drift at site_001, which the test asserts on).

## Committing changes to this project

Don't run `git commit` directly — go through `/commit`, which runs the
read-only `code-reviewer` subagent on the staged diff first. The
`lint_before_commit.py` hook separately blocks any `git commit` Bash call
if `ruff check .` fails. If the reviewer finds something, decide whether
to address it before committing rather than routing around it. (This
directory is not currently a git repository, so `/commit` needs a
`git init` first.)
