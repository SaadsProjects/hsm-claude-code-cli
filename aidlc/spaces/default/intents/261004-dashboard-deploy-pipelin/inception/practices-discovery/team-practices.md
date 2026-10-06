# Team Practices

## Way of Working

We work trunk-based on one trunk, `main`, hosted on GitHub
(`SaadsProjects/hsm-claude-code-cli`). Every change reaches `main` through a
short-lived branch and a pull request. `main` is protected: the CI checks are
required status checks, and nothing merges until they pass. We squash-merge,
so each branch (and each Construction Bolt) becomes one commit on `main`.
Direct pushes to `main` are no longer part of how we work.

Every local commit still goes through `/commit`. The `code-reviewer` subagent
reviews the staged diff, then the `lint_before_commit.py` hook blocks the
commit if `ruff check` fails on what the commit will contain. The local gate is
the fast first check. CI on the pull request is the authoritative gate, because
the local hook only exists in clones that copied `settings.local.json`.

Commit messages are a single imperative summary line ("Add …", "Restore …").

We keep a single trunk even with two environments. The production branch that
Streamlit Community Cloud tracks is a deployment pointer, not a work branch.
Nobody commits to it directly. It only ever moves to a commit that has already
passed CI on `main` (see Deployment).

## Walking Skeleton

We build a thin end-to-end slice first, before any later pipeline unit. The
slice runs: a commit merged to `main` → lint and the test suite in CI → an
automatic deploy to the staging app on Streamlit Community Cloud → a read-only
health check against staging that passes.

The slice must also prove two security properties, not just that the pieces
connect:

- the CI security checks (secret scan, dependency audit and bandit) actually
  run on the change as required checks, and
- the sign-in layer in front of staging turns away a visitor who is not on the
  viewer allowlist.

The health check is read-only. It never writes data and never calls
`publish_schedule` or `submit_purchase_order`. The skeleton is done when the
human has seen this slice work end to end and approved the skeleton
checkpoint.

## Testing Posture

- **Methodology**: tdd
- **Ordering**: For each behaviour, write a failing test first, then write only the code that makes it pass, then refactor with the suite green.
- Tests ship in the same commit as the code they cover.
- Coverage floor: 80% line coverage, measured over `agents/`, `dashboard/`,
  `mock_hsm/`, `mcp_server/` and `.claude/hooks/`, with `tests/` excluded.
  Code that only runs in subprocesses (the MCP server over stdio and the hook
  scripts) is measured with coverage's subprocess support switched on, so it
  is counted correctly rather than left out. We measure the baseline first,
  then switch the gate on. The floor and the measured package set are never
  lowered or narrowed to get a run to pass.
- CI runs the suite on a Python matrix of 3.10 (the declared floor) and 3.14
  (the version we develop on). Both must pass before merge.
- CI runs the suite with plain `python -m pytest tests/`. It never passes an
  unrelated `-m` expression, because any `-m` switches off the default `perf`
  skip in `tests/conftest.py`.
- The `perf`-marked timing tests never run in CI. They run by hand with
  `-m perf` when someone wants them.
- A flaky test may be retried once in CI. A test that fails on the retry
  blocks the merge.
- The suite runs serially. The fixed ports 8772 and 8773 in
  `test_mcp_tools.py` and `test_hooks.py` make `pytest-xdist` (`-n`) unsafe, so
  we do not parallelise until those ports are made ephemeral.
- Measured baseline (2026-10-04, commit `1586133`, Python 3.14.7): 757 tests
  collected, 745 passed, 12 `perf` skipped, 86.7 s. The existing suite stays
  green against this baseline.
- Every test's audit trail goes to a temp file through `HSM_AUDIT_PATH`
  (`tests/conftest.py`). CI does not export `HSM_BASE_URL`,
  `HSM_ACTIVE_USER` or `HSM_AUDIT_PATH`.
