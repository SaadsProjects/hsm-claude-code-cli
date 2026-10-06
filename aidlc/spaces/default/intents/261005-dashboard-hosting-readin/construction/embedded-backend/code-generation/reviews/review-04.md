## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T10:51:50Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | dashboard/app.py `run()` and tests/test_dashboard_embedded.py `_assert_only_screen_4` | Screen 4 now also carries the Account section (U3) and the build caption (U4) in the sidebar. The main area is still only the failure text, as contracts C4 and C5 intend. The U2 plan wording is superseded on this point. | Note at the unit gate that U3 and U4 amended Screen 4. No code change. | Unresolved |
| R-02 | Minor | tests/test_dashboard_embedded.py `test_a_real_start_failure_logs_the_cause_and_keeps_it_off_the_screen` | The real-failure case uses an unusable audit path because a missing secret now stops at the gate first. Coverage is preserved. | None. | Accepted risk |
| R-03 | Minor | dashboard/app.py `run()`, `except embedded.BackendNotRunning` | A backend lost mid-render removes the reset banner and adds the Screen 4 text. Anything `main()` already drew before the failing read, such as the sidebar persona panel and the unsaved-write notice, stays on the page. The main area is therefore not strictly "only" Screen 4 in that path. The risk is cosmetic, because no data is shown and the next rerun replaces the backend. | Optional: draw the main body into a container that `run()` can empty, or state in dashboard/README.md that sidebar content may remain. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| `.venv/bin/ruff check .` | PASS ("All checks passed!") | Lint is clean. |
| pytest on test_embedded_backend, test_dashboard_embedded, test_mcp_tools, test_hooks and test_secret_entry_points | PASS (75 passed) | The U2 guarantees and the separate-backend regressions hold in the final tree. |
| `grep HSM_BASE_URL dashboard` | Only docstring and README mentions | dashboard/ never reads HSM_BASE_URL. |

### Summary

U2's guarantees hold in the final tree.
- **Loopback and one instance:** `mock_hsm/embedded.py` binds only `127.0.0.1` and uses one lock-guarded process-wide holder.
- **Gate ordering:** `run()` calls `auth_gate.gate()` and stops on a non-ALLOW outcome before `embedded.start()`.
- **Failed start:** a failed start renders only the fixed Screen 4 text in the main area, plus the deliberate Account section and build caption in the sidebar.
- **Lost backend:** a backend lost mid-render drops the reset banner and shows the Screen 4 text, with only the cosmetic caveat in R-03.
- **Separate backend:** the separate backend path is covered by the passing MCP and hook tests.
