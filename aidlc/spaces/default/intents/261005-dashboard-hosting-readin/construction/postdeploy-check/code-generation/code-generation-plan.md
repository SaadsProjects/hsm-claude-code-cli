# Code Generation Plan — U5 postdeploy-check

## Sources

- `inception/requirements-analysis/requirements.md` FR7.1–FR7.5, FR8.1–FR8.6, NFR2, NFR6, NFR7
- `inception/user-stories/stories.md` US7.1–US7.4 (AC7.1.1–AC7.4.2), US8.2 (AC8.2.1–AC8.2.3), US8.3 (AC8.3.1–AC8.3.4)
- `inception/units-generation/unit-of-work.md` U5; `inception/contract-design/contract-summary.md` C6 (markers), C8 (check command line, exit codes, workflow), C9 (public surface)
- `memory/team.md` Testing Posture (browser tests, watch list, meta-test, retry, `perf`/`browser` never on one test), Deployment (smoke checks, pipeline hygiene, Chromium caching), Code Style (file placement); `memory/project.md` Forbidden F1 (never sign in as an allowlisted user, no identity-provider credentials in CI) and Mandated M2 (required-check renames change the ruleset), and the correction that the post-deploy check doesn't assert the build
- Current code: `.github/workflows/ci.yml` (`browser-tests` job), `scripts/check_workflows.py`, `tests/conftest.py` (`browser` and `perf` marks), `tests/ci_scripts.py`, `dashboard/markers.py`, `dashboard/auth_gate.py` (the identity seam), `requirements-dev.in`
- The human chose to plan this unit from the requirements, because the code-generation restart skipped its design stages. The decisions below stand in for them.

## Design Decisions Settled in This Plan

