# Code Generation Plan — U4 build-and-banner

## Sources

- `inception/requirements-analysis/requirements.md` FR5.1, FR5.2, FR6.1, FR6.2, NFR3, NFR5
- `inception/user-stories/stories.md` US5.1 (AC5.1.1–AC5.1.3), US5.2 (AC5.2.1–AC5.2.4), US6.1 (AC6.1.1, AC6.1.2)
- `inception/units-generation/unit-of-work.md` U4; `inception/domain-design/components.md` BuildInfo and DashboardShell
- `inception/contract-design/contract-summary.md` C5 (frame slots) and C6 (markers `RESET_BANNER`, `BUILD_CAPTION`)
- `inception/refined-mockups/mockups.md` Screen 3 (banner copy, build caption) and Screen 4 (Account section plus build caption)
- `memory/team.md` Code Style (`agents/` is framework-free; file placement `agents/build_info.py`), Deployment (build identifier: git SHA, source fingerprint fallback), Testing Posture; `memory/project.md` corrections (the post-deploy check doesn't assert the build)
- Current code: `dashboard/app.py` (`run`, `main`, the backend caption), `dashboard/markers.py`, `tests/gate_app.py`
- The human chose to plan this unit from the requirements, because the code-generation restart skipped its design stages. The decisions below stand in for them.

## Design Decisions Settled in This Plan

| # | Decision | Resolves |
|---|----------|----------|
| B1 | `agents/build_info.py` reads the commit from the `.git` directory with file reads only: `HEAD`, then the named ref under `refs/`, then `packed-refs`; a detached `HEAD` holds the SHA itself; a `.git` file (`gitdir: …`, a worktree) is followed. It runs no `git` subprocess, so no git binary is needed and bandit has nothing to flag. Anything unreadable or malformed falls back to the fingerprint (B2) | FR5.1, AC5.1.1 |
| B2 | The fingerprint is SHA-256 over the sorted relative paths and bytes of the source files the app runs: `*.py` under `agents/`, `dashboard/`, `mock_hsm/` and `mcp_server/`, plus `requirements.txt` and `.streamlit/config.toml`. It skips `__pycache__`, `*.pyc` and anything under `mock_hsm/audit/`, so files the app writes while running never change it | AC5.2.1–AC5.2.3 |
| B3 | `BuildInfo` is a frozen dataclass: `kind` (`"commit"` or `"fingerprint"`), `value` (the full SHA or hex digest) and `label` ("Build abc1234", the first 7 characters of the commit, or "Build src-1a2b3c4d", the first 8 of the fingerprint). `build_info(root=None)` computes it once per process (`functools.lru_cache` on the resolved root), because the build can't change without a restart | FR5.1, mockups Screen 3 |
| B4 | `python -m agents.build_info` prints the label, exactly what the app shows | AC5.1.3 |
| B5 | The build caption renders at the bottom of the sidebar as `st.caption(label)` inside `st.container(key=markers.BUILD_CAPTION)`. On Screen 3 it renders after `main()` returns, on every path that reaches the end of the frame. On Screen 4 it renders under the Account section. It never renders on a gate screen | FR5.2, AC5.1.2, C5 |
| B6 | The reset banner is `st.info("Demo data: changes you make are reset periodically.", icon="ℹ️")` inside `st.container(key=markers.RESET_BANNER)`. It renders once, first in `main()`'s main area, after the title and before the unsaved-write notice, the site caption and the tabs. So it shows on every tab and also before a persona logs in. Screen 4 and the gate screens don't show it | FR6.1, AC6.1.1, AC6.1.2, C5 |
| B7 | If computing the build raises anyway, `app.py` shows "Build unknown" and logs the error type. A caption must never break the signed-in frame. This is the only broad catch, with `# noqa: BLE001 -- <reason>` | NFR1 spirit (no crash), team.md broad-exception rule |
| B8 | No pull request or push without the human's go-ahead. The commit goes through `/commit` on `dashboard-hosting` | team.md Way of Working |

## Code Generation Steps

Each behaviour follows Red (write the failing tests, run them, record the failing output), then Green (the least code that passes), then Refactor (with the suite green).

- [x] **Step 1 — Runner and baseline.** Run `python3 -m pytest tests/test_dashboard_gate.py tests/test_dashboard_app.py -q` and the full suite once. Record the counts.
- [x] **Step 2 — Commit SHA from `.git` (US5.1; AC5.1.1; B1, B3).**
  - Red, in `tests/test_build_info.py` with throwaway `.git` trees in `tmp_path`:
    - a branch `HEAD` with a loose ref;
    - a ref only in `packed-refs`;
    - a detached `HEAD`;
    - a `.git` file pointing elsewhere;
    - a real check that `build_info()` on this repository equals `git rev-parse HEAD`, skipped when `git` isn't on `PATH`.
  - Green: `agents/build_info.py` with `BuildInfo`, `_commit_sha(root)` and `build_info(root=None)`.
- [x] **Step 3 — Fingerprint fallback (US5.2; AC5.2.1–AC5.2.3; B2).**
  - Red, on a copied source tree without `.git` in `tmp_path`:
    - two computations are equal and `kind == "fingerprint"`;
    - changing one `.py` file changes it;
    - adding `__pycache__/x.pyc`, a stray `.pyc` or `mock_hsm/audit/audit.jsonl` doesn't;
    - a malformed `.git` (a `HEAD` naming a missing ref) falls back to the fingerprint.
  - Green: `_fingerprint(root)` and the fallback.
- [x] **Step 4 — Label and command line (AC5.1.3, AC5.2.4; B3, B4).**
  - Red:
    - the labels "Build " plus 7 characters and "Build src-" plus 8 characters;
    - `python -m agents.build_info` (subprocess, repository root) prints the same label as `build_info().label`;
    - an AST test shows `agents/build_info.py` imports only the standard library, with no Streamlit.
  - Green: the `__main__` block.
- [x] **Step 5 — Build caption in the app (US5.1; AC5.1.2; B5, B7).**
  - Red, through `tests/gate_app.py`, allowed:
    - the last sidebar block carries `BUILD_CAPTION` and reads `build_info().label`, both before and after a persona login;
    - on Screen 4 (start forced to fail), the sidebar shows the Account section and then the build caption;
    - no gate screen shows it;
    - with `build_info` patched to raise, the caption reads "Build unknown", the frame still renders, and the log holds only the error type.
  - Green: `_build_caption()` in `app.py`, called from `run()`.
- [x] **Step 6 — Reset banner (US6.1; AC6.1.1, AC6.1.2; FR6.2; B6).**
  - Red, through `gate_app`:
    - an allowed visitor sees exactly one `st.info` with the exact copy and the info icon, in a block keyed `RESET_BANNER`, rendered before the tabs and outside them;
    - it's there before a persona login and after one;
    - it's absent on Screen 4 and on every gate screen;
    - the unsaved-write notice, when present, renders below it (C5 order).
  - Green: `_reset_banner()` in `app.py`, first in `main()`'s main area.
- [x] **Step 7 — Existing suite and docs (NFR3; FR10.1).**
  - Run the dashboard test files. Update any assertion that counted sidebar or main-area elements and now meets the caption or the banner.
  - Docs:
    - `dashboard/README.md`: the build caption, `python -m agents.build_info`, the banner;
    - `CLAUDE.md`: one line on `agents/build_info.py`.
- [x] **Step 8 — Verification and traceability.** Run the unit command, then:
  - `python3 -m pytest tests/ -q`;
  - `ruff check .` and `ruff format --check .`;
  - `coverage run -m pytest tests/ -q && coverage combine -q && coverage report`.

  The test count stays at or above `.test-floor` and coverage at or above `.coverage-floor`. Neither floor file is edited.

## Commits

After generation, the human is asked before the commit. One commit through `/commit` on `dashboard-hosting`: "Show the running build and a demo-data reset banner", with its tests. Pushing to draft pull request #7 also waits for the human's go-ahead.

## Story Traceability

| Story | Steps |
|-------|-------|
| US5.1 See which build is running | 2, 4, 5 |
| US5.2 Fingerprint fallback without git | 3, 4 |
| US6.1 Reset notice above the tabs | 6 |
| US10.1 Docs (U4 share) | 7 |

## Assumptions & Open Questions

- [assumption] Streamlit Community Cloud's checkout may lack `.git` (project.md Deployment learning), and the fingerprint covers that case. The owner confirms the build on staging by signing in and reading the caption (U6). The post-deploy check doesn't assert it (project.md correction).
- [assumption] `st.info` accepts `icon="ℹ️"` in Streamlit 1.64.0, and `AppTest` exposes it as `at.info[i].icon`.

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
