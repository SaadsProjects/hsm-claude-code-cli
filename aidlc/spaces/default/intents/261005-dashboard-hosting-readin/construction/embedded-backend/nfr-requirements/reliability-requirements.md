# Reliability Requirements — U2 embedded-backend

## Sources

- `construction/embedded-backend/functional-design/rules.md` BR2.2–BR2.5, BR3.3, BR4.2, BR5.1, BR6.1
- `construction/embedded-backend/functional-design/functional-spec.md` state machine and Error Handling
- `inception/user-stories/stories.md` US3.3, US3.4

## Requirements

| ID | Requirement | Pass condition | Source |
|----|-------------|----------------|--------|
| NFR3.3 | A failed start is reported, never retried within the same call, and retried at most once per later rerun | Tests: a forced failure returns status failed once; the next call makes exactly one new attempt | BR2.3 |
| NFR3.4 | A dead instance (thread stopped or socket not answering) is detected, shut down and its socket closed before one replacement attempt | A test stops the server, then shows the next start closes the old one and returns a new running instance | BR2.2, BR2.4 |
| NFR3.5 | An unusable audit trail (OS error or a corrupt existing file) fails the start instead of producing a running backend whose writes all return 503 | Tests with an unwritable path and with a corrupt file both give status failed with the audit module's reason | BR3.3 |
| NFR3.6 | Asking for a backend client with no live backend raises a clear error and never starts a backend | A test calls `client_for` with no instance and expects the error | BR4.2 |
| NFR3.7 | The separate-process backend keeps working unchanged | The existing MCP and hook tests pass unchanged | BR6.1, US3.4 |
| NFR3.8 | Unit U2 is built test-first; the suite stays at or above `.test-floor` on Python 3.10 and 3.14 and coverage at or above `.coverage-floor` | CI on the intent's pull request: both test legs and `coverage-gate` green | NFR3, team.md Testing Posture |

## Degradation

When the backend can't start, the visitor sees Screen 4 and can reload; nothing else on the page depends on a partial backend. In-memory demo data does not survive a replacement or a restart, which the reset banner (U4) states.

## Assumptions & Open Questions

None.
