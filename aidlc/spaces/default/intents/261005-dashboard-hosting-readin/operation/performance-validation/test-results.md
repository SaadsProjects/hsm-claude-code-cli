# Performance Test Results — Dashboard Hosting Readiness (staging)

## Sources

- `load-test-plan.md` (procedure, pass/fail)
- Runs on 2026-10-06 against `https://hsm-stg.streamlit.app` at `main` `fc820e2`, Python 3.14, Streamlit Community Cloud free tier
- Client: the owner's machine (macOS), `.venv` from `requirements-dev.txt`, Playwright Chromium
- Local results for NFR2.1–NFR2.5 and NFR2.11–NFR2.13: `construction/build-and-test/test-results.md`

## Cold-Start Runs

Each run began with the owner rebooting `hsm-stg` from the app menu. The check started within seconds of that.

| Run | Check start (UTC) | Check PASS (UTC) | Signed-out wall time | Signed-in time (owner's stopwatch) |
|-----|-------------------|------------------|----------------------|------------------------------------|
| 1 | 14:00:59 | 14:01:15 | 15.1 s (exit 0) | Not measured |
| 2 | 14:04:30 | 14:04:48 | 18.1 s (exit 0) | 24 s |

In both runs the check printed `waiting: the host shows its sleep or waking page` before the sign-in screen appeared.

- **Signed-out path:** the wall time runs from just after the reboot to a settled sign-in screen with no tabs. It includes the host's waking page.
- **Signed-in path (run 2):** timed from Google returning the owner to the app until the dashboard showed its tabs. It leaves out the time spent in Google's own sign-in screens. It covers the gate allowing the visitor, the embedded backend starting, and the first full dashboard render after a cold container.

## Observations

- **The host's waking page is recognised.** The check's wake wording matched what Streamlit Community Cloud actually shows, and it waited instead of failing. This closes U5's open item K3, which was untested against the real host until now. The wake-button click (U5 R-04) wasn't exercised, because a reboot shows the waking page, not the sleep page with its button.
- **Margin.** The signed-in figure, 24 s, leaves 6 s under the 30 s target, a narrower margin than the signed-out path's 12–15 s. Most of the signed-in time goes to the first full render after a cold start: the backend start (bounded at 2 s by NFR2.1), the persona and site loads, and Streamlit's first page build.
- **Single sample.** Only one signed-in run was stopwatched. That is enough for the target as agreed (Q2 A: measured once), but not a distribution.
- **Errors:** none. Both checks exited 0. The owner's sign-in reached the dashboard, and the caption read `Build fc820e2`.

## Bottleneck Analysis

The cold start is the bottleneck, as expected (Q4 A). The free tier gives one container and no scaling, so there is no auto-scaling to validate.

If the signed-in time ever crosses 30 s, the levers are, in order:
1. Defer non-essential loads on the first render.
2. Cache the persona and site lists per process.
3. Accept a host-side warm-up, such as keeping the app awake.

None is needed today.
