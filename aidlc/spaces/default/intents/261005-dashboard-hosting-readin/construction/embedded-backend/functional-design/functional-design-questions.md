# Functional Design Questions — U2 embedded-backend

The contract for this unit (C3) already settles who holds the backend address (`client_for` reads `current().address`), the audit path default (`<system temp dir>/hsm-audit.jsonl` when `HSM_AUDIT_PATH` is unset), the ephemeral port (`start(port=0)`), and that a failed start is never retried in a loop. These questions cover what is still open.

## Q1 — How is "the instance is still alive" checked?

The domain-design review (R-02) asks that a running backend is reused only while its thread is alive and its socket answers.

A. The server thread is alive and a plain TCP connect to `127.0.0.1:<port>` succeeds within a short timeout (no HTTP request, no route change) (Recommended)
B. The server thread is alive and an HTTP request to a new unauthenticated health route returns 200
C. The server thread is alive; no socket probe
X. Other (please specify)

[Answer]: A

## Q2 — What happens when a failed start is followed by another page load?

Screen 4 tells the visitor to "Reload the page or try again later".

A. Each rerun (page load or interaction) makes at most one new start attempt; a failure is reported for that rerun and never retried within it (Recommended)
B. The first failure is sticky for the life of the process; only an app restart tries again
C. Retry a fixed number of times with a delay inside one rerun
X. Other (please specify)

[Answer]: A

## Q3 — What does `client_for` do if no live backend exists when it is called?

DashboardShell starts or reuses the backend on every rerun before any screen renders, so this should only happen in a call that bypasses the shell.

A. Raise a clear error naming the cause; never start a backend from inside `client_for` (Recommended)
B. Start the backend lazily from inside `client_for`
C. Fall back to `HSM_BASE_URL`
X. Other (please specify)

[Answer]: A

## Q4 — Does the dashboard ever use a separately started backend?

US3.4 keeps `python3 -m mock_hsm.server` working for the MCP server and hooks. C2 says `HSM_BASE_URL` is not used by the dashboard when embedded.

A. The dashboard always embeds its own backend and ignores `HSM_BASE_URL`, locally and hosted (Recommended)
B. The dashboard uses `HSM_BASE_URL` when it is set, and embeds only when it is unset
C. A dedicated switch (for example `HSM_DASHBOARD_BACKEND=external`) selects a separate backend
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- **Liveness (Q1 A):** a backend is reused only while its server thread is alive and a TCP connect to `127.0.0.1:<port>` succeeds within a short timeout. A dead instance is reported as failed.
- **After a failure (Q2 A):** each rerun makes at most one new start attempt; a failure shows Screen 4 for that rerun and is never retried within it.
- **No live backend in `client_for` (Q3 A):** `client_for` raises a clear error naming the cause and never starts a backend itself.
- **External backend (Q4 A):** the dashboard always embeds its own backend and ignores `HSM_BASE_URL`; the separate-process backend stays for the MCP server and hooks.
- **From the contract (unchanged):** `client_for` uses `current().address`; the audit trail defaults to `<system temp dir>/hsm-audit.jsonl` when `HSM_AUDIT_PATH` is unset, and an unwritable path is a start failure; the port is free (`start(port=0)`); the caption shows the real address; Screen 4 shows only the fixed message and Sign out, with the technical cause in the log.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
