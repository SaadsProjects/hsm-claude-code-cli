# Team-Level Rules

> This team's affirmed practices and corrections. Loaded after `org.md` as
> strict-additive guidance; contradictions with broader policy are rejected.
> Populated by the practices-discovery affirmation gate. Edit at the gate,
> not directly.

## Way of Working

We work trunk-based on one trunk, `main`, hosted on GitHub
(`SaadsProjects/hsm-claude-code-cli`). Every change reaches `main` through a
short-lived branch and a pull request. We squash-merge, so each pull request
becomes one commit on `main`. Direct pushes to `main` are not part of how we
work.

`main` is protected by the repository ruleset `main_branch_protection`. It
requires a pull request, allows squash merges only, requires 10 status checks
(`lint`, `workflow-lint`, `secrets`, `audit`, `sast`, `lock-check`,
`tests (3.10)`, `tests (3.14)`, `coverage-gate`, `browser-tests`) with the
branch up to date with `main`, and has no bypass. A required check is listed in
the ruleset by its job name, so renaming or removing one of those jobs, or
adding a job that must gate merges, is a ruleset change made in the same piece
of work as the workflow change.

Because `main` refuses direct pushes, Construction work reaches `main` only
through pull requests. Bolts squash-merge locally into one working branch for
the intent, cut from `main`, and the intent ships as one pull request at the
end. A piece of work that has to land sooner than the rest ships first as its
own pull request from its own branch, and the remaining work continues on a
branch cut from the updated `main`. In the dashboard hosting work, the
burned-secret removal is that first pull request.

GitHub deletes a branch automatically once its pull request merges. The local
branch `backup/pre-rollback-2026-10-03` is kept on purpose.

Dependabot opens weekly pull requests for the Actions SHA pins and the Python
lockfiles, including major-version updates (we skip none). They go through the
same pull request and CI gates as any other change; a major update that breaks
the code is upgraded deliberately as its own piece of work.

Every local commit still goes through `/commit`. The `code-reviewer` subagent
reviews the staged diff, then the `lint_before_commit.py` hook blocks the
commit if `ruff check` fails on what the commit will contain. The local gate is
the fast first check. CI on the pull request is the authoritative gate, because
the local hook only exists in clones that copied `settings.local.json`.

Commit messages are a single imperative summary line ("Add …", "Restore …").
GitHub appends the pull request number to the squash commit ("… (#3)").

We keep a single trunk even with two environments. The production branch that
Streamlit Community Cloud tracks is a deployment pointer, not a work branch.
Nobody commits to it directly. It only ever moves to a commit that has already
passed CI on `main` (see Deployment).

## Walking Skeleton

We build a thin end-to-end slice first, before later work. What the slice
covers depends on what already exists.

- **When the hosted apps exist** (deploy and pipeline work), the slice runs: a
  commit merged to `main` → lint and the test suite in CI → an automatic deploy
  to the staging app on Streamlit Community Cloud → a read-only post-deploy
  check against staging that passes. It must also prove that the CI security
  checks (secret scan, dependency audit and bandit) run on the change as
  required checks, and that the sign-in layer in front of staging turns away a
  visitor whose verified email is not on the allowlist.
- **When no hosted app may exist yet** (the dashboard hosting work, where the
  apps are created only after the app changes merge), the slice is local: the
  first pull request (the burned-secret removal) merges with all 10 required
  checks green, and the dashboard starts locally with its in-process backend
  and shows the sign-in screen.

The proof that a piece of work is finished end to end (the Construction
Verification Command) is the CI run on its pull request, with all 10 required
checks green. A local `pytest` run alone does not exercise the secret scan, the
dependency audit, the lockfile check or the burned-secret check.

Any check the slice runs is read-only. It never writes data and never calls
`publish_schedule` or `submit_purchase_order`. The skeleton is done when the
human has seen the slice work end to end and approved the skeleton checkpoint.

## Testing Posture

