# Logical Components — U2 embedded-backend

## Sources

- `inception/domain-design/components.md` (EmbeddedBackend, MockBackend, DashboardShell, HsmClient)
- `inception/contract-design/contract-summary.md` C2, C3
- The other NFR design files in this directory

## Components

| Component | Location | Change in U2 | NFR patterns applied |
|-----------|----------|--------------|----------------------|
| EmbeddedBackend | `mock_hsm/embedded.py` (new) | New: `start(port=0)`, `current()`, `BackendHandle`, `BackendNotRunning`, the lock-guarded holder, audit-directory validation, liveness probe, retire | S1–S5, P1–P3, SC1, R1–R4, O1 |
| MockBackend audit | `mock_hsm/audit.py` | Adds one read-only function, `unavailable_reason()` | R3 |
| MockBackend server | `mock_hsm/server.py` | Unchanged; its handler class is hosted by EmbeddedBackend | R5 |
| DashboardShell | `dashboard/app.py` | Calls `embedded.start()` on every rerun before any data screen; renders Screen 4 on failure; caption from `current()`; clears cached reads after a replacement; drops the `HSM_BASE_URL` import and its use in the error text | O2, O3, BR2.5, BR5.4 |
| Session | `dashboard/session.py` | `client_for` takes its base address from `embedded.current()`; raises `BackendNotRunning` when none is live | R4, BR4.1 |
| HsmClient | `agents/hsm_client.py` | Unchanged; receives `base_url` | — |

## Failure Domains and Blast Radius

| Failure | Domain | Blast radius |
|---------|--------|--------------|
| Missing or bad secret | the app process | Screen 4 for every visitor until the secret is fixed and the app reloads |
| Audit directory or trail unusable | the app process | Screen 4 for every visitor |
| Server thread dies | the app process | One rerun detects it and replaces the backend; in-memory demo data resets |
| A single request raises | one request thread | That request gets a 500; the server keeps serving |

## Shared Resources

- The process-wide holder and its lock (shared by all visitor sessions).
- The audit trail file and the audit module's process-global configuration.
- The in-memory demo database in `mock_hsm.db` module state (process-global). Because the data lives in the module, not in the server object, a backend replacement within the same process keeps it; only a process restart resets it.

## Assumptions & Open Questions

None.
