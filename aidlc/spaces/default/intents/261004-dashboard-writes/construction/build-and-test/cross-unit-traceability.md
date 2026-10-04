# Cross-Unit Traceability — Restore dashboard writes

## Verdict

**PASS.** No upstream FR, NFR or AC IDs exist in this workflow: the approved
plan skipped requirements-analysis and user-stories, so there is no
`requirements.md` or `stories.md` to enumerate. The requirement set is the
`code-generation-plan`'s own R1–R8, traced in the stage-level
`construction/code-generation/traceability.json`. All eight have status `OK` and
an existing target file. `unit-test-instructions` and `code-summary` agree with
the mapping below.

## Coverage

| ID | Requirement | Owner | Target | Exists | Status |
|----|-------------|-------|--------|--------|--------|
| R1 | Writes to mock records for in-scope personas only | code-generation (stage-level) | `mock_hsm/writes.py` | yes | OK |
| R2 | Login/session per persona; 403 outside scope | code-generation (stage-level) | `tests/test_writes_routes.py` | yes | OK |
| R3 | Append-only audit trail, readable via `/audit` | code-generation (stage-level) | `mock_hsm/audit.py` | yes | OK |
| R4 | Publish/PO fail closed (503) when audit unavailable | code-generation (stage-level) | `tests/test_audit_routes.py` | yes | OK |
| R5 | Client write methods with bounded retry | code-generation (stage-level) | `agents/hsm_client.py` | yes | OK |
| R6 | Manage data and Audit tabs; no publish/submit action | code-generation (stage-level) | `tests/test_dashboard_app.py` | yes | OK |
| R7 | Existing safety gates unchanged | code-generation (stage-level) | `tests/test_hooks.py` | yes | OK (partial, see below) |
| R8 | Existing suite stays green | code-generation (stage-level) | `tests/test_mcp_tools.py` | yes | OK |

## Uncovered or partial elements

- **R7:** `tests/test_hooks.py` covers how the hooks behave. Nothing tests that
  the `ask` rules and the hook registration (in gitignored
  `.claude/settings.local.json`) are present; this was checked by reading the
  files. This was review finding R-02 at Code Generation, which you accepted.