- **Methodology**: tdd
- **Ordering**: For each behaviour, write a failing test first, then write only the code that makes it pass, then refactor with the suite green.
- Tests ship in the same commit as the code they cover.
- **Coverage**: line coverage is measured over `agents/`, `dashboard/`,
  `mock_hsm/`, `mcp_server/` and `.claude/hooks/`, with `tests/` excluded and
  subprocess measurement switched on (`.coveragerc`). `scripts/` is not
  measured; its scripts are held to their own tests instead. Coverage is
  measured on the gate Python leg (3.14) only. CI enforces the floor in
  `.coverage-floor` and, while that floor is at least 80, the 80% gate as well.
  Every new module under the measured packages counts toward the floor.
- **Test count**: `.test-floor` is the minimum number of passing tests, with no
  failures, that CI accepts in every leg of the Python matrix.
- Both floor files only rise; a pull request that lowers either one fails CI.
  The floors and the measured package set are never lowered or narrowed to get
  a run to pass, including through `# pragma: no cover` or a `.coveragerc`
  omit. At the end of an intent, Build and Test re-measures and raises both
  floor files, keeping some headroom, in the intent's final pull request.
  Measured figures live in the practices-discovery evidence, not in this file.
- CI runs the suite on a Python matrix of 3.10 (the declared floor) and 3.14
  (the version we develop on). Both must pass before merge. When the
  repository variable `HOSTED_PYTHON` is set to another version (the Python the
  hosted app runs on), CI adds it to the matrix.
- CI runs the suite with plain `python -m pytest tests/`. It never passes an
  unrelated `-m` expression, because any `-m` switches off the default `perf`
  skip in `tests/conftest.py`.
- The `perf`-marked timing tests never run in CI. They run by hand with
  `-m perf` when someone wants them. No test carries both the `perf` and the
  `browser` mark, and a test checks this.
- **Browser tests**: `browser`-marked tests need Playwright and Chromium. They
  are skipped unless the `-m` expression names `browser`, and they run in the
  required `browser-tests` job with `-m browser`. On a pull request they run
  only against an app started inside the job on loopback, with the identity
  provider replaced by a test double; staging is reached only by the
  post-deploy check. They do not count toward `.test-floor`.
- **`browser-tests` cannot pass without testing**: it runs on every pull
  request and skips the browser run only when no watched file changed. The
  watch list covers `scripts/postdeploy_check.py`, `dashboard/markers.py`,
  `dashboard/auth_gate.py`, `agents/build_info.py`, `tests/*browser*`,
  `requirements-dev.txt` and `.github/workflows/ci.yml`. A meta-test fails when
  a browser test file, or a source file it imports, is off the watch list. Once
  the first browser test exists, the job no longer accepts "no tests ran" as a
  pass, and it gets the same single retry as the `tests` jobs.
- A flaky test may be retried once in CI. A test that fails on the retry
  blocks the merge.
- The suite runs serially. The fixed ports 8772 and 8773 in
  `test_mcp_tools.py` and `test_hooks.py` make `pytest-xdist` (`-n`) unsafe, so
  we do not parallelise until those ports are made ephemeral. New tests that
  start a server bind port 0 and read back the assigned port; they never add a
  fixed port.
- **Signing secret in tests**: `tests/conftest.py` generates a throwaway
  secret per run and puts it in `os.environ` before any server or subprocess
  starts, so subprocess tests inherit it. No fixed test secret is committed.
- Every test's audit trail goes to a temp file through `HSM_AUDIT_PATH`
  (`tests/conftest.py`). CI does not export `HSM_BASE_URL`,
  `HSM_ACTIVE_USER`, `HSM_AUDIT_PATH` or a signing secret of its own.
- **Gate behaviour is tested first.** A hook or gate that cannot obtain the
  signing secret denies explicitly, and a failing test proves that before the
  code changes, because a crashed hook fails open. The sign-in decision is a
  pure function, unit-tested without Streamlit, and the dashboard wiring is
  tested with `AppTest` through a fake identity, asserting that no tab and no
  persona picker renders before the gate allows. The demo-data reset banner is
  a tested requirement.
- New pipeline helper scripts (such as the post-deploy check) get their own
  tests: the happy path plus at least two error cases.

## Guard Policy

