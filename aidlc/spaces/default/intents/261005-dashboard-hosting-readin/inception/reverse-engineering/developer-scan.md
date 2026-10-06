# Developer Code Scan: hsm-claude-code-cli

Scan date: 2026-10-04. Commit: `825a0f8` (main). Breadth: the whole repo (`./`). Depth: Standard.
Weighted toward the code the intent changes: `dashboard-hosting-readin`.

## Developer Code Scan Results

### Scan Coverage
- **Analyzed deeply**:
  - `mock_hsm/auth.py`
  - `mock_hsm/server.py`
  - `mock_hsm/db.py` (structure, seed data, clocks, lock)
  - `mock_hsm/audit.py` (module contract, configure, path resolution)
  - `mock_hsm/writes.py` (module contract, constants, sessions, `reset_for_tests`, `_started_at`)
  - `dashboard/app.py`
  - `dashboard/session.py`
  - `dashboard/actions.py` (module contract, function inventory)
  - `dashboard/data.py`
  - `agents/hsm_client.py` (errors, base URL, method inventory)
  - `agents/labor_scheduling_agent.py`, `agents/inventory_agent.py` (shape, constants)
  - `mcp_server/hsm_tools.py`
  - `.claude/hooks/require_no_violations.py`
  - `.claude/hooks/lint_before_commit.py` (contract and entry point)
  - `.claude/agents/labor-scheduler.md`, `.claude/agents/inventory-analyst.md`, `.claude/agents/code-reviewer.md`
  - `.claude/commands/commit.md`
  - `.claude/settings.json` (permissions only), `.claude/settings.local.json.example`
  - `scripts/check_burned_secret.py`, `scripts/start_mock_server.sh`, `scripts/run_pip_audit.sh`, `scripts/coverage_gate.py` (interface)
  - `.github/workflows/ci.yml`
  - `tests/conftest.py`, `tests/test_ci_burned_secret.py`, `tests/test_hooks.py` (fixtures), `tests/test_mcp_tools.py` (setup), `tests/test_dashboard_app.py` (fixtures, test inventory)
  - `requirements.in`, `requirements-dev.in`, `requirements.txt`, `requirements-dev.txt` (package lists)
  - `ruff.toml`, `.coveragerc`, `.streamlit/config.toml`, `.gitleaks.toml`, `security-exceptions.toml`, `.mcp.json`, `.gitignore`, `.test-floor`, `.coverage-floor`
  - `dashboard/README.md` (Start it, Reach, Log in)
