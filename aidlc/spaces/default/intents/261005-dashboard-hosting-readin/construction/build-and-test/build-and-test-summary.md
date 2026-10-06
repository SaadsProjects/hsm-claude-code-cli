# Build and Test Summary — Dashboard Hosting Readiness

## Sources

- Per-unit code-generation plans (Testing Contracts), unit-test instructions and code summaries for U1–U6
- Per-unit `nfr-requirements/` and `nfr-design/` for U1 secret-fail-closed, U2 embedded-backend and U3 sign-in-gate. U4–U6 had no NFR stages; their targets come from their Testing Contracts.
- `memory/team.md` Testing Posture; `test-results.md`; `cross-unit-traceability.md`

## Overall Status

- **Build:** success. Every static gate is clean (ruff, format, workflows, burned secret, locks, bandit, pip-audit).
- **Tests:** 1195 passed, 0 failed, 23 skipped by design (`perf` and `browser` run separately: 13 and 10 passed). Coverage 97.07%.
- **Hosted:** staging (`https://hsm-stg.streamlit.app`) passes the post-deploy check locally and in GitHub. The owner's allowlisted sign-in reached the dashboard, and a non-allowlisted verified account was refused.
- **Test strategy:** Standard. Integration instructions generated; performance and security instructions generated too, because the NFR stages set performance and security targets.

## Test Type Inventory

| Type | File | Runs where |
|------|------|-----------|
| Unit and `AppTest` | per-unit `unit-test-instructions.md` | Every PR, `tests (3.10)` and `tests (3.14)` |
| Integration (in-process and subprocess boundaries) | `integration-test-instructions.md` | Same jobs |
| Browser (Playwright, identity seam replaced) | `integration-test-instructions.md` | `browser-tests` job |
| Timing (`perf`) | `performance-test-instructions.md` | By hand only |
| Security gates and behaviour | `security-test-instructions.md` | `secrets`, `audit`, `sast`, `lock-check` jobs and the suite |
| Hosted smoke | `scripts/postdeploy_check.py`, `postdeploy` workflow | After each deploy, by hand or from GitHub |

## Coverage Expectations per Unit

| Unit | Expectation | Measured |
|------|-------------|----------|
| U1 secret-fail-closed | `mock_hsm/auth.py` and entry points fully exercised; repo ≥ `.coverage-floor` | Repo 97.07% |
| U2 embedded-backend | `mock_hsm/embedded.py` covered, including failure paths | Repo 97.07% |
| U3 sign-in-gate | Gate and bridge covered through the seam (no browser credit) | Repo 97.07% |
| U4 build-and-banner | `agents/build_info.py` and the new `app.py` helpers fully covered | Repo 97.07% |
| U5 postdeploy-check | `scripts/` unmeasured by rule; held to its own 63 ordinary + 10 browser tests | 63 + 10 passed |
| U6 staging-app | No measured code; runbook test only | 23 passed (on `raise-floors`) |

## Target Verification Matrix

