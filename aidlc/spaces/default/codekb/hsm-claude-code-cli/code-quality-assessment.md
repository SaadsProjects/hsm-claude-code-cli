# Code Quality Assessment: hsm-claude-code-cli

Commit `825a0f8`, scanned 2026-10-04. This file owns every finding; other
artifacts cite them by `CQ-n`.

## Summary

| Area | Rating | Basis |
|---|---|---|
| Tests | Strong | 837 tests collected; floors 745 tests / 95.00% coverage, ratchet-only |
| Linting and formatting | Strong | ruff check + format in CI as required checks; local commit hook |
| CI/CD | Strong for CI, absent for CD | 10 required jobs, SHA-pinned actions, `permissions: {}`; no deploy workflow |
| Security posture | Good locally, not host-ready | Gated writes, scoped tokens; burned secret still in use; no identity gate |
| Documentation | Good, partly stale for hosting | Docstrings say why; local docs assume no secret and open login |
| Tech debt | Low in general, concentrated on hosting readiness | No TODO/FIXME/HACK markers in project code |

## Test Coverage

- Suite: flat `tests/` (24 files), pytest with `perf` (skipped unless some
  `-m` is given) and `browser` (only when `-m` names it) markers in
  `tests/conftest.py:20-46`.
- Kinds: pure-function unit tests, backend route tests, write-service tests,
  subprocess tests (hooks on fixed port 8773, MCP on fixed port 8772 using
  `server.run()` in a thread), Streamlit `AppTest` screen tests against an
  ephemeral in-process server, CI-script tests via `tests/ci_scripts.py`.
- Coverage: `.coveragerc` measures `agents`, `dashboard`, `mock_hsm`,
  `mcp_server`, `.claude/hooks` with `patch = subprocess`, `parallel = true`.
- Autouse fixtures: `_session_audit_trail` (sets `HSM_AUDIT_PATH`, calls
  `audit.configure()`), `audit_path`, `write_test_reset`.
- No browser test exists yet.

## Linting, CI and Documentation

- ruff rules pinned in `ruff.toml` (E4/E7/E9, F, W, I, B, UP, SIM, RUF, BLE,
  DTZ, EXE, PLW, ASYNC; line length 120).
- CI jobs: `lint`, `workflow-lint`, `secrets`, `audit`, `sast`
  (bandit over `agents dashboard mcp_server mock_hsm .claude/hooks scripts`),
  `lock-check`, `matrix`, `tests (3.10/3.14[/HOSTED_PYTHON])`,
  `coverage-gate`, `browser-tests`.
- Error handling consistent: broad excepts only at boundaries; nine carry a
  reason, two do not (CQ-10).

## Findings

### CQ-1 Signing secret must be loaded at call time (High, hosting blocker)

`mock_hsm/auth.py:24` holds `_SECRET` as a module constant read by
`mint_token` (line 51) and `verify_token` (line 64). Every token-using process
depends on it (see `dependencies.md` § Coupling notes). Because
`tests/conftest.py` imports `mock_hsm.writes` at module top (line 17) and
`writes` imports `auth`, an environment read at import would run before any
fixture could set the variable. **The loader must read the secret when a token
is minted or verified, not at import.** No test fixture sets a secret today;
one will be needed (setting `HSM_SIGNING_SECRET` in `os.environ` early in
`conftest.py` also reaches the subprocess tests, which copy `os.environ`).
Failure behaviour is already sound in two callers: the publish hook denies when
`mint_token` raises (line 87) and MCP surfaces a `_client()` exception as a
tool error. The start script needs its own explicit check (CQ-7). Per
`project.md` Code Style, `auth.py` stays stdlib-only; any Streamlit-secrets
bridge belongs in `dashboard`.

### CQ-2 Burned-literal removal must be one atomic change (High)

`scripts/check_burned_secret.py:29` has
`TEMPORARY_EXCLUSIONS = ("mock_hsm/auth.py",)`, and `scan()` (lines 63-68)
fails as soon as `auth.py` no longer contains the literal. The literal and the
exclusion must leave in the same commit. `tests/test_ci_burned_secret.py` uses
a stand-in value, so it stays valid. The `.gitleaks.toml` allowlist entries
are permanent and stay.

### CQ-3 Persona picker is the only sign-in (High, hosting blocker)

`dashboard/app.py:376-388` (`_login_panel`) lets anyone choose any persona
from `USERS`; `main()` (447-500) has no identity gate before the sidebar.
Today the only control is `.streamlit/config.toml` `address = "127.0.0.1"`.
Hosting requires `st.login` plus the email allowlist in front, with the
picker kept as a selector inside it (`project.md` Deployment).

### CQ-4 In-process backend constraints (High, hosting blocker)

