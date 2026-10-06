# Load Test Plan — Dashboard Hosting Readiness (staging)

## Sources

- `construction/embedded-backend/nfr-requirements/performance-requirements.md` (NFR2.1–NFR2.3) and `scalability-requirements.md` (NFR2.4, NFR2.5, Load Context)
- `construction/sign-in-gate/nfr-requirements/performance-requirements.md` (NFR2.11–NFR2.13)
- `construction/embedded-backend/nfr-design/performance-design.md`, `scalability-design.md`; `construction/sign-in-gate/nfr-design/performance-design.md`
- `inception/requirements-analysis/requirements.md` NFR2 (the 30 s cold-start target)
- Answers Q1–Q4 and the summary confirmation in `performance-validation-questions.md`
- `construction/build-and-test/test-results.md` (local results for NFR2.1–NFR2.5 and NFR2.11–NFR2.13)
- No observability stage ran for this work (it stays with the parked deploy intent), so there are no dashboards. Evidence is command timing and the owner's observation.

## Scope

- **No load test** (Q1 A). Staging serves a handful of allowlisted people, one or two at a time. Streamlit Community Cloud's free tier runs one container with no scaling, so there is no auto-scaling to validate.
- **One hosted target:** NFR2. A visitor can use the dashboard within 30 seconds of the app waking (Q2 A).
- **No hosted throughput target** (Q3 A). NFR2.5 (10 concurrent backend requests) is a per-process property and was met locally.
- **Bottleneck under study:** the host's cold start (Q4 A). The container comes up, installs `requirements.txt`, then boots Streamlit, which starts the in-process backend on the first render.

## Environment

- **Staging:** `https://hsm-stg.streamlit.app`, tracking `main` at `fc820e2`, Python 3.14, free tier.
- **Client:** the owner's machine (macOS), using `.venv` from `requirements-dev.txt` with Playwright Chromium.

## Procedure

1. **Cold state.** The owner reboots `hsm-stg` from the app's ⋮ menu on share.streamlit.io and says when they clicked it. A reboot restarts the container, so the run measures a full cold start. That is the same or worse than waking from sleep, since a wake also restarts the container.
2. **Signed-out path, timed.** Immediately run:

   ```bash
   time python3 scripts/postdeploy_check.py https://hsm-stg.streamlit.app --timeout 180
   ```

   The check waits through the host's "waking up" or "in the oven" pages, then requires the sign-in screen, no tabs, and a settled page. Its wall time, from the start of the run to PASS, is the signed-out measure.
3. **Signed-in path, stopwatched.** As soon as the page answers, the owner signs in with the allowlisted account and times from the page answering to the dashboard showing its tabs and the `Build` caption. NFR2 counts from the app waking, so the time spent in Google's sign-in screens is noted but kept separate.
4. **Repeat if needed.** If the first measurement is borderline (25–35 s), repeat once after another reboot and record both.

## Pass / Fail

- **Pass:** the check exits 0 within 30 s of the app answering, and the owner reaches the dashboard within 30 s of the app being up, excluding time spent in Google's own screens.
- **Fail:** either part exceeds 30 s. Record the miss with its figures; don't hide it (runbook § Timing).
- **Inconclusive:** the check exits 3 (never answered within 180 s). Record it and repeat once.

## Not Covered Here

- Throughput, latency percentiles and auto-scaling (Q1–Q3).
- Production, which stays with the parked deploy intent.