| Target ID | Source | Expected | Actual | Evidence | Owning Stage | Verdict |
|-----------|--------|----------|--------|----------|--------------|---------|
| NFR1.1 | U1 security-requirements | No secret in source; exclusions empty | Check ok; `TEMPORARY_EXCLUSIONS = ()` | `check_burned_secret.py`; CI `secrets` | build-and-test | Met |
| NFR1.2 | U1 security-requirements | 31 bytes refused, 32 accepted | Tests pass | `tests/test_signing_secret.py` (56 passed with entry points) | build-and-test | Met |
| NFR1.3 | U1 security-requirements | No fallback secret | Mint/verify refuse unset | same | build-and-test | Met |
| NFR1.4 | U1 security-requirements | Hook denies without secret | Deny naming the variable | `tests/test_secret_entry_points.py`, `tests/test_hooks.py` | build-and-test | Met |
| NFR1.5 | U1 security-requirements | Backend and start script refuse; 503 mid-run | Tests pass | `tests/test_secret_entry_points.py` | build-and-test | Met |
| NFR1.6 | U1 security-requirements | Secret never in messages | Tests pass | `tests/test_signing_secret.py` | build-and-test | Met |
| NFR1.7 | U1 security-requirements | Burned value refused by hash | Tests pass | `tests/test_signing_secret.py` | build-and-test | Met |
| NFR1.8 | U1 security-requirements | No secret in committed config | Tests pass; gitleaks green in CI | `tests/test_secret_entry_points.py`; CI `secrets` | build-and-test | Met |
| NFR1.9 | U1 security-requirements | `.env.local` mode 600, git-ignored | Tests pass | `tests/test_secret_entry_points.py` | build-and-test | Met |
| NFR1.10 | U1 security-requirements | Loader never overrides, no expansion | Tests pass | `tests/test_signing_secret.py` | build-and-test | Met |
| NFR1.11 | U2 security-requirements | Loopback only | Tests pass | `tests/test_embedded_backend.py` (42 passed with dashboard_embedded) | build-and-test | Met |
| NFR1.12 | U2 security-requirements | No secret → nothing bound | Tests pass | same | build-and-test | Met |
| NFR1.13 | U2 security-requirements | 0700 audit dir; unsafe dir refused | Tests pass | same | build-and-test | Met |
| NFR1.14 | U2 security-requirements | No secret or detail on screen | Tests pass | `tests/test_dashboard_embedded.py` | build-and-test | Met |
| NFR1.21 | U3 security-requirements | Nothing before allow | Tests pass | `tests/test_dashboard_gate.py` (219 passed, U3 set) | build-and-test | Met |
| NFR1.22 | U3 security-requirements | Verified and exact allowlist match | Tests pass; real sign-ins on staging agree | `tests/test_auth_gate.py`; staging evidence | build-and-test | Met |
| NFR1.23 | U3 security-requirements | Pure decision; thin seam | AST tests pass | `tests/test_auth_gate.py` | build-and-test | Met |
| NFR1.24 | U3 security-requirements | Fails closed on every bad setting or error | Tests pass | `tests/test_auth_gate.py`, `tests/test_dashboard_gate.py` | build-and-test | Met |
| NFR1.25 | U3 security-requirements | Signing ≠ cookie secret; export wins | Tests pass | `tests/test_secrets_bridge.py` | build-and-test | Met |
| NFR1.26 | U3 security-requirements | No identity or setting in logs or screens | Tests pass | `tests/test_auth_gate.py` | build-and-test | Met |
| NFR1.27 | U3 security-requirements | Email shown literally | Tests pass | `tests/test_dashboard_gate.py` | build-and-test | Met |
| NFR1.28 | U3 security-requirements | Sign-out clears the persona | Tests pass | `tests/test_dashboard_gate.py` | build-and-test | Met |
| NFR2.1 | U2 performance-requirements | Start ≤ 2 s | Test passes | `tests/test_embedded_backend.py` | build-and-test | Met |
| NFR2.2 | U2 performance-requirements | 0.5 s liveness timeout | Test passes | same | build-and-test | Met |
| NFR2.3 | U2 performance-requirements | Reuse binds nothing new | Test passes | same | build-and-test | Met |
| NFR2.4 | U2 scalability-requirements | One backend per process | Tests pass | same | build-and-test | Met |
| NFR2.5 | U2 scalability-requirements | 10 concurrent requests succeed | Test passes | same | build-and-test | Met |
| NFR2.11 | U3 performance-requirements | Gate work ≤ 50 ms per rerun | `perf` test passes | `tests/test_dashboard_gate.py -m perf` (1 passed) | build-and-test | Met |
| NFR2.12 | U3 performance-requirements | No gate network or disk I/O | Test passes | `tests/test_dashboard_gate.py` | build-and-test | Met |
| NFR2.13 | U3 performance-requirements | No wait, retry or sleep | Test passes | same | build-and-test | Met |
| NFR3.1 | U1 security-requirements | U1 test-first; floors held on both legs | Red evidence in U1 summary; CI green | U1 code-summary; PR #6 CI | build-and-test | Met |
| NFR3.2 | U1 security-requirements | Tests generate their own secret | conftest test passes | `tests/conftest.py`; gitleaks | build-and-test | Met |
| NFR3.3 | U2 reliability-requirements | Failed start reported, one retry per rerun | Tests pass | `tests/test_embedded_backend.py` | build-and-test | Met |
| NFR3.4 | U2 reliability-requirements | Dead instance replaced once | Tests pass | same | build-and-test | Met |
| NFR3.5 | U2 reliability-requirements | Unusable audit fails the start | Tests pass | same | build-and-test | Met |
| NFR3.6 | U2 reliability-requirements | Client without backend raises | Test passes | `tests/test_dashboard_embedded.py` | build-and-test | Met |
| NFR3.7 | U2 reliability-requirements | Separate-process backend unchanged | MCP and hook tests pass | `tests/test_mcp_tools.py tests/test_hooks.py` (8 passed) | build-and-test | Met |
| NFR3.8 | U2 reliability-requirements | Floors held on 3.10 and 3.14 | 1195 ≥ 745; 97.07% ≥ 95.00% | `test_floor.py`, `coverage_gate.py`; PR #7 CI | build-and-test | Met |
| NFR3.11 | U3 performance-requirements | Gate covered via seam; floors held | Coverage 97.07% | `coverage_gate.py` | build-and-test | Met |
| NFR4.1 | U1 security-requirements | Refusals name the variable and rule | Tests pass | `tests/test_signing_secret.py` | build-and-test | Met |
| NFR4.2 | U2 observability-requirements | Start failure logged, never on screen | Test passes | `tests/test_embedded_backend.py` | build-and-test | Met |
| NFR4.3 | U2 observability-requirements | Replacement logged | Test passes | same | build-and-test | Met |
| NFR4.4 | U2 observability-requirements | Caption shows live address | Test passes | `tests/test_dashboard_embedded.py` | build-and-test | Met |
| NFR4.11 | U3 security-requirements | Refusals logged once, no identity | Tests pass | `tests/test_auth_gate.py` | build-and-test | Met |
| NFR5.1 | U2 observability-requirements | Screen 4 text under h1, no tabs | Test passes | `tests/test_dashboard_embedded.py` | build-and-test | Met |
| NFR5.11 | U3 security-requirements | One h1, text, keyboard button per screen | Tests pass | `tests/test_dashboard_gate.py` | build-and-test | Met |
| NFR7.1 | U1 security-requirements | No new dependency; locks and audit green | Lock check ok; audit ok | `test-results.md` § Build Status | build-and-test | Met |
| NFR7.2 | U2 security-requirements | Embedded module stdlib only | AST test passes | `tests/test_embedded_backend.py` | build-and-test | Met |
| NFR7.11 | U3 security-requirements | `streamlit[auth]==1.64.0` hash-pinned; audit clean | Lock ok; audit ok | `requirements.txt`; `test-results.md` | build-and-test | Met |
| TC-METHOD | U1–U6 Testing Contracts | TDD: Red recorded before Green | Red evidence in every unit's summary | `construction/*/code-generation/code-summary.md` | build-and-test | Met |
| TC-VOLUME | Testing Contracts (Standard) | 5–8 tests per component, plus integration | 1195 tests; every component has its own file | `test-results.md` | build-and-test | Met |
| TC-COV-80 | Testing Contracts (feature scope floor) | ≥ 80% line coverage | 97.07% | `coverage_gate.py` | build-and-test | Met |
| TC-CI | Testing Contracts (feature scope floor) | Selected tests run in CI before merge | PR #7 merged with all 10 required checks green | CI run 37457482148 | build-and-test | Met |
| TC-TEST-FLOOR | team.md Testing Posture | Passing count ≥ `.test-floor` | 1195 ≥ 745 | `scripts/test_floor.py` | build-and-test | Met |
| TC-COV-FLOOR | team.md Testing Posture | Coverage ≥ `.coverage-floor` | 97.07% ≥ 95.00% | `scripts/coverage_gate.py` | build-and-test | Met |
| TC-FLOOR-RAISE | team.md Testing Posture | Both floors raised with headroom in the intent's final PR | `.test-floor` 1100 (CI legs passed 1197), `.coverage-floor` 96.00 (measured 97.07%) | PR #9 merged as `fc820e2`, all 10 required checks green (run 37471893300) | build-and-test | Met |

## Readiness Assessment

- **Build-ready:** yes.
- **Test-ready:** yes. Every command passes and every target above is Met. The floors were raised in PR #9 (`fc820e2`).
- **Deployment-ready:** staging is deployed and proven. Production stays with the parked deploy intent.

## Known Limitations and Outstanding Items

- **NFR2 (30 s from a sleeping app):** owned by performance-validation, which needs the app asleep.
- **Redeploy-on-merge (runbook step (e)):** proven by the first merge after the app exists. That is the `raise-floors` PR.
- **FR8.7 / AC8.4.1:** the bare `noqa` at `.claude/hooks/lint_before_commit.py:372`, for the human to fix by hand.
- **Record items, accepted at checkpoints, not changed here:** U4's summary describes its pre-fix design (R-03); contract C8 doesn't list exit 4 (U5 R-05); `team.md`'s browser watch list is narrower than CI's (U5 R-06, via the practices or learnings path); U6's summary still has its pre-evidence "Still to Do" text and old counts (U6 R-06).
- **Cross-unit traceability:** fails the strict rule only because unit files cite ACs and NFRx.y rather than parent FR/NFR IDs. See `cross-unit-traceability.md`.
