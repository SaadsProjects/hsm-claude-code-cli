# Infrastructure Design Questions — U2 embedded-backend

The host is already decided (Streamlit Community Cloud, one process, backend on loopback inside it; team.md Deployment), and U2 adds no service, queue, database or cloud resource. Two infrastructure points are still open.

## Q1 — Where does the hosted app's audit trail go?

A. Nowhere configured: the hosted app leaves `HSM_AUDIT_PATH` unset and uses the private temp directory default, which resets with the app, matching the demo-data reset banner (Recommended)
B. Set `HSM_AUDIT_PATH` in each app's Streamlit secrets to an explicit path
X. Other (please specify)

[Answer]: A

## Q2 — Does U2 change the CI pipeline?

A. No: U2's tests run in the existing `tests (3.10)`, `tests (3.14)` and `coverage-gate` jobs; no job, step, permission or required check changes, and the `browser-tests` watch list is untouched (browser tests arrive with U3 and U5) (Recommended)
B. Add a dedicated CI job or step for the embedded backend
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- **Hosted audit trail (Q1 A):** the staging and production apps leave `HSM_AUDIT_PATH` unset. The trail lives in the app's private temp directory, `<temp>/hsm-demo-<user id>/audit.jsonl`, and resets with the app, as the demo-data reset banner says. Nothing new goes in Streamlit secrets for U2.
- **CI (Q2 A):** no change. U2's tests run in the existing `tests (3.10)`, `tests (3.14)` and `coverage-gate` jobs; no job, step, permission or required check changes, and the `browser-tests` watch list is untouched.
- **Fixed by earlier decisions:** one Streamlit Community Cloud process per app; the backend on `127.0.0.1` inside it, on a free port; no new service, database, queue or cloud resource; the app log is the only monitoring surface, and the post-deploy check (U5) is the deployment health signal.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
