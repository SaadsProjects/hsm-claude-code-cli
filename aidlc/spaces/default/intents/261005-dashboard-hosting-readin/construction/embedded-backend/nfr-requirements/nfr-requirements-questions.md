# NFR Requirements Questions — U2 embedded-backend

Most NFR targets for this unit follow directly from the inception NFRs and the approved functional design: loopback only, refusal without a valid secret, no secret in logs (NFR1); the technical cause in the log and never on screen (NFR4); standard library only, no new dependency (NFR7); test-first with the floors held (NFR3). These questions set the numbers that are still open.

## Q1 — How long may the in-process backend start take?

NFR2 gives the whole dashboard 30 seconds from the staging app waking to a usable page.

A. At most 2 seconds from the start call to a running instance, measured in a test on loopback (Recommended)
B. At most 5 seconds
C. No separate budget; only the 30-second whole-app target applies
X. Other (please specify)

[Answer]: A

## Q2 — How long may the liveness check wait for the TCP connect?

The check runs on every rerun before the page renders.

A. 0.5 seconds; a slower answer counts as not live (Recommended)
B. 1 second
C. 0.2 seconds
X. Other (please specify)

[Answer]: A

## Q3 — What concurrency must the embedded backend handle?

It is the existing threaded server, shared by every visitor session in the app process.

A. No new cap; a test proves 10 concurrent requests from separate threads all succeed against one instance (Recommended)
B. Cap the number of concurrent request threads
C. No concurrency requirement or test
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- **Start time (Q1 A):** at most 2 seconds from the start call to a running backend, tested on loopback.
- **Liveness check (Q2 A):** the TCP connect may take at most 0.5 seconds; slower counts as not live.
- **Concurrency (Q3 A):** no new cap; a test proves 10 concurrent requests from separate threads all succeed against one backend.
- **Carried from the inception NFRs and the approved design:** loopback only and refusal without a valid secret, with no secret value in any log or message (NFR1); the start failure cause logged and never shown on screen (NFR4); Screen 4 uses text with an h1 title (NFR5); standard library only and no new dependency (NFR7); test-first with both floors held (NFR3); the backend start counts toward the 30-second cold-start target (NFR2). NFR6 (read-only checks) does not apply to this unit.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
