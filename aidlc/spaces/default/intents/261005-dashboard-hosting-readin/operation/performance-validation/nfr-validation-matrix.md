# NFR Validation Matrix — Dashboard Hosting Readiness

## Sources

- `construction/embedded-backend/nfr-requirements/performance-requirements.md`, `scalability-requirements.md`
- `construction/sign-in-gate/nfr-requirements/performance-requirements.md`
- `inception/requirements-analysis/requirements.md` NFR2
- `test-results.md` (staging runs); `construction/build-and-test/test-results.md` (local runs)

## Matrix

| NFR | Target | Actual | Status | Test Date | Notes |
|-----|--------|--------|--------|-----------|-------|
| NFR2 (signed-out) | Usable within 30 s of waking | 15.1 s and 18.1 s from a cold reboot to a settled sign-in screen | PASS | 2026-10-06 | Two runs; the host's waking page was handled |
| NFR2 (signed-in) | Usable within 30 s of the app being up, Google's screens excluded | 24 s from Google's return to the dashboard tabs (cold container) | PASS | 2026-10-06 | One run; 6 s margin |
| NFR2.1 | Backend start ≤ 2 s | Test passes | PASS | 2026-10-06 | Local, in CI |
| NFR2.2 | Liveness connect timeout 0.5 s | Test passes | PASS | 2026-10-06 | Local, in CI |
| NFR2.3 | Rerun reuses the live instance | Test passes | PASS | 2026-10-06 | Local, in CI |
| NFR2.4 | One backend per process | Tests pass | PASS | 2026-10-06 | Local, in CI |
| NFR2.5 | 10 concurrent requests succeed | Test passes | PASS | 2026-10-06 | Local, in CI; no hosted throughput target (Q3 A) |
| NFR2.11 | Gate work ≤ 50 ms per rerun | `perf` test passes | PASS | 2026-10-06 | By hand (`-m perf`) |
| NFR2.12 | No gate network or disk I/O | Test passes | PASS | 2026-10-06 | Local, in CI |
| NFR2.13 | The gate adds no wait, retry or sleep | Test passes | PASS | 2026-10-06 | Local, in CI |
| Throughput / percentiles / auto-scaling | Not set (Q1–Q3 A) | — | N/A | — | Free tier, single container, handful of users |

## Verdict

Every performance target set for this work passes. NFR2 is met on both paths from a cold start. The signed-in path is the tighter one (24 s of 30 s, single sample), so it's worth re-timing if the first-render work grows.
