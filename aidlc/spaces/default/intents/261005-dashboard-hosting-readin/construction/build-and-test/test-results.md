# Test Results — Dashboard Hosting Readiness

## Sources

- Runs on 2026-10-06 at commit `e1ddc16`, the same tree as `main` at `23396d7` (`git diff e1ddc16 main` is empty), on macOS with Python 3.14 from `.venv` (installed from `requirements-dev.txt`)
- CI on PR #7 at `e1ddc16`: all 10 required checks green (run 37457482148)
- Staging evidence: `construction/staging-app/code-generation/code-summary.md` § Staging Evidence

## Build Status

**Success.** There is nothing to compile. The hash-pinned dev lock installs, and every static gate passes:

| Check | Command | Result |
|-------|---------|--------|
| Lint | `ruff check .` | All checks passed |
| Format | `ruff format --check .` | 555 files already formatted |
| Workflows | `python3 scripts/check_workflows.py .github/workflows` | ok (2 files) |
| Burned secret | `python3 scripts/check_burned_secret.py` | ok |
| Locks match inputs (CI method, starting from the committed locks) | `uv pip compile …` + `diff -u` | ok, no drift |
| SAST | `bandit … \| filter_bandit.py` | ok, no high-severity findings |
| Dependency audit | `run_pip_audit.sh \| filter_audit.py` | ok, no known vulnerabilities |
| Secret scan (gitleaks) | not installed locally | CI's `secrets` job passed on PR #7 |

A first local lock check compiled from scratch and showed `filelock` 4.0.10 → 4.0.12. That came from compiling without the committed locks, not from drift; CI's method shows no difference.

## Test Results

| Run | Total | Passed | Failed | Skipped |
|-----|-------|--------|--------|---------|
| Full suite with coverage (`coverage run -m pytest tests/ -q`) | 1218 | 1195 | 0 | 23 (13 `perf`, 10 `browser`, by design) |
| Browser tests (`-m browser`) | 10 | 10 | 0 | 0 |
| Timing tests (`-m perf`, by hand) | 13 | 13 | 0 | 0 |
| Test floor (`scripts/test_floor.py`) | — | ok: 1195 passed against floor 745 | — | — |
| Coverage gate (`scripts/coverage_gate.py`) | — | ok: 97.07% against floor 95.00% and the 80% gate | — | — |

### Per-unit commands (each distinct command run once)

| Unit | Command | Result |
|------|---------|--------|
| U1 | `tests/test_signing_secret.py tests/test_secret_entry_points.py` | 56 passed |
| U1 | `tests/test_hooks.py` | 7 passed |
| U2 | `tests/test_embedded_backend.py tests/test_dashboard_embedded.py` | 42 passed |
| U2 | `tests/test_mcp_tools.py tests/test_hooks.py` | 8 passed |
| U3 | `tests/test_dashboard_app.py tests/test_dashboard_data.py tests/test_dashboard_embedded.py` | 77 passed, 4 skipped |
| U3 | `tests/test_gate_app.py … tests/test_dashboard_embedded.py` (7 files) | 219 passed, 5 skipped |
| U3 | `tests/test_auth_gate.py -k decide` | 15 passed |
| U3 | `tests/test_dashboard_gate.py -m perf` | 1 passed |
| U4 | `tests/test_dashboard_gate.py tests/test_dashboard_app.py` | 84 passed, 5 skipped |
| U4 | `tests/test_build_info.py … tests/test_dashboard_embedded.py` (5 files) | 139 passed, 5 skipped |
| U4 | `tests/test_build_info.py -k fingerprint` | 13 passed |
| U5 | `tests/test_ci_check_workflows.py tests/test_conftest_markers.py` | 12 passed |
| U5 | `tests/test_postdeploy_check.py tests/test_ci_browser_watch.py tests/test_postdeploy_workflow.py` | 63 passed |
| U5 | `tests/test_postdeploy_browser.py -m browser` | 10 passed |
| U5 | `scripts/postdeploy_check.py http://127.0.0.1:8501 --timeout 30` | Not run as written: no app runs on 8501 here. The same check ran against browser-test apps (above) and against staging (exit 0) |
| U6 | `tests/test_postdeploy_check.py` | 37 passed |
| U6 | `tests/test_staging_runbook.py` | 21 passed |
| U6 | `tests/test_staging_runbook.py -k keys` | 2 passed |

### Failures

None.

## Coverage

97.07% total line coverage over `agents/`, `dashboard/`, `mock_hsm/`, `mcp_server/` and `.claude/hooks/` (4237 statements, 124 missed). `scripts/` and `tests/` aren't measured, as the team rule sets out.

## Hosted Evidence (staging)

| Check | Result |
|-------|--------|
| `scripts/postdeploy_check.py https://hsm-stg.streamlit.app --timeout 180` | Exit 0, PASS, 8.5 s wall time with the app awake |
| `postdeploy` workflow run 37464999295 on `main` (`23396d7`) | Success |
| Owner sign-in, allowlisted account | Dashboard reached, caption `Build 23396d7` |
| Owner sign-in, verified account not on the allowlist | The app's refusal screen |
| Check rerun about 2 minutes after PR #9 merged (`fc820e2`) | Exit 0, PASS, 8.5 s |
| Owner sign-in after the PR #9 merge | Caption read `Build fc820e2`: staging redeployed itself on merge, so runbook step (e) is closed |

## Floors Raised (follow-up pull request)

Branch `raise-floors` (from `main`) raises `.test-floor` 745 → 1100 and `.coverage-floor` 95.00 → 96.00. On that branch: 1197 passed, floor check ok against 1100; coverage gate ok at 97.07% against 96.00%. It also carries the agreed runbook fixes, with tests written first:
- First Red: 2 failed, 21 passed. Green: 23 passed.
- After the `/commit` review, one test was tightened. Red: 1 failed, 22 passed. Green: 23 passed.

It was committed as `8fd4a81` and opened as PR #9. All 10 required checks passed (run 37471893300), and it was squash-merged into `main` as `fc820e2` on 2026-10-06.
