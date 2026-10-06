# Code Generation Plan — U6 staging-app

## Sources

- `inception/requirements-analysis/requirements.md` FR9.1–FR9.3, FR4.2–FR4.4, FR7.1–FR7.3, NFR1, NFR2, NFR6; Constraints ("No staging app exists until the sign-in gate and the secret handling have merged"); Out of Scope (production app, hosted Python in the CI matrix)
- `inception/units-generation/unit-of-work.md` U6 (hosting configuration only, the owner's console action, not code; requirements finding R-04)
- `inception/contract-design/contract-summary.md` C7 (Streamlit secrets schema) and C8 (post-deploy check command line and exit codes)
- `memory/team.md` Walking Skeleton (the hosted slice: merge → CI → automatic staging deploy → read-only post-deploy check, and the sign-in layer turning away a verified email that isn't allowlisted), Deployment (staging tracks `main`, per-environment secrets, signing secret ≠ cookie secret, smoke checks, rollback), Way of Working (pull request, squash merge, no direct push); `memory/project.md` Forbidden F1 (the check never signs in; no identity-provider credentials in CI) and F2 (never commit `.streamlit/secrets.toml`), and the correction that the owner confirms the build by signing in and reading the caption
- Current code: `.streamlit/secrets.toml.example` (the five sign-in keys, `HSM_ALLOWED_EMAILS`, and `HSM_SIGNING_SECRET` as a comment), `scripts/postdeploy_check.py` (exit codes 0–4), `.github/workflows/postdeploy.yml`, `agents/build_info.py`, draft pull request #7 (U2–U5, all 10 required checks green at e436355)
- The human chose "Plan U6, then merge" at the start of this unit: the plan is a runbook, and pull request #7 is marked ready and merged only at the step that says so, with the human's go-ahead.

## Design Decisions Settled in This Plan

| # | Decision | Resolves |
|---|----------|----------|
| S1 | The only repository change is a staging runbook, `docs/staging-app.md`, and its test. Creating the app, the Google OAuth client and the secrets are console actions by the owner; no hosting configuration, credential or URL is committed. Nothing in `dashboard/`, `agents/`, `mock_hsm/` or `scripts/` changes | U6 boundaries, F2, NFR1 |
| S2 | The runbook ships in pull request #7 before it merges, as one more commit through `/commit` on `dashboard-hosting`, so the docs land with the change they describe | FR10.1, team.md Way of Working |
| S3 | `tests/test_staging_runbook.py` keeps the runbook in step with the code. It reads the key names from `.streamlit/secrets.toml.example` with a line pattern (Python 3.10 has no `tomllib`), including the commented `HSM_SIGNING_SECRET`, and fails when the runbook doesn't name one of them | C7, FR9.2 |
| S4 | Pull request #7 is marked ready and squash-merged only after its required checks are green on the runbook commit and the human says to merge. No staging app is created before that merge | Constraints, team.md Deployment (Order) |
| S5 | The staging app tracks `main`, with main file `dashboard/app.py`, and uses `requirements.txt` (the runtime lock). Its Python version is the newest one Streamlit Community Cloud offers that is no newer than 3.14, recorded in the code summary. Adding that version to the CI matrix stays out of scope | FR9.1, requirements Out of Scope |
| S6 | Staging gets its own Google OAuth client (web application) whose only authorised redirect URI is `https://<staging-app>.streamlit.app/oauth2callback`, and its own secrets: a fresh `HSM_SIGNING_SECRET` and a fresh `cookie_secret` (each from `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`, never the same value, never the local `.env.local` value), the client id and secret, and `HSM_ALLOWED_EMAILS` holding the owner's address. The values go only into the app's Secrets settings | FR9.2, team.md Deployment |
| S7 | Proof that staging works, in this order: (a) `python3 scripts/postdeploy_check.py https://<staging-app>.streamlit.app --timeout 180` exits 0 on the owner's machine; (b) the manual `postdeploy` workflow, run against the same URL, passes; (c) the owner signs in with the allowlisted Google account and reads a build caption equal to the short SHA of `main` (or a `src-` fingerprint, if the host's checkout has no `.git`); (d) the owner signs in with a verified Google account that isn't on the allowlist and sees "This account doesn't have access" with Sign out. The check never signs in; (c) and (d) are the owner's own sign-ins | FR9.3, FR4.3, FR4.4, team.md Walking Skeleton, F1 |
| S8 | NFR2 (usable within 30 s of the app waking) is read from the check's own timing in (a), and from the owner's sign-in in (c), with the app first left asleep. A miss is recorded, not hidden | NFR2 |
| S9 | Rollback for staging is to revert on `main` and let the app redeploy, then re-run the check. If the gate ever lets in a visitor it shouldn't, the owner deletes the app first (or removes every address from `HSM_ALLOWED_EMAILS`, which fails closed) and investigates afterwards | team.md Deployment (Rollback), project.md Forbidden |

## Code Generation Steps

Each behaviour follows Red (write the failing tests, run them, record the failing output), then Green (the least change that passes), then Refactor (with the suite green).

- [x] **Step 1 — Runner and baseline.** Run `python3 -m pytest tests/test_postdeploy_check.py -q` and the full suite once. Record the counts.
- [x] **Step 2 — Runbook test (FR9.2; S3).**
  - Red, in `tests/test_staging_runbook.py`:
    - `docs/staging-app.md` exists;
    - it names every key from `.streamlit/secrets.toml.example` (`HSM_SIGNING_SECRET`, `HSM_ALLOWED_EMAILS`, `redirect_uri`, `cookie_secret`, `client_id`, `client_secret`, `server_metadata_url`);
    - it states that the signing secret and the cookie secret are different values;
    - it names the main file `dashboard/app.py` and the branch `main`;
    - it gives the `scripts/postdeploy_check.py` command and the `/oauth2callback` redirect path;
    - a self-test: the key reader returns all seven names from the example file, so a renamed key can't slip past.
  - Green: write `docs/staging-app.md` (Step 3).
- [x] **Step 3 — Runbook content (FR9.1–FR9.3; S5–S9).** Write `docs/staging-app.md` with these sections:
  - before you start (pull request #7 merged, all checks green);
  - create the Google OAuth client;
  - create the app;
  - enter the secrets;
  - prove it (S7 a–d);
  - rollback (S9).
  - Also link it from `README.md` (one line) and `CLAUDE.md` (one line beside the postdeploy workflow paragraph).
- [x] **Step 4 — Verification.** Run:
  - the unit command;
  - `python3 -m pytest tests/ -q`;
  - `ruff check .` and `ruff format --check .`.

  The test count stays at or above `.test-floor`. Coverage is unchanged, because no measured file changes. Neither floor file is edited.
- [ ] **Step 5 — Commit, push and merge (S2, S4). Human go-ahead at each step.**
  - Commit "Add the staging app runbook" through `/commit`.
  - Push to draft pull request #7, and wait for all 10 required checks.
  - Mark the pull request ready.
  - Squash-merge it into `main`.
- [ ] **Step 6 — Owner: Google OAuth client and staging app (FR9.1, FR9.2; S5, S6).** The owner follows the runbook in the Google Cloud console and on Streamlit Community Cloud. I give the exact values to enter and generate the two secrets locally on request; nothing is committed.
- [ ] **Step 7 — Prove staging (FR9.3, NFR2; S7, S8).**
  - Run the check locally against the staging URL.
  - Trigger the `postdeploy` workflow (with the human's go-ahead) and read its result.
  - The owner reports the two sign-ins (S7 c and d) and the build caption.
  - Record the evidence and the timings in `code-summary.md`.

## Commits

One commit through `/commit` on `dashboard-hosting`, "Add the staging app runbook", with its test. The push, the ready-for-review change and the merge of pull request #7 each wait for the human's go-ahead. Steps 6–7 change nothing in the repository.

## Story Traceability

| Story / requirement | Steps |
|---------------------|-------|
| FR9.1 Staging app tracking `main` | 3, 5, 6 |
| FR9.2 Its own secrets, OAuth client and allowlist | 2, 3, 6 |
| FR9.3 The post-deploy check passes against staging | 3, 7 |
| FR4.3, FR4.4 Only a verified, allowlisted email gets in (real Google, first time) | 7 |
| NFR2 Usable within 30 s of waking | 7 |
| FR10.1 Docs in the same pull request | 3, 5 |

## Assumptions & Open Questions

- [assumption] Streamlit Community Cloud lets one account create this public app on the free tier, and serves it at `https://<name>.streamlit.app`.
- [assumption] Google reports `email_verified` as the boolean `True` for a Google account through `st.user` (feasibility R1). S7 (c) is the first real proof; if it fails, the gate refuses entry (fail closed) and the finding goes back to U3.
- [assumption] The host's sleep and wake wording in `scripts/postdeploy_check.py` matches what Streamlit Community Cloud shows today. S7 (a), run against a sleeping app, is the first real proof (U5 open item K3).
- The owner holds the Google Cloud project and the Streamlit Community Cloud account. Their console steps can't be automated from here.

## Testing Contract

```json
{
  "version": 1,
  "methodology": "tdd",
  "source": "team",
  "ordering": "For each behaviour, write a failing test first, then write only the code that makes it pass, then refactor with the suite green.",
  "scope": "feature",
  "test_strategy": "standard",
  "project_type": "brownfield",
  "applicable_notes": [
    {
      "layer": "org",
      "text": "We treat tests as a first-class deliverable in every Bolt. The specific\nmethodology (TDD, BDD, ATDD, or classic test-after) is affirmed at\npractices-discovery and recorded in `team.md` under this heading with explicit\n`Methodology` and `Ordering` fields; Code Generation resolves those fields\nindependently from coverage, tooling, and scope notes.\n\nWhen no posture has been affirmed, our default per scope is:\n- **Methodology**: test-after\n- **Ordering**: implement each applicable testable layer, then write and run\n  that layer's tests.\n- `mvp`, `enterprise`, `feature`, `infra`, `classic` add an 80% line-coverage\n  floor and CI execution before merge.\n- `bugfix`, `security-patch` add a targeted regression for the specific\n  bug/vulnerability and require the existing suite to remain green.\n- `express` uses the Minimal strategy: requirement-driven unit tests (one per\n  requirement, with a happy-path floor per component); existing tests remain\n  green.\n- `poc`, `refactor`, `workshop` add no extra new-test floor and require the\n  existing suite to remain green.\n\nThe active `Test Strategy` still applies in every scope and determines test\nvolume/types. Scope floors are additive; they never reduce or replace the\nselected strategy.\n\nBuild and Test verifies defined coverage floors and affirmed quality targets;\nthey may not be weakened to make a step pass.\n\nAffirm a stricter posture in `team.md` if the team commits to one."
    },
    {
      "layer": "team",
      "text": "- **Methodology**: tdd\n- **Ordering**: For each behaviour, write a failing test first, then write only the code that makes it pass, then refactor with the suite green.\n- Tests ship in the same commit as the code they cover.\n- **Coverage**: line coverage is measured over `agents/`, `dashboard/`,\n  `mock_hsm/`, `mcp_server/` and `.claude/hooks/`, with `tests/` excluded and\n  subprocess measurement switched on (`.coveragerc`). `scripts/` is not\n  measured; its scripts are held to their own tests instead. Coverage is\n  measured on the gate Python leg (3.14) only. CI enforces the floor in\n  `.coverage-floor` and, while that floor is at least 80, the 80% gate as well.\n  Every new module under the measured packages counts toward the floor.\n- **Test count**: `.test-floor` is the minimum number of passing tests, with no\n  failures, that CI accepts in every leg of the Python matrix.\n- Both floor files only rise; a pull request that lowers either one fails CI.\n  The floors and the measured package set are never lowered or narrowed to get\n  a run to pass, including through `# pragma: no cover` or a `.coveragerc`\n  omit. At the end of an intent, Build and Test re-measures and raises both\n  floor files, keeping some headroom, in the intent's final pull request.\n  Measured figures live in the practices-discovery evidence, not in this file.\n- CI runs the suite on a Python matrix of 3.10 (the declared floor) and 3.14\n  (the version we develop on). Both must pass before merge. When the\n  repository variable `HOSTED_PYTHON` is set to another version (the Python the\n  hosted app runs on), CI adds it to the matrix.\n- CI runs the suite with plain `python -m pytest tests/`. It never passes an\n  unrelated `-m` expression, because any `-m` switches off the default `perf`\n  skip in `tests/conftest.py`.\n- The `perf`-marked timing tests never run in CI. They run by hand with\n  `-m perf` when someone wants them. No test carries both the `perf` and the\n  `browser` mark, and a test checks this.\n- **Browser tests**: `browser`-marked tests need Playwright and Chromium. They\n  are skipped unless the `-m` expression names `browser`, and they run in the\n  required `browser-tests` job with `-m browser`. On a pull request they run\n  only against an app started inside the job on loopback, with the identity\n  provider replaced by a test double; staging is reached only by the\n  post-deploy check. They do not count toward `.test-floor`.\n- **`browser-tests` cannot pass without testing**: it runs on every pull\n  request and skips the browser run only when no watched file changed. The\n  watch list covers `scripts/postdeploy_check.py`, `dashboard/markers.py`,\n  `dashboard/auth_gate.py`, `agents/build_info.py`, `tests/*browser*`,\n  `requirements-dev.txt` and `.github/workflows/ci.yml`. A meta-test fails when\n  a browser test file, or a source file it imports, is off the watch list. Once\n  the first browser test exists, the job no longer accepts \"no tests ran\" as a\n  pass, and it gets the same single retry as the `tests` jobs.\n- A flaky test may be retried once in CI. A test that fails on the retry\n  blocks the merge.\n- The suite runs serially. The fixed ports 8772 and 8773 in\n  `test_mcp_tools.py` and `test_hooks.py` make `pytest-xdist` (`-n`) unsafe, so\n  we do not parallelise until those ports are made ephemeral. New tests that\n  start a server bind port 0 and read back the assigned port; they never add a\n  fixed port.\n- **Signing secret in tests**: `tests/conftest.py` generates a throwaway\n  secret per run and puts it in `os.environ` before any server or subprocess\n  starts, so subprocess tests inherit it. No fixed test secret is committed.\n- Every test's audit trail goes to a temp file through `HSM_AUDIT_PATH`\n  (`tests/conftest.py`). CI does not export `HSM_BASE_URL`,\n  `HSM_ACTIVE_USER`, `HSM_AUDIT_PATH` or a signing secret of its own.\n- **Gate behaviour is tested first.** A hook or gate that cannot obtain the\n  signing secret denies explicitly, and a failing test proves that before the\n  code changes, because a crashed hook fails open. The sign-in decision is a\n  pure function, unit-tested without Streamlit, and the dashboard wiring is\n  tested with `AppTest` through a fake identity, asserting that no tab and no\n  persona picker renders before the gate allows. The demo-data reset banner is\n  a tested requirement.\n- New pipeline helper scripts (such as the post-deploy check) get their own\n  tests: the happy path plus at least two error cases."
    },
    {
      "layer": "project",
      "text": "- With no requirements or NFR artifacts in this workflow, the target inventory was built from the Testing Contract and the unit-test instructions' coverage targets, and cross-unit traceability used the plan's own R1-R8. (learned 2026-10-04) \n\n- Initial CI floors are set with headroom below the local measurement (coverage floor 95.00 against 96%, test floor 745 against 811 passing) so runner differences don't fail the first run; floors only ever rise afterwards. (learned 2026-10-04)"
    }
  ],
  "obligations": {
    "strategy": "standard",
    "strategy_volume": [
      "Five to eight tests per component.",
      "Unit tests plus integration tests for key boundaries.",
      "Add E2E, performance, or security tests when requirements demand them."
    ],
    "scope_floor": [
      "Meet an 80% line-coverage floor.",
      "Run the selected tests in CI before merge."
    ],
    "combination_rule": "Apply every selected-strategy obligation and every scope-floor obligation; neither replaces the other, and a targeted scope regression may add the narrowest necessary test type beyond the strategy default."
  },
  "plan_profile": {
    "methodology": "tdd",
    "runner_step": "Verify the existing test runner/configuration and record the exact unit-scoped command.",
    "runner_ready_before_first_test": true,
    "testable_layers": [
      "Data model / database behavior",
      "Repository / data access",
      "Business logic",
      "API / endpoint",
      "Frontend behavior"
    ],
    "steps": [
      "Project structure and production configuration skeleton.",
      "Verify the existing test runner/configuration and record the exact unit-scoped command.",
      "Data model / database behavior - Red: write the failing tests and record the failing command output.",
      "Data model / database behavior - Green: implement only enough behavior to pass.",
      "Data model / database behavior - Refactor: improve the implementation while tests stay green.",
      "Repository / data access - Red: write the failing tests and record the failing command output.",
      "Repository / data access - Green: implement only enough behavior to pass.",
      "Repository / data access - Refactor: improve the implementation while tests stay green.",
      "Business logic - Red: write the failing tests and record the failing command output.",
      "Business logic - Green: implement only enough behavior to pass.",
      "Business logic - Refactor: improve the implementation while tests stay green.",
      "API / endpoint - Red: write the failing tests and record the failing command output.",
      "API / endpoint - Green: implement only enough behavior to pass.",
      "API / endpoint - Refactor: improve the implementation while tests stay green.",
      "Frontend behavior - Red: write the failing tests and record the failing command output.",
      "Frontend behavior - Green: implement only enough behavior to pass.",
      "Frontend behavior - Refactor: improve the implementation while tests stay green.",
      "Environment/build configuration.",
      "Documentation and traceability."
    ]
  },
  "input_sha256": "sha256:ed1172a231d8ff0fee1c6e3eb2c1f66689d445beb7466da34df8c830cbd54159",
  "contract_sha256": "sha256:a73ec1a748dc439c0dd9c9de5fc8ccef200edbba9c8676d7d802f32eaf4cf117"
}
```
