## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-05T22:49:16Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | tests/test_dashboard_app.py (AppTest tests of dashboard/app.py), tests/test_dashboard_data.py | These existing suites now run `app.run()`, which calls `embedded.start()`. Neither file resets the holder (`reset_for_tests` appears only in the two new test files). The real embedded backend started by the first such test stays alive for the rest of the pytest process. The audit path it was configured with (the first test's temp `HSM_AUDIT_PATH`) is reused by later tests, so test state is shared across tests and the audit trail is not isolated per test. | Add an autouse fixture or conftest hook that calls `embedded.reset_for_tests()` after tests that start the real app. Alternatively, record the leak as accepted in code-summary.md. | New |
| R-02 | Minor | mock_hsm/embedded.py > `current()` / `_is_live_locked()` / `start()` | The lock is held across a TCP probe (up to 0.5 s) and across `_stop_locked()` (bounded to about 1 s plus `server_close`). `client_for` calls `current()` on every client construction, so each call takes the lock and opens a TCP connection to the app's own server. A slow or wedged probe serialises every visitor session, and each probe spawns a handler thread on the server. The code does not deadlock: the stopper thread is bounded and daemonised, and the lock is a plain Lock never re-entered. This is a latency and amplification concern, not a correctness bug, and the design accepts it (P2, NFR2.2). | Consider caching a recent liveness result for a short time, or document the per-call probe cost as accepted. | New |
| R-03 | Minor | mock_hsm/embedded.py > `_default_audit_path()` / `_check_existing_audit_dir()` | The directory check is check-then-use. It uses `lstat`, so it rejects symlinks, wrong owners and loose modes, but another process running as the same user could swap the directory between the check and `audit.configure`. A same-uid attacker already has full access, so the residual risk is negligible for this demo. `os.getlogin()` is the fallback only when `getuid` is absent (Windows) and can raise `OSError` outside `start()`'s handling. | Optionally wrap the fallback so it fails as `_AuditDirRefused`, or accept it as Windows-only and unsupported. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/embedded-backend/code-generation/code-summary.md > Deviations | The docs edits to CLAUDE.md, README.md and dashboard/README.md overlap files that the sibling unit secret-fail-closed also changed. Its recorded evidence is stale, as the summary itself notes. The unit's own manifest is complete: all nine paths match `git status`. | Track the secret-fail-closed re-check as a follow-up before the final pull request. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| pytest tests/test_embedded_backend.py tests/test_dashboard_embedded.py | 41 passed in 6.65s | Matches the claimed 41 tests. |
| ruff check . | All checks passed | Clean. |
| ruff format --check . | 474 files already formatted | Clean. |
| Manifest vs git status | The 9 manifest paths equal the changed non-aidlc paths | No unclaimed changes. |

### Summary

No Critical or Major findings. The holder is lock-guarded, the shutdown is bounded and runs on a separate thread, and the audit directory is checked with `lstat` and created 0700. The secret never reaches a log or the screen: the failure text on screen is a fixed string and the cause names only the variable. The four Minor items concern test isolation, per-call probe cost, a narrow same-user TOCTOU window, and stale sibling-unit evidence.
