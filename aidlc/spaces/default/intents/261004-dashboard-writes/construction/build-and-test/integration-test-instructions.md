# Integration Test Instructions — Restore dashboard writes

The test strategy is Minimal, which requires no separate integration suite.
This file records the integration-level tests a189674 already ships, so they
are run deliberately. Sources: `code-generation-plan` Step 10,
`unit-test-instructions` (mocking guidance: real in-process backend), and
`code-summary` (test results per layer).

## What counts as integration here

These tests start the real mock backend on local ports and talk to it over
HTTP, either directly or through `HsmClient`:

| File | Boundary exercised |
|------|--------------------|
| `tests/test_writes_routes.py` | HTTP write routes, sessions, 403 outside persona scope |
| `tests/test_audit_routes.py` | `/audit` route, 503 fail-closed on publish/PO when the trail is unavailable |
| `tests/test_hsm_client_writes.py` | `HsmClient` write methods and retry against the live server |
| `tests/test_dashboard_app.py` | Streamlit `AppTest` driving the dashboard against the backend |
| `tests/test_mcp_tools.py` | Existing MCP-protocol scenario (unchanged) |

## How to run

```bash
.venv/bin/python -m pytest tests/test_writes_routes.py tests/test_audit_routes.py tests/test_hsm_client_writes.py -q
.venv/bin/python -m pytest tests/test_dashboard_app.py tests/test_mcp_tools.py -q
```

Ports 8772, 8773 and one ephemeral port must be free.

## Expectations

All pass. No coverage floor applies in this scope.
