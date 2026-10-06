# Code Generation Plan — U2 embedded-backend

## Sources

- `functional-design/` (entities.md, rules.md BR1.1–BR6.1 incl. BR2.4, BR2.5, BR3.3, BR5.4; functional-spec.md W1–W4; 9 ACs AC3.1.1–AC3.4.1)
- `nfr-requirements/` (NFR1.11–NFR1.14, NFR2.1–NFR2.5, NFR3.3–NFR3.8, NFR4.2–NFR4.4, NFR5.1, NFR7.2)
- `nfr-design/` (S1–S5, P1–P3, SC1–SC3, R1–R6, O1–O4, logical-components) and its review's open minor/major items, settled below
- `infrastructure-design/` (no CI change; hosted `HSM_AUDIT_PATH` unset) and its review's minor items
- `inception/contract-design/contract-summary.md` C2, C3; `inception/units-generation/unit-of-work.md` U2 (US3.1–US3.4, plus the U2 share of US10.1 docs)
- Current code: `mock_hsm/server.py` (`Handler`, `run`, `main`), `mock_hsm/audit.py` (`configure`, `_current.state.unavailable`), `mock_hsm/db.py` and `mock_hsm/writes.py` (module-level state), `dashboard/session.py` (`client_for`), `dashboard/app.py` (lines 27, 46–49, 483, 503–514), `tests/conftest.py`

## Design Decisions Settled in This Plan

| # | Decision | Resolves |
|---|----------|----------|
| P1 | No cache clear after a replacement. The demo data and sessions live in module state (`mock_hsm.db`, `writes._state`), so a replacement keeps them, and every client reads the address at call time, so cached reads stay correct. The cache-clear clause of BR2.5 is dropped; the "address read at each use" clause stays. No replacement signal is added to `BackendHandle`. | NFR-design review R-01 (Major) |
| P2 | Liveness = server thread alive AND a TCP connect to the port succeeds within 0.5 s AND `audit.unavailable_reason()` is `None`. A wedged serve loop that still accepts connections is not detectable at TCP level and is accepted as a limit; `retire` still uses a bounded `shutdown` for a live thread. A trail that failed at runtime makes the instance not live, so the next rerun retires it and starts again, which calls `audit.configure()` again. | NFR-design review R-02, R-03 |
| P3 | The caption reads `embedded.current()` at render time and shows `Backend: not running` when it returns `None`. The `URLError` text in `run()` becomes "Can't reach the demo backend (<reason>). Reload the page or try again later." with no address and no start command. | NFR-design review R-04 |
| P4 | `mock_hsm/embedded.py` constructs `ThreadingHTTPServer(("127.0.0.1", port), server.Handler)` itself and never calls `server.run()`. Allowed imports: `dataclasses`, `datetime`, `http.server`, `logging`, `os`, `pathlib`, `socket`, `stat`, `tempfile`, `threading`, and `mock_hsm` modules. | NFR-design review R-05 |
| P5 | The user id for the audit directory uses `os.getuid()` when `hasattr(os, "getuid")`, else the login name. An operator-set `HSM_AUDIT_PATH` is passed through unchanged and is the operator's responsibility (the audit module may narrow its parent). The NFR1.13 tests unset `HSM_AUDIT_PATH` and redirect `tempfile.gettempdir()` to `tmp_path`. | NFR-design review R-06 |
| P6 | Replacement warning text: "embedded backend replaced on a new port; the demo data is kept". | NFR-design R2/O1 correction |
| P7 | Tests that render the dashboard get the embedded backend through one seam: `dashboard.app` calls `embedded.start()` via a module-level name the tests can patch, so the existing `AppTest` suite (which patches `session.client_for`) keeps passing unchanged. | Keep the existing suite green |
| P8 | Work lands on the intent branch `dashboard-hosting`, cut from `main` after pull request #6 merges. If #6 has not merged when generation starts, the branch is cut from `secret-fail-closed` and rebased onto `main` once #6 merges. | team.md Way of Working |
| P9 | The browser-tests watch list is not changed here; the unit whose browser test first imports `mock_hsm/embedded.py` (U3 or U5) adds it. The timing tests are ordinary wide-margin tests that rely on the existing single CI retry. | Infrastructure-design review R-01, R-03 |

## Code Generation Steps

Each behaviour follows Red (write the failing tests, run them, record the failing output), Green (the least code that passes), then Refactor (with the suite green). New tests go in `tests/test_embedded_backend.py` (the `mock_hsm` side) and `tests/test_dashboard_embedded.py` (the dashboard side).

- [x] **Step 1 — Branch and runner check.** Create the branch per P8. Run the existing `python3 -m pytest tests/test_mcp_tools.py tests/test_hooks.py -q` and the full suite once; record the baseline counts.
- [x] **Step 2 — Audit readiness query (NFR3.5; R3).**
  - Red: `audit.unavailable_reason()` returns `None` after a good `configure(path)` and the reason string after configuring a corrupt file and an unwritable path.
  - Green: add the read-only function to `mock_hsm/audit.py`.
