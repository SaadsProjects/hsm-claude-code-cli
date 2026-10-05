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
pip install --require-hashes -r requirements-dev.txt   # Python 3.10+; dev/test lock (requirements.txt is the hosted-app runtime lock)
scripts/dev-secret.sh                    # once per clone: writes HSM_SIGNING_SECRET to .env.local (git-ignored, mode 600)
python3 -m mock_hsm.server &             # mock backend on 127.0.0.1:8770 (or scripts/start_mock_server.sh [--port N])
python3 -m pytest tests/ -q              # all tests; they start their own mock servers (:8772, :8773, one ephemeral)
python3 -m pytest tests/ -q -m perf      # the timing tests, which are skipped by default
python3 -m pytest tests/ -q -m browser   # Playwright tests, skipped by default (need Chromium)
python3 -m pytest tests/test_labor_rules.py -k overnight  # a single test
ruff check .                             # lint (same check the commit hook runs; rules pinned in ruff.toml)
ruff format --check .                    # formatting, checked in CI
coverage run -m pytest tests/ -q && coverage combine -q && coverage report   # coverage (.coveragerc; subprocesses measured)
python3 mcp_server/hsm_tools.py          # run the MCP server standalone over stdio
mcp dev mcp_server/hsm_tools.py          # MCP Inspector (needs the mcp[cli] extra)
streamlit run dashboard/app.py           # dashboard with login and data writes (needs the mock backend and the secret exported, see below)
```

**Signing secret.** Tokens are signed with `HSM_SIGNING_SECRET` (at least 32
bytes). There is no default anywhere: without it the backend and the start
script refuse to start, the publish hook denies, MCP tools return an error
naming the variable, and a running backend answers 503. Run
`scripts/dev-secret.sh` once to write it to `.env.local` (`--force` replaces
it). The backend, the start script, the publish hook and the MCP server read
`.env.local` themselves when the variable isn't exported, so the `claude`
shell needs nothing extra; an exported value always wins. The local dashboard
doesn't read the file yet, so export it in that shell first:
`export HSM_SIGNING_SECRET="$(sed -n 's/^HSM_SIGNING_SECRET=//p' .env.local)"`.
Tests generate their own secret per run (`tests/conftest.py`); CI holds none.

Test layout:
- `test_labor_rules.py` and `test_calculations.py` call the validator handler
  and the pure calculation functions directly.
- `test_hooks.py` and `test_lint_hook.py` pipe JSON into the hook scripts the
  way Claude Code does. The hung-backend case takes ~5s by design, and the
  lint-hook tests build throwaway git repos in `tmp_path`.
- `test_mcp_tools.py` is one sequential MCP-protocol scenario (`_run()`) in a
  single pytest test, so the first failed assertion stops it; it can also be
  run directly. Adding a new MCP tool means adding its name to its
  `expected` set.

If the `hsm` MCP server fails to connect, check that `mcp` is installed for
the `python3` on PATH. If `ruff` isn't installed, the lint hook blocks
every commit — install it rather than working around the hook. Because
commit detection deliberately over-matches, it also blocks any Bash command
whose text merely contains `git commit` (e.g. inside a heredoc) while ruff
is missing or lint is dirty; use Edit/Write for such file edits.

## Running the workflows

The mock backend must be running, `.env.local` must hold the signing secret
(`scripts/dev-secret.sh`, see Commands), and `HSM_ACTIVE_USER` must be exported
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
  fetch data through `HsmClient` and call these; never import `mock_hsm.db`
  from the tool layer, or it breaks when `HSM_BASE_URL` points elsewhere.
  New calculations belong in `agents/`, not inline in a tool.
- **Dates are site-local and come from the backend.** Each site in
  `mock_hsm/db.py` has a `timezone`; forecast and sales rows carry a real
  `date`, and `compute_demand` labels days from those rows. Don't derive
  dates from the host clock in the tool layer.
- **Rule validation** happens server-side in the mock's
  `/labor/rules/validate` route (`labor_rules_validate` in
  `mock_hsm/server.py`). Times must be strict `HH:MM` wall-clock (anything
  else is a 400). An end at or before the start means the shift runs past
  midnight. Same-day split shifts are allowed, but their combined hours are
  capped (`max_daily_hours`) and shifts can't overlap.
  `daily_ot_threshold_hours` is a cost input, not a violation.
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

The project's two hooks (`require_no_violations.py` and
`lint_before_commit.py`) are registered in `.claude/settings.local.json`, not
`settings.json`. That file is gitignored, so a fresh clone has neither gate
until you copy `.claude/settings.local.json.example` to
`.claude/settings.local.json` (it carries both hooks and enables the `hsm`
MCP server), then restart Claude Code. `settings.json` holds AI-DLC's hook wiring;
`aidlc doctor` fails if any other hook is registered in it. `aidlc config
--force` rewrites `settings.json`, so it would also drop the `ask` rules above;
re-add them afterwards.

The Streamlit dashboard (`dashboard/app.py`, loaders in `dashboard/data.py`)
goes through `HsmClient` like the MCP tools and reuses the `agents/`
calculation functions. Its Overview, Labor and Inventory tabs are read-only;
their only POST is the side-effect-free `/labor/rules/validate`. Published
schedules and POs are read through the GET routes
`/labor/sites/{site_id}/schedules` and `/inventory/purchase-orders`, which the
server filters to the persona's scope.

After a login (`POST /sessions`), the dashboard can also write. Its "Manage
data" tab adds, edits, deletes and bulk-uploads (CSV) 11 kinds of record
through the per-kind routes in `mock_hsm/writes.py`. Its "Audit" tab pages
through `GET /audit`. The modules are `dashboard/actions.py`, `session.py`,
`manage_tab.py`, `audit_tab.py`, `kind_forms.py`, `csv_rows.py` and
`safe_text.py`; `dashboard/README.md` covers them. The dashboard never
publishes a schedule or submits a PO, and a test enforces that.

Every data write, and every publish or PO attempt, is appended to an audit
trail (`mock_hsm/audit.py`, file from `HSM_AUDIT_PATH`, default
`mock_hsm/audit/audit.jsonl`, gitignored). If the trail is unavailable, the
publish and PO routes return 503 "audit unavailable", which reaches the MCP
tools as an error. Tests point the trail at a temp file through `tests/conftest.py`.

A new gated write tool needs an `ask` rule in `settings.json`, in the same
way as the existing two. A new project hook goes in `settings.local.json`.

Mock backend state (`mock_hsm/db.py`) is in-memory: published schedules and
POs reset when the server restarts. Forecast/usage data comes from seeded
RNG, but rows are dated from the site's current date and the Fri/Sat bump
follows the real weekday, so forecast, sales and reorder numbers shift from
day to day. Usage variance doesn't depend on the weekday bump. Some
anomalies are planted on purpose (e.g. the `rm_ground_beef` drift at
site_001, which the test asserts on).

## Committing changes to this project

Don't run `git commit` directly — go through `/commit`, which runs the
`code-reviewer` subagent (no Edit/Write tools) on the staged diff first. The
`lint_before_commit.py` hook separately blocks the commit if ruff fails on
what the commit will contain: the staged index (exported to a temp dir),
plus tracked working-tree files for `commit -a`/`-i`/`-o` or pathspecs, plus
untracked non-ignored files when the same Bash command also runs a git
subcommand that can stage (`git add . && git commit ...`). So re-stage
after fixing lint errors. It runs before the whole command, so files
edited or staged by a non-git command earlier in it (`sed -i`, a script,
`make`) aren't seen. It always checks this project's repo and default index, so `git -C`,
`cd elsewhere &&` or `GIT_INDEX_FILE` commits aren't linted against what
they actually commit.
If the reviewer finds something, decide whether to address it before
committing rather than routing around it.

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request into `main`. Every job
except `matrix` is meant to be a required check:
- **Lint:** `lint`, which runs ruff check and ruff format, and `workflow-lint`,
  which runs actionlint and `scripts/check_workflows.py`.
- **Secrets:** `secrets` runs gitleaks over full history and
  `scripts/check_burned_secret.py`.
- **Dependencies:** `audit` runs pip-audit with `scripts/filter_audit.py`, failing
  on high or critical findings. `lock-check` verifies the lockfiles match
  their inputs.
- **Static analysis:** `sast` runs bandit with `scripts/filter_bandit.py`, failing
  on high severity.
- **Tests:** `tests (3.10)` and `tests (3.14)` (plus `vars.HOSTED_PYTHON` when it
  is set) run with one retry and the `.test-floor` check. `coverage-gate`
  checks coverage against `.coverage-floor` and the 80% gate.
- **Browser tests:** `browser-tests` always reports, so it can be required, and
  passes without running anything unless a browser-check file changed.

The CI gate scripts live in `scripts/`. Their tests are `tests/test_ci_*.py`,
loaded through `tests/ci_scripts.py`.

**Floors and exceptions:**
- `.test-floor` and `.coverage-floor` may only rise. A PR that lowers either
  one fails.
- Findings that cannot be fixed go in `security-exceptions.toml`. Each entry
  needs a reason and an expiry date at most 90 days out. This is the only
  waiver: CI runs bandit with `--ignore-nosec`, so inline `# nosec` comments
  have no effect.

**Dependencies:**
- Edit `requirements.in` (hosted-app runtime) or `requirements-dev.in`, never
  the compiled `.txt` files.
- Recompile with the `uv pip compile` command at the top of each `.in` file.

**Burned secret:** the old mock signing secret, once hard-coded in
`mock_hsm/auth.py`, is burned and has been removed. `scripts/check_burned_secret.py`
fails on it in any tracked file outside `.gitleaks.toml` and the AI-DLC record
tree, and `TEMPORARY_EXCLUSIONS` is empty. `mock_hsm/auth.py` keeps only its
SHA-256 and refuses it as `HSM_SIGNING_SECRET`.
