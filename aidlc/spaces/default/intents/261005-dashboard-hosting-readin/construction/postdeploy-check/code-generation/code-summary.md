# Code Summary — U5 postdeploy-check

## Files

| File | Change | What it holds |
|------|--------|---------------|
| `scripts/postdeploy_check.py` | Created | `main(argv)` with the C8 exit codes (0, 1, 2, 3), `classify(state)`, selectors built from `dashboard.markers`, the host wake-wording constants, and the browser function. The browser function searches every frame, presses the host's wake button at most once, and retries while the page is waking. Playwright is imported lazily |
| `.github/workflows/postdeploy.yml` | Created | `workflow_dispatch` only, with inputs `url` and `timeout`. Permissions are `{}` at the top and `contents: read` on the job; there are no secrets. Actions are SHA-pinned, checkout uses `persist-credentials: false`, and inputs pass through `env`. Job `postdeploy-check`, not a required check |
| `.github/workflows/ci.yml` | Modified (`browser-tests` only) | The watch list adds `requirements-dev.txt`, `.github/workflows/ci.yml` and `dashboard/app.py`. Chromium is cached by Playwright version and installed only when tests run. The run is now `python -m pytest tests/ -m browser -q --reruns 1`, so "no tests ran" fails. The job name is unchanged |
| `requirements-dev.in`, `requirements-dev.txt` | Modified | `playwright==1.63.0`, plus greenlet and pyee, hash-pinned. The runtime lock is unchanged |
| `tests/browser_app.py` | Created | Test-only entry script: patches `auth_gate.current_identity` from an environment-variable JSON, then runs `dashboard/app.py` |
| `tests/test_postdeploy_check.py` | Created | Usage errors, `classify`, selectors, and the AST read-only scan with its self-tests |
| `tests/test_postdeploy_browser.py` | Created (`browser`) | Harness health; the check passing on Screen 1; exit 1 against a tabs-without-gate double and against a plain page; exit 3 on a closed port; Screen 2 for a verified but unlisted email and for an unverified one |
| `tests/test_ci_browser_watch.py` | Created | The required paths, every browser test file, and the project sources those files import or launch are all on the watch list; no test carries both `perf` and `browser` |
| `tests/test_postdeploy_workflow.py` | Created | Workflow trigger, permissions, no secrets, SHA pins, inputs through `env`, plus a self-test proving the check catches an input spliced into a command |
| `README.md`, `dashboard/README.md`, `CLAUDE.md` | Modified | Running the check by hand and from GitHub, its exit codes, and the Chromium install for browser tests |

## Key Implementation Decisions

- K1–K11 are implemented as planned. The deviations are listed below.
- A page whose body stays empty counts as "didn't answer" (exit 3). A page that shows other text fails at once (exit 1).
- A Playwright launch error is exit 1 with a `FAIL:` line.
- The workflow tests read the YAML as text, because PyYAML is not a declared dependency.

## Test Coverage Summary

| Measure | Result |
|---------|--------|
| Ordinary unit command (3 files) | 54 passed (re-run by the conductor after generation) |
| Browser tests (`-m browser`) | 8 passed, about 37 s (re-run by the conductor) |
| Full suite | 1165 passed, 21 skipped (baseline 1111 passed, 13 skipped; `.test-floor` 745). The extra skips are the 8 browser tests |
| Coverage | 97% total (`.coverage-floor` 95.00). `scripts/` and `tests/` aren't measured |
| `ruff check .` / `ruff format --check .` | All checks passed / 534 files already formatted (re-run by the conductor) |
| `scripts/check_workflows.py .github/workflows` | ok (2 files) (re-run by the conductor) |
| Lock check | Both locks match their inputs |
| actionlint | Not run locally (see deviations). CI's required `workflow-lint` job runs it |

### Red evidence (TDD)

| Step | Failing command | Failure |
|------|-----------------|---------|
| 3 | `pytest tests/test_postdeploy_check.py -q` | `FileNotFoundError: … scripts/postdeploy_check.py` |
| 4 | same | `AttributeError: module 'postdeploy_check' has no attribute 'WAKE_WORDING'` |
| 5 | same, with the scanner stubbed | 13 failed, e.g. `test_the_scan_catches_each_forbidden_pattern[fill]` |
| 6 | `pytest tests/test_postdeploy_browser.py -m browser -q` | `RuntimeError: the app exited early with code 2 … File does not exist: …/tests/browser_app.py` |
| 7 | same | 4 failed: `assert 1 == 0`, `IndexError`, `assert 1 == 3` |
| 8 | same, refusal cases | Passed on the first run, because U3 built the gate. The assertion was shown to fail once, from a scratch run with an allowed identity (`TimeoutError … waiting for locator`) |
| 9 | `pytest tests/test_ci_browser_watch.py -q` | 5 failed: `dashboard/app.py is not on the browser-tests watch list`, and the same for `requirements-dev.txt` and `ci.yml` |
| 10 | `pytest tests/test_postdeploy_workflow.py -q` | 5 failed: `FileNotFoundError: … postdeploy.yml` |

