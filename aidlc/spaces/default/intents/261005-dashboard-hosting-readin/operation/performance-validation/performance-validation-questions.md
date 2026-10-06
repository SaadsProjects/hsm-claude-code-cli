# Performance Validation Questions — Dashboard Hosting Readiness

Context: the measurable targets come from U2's and U3's performance and scalability records. NFR2.1–NFR2.5 and NFR2.11–NFR2.13 already passed locally in Build and Test. Only the whole-app NFR2 figure needs the hosted app: usable within 30 seconds of waking. Staging is `https://hsm-stg.streamlit.app` on Streamlit Community Cloud's free tier.

## Q1 — Traffic pattern

What traffic should staging be validated for?

A. A handful of allowlisted people, one or two at a time; no load test (matches U2's scalability Load Context)
B. A small burst: 10 concurrent visitors through the gate
C. Sustained load for an hour
X. Other (please specify)

[Answer]: A

## Q2 — Latency target

Which latency target applies?

A. Only NFR2: usable within 30 s of the app waking, measured once from cold (check time and a stopwatched sign-in); no percentile targets
B. NFR2 plus a p95 page-load target for an awake app
X. Other (please specify)

[Answer]: A

## Q3 — Throughput

What throughput must staging sustain?

A. None beyond U2's NFR2.5 (10 concurrent backend requests, already met locally); no hosted throughput target
B. A stated requests-per-second target on staging
X. Other (please specify)

[Answer]: A

## Q4 — Likely bottleneck

Where is the likely bottleneck?

A. The host's cold start: the container wakes, installs nothing new, then boots Streamlit and the in-process backend. The free tier gives no scaling to validate
B. The embedded backend under concurrent requests
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- **Scope:** no load test. Staging serves a handful of allowlisted people (Q1 A).
- **Target:** NFR2 only. The app must be usable within 30 s of waking from cold, measured once in two parts (Q2 A):
  - the post-deploy check timed with `time`, right after the owner reboots `hsm-stg`;
  - the owner's stopwatched sign-in to the dashboard from the same cold start.
- **No hosted throughput target:** NFR2.5 was already met locally (Q3 A).
- **Bottleneck under study:** the host's cold start. The free tier has no scaling to validate (Q4 A).
- **Artifacts:** a load test plan stating the no-load scope, the test results, and an NFR validation matrix covering NFR2 and the already-met NFR2.1–NFR2.5 and NFR2.11–NFR2.13.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
