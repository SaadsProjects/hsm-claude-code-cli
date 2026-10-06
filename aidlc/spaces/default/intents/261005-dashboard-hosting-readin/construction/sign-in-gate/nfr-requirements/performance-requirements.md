# Performance Requirements — U3 sign-in-gate

## Sources

- `inception/requirements-analysis/requirements.md` NFR2 (30-second cold start), NFR3
- `construction/sign-in-gate/functional-design/functional-spec.md` W1 (the gate runs first on every rerun)
- `nfr-requirements-questions.md` Q1; `memory/team.md` Testing Posture (`perf` tests never run in CI)

## Requirements

| ID | Requirement | Pass condition | Source |
|----|-------------|----------------|--------|
| NFR2.11 | The gate's own work on one rerun adds at most 50 ms. This covers the page header, the bridge, the settings check, allowlist parsing, the identity read, the decision and rendering a gate screen. It excludes Google's sign-in round trip and the embedded backend's start | A `perf`-marked test runs the gate 50 times in-process with a fake identity and a 50-entry allowlist and asserts the 95th-percentile time is at most 50 ms. It runs by hand with `-m perf`, never in CI (team.md; project.md Forbidden), so this budget is advisory: nothing enforces it on a merge. NFR2.12's no-I/O test is the CI-enforced proxy that keeps the gate cheap | NFR2, Q1 |
| NFR2.12 | The gate does no network or disk I/O of its own beyond reading the app's secrets and writing a log line. The only network work on a rerun is Streamlit's sign-in redirect, which the visitor starts | A test patches the socket layer during an allowed and a refused gate run and asserts no connection is attempted by the gate | NFR2, BR3.5 |
| NFR2.13 | The gate adds no wait, retry or sleep, so it never stretches NFR2's 30-second target. U3 does not measure that 30-second figure: the post-deploy check (U5) times the signed-out path on staging (app awake to Screen 1), and the signed-in path is confirmed by hand when the owner signs in (U6) | A test searches `dashboard/auth_gate.py` and `dashboard/secrets_bridge.py` for `time.sleep` and retry loops and finds none | NFR2 |
| NFR3.11 | The gate and the bridge are covered by ordinary and `AppTest` tests through the seam, so line coverage over `dashboard/` doesn't fall. The suite's passing count stays at or above `.test-floor` on both Python legs | `coverage-gate` green; both `tests` jobs green with a count at or above the floor | NFR3, AC4.8.2 |

## Load and Concurrency

The gate keeps no shared state between browser sessions. Each rerun is independent, and the allowlist is small (tens of entries), so the gate adds no concurrency limit of its own. Concurrency belongs to Streamlit and to the embedded backend (U2).

## Assumptions & Open Questions

- [assumption] Streamlit's own sign-in redirect and callback time is outside this unit's budget. The post-deploy check never signs in, so it measures only the signed-out path. The signed-in part of NFR2 is a manual check by the owner on staging.