Streamlit Cloud runs one process, so the backend must start inside the app:
- `mock_hsm/server.py:757` `run()` blocks in `serve_forever()`; there is no
  background start function. Tests start servers three different ways.
- The in-process start must call `audit.configure()` as `run()` does and bind
  `127.0.0.1` only (Forbidden rule R-SEC-2).
- `agents/hsm_client.py:22` freezes `HSM_BASE_URL` at import and uses it as the
  constructor default (line 147), which `dashboard/session.client_for` relies
  on. Set the variable before `agents.hsm_client` is first imported, or pass
  `base_url` explicitly.
- Nothing guards against a second instance. `dashboard/app.py` runs `run()` at
  import (line 514) and is re-executed on every interaction, so the
  single-instance guard must live in an imported module (cached in
  `sys.modules`), not in `app.py`.
- A hosted backend on 8770 does not collide with the test ports.

### CQ-5 Data persistence conflicts with team.md (High, needs a decision)

All demo state is in memory (`mock_hsm/db.py` collections such as
`PURCHASE_ORDERS`, `SCHEDULES`, `ON_HAND`; `mock_hsm/writes.py` `_state` with
sessions, meta and counters) and is lost on every restart. The audit trail is
on the app's disk at `HSM_AUDIT_PATH`, default `mock_hsm/audit/audit.jsonl`
inside the checkout (`audit.py:66,142`), so it is also lost on a Streamlit
Cloud redeploy. The intent's "demo-data reset banner" accepts this reset, but
`team.md` § Deployment says data and audit log both survive a redeploy.
**Requirements Analysis must resolve this conflict explicitly** (accept reset
and amend the rule through the gate, or add a persistent store). Reusable
pieces: `writes._started_at` (line 1836) for the banner, and
`actions.ENDED_GENERIC`, which already says "the backend may have restarted".

### CQ-6 Missing dependencies: Authlib and Playwright (Medium)

- `st.login` needs `Authlib` (`streamlit[auth]`); it is in neither lockfile.
  Add to `requirements.in` and recompile both locks or `lock-check` fails.
- `playwright` is not in `requirements-dev.in`, and `browser-tests`
  (`ci.yml:255-259`) has no `playwright install --with-deps chromium` step;
  it currently tolerates pytest exit 5 ("no tests ran").
- Both packages enter the `pip-audit` gate.

### CQ-7 Local start paths have no secret step (Medium)

`scripts/start_mock_server.sh` (6 lines) runs `python3 -m mock_hsm.server`;
`.mcp.json` passes only `HSM_BASE_URL`. After CQ-1 both need a secret source
and the start script needs an explicit missing-secret check. The earlier
intent planned `scripts/dev-secret.sh` and `.env.local`; neither exists yet.

### CQ-8 CI path expectations for new files (Medium)

`browser-tests` (`ci.yml:241`) only runs when a changed file matches
`scripts/postdeploy_check.py`, `dashboard/markers.py`,
`dashboard/auth_gate.py`, `agents/build_info.py` or `tests/*browser*`. New
files must use exactly these paths, or the required check silently no-ops.

### CQ-9 .gitignore gaps for secret files (Medium)

`.env.local` is ignored only through `*.local` inside the AI-DLC-managed block
(`.gitignore:30`), which `aidlc config --force` can rewrite.
`.streamlit/secrets.toml` is not ignored at all. Add explicit lines outside
the AI-DLC block.

### CQ-10 Two `noqa: BLE001` without a reason (Low)

`.claude/hooks/lint_before_commit.py:372` and
`.claude/hooks/require_no_violations.py:87` lack the `-- <reason>` text the
team Code Style rule requires.

### CQ-11 Stale local docs (Low, same change as CQ-1/CQ-3)

`dashboard/README.md` § Reach ("There is no password: anyone who can open the
page can log in as any persona") and the start command
`python3 -m mock_hsm.server &` in `CLAUDE.md` § Commands,
`dashboard/README.md` and `README.md` § Quick start assume no secret and an
open login. Update them in the same change.

### CQ-12 Test baseline and floors (Constraint)

837 tests collected at `825a0f8` (team baseline 757 predates the CI gate
tests). `.test-floor` 745 and `.coverage-floor` 95.00 must not drop, and every
new module under `dashboard/`, `agents/` or `mock_hsm/` counts toward the 95%
floor. Fixed ports 8772/8773 keep the suite serial (accepted by the team).

### Other observations

- `mock_hsm/writes.py` (1,870 lines) and `mock_hsm/audit.py` (740) are large
  but cohesive and documented; the intent only reads them.
- The `hsm` MCP server's dependency is dev-only; fine, since the hosted app
  does not run it.
- The local hook gates exist only in clones that copied
  `.claude/settings.local.json`; CI is the authoritative gate.