<!-- Affirmed by the team. Mode: strict, relaxed, or off. Strict here holds for every intent and cannot be changed from chat. A section under the retired Change Control heading, written by an earlier release, is still read. -->

## Deployment

- **Host**: Streamlit Community Cloud. The mock backend runs in the same
  process as the dashboard (Streamlit Cloud runs a single process), bound to
  loopback only, with at most one backend per app process. The backend is
  never reachable from outside the app.
- **Who can reach it**: the internet, but only behind a sign-in layer. Both
  apps are public Streamlit Cloud apps that sign people in with Streamlit's
  `st.login`. The in-app persona picker stays as a selector *inside* that layer,
  not as the sign-in itself. The sign-in gate:
  - runs before anything else renders and before the backend is reached, and
    fails closed: missing or broken sign-in settings, an empty or malformed
    allowlist, or any error in the gate refuses entry and never falls back to
    the persona picker;
  - lets in only a signed-in visitor whose identity provider says the email is
    verified;
  - compares the email, trimmed and lower-cased, for an exact match with the
    allowlist, with no domain wildcards;
  - keeps a way out (Sign out or reload) on every refusal screen.
- **Allowlist**: it lives in each app's Streamlit secrets, and the repository
  owner maintains it. Anyone on it can pick any persona, including the system
  administrator, so being on the allowlist means full demo access. We accept
  that risk for a demo.
- **Order**: no hosted app exists, and nothing is exposed beyond loopback,
  until the sign-in gate and the signing-secret handling have merged to `main`.
  The two apps are created, and their secrets entered, only after that.
- **Environments**: two Streamlit Cloud apps that track two branches.
  - Staging tracks `main` and redeploys automatically on every merge.
  - Production tracks a separate production branch. Promotion is the gated
    step: a manual approval by the repository owner, who is the single
    approver, moves the production branch to a commit that already passed CI
    and the staging post-deploy check on `main`.
- **Signing secret**: the token-signing secret comes from the environment
  (`HSM_SIGNING_SECRET`), which is Streamlit secrets when hosted. There is no
  fallback anywhere, not even for local development: every entry point (the
  dashboard, the backend, the hooks, the MCP server and the start script)
  refuses to run without it. Local development uses a git-ignored `.env.local`
  written by the dev-secret script. The secret is read when a token is minted
  or verified, not at import. A secret shorter than 32 bytes is refused. Error
  messages name the variable, never the value. The secret never appears in
  committed configuration (`.mcp.json`, `.streamlit/config.toml`, settings
  examples); the MCP server inherits it from the shell.
- **Per-environment secrets**: staging and production each have their own
  signing secret, sign-in cookie secret and OAuth client. The signing secret
  and the cookie secret are never the same value.
- **Data and audit log**: the hosted demo keeps its data in memory and its
  audit trail on the app's own disk, so both reset when the app restarts or
  redeploys. The app shows a banner telling viewers that the demo data resets.
- **Build identifier**: each hosted build shows which commit it runs: the git
  SHA, with a fingerprint of the source as a fallback when the checkout has no
  `.git`.
- **Before any deploy**, CI runs and must pass: `ruff check` and
  `ruff format --check`, the test suite with the coverage floor, secret
  scanning (gitleaks, plus GitHub push protection), a dependency audit
  (`pip-audit` against the hash-pinned lockfile), and static security analysis
  (bandit as its own CI job). If CI ever builds a container image, that image
  is scanned with Trivy; today none is built.
- **Pipeline hygiene**: third-party GitHub Actions are pinned by full commit
  SHA, workflows get least-privilege `permissions`, and any cloud credential
  CI needs comes from short-lived OIDC, never from long-lived keys stored as
  repository secrets. Chromium for browser tests is installed by Playwright,
  cached under a key that includes the Playwright version, and only in jobs
  that hold no secrets and have only `contents: read`.
- **Smoke checks**: after every deploy, a read-only post-deploy check runs
  against the environment in a real browser (Playwright). It confirms that the
  app answers, that it runs the expected build, and that a visitor who is not
  signed in or not allowlisted is refused. It never signs in as an allowlisted
  user. A deploy is not done until that check passes. Smoke checks never write
  data and never call `publish_schedule` or `submit_purchase_order`.
