# Performance Requirements — U2 embedded-backend

## Sources

- `inception/requirements-analysis/requirements.md` NFR2 (cold start within 30 seconds)
- `construction/embedded-backend/functional-design/functional-spec.md` W1, W2
- `nfr-requirements-questions.md` Q1, Q2 (both answered A)

## Requirements

| ID | Requirement | Pass condition | Source |
|----|-------------|----------------|--------|
| NFR2.1 | The in-process backend start takes at most 2 seconds from the start call to a running instance | An ordinary test (runs in CI) times one fresh start on loopback and asserts under 2 seconds; a loopback start normally takes milliseconds, so the bound has a wide margin | NFR2, Q1 |
| NFR2.2 | The liveness check's TCP connect uses a 0.5-second timeout; a refused or timed-out connect counts as not live | An ordinary test (runs in CI) asserts the connect is made with timeout 0.5 and that a refused connect (a closed port) and a simulated timeout (the connect replaced by one that raises a timeout) both yield "not live"; a second ordinary test against a closed port asserts the check returns in under 1.5 seconds | NFR2, BR2.2, Q2 |
| NFR2.3 | Reusing a live instance adds no new start work to a rerun: only the liveness check runs | An ordinary test shows a second start call returns the same handle without binding again | NFR2, BR2.1 |

The backend start is one part of NFR2's 30-second whole-app cold-start target; the rest belongs to the sign-in gate (U3) and the hosted app (U6).

All three timing checks above are ordinary tests that run in CI; none carries the `perf` mark, and none carries both the `perf` and `browser` marks (team.md Testing Posture). Their bounds are wide enough to hold on CI runners.

## Assumptions & Open Questions

None.
