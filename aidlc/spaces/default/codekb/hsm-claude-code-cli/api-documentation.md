# API Documentation: hsm-claude-code-cli

Commit `825a0f8`.

## 1. Mock HSM REST API (`mock_hsm/server.py`)

JSON over HTTP, `ThreadingHTTPServer`, default `127.0.0.1:8770`.

### Cross-cutting contract

- **Auth:** every route except `GET /healthz` requires
  `Authorization: Bearer <token>`; `verify_token` failure → 401.
- **Scope:** each handler checks site/region scope from the token claims → 403
  outside the persona's scope.
- **Body limits:** over 1 MiB → 400; over 8 MiB also closes the connection.
- **Audit:** every data write and every publish/PO attempt is appended to the
  audit trail; publish and PO return 503 "audit unavailable" if it cannot be
  written.

### Explicit routes (29)

| Area | Method and path |
|---|---|
| Admin | `GET /admin/orgs/{org_id}`, `GET /admin/sites`, `GET /admin/sites/{site_id}` |
| Catalog / sales | `GET /catalog/menu-items`, `GET /sales/gl-codes`, `GET /sales/job-codes` |
| Forecast / actuals | `GET /forecast/sites/{site_id}/sales`, `GET /transaction-data/sites/{site_id}/sales` |
| Inventory reads | `GET /inventory/uom`, `GET /inventory/raw-materials`, `GET /inventory/recipes`, `GET /inventory/recipes/{menu_item_id}`, `GET /inventory/vendors`, `GET /inventory/sites/{site_id}/on-hand`, `GET /inventory/par-levels`, `GET /inventory/reorder-points`, `GET /inventory/sites/{site_id}/usage` |
| Purchase orders | `POST /inventory/purchase-orders` (gated write), `GET /inventory/purchase-orders` (scope-filtered) |
| Labor | `GET /labor/sites/{site_id}/employees`, `GET /labor/rules`, `POST /labor/rules/validate` (side-effect free; strict `HH:MM`, else 400) |
| Schedules | `POST /labor/sites/{site_id}/schedules/publish` (gated write), `GET /labor/sites/{site_id}/schedules` |
| Audit | `GET /audit` (paged, `before` cursor, scope-filtered) |
| Sessions | `POST /sessions`, `POST /sessions/{session_id}/logout`, `GET /sessions/{session_id}` |
| Health | `GET /healthz` → `200 {"status": "ok"}`; the only public route |

### Generated write routes (55)

`_register_write_routes()` adds five routes for each of the 11 kinds in
`mock_hsm.writes.KINDS` (`menu_item`, `recipe`, `raw_material`, `uom`,
`vendor`, `employee`, `job_code`, `on_hand`, `par_level`, `reorder_point`,
`labor_rule`):

| Method | Path | Purpose |
|---|---|---|
| GET | `<collection>/template` | CSV template |
| POST | `<collection>/bulk` | CSV bulk add |
| POST | `<collection>` | add |
| PUT | `<item>` | update (needs `version`) |
| DELETE | `<item>` | delete (needs `version`) |

Writes carry a `session_id` and optional `request_id` (idempotent retry).

### Server entry point

`run(host="127.0.0.1", port=8770)` calls `audit.configure()` then
`serve_forever()` and blocks. There is no non-blocking start function (see
`code-quality-assessment.md` CQ-4).

## 2. MCP Tools (`mcp_server/hsm_tools.py`, stdio, server name `hsm`)

| Tool | Kind | Backend use |
|---|---|---|
| `get_forecast(site_id, start_offset_days=0, days=7)` | read | forecast route |
| `get_employees(site_id)` | read | employees route |
| `get_labor_rules(jurisdiction)` | read | `/labor/rules` |
| `get_vendors()` | read | vendors route |
| `get_on_hand(site_id)` | read | on-hand route |
| `compute_labor_demand(site_id, start_offset_days=7, days=7)` | calculation | forecast → `compute_demand` |
| `validate_schedule(jurisdiction, shifts)` | calculation (authoritative) | `POST /labor/rules/validate` |
| `compute_usage_anomalies(site_id)` | calculation | usage/recipes/sales → `compute_usage_anomalies` |
| `compute_reorder_needs(site_id)` | calculation | on-hand/par/reorder → `compute_reorder_needs` |
| `publish_schedule(site_id, shifts)` | **gated write** | publish route |
| `submit_purchase_order(...)` | **gated write** | PO route |

`_client()` raises `RuntimeError` when `HSM_ACTIVE_USER` is unset and mints a
fresh token on every call. Exposed to Claude as `mcp__hsm__<tool>`.

## 3. Claude Code Hook Contracts

JSON on stdin, JSON on stdout; output is either a `deny` decision or `{}`.

- `require_no_violations.py` (matcher `mcp__hsm__publish_schedule`):
  re-validates the exact `shifts` with `HSM_JURISDICTION` (default `GA`);
  denies on violations or any exception (line 87).
- `lint_before_commit.py` (matcher `Bash`; acts when the command text
  contains `git commit`): runs
  `ruff check` over what the commit will contain; denies on lint errors or a
  missing `ruff`.

## 4. Internal Python APIs

- **`agents.hsm_client.HsmClient(user_token, base_url=HSM_BASE_URL)`**: about
  35 methods in three groups: reads (`get_sites`, `get_forecast`,
  `get_on_hand`, `get_usage`, `get_employees`, `get_labor_rules`,
  `get_purchase_orders`, `get_published_schedule`, ...), gated writes
  (`publish_schedule`, `submit_purchase_order`), and dashboard data/session
  methods (`start_session`, `end_session`, `session_status`, `list_records`,
  `add_record`, `update_record`, `delete_record`, `bulk_add`, `csv_template`,
  `audit_page`, `retry_write`).
- **`mock_hsm.auth`**: `mint_token(user_id)`, `verify_token(token)`,
  `site_allowed`, `region_allowed`, `TokenError`.
- **`agents` calculations**: `compute_demand`, `compute_usage_anomalies`,
  `compute_reorder_needs` (pure; no I/O).
- **`dashboard.session.client_for(user_id)`**: the single client factory;
  tests monkeypatch it.

## 5. Contracts the Hosting Intent Must Honour

- New files must use the exact paths the `browser-tests` CI job already names
  (`scripts/postdeploy_check.py`, `dashboard/markers.py`,
  `dashboard/auth_gate.py`, `agents/build_info.py`, `tests/*browser*`); see
  `code-quality-assessment.md` CQ-8.
- `GET /healthz` is the natural read-only target for a post-deploy check; it
  never writes and never touches the gated routes.
