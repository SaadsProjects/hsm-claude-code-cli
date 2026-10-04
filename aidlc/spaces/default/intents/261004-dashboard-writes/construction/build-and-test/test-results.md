# Test Results — Restore dashboard writes

Run on 2026-10-04 against the working tree after Code Generation. Commands come
from `unit-test-instructions` and the instruction files in this directory, and
each distinct command ran once. `code-generation-plan` Step 2 recorded the
baseline of 121 passed before the restore, and `code-summary` holds the
per-layer results from the restore itself.

## Build

| Check | Result |
|-------|--------|
| `.venv/bin/python -m pip check` | No broken requirements found |
| Import check (`mock_hsm.server`, `mock_hsm.writes`, `mock_hsm.audit`, `agents.hsm_client`, `dashboard.app`) | OK; streamlit 1.64.0 |
| `.venv/bin/ruff check .` | All checks passed |

## Tests

| Command | Passed | Failed | Skipped | Time |
|---------|--------|--------|---------|------|
| `pytest tests/ -q` (full suite) | 735 | 0 | 12 | 86.4 s |
| `pytest tests/test_dashboard_data.py -q` | 24 | 0 | 0 | 5.1 s |
| `pytest tests/test_audit_log.py -q` | 77 | 0 | 3 | 0.7 s |
| `pytest tests/test_writes_core.py tests/test_writes_service.py -q` | 216 | 0 | 0 | 1.0 s |
| `pytest tests/test_writes_routes.py tests/test_audit_routes.py tests/test_hsm_client_writes.py -q` | 185 | 0 | 5 | 31.8 s |
| `pytest tests/test_dashboard_units.py tests/test_dashboard_app.py -q` | 136 | 0 | 4 | 38.3 s |
| `pytest tests/ -q -m perf` | 12 | 0 | 0 (735 deselected) | 7.5 s |

The per-layer commands are subsets of the full suite, so the totals are not
additive. The 12 full-suite skips are the `perf` tests, which pass when
selected.

Integration and security commands from the instruction files are subsets of the
rows above and passed within them.

## Failures

None.

## Coverage

No coverage tool is configured and no coverage floor applies in this scope.
Requirement-level coverage is in `cross-unit-traceability.md`.
