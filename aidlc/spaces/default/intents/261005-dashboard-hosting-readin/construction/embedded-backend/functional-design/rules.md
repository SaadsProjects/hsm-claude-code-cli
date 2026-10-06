# Business Rules — U2 embedded-backend

## Sources

- `inception/requirements-analysis/requirements.md` FR3.1–FR3.4, NFR1
- `inception/contract-design/contract-summary.md` C2, C3
- `inception/domain-design/reviews/review-01.md` R-01, R-02, R-03
- `inception/refined-mockups/mockups.md` Screen 4
- `functional-design-questions.md` Q1–Q4

## Rules

```yaml
rules:
  - id: BR1.1
    statement: The embedded backend binds 127.0.0.1 only.
    category: constraint
    applies_to: BackendInstance
    trigger: a new start attempt
    logic: IF a backend is started inside the dashboard THEN it listens on 127.0.0.1 and nothing else
    violation: not possible by design; any other host is a defect
    source: FR3.1, NFR1

  - id: BR1.2
    statement: The start function and its module use only the standard library and mock_hsm.
    category: constraint
    applies_to: EmbeddedBackend
    trigger: always
    logic: IF the embedded module is imported THEN it imports nothing outside the standard library and mock_hsm (no Streamlit)
    violation: a test fails
    source: FR3.1

  - id: BR2.1
    statement: At most one live backend exists per process.
    category: constraint
    applies_to: BackendInstance, StartAttempt
    trigger: every start call, from any rerun or thread
    logic: IF a live instance exists THEN return it (outcome reused), ignoring any port argument ELSE make one new attempt, where a port argument applies; start calls are serialised by one process-wide lock
    violation: not possible by design; two concurrent calls get the same address
    source: FR3.2

  - id: BR2.4
    statement: A dead instance is shut down and its socket closed before a replacement is attempted, and the replacement is logged as a demo-data reset.
    category: policy
    applies_to: BackendInstance
    trigger: a start call finds the previous instance not live
    logic: IF the previous instance is not live THEN stop it, close its socket, log a warning that the backend was replaced and its in-memory demo data reset, THEN make one new attempt
    violation: not applicable
    source: R-02 (domain design), functional-design review R-03

  - id: BR2.5
    statement: The backend address is read from the live instance at the moment of each use and never cached by callers.
    category: constraint
    applies_to: ClientRequest, DashboardShell
    trigger: every client_for call and every caption render
    logic: IF a caller needs the address THEN it asks for the current live instance at that moment; on replacement, DashboardShell also clears its cached reads so no data from the old instance is shown
    violation: a stale address or stale data would be shown; a test covers replacement
    source: functional-design review R-03

  - id: BR2.2
    statement: An instance counts as live only while its server thread is alive and a TCP connect to its port succeeds within a short timeout.
    category: validation
    applies_to: BackendInstance
    trigger: every start call and every current() call
    logic: IF the thread is not alive OR the connect fails THEN the instance is not live (current() returns none; the next start makes a new attempt)
    violation: a dead instance is never handed out
    source: R-02, Q1

  - id: BR2.3
    statement: A start call makes at most one new attempt and never retries in a loop.
    category: policy
    applies_to: StartAttempt
    trigger: no live instance
    logic: IF the one attempt fails THEN report status failed with its cause and return; the next rerun may make one new attempt
    violation: not applicable
    source: C3, Q2

  - id: BR3.1
    statement: The start refuses without a valid signing secret.
    category: validation
    applies_to: StartAttempt
    trigger: a new start attempt
    logic: IF the signing secret check refuses THEN the attempt fails with the refusal reason as its cause and nothing binds
    violation: status failed
    source: NFR1 (U1 contract C1)

  - id: BR3.2
    statement: The audit trail is configured before the backend serves, from HSM_AUDIT_PATH or else a private directory the app owns under the system temp directory.
    category: policy
    applies_to: AuditTrail
    trigger: a new start attempt
    logic: >
      IF HSM_AUDIT_PATH is set THEN use it ELSE use <system temp dir>/hsm-demo-<user id>/audit.jsonl, creating that
      directory with owner-only access when missing. The file is never placed directly in a shared directory such as
      the system temp directory, because the audit module narrows its parent directory's permissions.
    violation: status failed with the cause
    source: FR3.3, C2 (refined), domain-design R-03, functional-design review R-01

  - id: BR3.3
    statement: An audit trail that cannot be used makes the start fail; this is read back after configuring, not inferred from an exception.
    category: validation
    applies_to: AuditTrail, StartAttempt
    trigger: after the audit trail is configured in a new start attempt
    logic: >
      Configuring the trail never raises; it records an unavailable reason instead. IF, after configuring, the audit
      module reports an unavailable reason (an OS error such as an unwritable path, or a corrupt existing trail)
      THEN the attempt fails with that reason as its cause and nothing binds. The audit module gains a small public
      query that returns the unavailable reason or none.
    violation: status failed with the cause
    source: FR3.3, functional-design review R-02

  - id: BR4.1
    statement: The dashboard's backend client takes its address from the live embedded instance, never from HSM_BASE_URL.
    category: policy
    applies_to: ClientRequest
    trigger: every client_for call without an explicit base_url
    logic: >
      IF no base_url is given THEN use the live instance's address. The dashboard ignores HSM_BASE_URL everywhere:
      dashboard/session.py client_for (today the client default), and dashboard/app.py's import of HSM_BASE_URL, its
      sidebar backend caption and its "can't reach the HSM backend" error text. No dashboard module builds a backend
      client other than through client_for; a test asserts that no dashboard module imports HSM_BASE_URL.
    violation: the test fails
    source: FR3.3, C3, domain-design R-01, Q4, functional-design review R-04

  - id: BR4.2
    statement: Asking for a client with no live backend is an error that names the cause; it never starts a backend.
    category: validation
    applies_to: ClientRequest
    trigger: client_for with no live instance
    logic: IF no live instance exists THEN raise an error stating that the embedded backend is not running
    violation: the error reaches the caller
    source: Q3

  - id: BR5.1
    statement: A failed start shows only Screen 4's fixed message and the Account section with Sign out.
    category: policy
    applies_to: DashboardShell
    trigger: a start attempt reports status failed
    logic: IF the start failed THEN show exactly "The demo backend didn't start. Reload the page or try again later." with no tabs, persona login, site picker or banner, and no error type, stack trace or address
    violation: not applicable
    source: FR3.4, Screen 4
    note: The Account section with "Sign out" comes from U3 (sign-in-gate). Until U3 lands, Screen 4 renders without it, and the "Sign out" half of AC3.3.2 is verified by U3's tests.

  - id: BR5.4
    statement: The backend start runs on every rerun before any screen that reads data, and after the sign-in gate once it exists.
    category: policy
    applies_to: DashboardShell
    trigger: every rerun
    logic: IF the dashboard reruns THEN the order is the secrets bridge and sign-in gate (U3), then the backend start, then the screens; until U3 lands, the backend start is the first step of the render
    violation: not applicable
    source: components.md DashboardShell, interaction-spec step 3, functional-design review R-04

  - id: BR5.2
    statement: A failed start writes its technical cause to the app log.
    category: policy
    applies_to: DashboardShell
    trigger: a start attempt reports status failed
    logic: IF the start failed THEN log the failure_cause (never the secret value)
    violation: not applicable
    source: FR3.4, NFR1

  - id: BR5.3
    statement: The backend caption shows the live instance's real address.
    category: policy
    applies_to: DashboardShell
    trigger: a running instance
    logic: IF the backend is running THEN the caption shows its address, not the import-time HSM_BASE_URL
    violation: not applicable
    source: R-01, C3

  - id: BR6.1
    statement: The separate-process backend keeps working unchanged for the MCP server and hooks.
    category: constraint
    applies_to: MockBackend
    trigger: python3 -m mock_hsm.server
    logic: IF the server runs as its own process with a valid secret THEN it behaves as before this unit
    violation: the existing MCP and hook tests fail
    source: US3.4
```

