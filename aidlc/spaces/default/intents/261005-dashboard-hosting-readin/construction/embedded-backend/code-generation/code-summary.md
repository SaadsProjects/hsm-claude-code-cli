# Code Summary — U2 embedded-backend

## Files Changed

Uncommitted on branch `dashboard-hosting`, cut from `secret-fail-closed` because pull request #6 had not merged (plan P8); it is rebased onto `main` once #6 merges.

| File | Change |
|------|--------|
| `mock_hsm/embedded.py` (new) | `BackendHandle`, `BackendNotRunning`, a lock-guarded process-wide holder, `start(port=0)` and `current()`. Loopback only; secret check first; private audit directory (`<temp>/hsm-demo-<uid>`, created 0700, a pre-existing loose, symlinked or foreign-owned directory refused); audit read-back; liveness (thread alive, 0.5 s TCP connect, audit usable); bounded retire of a dead instance; logging on `mock_hsm.embedded`. Test helpers `reset_for_tests()` and `bound_address()` follow the existing `writes.reset_for_tests()` pattern. |
| `mock_hsm/audit.py` | Adds the read-only `unavailable_reason()`. |
| `dashboard/session.py` | `client_for` takes its address from `embedded.current()`; raises `BackendNotRunning` when none is live. |
| `dashboard/app.py` | Drops the `HSM_BASE_URL` import; `run()` starts the backend first and renders Screen 4 on failure; the caption reads `current()` (`Backend: not running` when none); the `URLError` text no longer names an address or start command. |
| `CLAUDE.md`, `README.md`, `dashboard/README.md` | The dashboard runs its own backend; `HSM_BASE_URL` is for the MCP server and hooks. |
| `tests/test_embedded_backend.py` (new, 33 tests), `tests/test_dashboard_embedded.py` (new, 8 tests) | Unit and `AppTest` coverage of every behaviour above. |

## Key Implementation Decisions

- Plan decisions P1–P9 applied. No cache clear on replacement (data lives in module state); liveness includes the audit read-back; the caption and error text follow P3.
- The `AppTest` seam (P7) patches `mock_hsm.embedded.start`, because `AppTest` runs `app.py` as a script; unpatched suites start a real backend using conftest's per-test `HSM_AUDIT_PATH`, and no `hsm-demo-*` directory appears in the real temp directory.
- A failed handle is never stored, so `current()` stays `None` after a failure.
- The serve loop polls every 0.1 s; `SHUTDOWN_WAIT_S` is 1.0.

## Test Coverage

- Unit command: 41 passed.
- Full suite: 922 passed, 0 failed, 12 skipped (baseline 881); test floor 745.
- Coverage 96.86% total against the 95.00 floor; `mock_hsm/embedded.py` 100%. Floor files, `.coveragerc` and `ruff.toml` unchanged; no `pragma: no cover` or `nosec`.
- `ruff check` and `ruff format --check` clean. Python 3.10 was not run locally.

## Deviations from the Plan

- `run()` also catches `BackendNotRunning` and shows the Screen 4 text, so a backend lost between the start and the sidebar's first load shows no stack trace. Not in the plan; tested.
- The `URLError` reason is passed through the existing `escape_md`.
- Four extra branch tests (existing valid directory, existing non-directory, uncreatable directory, no `getuid`) were added after the first coverage run to meet the "every branch" target.
- The docs edits touch files that secret-fail-closed also changed (`CLAUDE.md`, `README.md`, `dashboard/README.md`), so secret-fail-closed's recorded review and sign-off evidence is now out of date and needs a fresh check.