| # | Decision | Resolves |
|---|----------|----------|
| K1 | `scripts/postdeploy_check.py` has `main(argv) -> int` and the C8 exit codes: 0 passed, 1 assertion failed, 2 bad usage, 3 no answer or still waking at the timeout. It prints one line per assertion and a final `PASS` or `FAIL: <reason>`. Playwright is imported inside the browser function only, so the argument parsing and page classification can be tested without a browser | C8, FR7.2 |
| K2 | Page classification is a pure function, `classify(state) -> "pass" / "waking" / "not-gated" / "not-app"`, over what the browser saw: whether the `SIGN_IN_SCREEN` block is visible, whether the `APP_TABS` block or any tab is present, and the visible page text. The browser part only gathers that state, by searching every frame for the Streamlit key classes `.st-key-<marker>` | C8, AC7.1.2 (selectors from `dashboard/markers.py`) |
| K3 | The host's sleep and waking pages are recognised by their wording ("gone to sleep", "get this app back up", "Your app is in the oven", "waking up"), held as constants. While one shows, the check waits and retries until the timeout, and such a page is never a pass. If the sleep page offers the host's own wake button, the check presses it once. That button is the hosting platform's, not the app's: it signs nobody in and writes no data. The source scan in K6 allows exactly that one click and no other | C8 open question, NFR2, NFR6 |
| K4 | Browser tests launch the real `dashboard/app.py` through a test-only entry script, `tests/browser_app.py`. That script patches only the identity seam (`auth_gate.current_identity`, from a JSON identity in an environment variable) and then runs the app. The app code gets no test hook. Each test starts `streamlit run tests/browser_app.py` on `127.0.0.1` on a free port (bind port 0, read it back, release it) with a temp secrets file, waits for `/_stcore/health`, and stops the process afterwards | FR8.5, AC8.2.2, team.md (port 0, loopback only) |
| K5 | `tests/test_postdeploy_browser.py` (marked `browser`) covers these cases. A failing check case asserts the exit code as well as the output line. **Proof cases:** a signed-out visitor makes the check exit 0 and sees only Screen 1 (AC7.1.1); a verified email that isn't on the allowlist, and an unverified email, each see Screen 2 (AC8.2.3). **Error cases:** a test double that renders tabs and no gate makes the check exit 1 (AC7.2.1); a plain `http.server` page makes it exit 1 (AC7.2.2); a closed port with `--timeout 3` makes it exit 3 within about 10 s (AC7.2.3) | FR7.4, US7.1, US7.2, US8.2 |
| K6 | Ordinary (non-browser) tests in `tests/test_postdeploy_check.py`: argument errors give exit 2 (a missing URL, a non-http URL, a bad timeout); `classify` gets one case per outcome; the selectors are built from `dashboard.markers`. An AST scan of the script finds no `fill`/`type`/`press` on inputs, no click except the K3 wake button, no secret or credential names, no `login`/`sign_in`, and no `publish_schedule`/`submit_purchase_order`. These count toward `.test-floor`; the browser tests don't | AC7.1.2, AC7.3.1, FR7.4 |
| K7 | `playwright` goes in `requirements-dev.in`, pinned with `==` at the latest release that resolves on Python 3.10 and 3.14. Both locks are recompiled with the commands at the top of each `.in` file; the runtime lock is unchanged. Chromium is installed with `python -m playwright install --with-deps chromium` and cached under `~/.cache/ms-playwright` with a key that includes the Playwright version read from `requirements-dev.txt` | FR8.1, FR8.2, AC8.1.1, AC8.2.1 |
| K8 | `browser-tests` job: keep its name, triggers and `contents: read`. Its watch list adds `requirements-dev.txt`, `.github/workflows/ci.yml` and `dashboard/app.py` (`tests/browser_app.py` is already matched by `tests/.*browser.*`). The run becomes `python -m pytest tests/ -m browser -q --reruns 1`, so "no tests ran" (exit 5) now fails the job and a flaky failure gets one retry. The Chromium install and cache steps run only when tests run. No required job is renamed, added or removed, so the `main_branch_protection` ruleset stays as it is (AC8.3.4 evidence: the job names are unchanged) | FR8.3, FR8.4, AC8.3.1, AC8.3.3, M2 |
| K9 | A meta-test, `tests/test_ci_browser_watch.py`, reads the watch-list pattern from `ci.yml`. It fails when any `tests/*browser*` file is off the list, or when any project source file such a test imports or launches is off the list (found from imports, and from `.py` path strings in the test files). It also checks that no test carries both `perf` and `browser` (kept if a test for this already exists) | FR8.3, AC8.3.2, team.md |
| K10 | A new `.github/workflows/postdeploy.yml` triggers on `workflow_dispatch` only, with inputs `url` (required) and `timeout` (default "120"). It has top-level `permissions: {}` and `contents: read` on its single job, and no secrets. Its actions are the same SHA-pinned versions `ci.yml` uses, and its cache action is pinned by full SHA. It installs the dev lock and Chromium, then runs `python scripts/postdeploy_check.py "$URL" --timeout "$TIMEOUT"`, with the inputs passed through `env`, never interpolated into the shell. It must pass `actionlint` and `scripts/check_workflows.py` | FR7.3, AC7.4.1, F1, project.md Mandated |
| K11 | No commit, push or pull request without the human's go-ahead. The commit goes through `/commit` on `dashboard-hosting` | team.md Way of Working |

## Code Generation Steps

Each behaviour follows Red (write the failing tests, run them, record the failing output), then Green (the least code that passes), then Refactor (with the suite green).

- [x] **Step 1 — Runner and baseline.** Run `python3 -m pytest tests/test_ci_check_workflows.py tests/test_conftest_markers.py -q` and the full suite once. Record the counts.
- [x] **Step 2 — Playwright through the locks (US8.1; K7).** Add `playwright==<version>` to `requirements-dev.in`. Recompile both locks and install the dev lock, then run `python -m playwright install chromium` locally. Record the version.
- [x] **Step 3 — Arguments and exit codes (US7.2; AC7.2.3 partly; K1).**
  - Red: `main([])`, `main(["ftp://x"])` and `main(["https://x", "--timeout", "-1"])` return 2 with a usage line.
  - Green: the argument parser and `main`.
- [x] **Step 4 — Page classification (US7.1, US7.2; K2, K3).**
  - Red: `classify` returns `pass` for a visible sign-in marker with no tabs, `not-gated` when tabs or `APP_TABS` are present (even with the sign-in marker), `waking` for each host wake wording, and `not-app` otherwise.
  - Red: the selectors equal `.st-key-` plus `markers.SIGN_IN_SCREEN` and `markers.APP_TABS`.
  - Green: `classify` and the selector constants.