- **Rollback**: revert on `main` (staging) or move the production branch back
  to the previous good commit, and let Streamlit Cloud redeploy it. Then
  re-run the post-deploy check.

## Code Style

- Python 3.10+ (`ruff.toml` `target-version = "py310"`), stdlib first. The
  mock server and client use only `http.server` and `urllib`, and `mock_hsm/`
  never depends on Streamlit.
- Naming: snake_case for modules, functions and variables; UPPER_SNAKE for
  module-level constants; a leading underscore for private helpers; error
  classes end in `Error` or name the condition (`HsmApiError`,
  `SessionExpired`). Comments and docstrings say why, not what.
- **Linter**: ruff, with its rules pinned in `ruff.toml` (line length 120;
  E4/E7/E9, F, W, I, B, UP, SIM, RUF, BLE, DTZ, EXE, PLW, ASYNC). `ruff check`
  runs in the local commit hook and as a required CI check.
- **Formatter**: `ruff format`, checked by the required `lint` job with
  `ruff format --check`. The code base is formatted. Formatting-only changes go
  in their own commit, apart from feature or pipeline changes.
- **Broad exceptions**: a broad `except Exception` is allowed only (a) at a
  boundary that turns the failure into visible state, a deny, or an HTTP
  status, with a `# noqa: BLE001 -- <reason>` comment, or (b) to record or
  clean up and then re-raise unchanged, which needs no `noqa`. Never swallow an
  exception silently. Ruff does not check the reason text; the `code-reviewer`
  review through `/commit` does.
- **Dependencies**: a hash-pinned lockfile, split into runtime requirements
  (what the deployed app installs) and dev requirements (ruff, pytest,
  coverage, security tools). The gate tools' versions come from the lockfile,
  so CI and the local hook give the same answer. We edit only
  `requirements.in` and `requirements-dev.in`, recompile both locks with the
  `uv pip compile` command at the top of each file, and commit both locks in
  the same change; the required `lock-check` job fails on drift. A runtime
  dependency (for example Authlib through `streamlit[auth]`, which `st.login`
  needs) goes in `requirements.in`; a test-only one (for example `playwright`)
  goes in `requirements-dev.in`. Both are covered by the `pip-audit` gate.
- **Exceptions to the security gates** go only in `security-exceptions.toml`,
  each with a reason and an expiry at most 90 days out. Inline `# nosec` has no
  effect, because bandit runs with `--ignore-nosec`.
- **Layer boundaries**: `agents/` holds deterministic, framework-free code: the
  domain calculations and small pure helpers such as build identification. It
  never imports Streamlit. Backend data is read and written only through
  `HsmClient`. The MCP tool layer never imports `mock_hsm.db`. The dashboard
  does import `mock_hsm.db.USERS` (the persona list) and
  `mock_hsm.auth.mint_token`, so the dashboard always ships together with the
  `mock_hsm` package. Dates are site-local and come from the backend.
  `mock_hsm/auth.py` imports only the standard library and `mock_hsm` itself,
  never Streamlit or another third-party package, because the MCP server, the
  hooks and the dashboard all import it. Streamlit-specific code, such as
  copying Streamlit secrets into the environment, lives in `dashboard/`.
- **File placement for hosting code**: the sign-in gate goes in
  `dashboard/auth_gate.py`, the markers the browser check asserts on in
  `dashboard/markers.py`, the build identifier in `agents/build_info.py`, the
  post-deploy check in `scripts/postdeploy_check.py`, and browser tests in
  `tests/test_*browser*.py`. The single in-process backend start is an
  imported, standard-library-only function in `mock_hsm/`, not code in
  `dashboard/app.py`, which re-runs on every interaction. Decisions such as the
  allowlist check stay in plain functions that ordinary tests can call, with
  the Streamlit calls kept thin.
## Forbidden

<!-- Team-specific forbidden patterns -->

## Mandated

<!-- Team-specific mandates -->

## Corrections

<!-- Self-learning loop appends here. -->
