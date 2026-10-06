# Performance Test Instructions — Dashboard Hosting Readiness

## Sources

- `construction/embedded-backend/nfr-requirements/performance-requirements.md` and `scalability-requirements.md` (NFR2.1–NFR2.5)
- `construction/sign-in-gate/nfr-requirements/performance-requirements.md` (NFR2.11–NFR2.13)
- `inception/requirements-analysis/requirements.md` NFR2 (the 30-second cold-start target)
- `memory/team.md` Testing Posture (`perf` tests run by hand, never in CI)

## Targets and How They Are Checked

| Target | Expected | Where it runs | Command |
|--------|----------|---------------|---------|
| NFR2.1 backend start | ≤ 2 s from start call to running | Ordinary test, in CI | `python3 -m pytest tests/test_embedded_backend.py -q` |
| NFR2.2 liveness connect | 0.5 s timeout; refused or timed out counts as not live | Ordinary test, in CI | as above |
| NFR2.3 rerun reuse | No new bind on a live instance | Ordinary test, in CI | as above |
| NFR2.5 concurrency | 10 concurrent requests to one backend all succeed | Ordinary test, in CI | as above |
| NFR2.11 gate overhead | ≤ 50 ms of gate work per rerun | `perf`-marked test, by hand | `python3 -m pytest tests/test_dashboard_gate.py -m perf -q` |
| NFR2.12 no gate I/O | No socket use by the gate on a rerun | Ordinary test, in CI | `python3 -m pytest tests/test_dashboard_gate.py -q` |
| NFR2.13 no wait | The gate adds no sleep, wait or retry | Ordinary test, in CI | as above |
| All `perf` tests | Pass on the developer's machine | By hand | `python3 -m pytest tests/ -m perf -q` |
| NFR2 whole-app cold start | Usable within 30 s of the hosted app waking | Against staging; owned by **performance-validation** | `time python3 scripts/postdeploy_check.py https://<staging-app>.streamlit.app --timeout 180` from a sleeping app, plus a stopwatched sign-in (`docs/staging-app.md` § Timing) |

## Notes

- `perf` tests are machine-dependent by design. They never run in CI and never block a merge (project.md Forbidden). No test carries both `perf` and `browser`.
- The 30-second target needs the real host asleep. It can't run locally or in CI, so it belongs to the scheduled performance-validation stage. An awake-app run on 2026-10-06 took 8.5 s; it is not the NFR2 measurement.
- No load test is planned. The demo serves a handful of allowlisted people (scalability requirements, Load Context).