- [x] **Step 5 — Read-only by construction (US7.3; AC7.3.1; K6).**
  - Red: the AST scan rules from K6, run against the script.
  - Green: whatever the browser function needs to satisfy them. The browser function is written in Step 7, so this scan stays in force from here on.
- [x] **Step 6 — Browser test harness (US8.2; K4).**
  - Red: a `browser` test starts the app through `tests/browser_app.py` with a signed-out identity and asserts that `/_stcore/health` answers. It fails until the entry script and the fixture exist.
  - Green: `tests/browser_app.py` and the server fixture (free port, temp secrets, health wait, teardown).
- [x] **Step 7 — The check in a browser (US7.1, US7.2; AC7.1.1, AC7.2.1–AC7.2.3; K1, K3, K5).**
  - Red: the K5 check cases against the harness, the test doubles and a closed port.
  - Green: the browser function, which loads the page, gathers state from every frame, presses the wake button at most once, retries while `waking` until the timeout, and maps each outcome to its exit code and output line.
- [x] **Step 8 — Refusal proof in a browser (US8.2; AC8.2.3; K5).**
  - Red/Green: with the stand-in signing in a verified email that isn't on the allowlist, and then an unverified one, the page shows the `REFUSAL_SCREEN` block and no tabs.
- [x] **Step 9 — CI: browser-tests job (US8.2, US8.3; AC8.2.1, AC8.3.1, AC8.3.3; K7, K8).**
  - Red: the K9 meta-test fails on the current watch list, because `dashboard/app.py`, `requirements-dev.txt` and `ci.yml` are missing from it.
  - Green: the `ci.yml` changes from K8, with the Chromium cache and install steps guarded by the same `run` condition.
  - Run `actionlint` (if installed) and `python3 scripts/check_workflows.py .github/workflows`.
- [x] **Step 10 — Manual workflow (US7.4; AC7.4.1; K10).**
  - Red: a test asserts that `postdeploy.yml` triggers on `workflow_dispatch` only, sets `contents: read` and nothing broader, references no `secrets.`, pins every `uses:` by a 40-hex SHA, and passes the inputs through `env`.
  - Green: the workflow. `check_workflows.py` passes on it.
- [x] **Step 11 — Docs (US10.1 U5 share; FR10.1).**
  - `README.md` and `dashboard/README.md`: how to run the check by hand and from GitHub, with its exit codes.
  - `CLAUDE.md`: the browser-test command needs `python -m playwright install chromium`, plus one line on the check and its workflow.
- [x] **Step 12 — Verification and traceability.**
  - Run the unit commands, including `python3 -m pytest tests/ -m browser -q`.
  - Run the full suite (`python3 -m pytest tests/ -q`), `ruff check .`, `ruff format --check .` and coverage.
  - The test count stays at or above `.test-floor` and coverage at or above `.coverage-floor`. Neither floor file is edited, and `.coveragerc` stays as it is (`scripts/` stays unmeasured).

## Commits

After generation, the human is asked before the commit. One commit through `/commit` on `dashboard-hosting`: "Add a read-only post-deploy browser check and real browser tests in CI". Pushing to draft pull request #7 also waits for the human's go-ahead. Running the manual workflow against staging belongs to U6.

## Story Traceability

| Story | Steps |
|-------|-------|
| US7.1 Check a deployed app by hand | 4, 7 |
| US7.2 Check fails loudly | 3, 4, 7 |
| US7.3 Check never signs in or writes | 5 |
| US7.4 Run the check from GitHub | 10 |
| US8.1 New packages through the locks (Playwright share) | 2 |
| US8.2 Browser tests run locally against a fake identity | 6, 7, 8, 9 |
| US8.3 Browser check can't pass without testing | 9 |
| US10.1 Docs (U5 share) | 11 |

## Assumptions & Open Questions

- [assumption] Streamlit Community Cloud's sleep and waking wording matches the K3 constants. The check is first run against staging in U6. If the wording differs, staging gets exit 3 and the constants are updated there.
- [assumption] Streamlit renders `st.container(key=…)` and keyed buttons with a `st-key-<key>` CSS class in 1.64.0, so the browser selectors can be built from the markers.
- This unit edits `.github/workflows/ci.yml` and the shared docs, which are also claimed by earlier units. The human has accepted that this makes their reviews stale, and that code generation is restarted once afterwards.

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
