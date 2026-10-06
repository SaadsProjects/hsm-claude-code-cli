# Code Structure: hsm-claude-code-cli

Commit `825a0f8`. Line counts from `wc -l`.

## Top-Level Layout

| Path | Classification | Notes |
|---|---|---|
| `agents/` | library | Python package; REST client and pure calculations |
| `mock_hsm/` | service | Python package; mock HSM backend |
| `dashboard/` | UI | Python package; Streamlit app, `app.py` entry script |
| `mcp_server/` | service | Directory without `__init__.py`; one FastMCP stdio server |
| `.claude/hooks/*.py` | tooling | Two project PreToolUse hooks (the `*.ts` files are AI-DLC) |
| `.claude/agents/{labor-scheduler,inventory-analyst,code-reviewer}.md` | config | Project subagents (the `aidlc-*` files are AI-DLC) |
| `.claude/commands/` | config | `schedule-labor`, `review-inventory`, `commit` |
| `scripts/` | tooling | CI gate scripts and the dev start script |
| `tests/` | tests | Flat pytest suite, 24 files |
| `.github/workflows/ci.yml` | CI | The only workflow; no deploy workflow yet |
| `docs/ARCHITECTURE.md`, `README.md`, `CLAUDE.md`, `dashboard/README.md` | docs | |
| `aidlc/`, `.claude/aidlc-common/`, `.claude/tools/`, `.claude/knowledge/`, ... | AI-DLC tooling | Excluded from analysis |

## Module Map

### `agents/`
- `hsm_client.py` (475): `HsmClient` (about 35 methods), `HsmApiError` and
  friends, retry helper `retry_write`. Module constant `HSM_BASE_URL` read
  from the environment at import (line 22) and used as the constructor
  default (line 147).
- `labor_scheduling_agent.py` (40): `compute_demand`.
- `inventory_agent.py` (101): `compute_usage_anomalies`,
  `compute_reorder_needs`, 15% variance threshold.

### `mock_hsm/`
- `server.py` (769): `route` decorator and regex route table, 29 explicit
  routes plus 55 generated write routes, `Handler`, `_PUBLIC_ROUTES`,
  blocking `run(host="127.0.0.1", port=8770)` at line 757.
- `auth.py` (82): `_SECRET` module constant (line 24), `mint_token`,
  `verify_token`, `site_allowed`, `region_allowed`, `TokenError`, 3600 s TTL.
- `db.py` (380): sites with timezones, `USERS`, catalog, seeded-RNG
  forecast/sales/usage generators, in-memory collections, lock.
- `writes.py` (1,870): `Kind` catalogue (`KINDS`, 11 kinds), field validators,
  sessions, versioned add/update/delete, bulk CSV, `reset_for_tests`,
  `_started_at` (line 1836).
- `audit.py` (740): JSONL audit trail, `configure()`, path from
  `HSM_AUDIT_PATH` (default `mock_hsm/audit/audit.jsonl`), paging.

### `dashboard/`
- `app.py` (514): `run()` executed at import (line 514) so Streamlit reruns
  the whole script on every interaction; `_login_panel` (376), `main` (447),
  five tabs (Overview, Labor, Inventory, Manage data, Audit).
- `session.py` (179): `client_for(user_id)`, the single client factory.
- `actions.py` (635): write actions and user-facing messages
  (`ENDED_GENERIC`).
- `data.py` (150): read loaders that call `agents` functions.
- `manage_tab.py` (289), `kind_forms.py` (319), `csv_rows.py` (99),
  `audit_tab.py` (97), `safe_text.py` (26): skimmed only.

### `mcp_server/`
- `hsm_tools.py` (168): `_client()` (mints a token from `HSM_ACTIVE_USER`
  per call), 11 `@mcp.tool()` functions.

### `.claude/hooks/`
- `require_no_violations.py` (88): PreToolUse gate for `publish_schedule`.
- `lint_before_commit.py` (378): PreToolUse gate for Bash `git commit`.

### `scripts/`
`check_burned_secret.py`, `check_exceptions.py`, `check_workflows.py`,
`coverage_gate.py`, `filter_audit.py`, `filter_bandit.py`, `floor_ratchet.py`,
`job_summary.py`, `test_floor.py`, `run_pip_audit.sh`,
`start_mock_server.sh`.

### `tests/`
`conftest.py` (autouse audit-path and write-reset fixtures; `perf` and
`browser` markers), `ci_scripts.py` (loads `scripts/` by path), and test files
for labor rules, calculations, hooks, lint hook, MCP tools, purchase orders,
writes (core, routes, service), HSM client writes, audit log and routes,
dashboard (app, data, units), conftest markers and CI scripts.

## Code Patterns

- **Import by path.** No package metadata; entry points insert the repo root
  into `sys.path` (`dashboard/app.py:21`, `mcp_server/hsm_tools.py:22`,
  `.claude/hooks/require_no_violations.py:31`, `tests/conftest.py:15`).
- **Route table by decorator** in the backend; generated per-kind routes
  registered `first=True` so reserved ids win.
- **Pure function + thin adapter.** Tools and dashboard loaders fetch through
  `HsmClient` and call `agents` functions; they never import `mock_hsm.db`
  (the dashboard's `USERS` import is the documented exception).
- **Boundary-only broad excepts** with `# noqa: BLE001 -- <reason>`.
- **Module-level configuration read at import** (`HSM_BASE_URL`, `_SECRET`).
  This is the pattern the hosting intent has to change; see
  `code-quality-assessment.md` CQ-1 and CQ-4.