- [x] **Step 3 — Start on loopback (AC3.1.1; BR1.1, BR1.2; NFR1.11, NFR7.2; S1, S5, P4).**
  - Red: `start()` returns a running `BackendHandle` with host `127.0.0.1` and a live port that answers an authenticated GET; an AST test shows the module imports only the allowed modules.
  - Green: `mock_hsm/embedded.py` with `BackendHandle`, `BackendNotRunning`, the holder, `start(port=0)`, `current()`.
- [x] **Step 4 — Secret refusal (BR3.1; NFR1.12, NFR1.14; S2).**
  - Red: with `HSM_SIGNING_SECRET=""`, `start()` returns status failed, a cause naming the variable, no listener, and no audit directory created; a short secret's value is absent from the cause.
- [x] **Step 5 — Audit directory and readiness (AC3.1.2; BR3.2, BR3.3; NFR1.13, NFR3.5; S3, P5).**
  - Red, with `HSM_AUDIT_PATH` unset and the temp dir redirected: a fresh start creates `hsm-demo-<uid>` with mode 0700 and leaves the parent's mode unchanged; a pre-existing directory with group/other access, a symlink, and (where possible) a foreign-owned directory each fail the start; a corrupt trail at an explicit `HSM_AUDIT_PATH` fails the start with the audit reason; an explicit `HSM_AUDIT_PATH` is passed through.
- [x] **Step 6 — One backend per process (AC3.2.1, AC3.2.3; BR2.1; NFR2.3, NFR2.4; SC1).**
  - Red: two calls return the same address; a different port on reuse is ignored; two threads behind a barrier get the same address and exactly one server exists.
- [x] **Step 7 — Liveness and replacement (BR2.2–BR2.4; NFR2.2, NFR3.3, NFR3.4, NFR4.3; P2, P6, R1, R2).**
  - Red: `LIVENESS_TIMEOUT_S == 0.5`; a refused connect and a simulated timeout give not live; a closed-port check returns in under 1.5 s; after the server is stopped, `current()` is `None` and the next `start()` closes the old socket, logs the P6 warning and returns a new running handle; an audit trail made unavailable at runtime makes the instance not live and the next start reconfigures it; a forced bind failure returns failed once with no retry.
- [x] **Step 8 — Logging (NFR4.2; O1).**
  - Red: `caplog` on `mock_hsm.embedded` shows a WARNING with the cause on every failed start and an INFO on a successful one, and never the secret value.
- [x] **Step 9 — Client address from the embedded backend (AC3.1.2; BR4.1, BR4.2; NFR3.6; R4).**
  - Red: `session.client_for(user_id)` uses `current().address`; with no live backend it raises `BackendNotRunning`; a guard test shows no `dashboard/` module imports `HSM_BASE_URL`.
  - Green: change `client_for`; drop the import from `dashboard/app.py`.
- [x] **Step 10 — Dashboard wiring, Screen 4 and caption (AC3.1.1, AC3.2.2, AC3.3.1, AC3.3.3; BR5.1–BR5.4; NFR4.4, NFR5.1; P3, P7).**
  - Red (`AppTest`): with the start forced to fail, the main area shows exactly "The demo backend didn't start. Reload the page or try again later." under the title, with no tabs, persona login or site picker, and the log holds the cause; with a running backend, the caption shows its address; repeated reruns leave one backend; the `URLError` text matches P3.
  - Green: `run()` calls the start first (before `main()`), renders Screen 4 on failure, builds the caption from `current()`.
- [x] **Step 11 — Concurrency and start time (NFR2.1, NFR2.5; P1, SC2).**
  - Red: one fresh start completes in under 2 s; 10 concurrent authenticated GETs from separate threads all return 200.
- [x] **Step 12 — Separate backend unchanged (AC3.4.1; BR6.1; NFR3.7).**
  - Run `tests/test_mcp_tools.py`, `tests/test_hooks.py` and `tests/test_secret_entry_points.py` unchanged; all pass.
- [x] **Step 13 — Docs (US10.1, AC10.1.3).** Update `CLAUDE.md` (architecture paragraph and the dashboard command: the dashboard runs its own backend; `HSM_BASE_URL` is for the MCP server and hooks), `README.md` and `dashboard/README.md` (no separate backend needed for the dashboard).
- [x] **Step 14 — Verification and traceability.** Run the unit command, the full suite `python3 -m pytest tests/ -q`, `ruff check .`, `ruff format --check .`, and `coverage run -m pytest tests/ -q && coverage combine -q && coverage report`. The test count stays at or above `.test-floor` and coverage at or above `.coverage-floor`; neither floor file is edited.

## Commits

After generation, the human is asked before the commit. One commit through `/commit` on the intent branch: "Run the mock backend inside the dashboard process", with its tests. No pull request is opened for U2 alone; the intent ships as one pull request at the end (team.md Way of Working).

## Story Traceability

| Story | Steps |
|-------|-------|
| US3.1 Dashboard runs with its own backend | 3, 5, 9, 10 |
| US3.2 Only one backend per process | 6, 10 |
| US3.3 Backend failure is explained plainly | 4, 5, 7, 8, 10 |
| US3.4 Separate backend still works | 12 |
| US10.1 Docs (U2 share) | 13 |

## Assumptions & Open Questions

- AC3.3.2's "Sign out" half is verified by U3's tests; U2 verifies the rest of AC3.3.2 (no error type, trace or address on Screen 4).

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
