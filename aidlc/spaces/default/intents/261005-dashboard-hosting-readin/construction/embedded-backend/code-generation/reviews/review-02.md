## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T04:28:14Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | dashboard/app.py `run()` and tests/test_dashboard_embedded.py `_assert_only_screen_4` | After U3 (fa3264b), Screen 4 is no longer literally the only content on the page. The sidebar now carries the Account section with Sign out, and the test was loosened from "no buttons" to "only the Sign out button". The plan's step 10 and the code-summary still describe the pre-gate shape (backend started first, no buttons). The U2 guarantees that matter still hold: the main area is exactly the Screen 4 text under the title, with no tabs, persona login or site picker, and the cause goes only to the log. The change is deliberate (D11, "every refusal screen keeps a way out") and matches team.md. | Note at the unit gate that U3 amended Screen 4 to include the Account section, so the U2 plan wording is superseded on this point. No code change. | New |
| R-02 | Minor | tests/test_dashboard_embedded.py `test_a_real_start_failure_logs_the_cause_and_keeps_it_off_the_screen` | U3 changed the real-failure case from a missing signing secret to an unusable audit path, because a missing secret now stops at the gate (Screen 5) before `embedded.start()` runs. The secret-refusal behaviour (BR3.1) is still covered at the module level in tests/test_embedded_backend.py, and the new gate-side test asserts that no backend starts. Coverage is preserved. | None. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| ruff check . | PASS ("All checks passed!") | No lint regressions from U3's edits. |
| pytest test_embedded_backend, test_dashboard_embedded, test_mcp_tools, test_hooks, test_secret_entry_points | PASS (75 passed, 16.31s) | U2's guarantees still hold. The separate backend (AC3.4.1) is unchanged and its tests pass. |
| git diff 6f9b4ce on mock_hsm/, dashboard/session.py, tests/test_embedded_backend.py | Empty | U3 did not touch the embedded module, audit.py, session.py or the U2 module tests. |
| grep HSM_BASE_URL in dashboard/ | Only comments and docs (session.py:54, app.py:12, README.md:31) | The dashboard does not read HSM_BASE_URL. |
| Reading mock_hsm/embedded.py | Loopback-only bind (HOST = "127.0.0.1"), one lock-guarded holder with a reuse check, and `start()` never raises or retries | Loopback-only, one backend per process and fail-closed behaviour are intact. |
| Gate ordering in dashboard/app.py `run()` | Header, then `auth_gate.gate()`, then `st.stop()` unless ALLOW, then `embedded.start()`. `embedded.start` is called through the module attribute, so tests can patch it (P7). | The backend starts only after the gate allows (team.md Deployment). U2's start-before-data rule (BR5.4) is preserved. |

### Summary

U2's claimed paths still match the approved plan. U3's edits to dashboard/app.py and the tests only add the sign-in gate ahead of the backend start and keep a Sign out way out on Screen 4. The embedded module, audit.py and session.py are byte-identical to the U2 commit, ruff is clean, and all 75 targeted tests pass. The two Minor notes record documented, intentional drift and need no rework.