## Summary

| ID | Rule | Category |
|----|------|----------|
| BR1.1 | Binds 127.0.0.1 only | constraint |
| BR1.2 | Standard library and `mock_hsm` only | constraint |
| BR2.1 | One live backend per process; calls serialised | constraint |
| BR2.2 | Live = thread alive and TCP connect succeeds | validation |
| BR2.3 | One attempt per call, no retry loop | policy |
| BR2.4 | Dead instance closed before replacement; reset logged | policy |
| BR2.5 | Address read at each use; cached reads cleared on replacement | constraint |
| BR3.1 | Refuses without a valid secret | validation |
| BR3.2 | Audit path from `HSM_AUDIT_PATH` or a private app-owned temp subdirectory | policy |
| BR3.3 | Unusable audit trail (OS error or corrupt file) fails the start, read back after configuring | validation |
| BR4.1 | Client address from the live instance, never `HSM_BASE_URL`; named call sites; guard test | policy |
| BR4.2 | No live backend → error, never a lazy start | validation |
| BR5.1 | Failure shows only Screen 4 (Sign out from U3) | policy |
| BR5.2 | Failure cause goes to the log | policy |
| BR5.3 | Caption shows the real address | policy |
| BR5.4 | Start runs every rerun, after the gate, before data screens | policy |
| BR6.1 | Separate-process backend unchanged | constraint |