## Deviations from the Plan

- **actionlint not run locally.** It isn't installed, and a downloaded copy was blocked by a workflow hook, so it was removed rather than worked around. The required `workflow-lint` job runs actionlint on the pull request.
- **`APP_TABS` not used by the app.** `dashboard/app.py` doesn't wrap its real tabs in an `APP_TABS` block, so the check also treats any `[role="tab"]` as not gated (K2 allows this). The `APP_TABS` selector is exercised by the ungated test double.
- **Selectors confirmed.** The `st-key-<key>` class assumption holds in Streamlit 1.64.0, and the browser tests find the gate screens by it.

## Fixes from the Unit Review

The architecture review was READY with one Major and three Minor findings. The human chose to fix R-01 and R-02, each test first, before committing.

- **R-01 (Major): a passing check before the page finished drawing.** A gate that showed the sign-in screen and then added tabs used to pass.
  - Red: a test app that renders the sign-in screen, waits 1.5 s, then adds tabs. The check exited 0.
  - Fix: after the sign-in screen first appears, the check waits until Streamlit's running icon (`[data-testid="stStatusWidgetRunningIcon"]`) is gone from every frame and the page has stayed the same for 2 s. It then gathers the state again and classifies it. Tabs appearing during the wait fail the check at once, and a timeout never passes.
  - Result: the leaky app now gives exit 1. A scratch run with a 4 s delay also failed, as it should.
- **R-02 (Minor): a frame error could give a false pass.** Each frame's reads now count only if all of them succeed. Any failed read makes the state unreliable, which `classify` reports as `unsettled`, and an unsettled page is polled again. A page that never settles exits 3 and never 0. Red: unit tests with fake frames where a tab query raises (`'PageState' object has no attribute 'reliable'`).
- **R-03 and R-04 are recorded as known limits, not fixed.**
  - R-03: the watch-list meta-test follows only the browser tests' direct imports. Files that `dashboard/app.py` imports aren't on the watch list, as `team.md` writes it.
  - R-04: the wake click isn't limited to the host's top frame. It runs only on a waking page.

After the fixes: 57 ordinary tests and 9 browser tests pass (the happy-path browser test now takes about 4.7 s), the full suite gives 1168 passed and 22 skipped, and ruff and `check_workflows.py` are clean. `dashboard/README.md` also gained one sentence on the settle wait and the widened exit 3.

## Fixes from the Commit Review

The `/commit` code reviewer found five more issues. The human chose to fix all of them, each test first, before committing. The fixes are in commit `e436355`.

1. **Running-script guard in embed mode.** Streamlit hides the running icon at `/?embed=true`. The check now also treats `[data-testid="stApp"][data-test-script-state="running"]` in any frame as a running script. The leaky-gate test now sleeps 4 s, longer than the quiet window, and runs at `/` and at `/?embed=true`. The embedded case exited 0 before the fix and exits 1 now.
2. **A slow page was reported as broken.** When the overall `--timeout` cuts the settle window short, the check exits 3 ("may still be starting"). It exits 1 for a page that isn't the app only after a full settle window. Unit tests cover both branches.
3. **The watch list follows imports transitively.** The meta-test now follows project imports and launched scripts all the way down, and requires `tests/conftest.py`. The `browser-tests` pattern now covers every `.py` file under `agents/`, `dashboard/` and `mock_hsm/`, plus `scripts/postdeploy_check.py`, `tests/*browser*`, `tests/conftest.py`, `requirements-dev.txt` and `ci.yml`. This supersedes the earlier R-03 limit. `team.md`'s written watch list is now narrower than what CI enforces, and needs updating through the practices or learnings path.
4. **Exit 4 for a broken browser.** A Playwright that is missing or fails to launch, or a Playwright error during the run, now exits 4 instead of 1. Codes 0–3 are unchanged, an additive change to contract C8, and exit 4 is documented.
5. **Fixtures.** All test servers share one `stop()` helper (terminate, wait, kill), and `free_port()` explains why it picks the port itself.

After the fixes: 63 ordinary tests and 10 browser tests pass, the full suite gives 1174 passed and 23 skipped, and ruff and `check_workflows.py` are clean.

## Open Items for the Human

- The K3 sleep and wake wording, and the wake button, are confirmed only by running the check against staging (U6).
- Commit through `/commit` and push to draft PR #7, both when you give the go-ahead. CI's `workflow-lint` will be the first actionlint run on `postdeploy.yml`.
- As agreed, this unit edits `ci.yml` and the shared docs, so the earlier units' reviews go stale and code generation gets one more restart.