- **Skimmed only**:
  - `dashboard/audit_tab.py`, `dashboard/manage_tab.py`, `dashboard/kind_forms.py`, `dashboard/csv_rows.py`, `dashboard/safe_text.py` (by name and the app's use of them)
  - `mock_hsm/writes.py` validator, kind catalogue and bulk internals (lines 224 to 1730)
  - `scripts/check_exceptions.py`, `check_workflows.py`, `filter_audit.py`, `filter_bandit.py`, `floor_ratchet.py`, `job_summary.py`, `test_floor.py`
  - `tests/` other than the files listed above (counted, not read)
  - `README.md`, `docs/ARCHITECTURE.md`, `CLAUDE_CODE_CLI_PLAN.md`, `architecture-diagram.html` (headings only)
  - `.github/dependabot.yml`
- **Excluded as AI-DLC tooling** (noted, not analyzed): `aidlc/` (records, memory, codekb), `.claude/aidlc-common/`, `.claude/tools/`, `.claude/skills/aidlc*`, `.claude/agents/aidlc-*`, `.claude/knowledge/`, `.claude/sensors/`, `.claude/scopes/`, `.claude/rules/`, `.claude/hooks/*.ts`, `.claude/CLAUDE.md`. One exception: I grepped the earlier intent `261004-dashboard-deploy-pipelin` for the planned file names (`scripts/dev-secret.sh`, `.env.local`, `agents/build_info.py`) so this scan could check them against the tree.

### Packages Found
- `agents` (Python package, plain directory with `__init__.py`). Library code. It holds the stdlib-only REST client `HsmClient` and the pure calculation functions `compute_demand`, `compute_usage_anomalies` and `compute_reorder_needs`.
- `mock_hsm` (Python package). Service code: the mock HSM backend.
  - `server.py`: an `http.server` `ThreadingHTTPServer` with a regex route table.
  - `auth.py`: HMAC token mint and verify.
  - `db.py`: in-memory seed data and seeded-RNG generators.
  - `writes.py`: sessions and data writes for 11 kinds of record.
  - `audit.py`: a durable JSONL audit trail.
- `dashboard` (Python package). UI code: the Streamlit app. `app.py` is the entry script and runs `run()` at import. The other modules are `session`, `actions`, `data`, `manage_tab`, `audit_tab`, `kind_forms`, `csv_rows` and `safe_text`.
- `mcp_server` (a directory with no `__init__.py`). Service code: one FastMCP stdio server, `hsm_tools.py`, with 11 tools.
- `.claude/hooks` (Python scripts). Tooling: two PreToolUse hooks, run as subprocesses.
- `scripts` (Python and sh). CI gate scripts and one dev start script. Tests load them by file path through `tests/ci_scripts.py`.
- `tests` (pytest). The test suite: 837 tests are collected today. The team baseline of 757 dates from before the CI gate tests.

### Build System
- **Type**: pip with hash-pinned lockfiles compiled by `uv pip compile` (`--universal --generate-hashes --python-version 3.10`). There is no `pyproject.toml` and no packaging. Code is imported through `sys.path.insert(0, <repo root>)` in `dashboard/app.py:21`, `mcp_server/hsm_tools.py:22`, `.claude/hooks/require_no_violations.py:31` and `tests/conftest.py:15`.
- **Config Files**: `requirements.in` → `requirements.txt` (runtime; Streamlit Cloud installs this one). `requirements-dev.in` (`-r requirements.in`) → `requirements-dev.txt`. Also `ruff.toml`, `.coveragerc`, `.streamlit/config.toml` and `.mcp.json`.
- **Build Dependencies**:
  - `dashboard` → `agents.hsm_client`, `agents.*_agent`, `mock_hsm.auth.mint_token`, `mock_hsm.db.USERS`.
  - `mcp_server` → `agents.*`, `mock_hsm.auth.mint_token`.
  - `.claude/hooks/require_no_violations.py` → `agents.hsm_client`, `mock_hsm.auth`.
  - `mock_hsm.server` → `mock_hsm.{audit, db, writes, auth}`.
  - `mock_hsm.writes` → `mock_hsm.{audit, db, auth.site_allowed}`.
  - `mock_hsm.auth` → `mock_hsm.db`.
  - There are no cycles.

### APIs Discovered
- **REST (JSON over HTTP)**: `mock_hsm/server.py`.
  - 29 `@route` handlers are written out: admin, catalog, sales, forecast, transaction-data, inventory, labor, the rules validator, schedule publish and read, PO submit and list, audit, sessions (start, logout, status) and `/healthz`.
  - `_register_write_routes()` adds 5 generated routes for each of the 11 kinds (template, bulk, add, update, delete), so 55 more.
  - Every route except `GET /healthz` (`_PUBLIC_ROUTES`, line 655) needs `Authorization: Bearer <token>`. The token is checked by `verify_token`; a bad one gets a 401. Site and region scope is enforced in each route.
  - Bodies over 1 MiB are refused with a 400, and bodies over 8 MiB also close the connection.
  - `run(host="127.0.0.1", port=8770)` calls `audit.configure()` and then `serve_forever()`, which blocks. No function starts the server in the background.
- **MCP (stdio)**: `mcp_server/hsm_tools.py`.
  - 11 tools: 5 reads, 4 deterministic calculations (`validate_schedule` among them) and 2 gated writes (`publish_schedule`, `submit_purchase_order`).
  - `_client()` raises `RuntimeError` when `HSM_ACTIVE_USER` is missing and mints a token on every call.
- **Claude Code hooks**: JSON on stdin and stdout. `require_no_violations.py` denies on any exception (`except Exception`, line 87). If the secret loader raises inside `mint_token`, the hook therefore already denies.
- **Internal Python API**:
  - `HsmClient` has about 35 methods.
  - `mock_hsm.auth` provides `mint_token`, `verify_token`, `site_allowed`, `region_allowed` and `TokenError`.
  - `dashboard.session.client_for(user_id)` is the single client factory. Tests monkeypatch it.

### Frameworks & Libraries
- Python 3.10 floor (`ruff.toml` `target-version = "py310"`). Development and the CI gate run on 3.14.7.
- `streamlit` 1.64.0: the UI. It brings `pandas` (2.3.3 or 3.0.6 by marker), `altair` 6.x, `pyarrow` 25 and `tornado`. **`Authlib` is not in either lockfile.** `st.login` needs it (the `streamlit[auth]` extra), so the sign-in gate needs a `requirements.in` change and a lock recompile.
- `mcp[cli]` 1.30.0 (dev only): FastMCP, pinned to 1.x. **The MCP server's runtime dependency is in `requirements-dev.txt` only**. That is fine for hosting, because the hosted app does not run the MCP server.
- Test and gate tooling: `pytest` 9.1.1, `pytest-rerunfailures` 16.7, `coverage` 7.16.2, `ruff` 0.16.8, `bandit` 1.9.4, `pip-audit` 2.10.1, `cvss`, `tomli` (Python below 3.11).
- **`playwright` is not in `requirements-dev.in`.** The `browser-tests` CI job and the browser marker are already wired up, but nothing installs Playwright or Chromium yet (ci.yml:255-259).
- Stdlib-only backend and client: `http.server`, `urllib`, `hmac`, `hashlib`, `threading`, `zoneinfo`.

### Test Coverage
- **Test Directories**: `tests/`, a flat directory of 24 files, with CI-script tests loaded through `tests/ci_scripts.py`.
- **Test Frameworks**:
  - pytest, with the custom markers `perf` (skipped unless some `-m` is given) and `browser` (runs only when `-m` names `browser`). Both are defined in `tests/conftest.py:20-46`.
  - Streamlit `AppTest` drives the screen tests in `tests/test_dashboard_app.py`, against an in-process `ThreadingHTTPServer` on an ephemeral port.
  - Subprocess tests run the hook (`test_hooks.py`, fixed port 8773) and the MCP server (`test_mcp_tools.py`, fixed port 8772, which uses `server.run()` in a thread).
  - There is no `tests/*browser*` file yet.
- **Coverage Config**: present. `.coveragerc` measures `agents`, `dashboard`, `mock_hsm`, `mcp_server` and `.claude/hooks`, with `patch = subprocess` and `parallel = true`. `.coverage-floor` is 95.00 and `.test-floor` is 745. Both floors only rise (`scripts/floor_ratchet.py`).
- `tests/conftest.py` fixtures, all autouse:
  - `_session_audit_trail` (session scope): sets `HSM_AUDIT_PATH` and calls `audit.configure()`.
  - `audit_path`: a per-test audit file.
  - `write_test_reset`: calls `writes.reset_for_tests()`.
  - **No fixture sets a signing secret.** Today none is needed, because the secret is a module constant.

### Code Quality Indicators
- **Linting**: ruff, configured in `ruff.toml` (E4/E7/E9, F, W, I, B, UP, SIM, RUF, BLE, DTZ, EXE, PLW, ASYNC; line length 120). `ruff format --check` runs in CI. The local hook `.claude/hooks/lint_before_commit.py` is wired only in `settings.local.json`.
- **CI/CD**: `.github/workflows/ci.yml`.
  - Jobs: `lint`, `workflow-lint` (actionlint plus `check_workflows.py`), `secrets` (gitleaks over full history plus `check_burned_secret.py`), `audit` (pip-audit plus `filter_audit.py`), `sast` (bandit `--ignore-nosec` over `agents dashboard mcp_server mock_hsm .claude/hooks scripts`), `lock-check`, `matrix`, `tests (3.10/3.14[/HOSTED_PYTHON])`, `coverage-gate` and `browser-tests`.
  - Actions are pinned by SHA, and `permissions: {}` is set at the top level.
  - `.github/dependabot.yml` is present.
  - There is no deploy workflow yet.
- **Documentation**: good overall.
  - Module docstrings explain why, as the team style asks.
  - `README.md`, `dashboard/README.md`, `docs/ARCHITECTURE.md` and `CLAUDE.md` are current for local use.
  - `dashboard/README.md` § Reach still says "There is no password: anyone who can open the page can log in as any persona". That changes with this intent.
  - `CLAUDE.md` and `dashboard/README.md` give `python3 -m mock_hsm.server &` as the start command, and that command has no secret step.
- **Error handling**: consistent. Broad excepts sit only at boundaries. Nine of them carry `# noqa: BLE001 -- <reason>`, and two have no reason text (`lint_before_commit.py:372`, `require_no_violations.py:87`), contrary to the team Code Style rule.

### Technical Debt Signals
- **Hard-coded signing secret.** `mock_hsm/auth.py:24`: `_SECRET = b"<burned literal>"` is read at module level, and `mint_token` (line 51) and `verify_token` (line 64) both use it. `scripts/check_burned_secret.py:29` holds `TEMPORARY_EXCLUSIONS = ("mock_hsm/auth.py",)`, and `scan()` (lines 63-68) fails as soon as `auth.py` no longer contains the value. The literal and the exclusion therefore have to leave in the same commit. The allowlist entries in `.gitleaks.toml` are permanent and stay.
- **Base URL frozen at import.** `agents/hsm_client.py:22` sets `HSM_BASE_URL = os.environ.get(...)` at import time, and it is the default argument of `HsmClient.__init__` (line 147). `dashboard/session.client_for` relies on that default. An in-process backend on any port other than 8770 must set the environment variable before `agents.hsm_client` is first imported, or pass `base_url` explicitly.
- **No in-process start function.** `mock_hsm/server.py:757` `run()` blocks in `serve_forever()` and is the only way to start the backend. The tests start servers themselves, in three different ways (`ThreadingHTTPServer(... , 0)` in two files, and `run()` in a thread in `test_mcp_tools.py`). Nothing guards against a second instance. Streamlit re-runs `dashboard/app.py` on every interaction (`run()` at line 514), so a guard placed in `app.py` would run on every rerun. It belongs in an imported module, which is cached in `sys.modules`.
- **Persona picker is the only sign-in.** `dashboard/app.py:376-388` (`_login_panel`) lets anyone pick any persona from `mock_hsm.db.USERS`. `main()` (lines 447-500) has no identity gate before the sidebar. `.streamlit/config.toml` binds to `127.0.0.1`, which is the only control today.
- **Demo state is in memory.** `mock_hsm/db.py` (`PURCHASE_ORDERS`, `SCHEDULES`, `ON_HAND` and the other collections) and the `mock_hsm/writes.py` `_state` (sessions, meta and counters) are lost on every restart. The data has no persistence layer.
  - `writes._started_at` (line 1836) is a process-start timestamp already in memory, which a reset banner could reuse.
  - `actions.ENDED_GENERIC` already says "the backend may have restarted".
- **Audit trail on the app's disk.** It goes to `HSM_AUDIT_PATH`, defaulting to `mock_hsm/audit/audit.jsonl` inside the checkout (`audit.py:66,142`).
- **Secret files and the ignore list.** `.env.local` is ignored only because of `*.local` inside the AI-DLC-managed `.gitignore` block (`.gitignore:30`). `.streamlit/secrets.toml` is not ignored at all.
- **Local start paths have no secret step.** `scripts/start_mock_server.sh` (6 lines) runs `python3 -m mock_hsm.server`, and `.mcp.json` passes only `HSM_BASE_URL`.
- **Fixed test ports.** 8772 and 8773 make the suite unsafe for `pytest-xdist`, which the team has already accepted. A hosted in-process backend on 8770 does not collide with them.
- **Two `noqa: BLE001` without a reason** (listed under Code Quality Indicators).
- **Large modules.** `mock_hsm/writes.py` is 1,870 lines and `mock_hsm/audit.py` is 740. Both are cohesive, with documented components, and neither is touched by this intent beyond reads.
- There are no TODO, FIXME or HACK markers in project code.

## Handoff Summary
- **Intent-relevant finding**:
  - The signing secret is a single module constant, `mock_hsm/auth.py:24`. Every process that mints or verifies a token reads it:
    - the dashboard: `session.client_for` (`dashboard/session.py:51-54`) and `app.py`'s import of `USERS`;
    - the MCP server: `_client` (`mcp_server/hsm_tools.py:45-52`);
    - the publish hook (`.claude/hooks/require_no_violations.py:70`);
    - the backend: `verify_token` (`mock_hsm/server.py:718`);
    - about 10 test modules that call `mint_token` in-process, plus the hook and MCP subprocess tests.
  - The tests copy `os.environ` into their subprocesses (`test_hooks.py` `_run_hook`, `test_mcp_tools.py:53`). If `conftest.py` sets `HSM_SIGNING_SECRET` in `os.environ` early enough, it reaches every subprocess.
  - `conftest.py` imports `mock_hsm.writes` at module top (line 17), and `writes` imports `auth`. **The loader therefore has to read the secret when a token is minted or verified, not at import.** An import-time read would fail before any fixture can set the variable.
  - The hook already denies when `mint_token` raises (line 87). The MCP tool surfaces an exception from `_client()` as a tool error. The start script needs its own explicit check.
  - The CI `browser-tests` job (ci.yml:241) already names `scripts/postdeploy_check.py`, `dashboard/markers.py`, `dashboard/auth_gate.py`, `agents/build_info.py` and `tests/*browser*`. New files must use exactly those paths, or that required check silently no-ops.
- **Risks / follow-up**:
  1. **Missing dependencies.**
     - `st.login` needs `Authlib` (`streamlit[auth]`). It must be added to `requirements.in` and both lockfiles recompiled, or `lock-check` fails.
     - Playwright must be added to `requirements-dev.in`, and the `browser-tests` job needs a `playwright install --with-deps chromium` step.
     - Both new packages enter the `pip-audit` gate.
  2. **Burned-literal removal has to be one atomic change.** It covers `auth.py` and the `TEMPORARY_EXCLUSIONS` entry together. `tests/test_ci_burned_secret.py` tests the mechanism with a stand-in value, so those tests stay valid.
  3. **In-process backend.** It must call `audit.configure()` the way `run()` does, bind `127.0.0.1` only (team Forbidden rule R-SEC-2), and set `HSM_BASE_URL` before `agents.hsm_client` is imported, or the client must take an explicit `base_url`. The single-instance guard must live outside `dashboard/app.py`.
  4. **Gitignore entries.** Add explicit `.env.local` and `.streamlit/secrets.toml` lines outside the AI-DLC block, because `aidlc config --force` can rewrite that block.
  5. **Persistence conflict for the architect.** Data and the audit trail stay in memory or on the app's disk, so they reset on redeploy. The intent's "demo-data reset banner" accepts that reset. The `team.md` Deployment rule says both survive a redeploy, so requirements need to resolve that conflict explicitly.
  6. **Stale local docs.** `dashboard/README.md` § Reach, `CLAUDE.md` § Commands and `README.md` § Quick start all say the backend starts without a secret, so they need updating in the same change.
  7. **Test baseline.** 837 tests are collected at `825a0f8`. The test floor of 745 and the coverage floor of 95.00 must not drop, and every new module in `dashboard/`, `agents/` or `mock_hsm/` counts toward the 95% coverage floor.