- New pipeline helper scripts (such as the health-check script) get their own
  tests: the happy path plus at least two error cases.

## Deployment

- **Host**: Streamlit Community Cloud. The mock backend runs in the same
  process as the dashboard (Streamlit Cloud runs a single process), bound to
  loopback only. The backend is never reachable from outside the app.
- **Who can reach it**: the internet, but only behind a sign-in layer. Both
  apps are private Streamlit Cloud apps with a viewer allowlist. The
  in-app persona picker stays as a selector *inside* that layer, not as the
  sign-in itself.
- **Environments**: two Streamlit Cloud apps that track two branches.
  - Staging tracks `main` and redeploys automatically on every merge.
  - Production tracks a separate production branch. Promotion is the gated
    step: a manual approval moves the production branch to a commit that
    already passed CI and the staging health check on `main`.
- **Signing secret**: the token-signing secret comes from the environment,
  which is Streamlit secrets when hosted. Outside local development the app
  refuses to start when the secret is missing (fail closed). The hard-coded
  demo secret is never used for a hosted deploy.
- **Data and audit log**: both survive a redeploy. Because the backend keeps
  its data in memory today, this needs a persistent datastore for the data and
  the audit trail. Requirements Analysis sizes that change.
- **Before any deploy**, CI runs and must pass: `ruff check` and
  `ruff format --check`, the test suite with the coverage floor, secret
  scanning (gitleaks, plus GitHub push protection), a dependency audit
  (`pip-audit` against the hash-pinned lockfile), and static security analysis
  (bandit as its own CI job). Any container image CI builds is scanned with
  Trivy.
- **Pipeline hygiene**: third-party GitHub Actions are pinned by full commit
  SHA, workflows get least-privilege `permissions`, and any cloud credential
  CI needs comes from short-lived OIDC, never from long-lived keys stored as
  repository secrets.
- **Smoke checks**: after every deploy, a read-only health check runs against
  the environment. A deploy is not done until that check passes. Smoke checks
  never write data and never call `publish_schedule` or
  `submit_purchase_order`.
- **Rollback**: revert on `main` (staging) or move the production branch back
  to the previous good commit, and let Streamlit Cloud redeploy it. Then
  re-run the health check.

## Code Style

- Python 3.10+ (`ruff.toml` `target-version = "py310"`), stdlib first. The
  mock server and client use only `http.server` and `urllib`.
- Naming: snake_case for modules, functions and variables; UPPER_SNAKE for
  module-level constants; a leading underscore for private helpers; error
  classes end in `Error` or name the condition (`HsmApiError`,
  `SessionExpired`). Comments and docstrings say why, not what.
- **Linter**: ruff, with its rules pinned in `ruff.toml` (line length 120;
  E4/E7/E9, F, W, I, B, UP, SIM, RUF, BLE, DTZ, EXE, PLW, ASYNC). `ruff check`
  runs in the local commit hook and as a required CI check.
- **Formatter**: `ruff format`, checked in CI with `ruff format --check`. We
  introduce it in a formatting-only commit, kept apart from feature or
  pipeline changes.
- A broad `except Exception` is allowed only at a boundary that turns the
  failure into visible state or an HTTP status, and it carries a
  `# noqa: BLE001 -- <reason>` comment.
- **Dependencies**: a hash-pinned lockfile, split into runtime requirements
  (what the deployed app installs) and dev requirements (ruff, pytest,
  coverage, security tools). The gate tools' versions come from the lockfile,
  so CI and the local hook give the same answer.
- **Layer boundaries**: deterministic calculations live in `agents/`. Backend
  data is read and written only through `HsmClient`. The MCP tool layer never
  imports `mock_hsm.db`. The dashboard does import `mock_hsm.db.USERS` (the
  persona list) and `mock_hsm.auth.mint_token`, so the dashboard always ships
  together with the `mock_hsm` package. Dates are site-local and come from the
  backend.
