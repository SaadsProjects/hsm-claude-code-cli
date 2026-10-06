# NFR Design Questions — U1 secret-fail-closed

## Sources

- `construction/secret-fail-closed/nfr-requirements/security-requirements.md` (NFR1.1–NFR1.10, NFR3.1–NFR3.2, NFR4.1, NFR7.1) and `tech-stack-decisions.md`
- `construction/secret-fail-closed/functional-design/functional-spec.md` (W1–W9)
- `inception/contract-design/contract-summary.md` C1, C2
- Current code: `mock_hsm/server.py` `_dispatch` (catches `TokenError` as 401; any other handler exception becomes a 500)

Everything else in this unit's design follows from earlier answers. One observability point is open.

## Q1. Should the backend log when it answers 503 because the secret is missing or invalid mid-run?

A. Yes: one warning line per such request on the backend's stderr, naming the request path and `HSM_SIGNING_SECRET`, never the value
B. No: the 503 response is enough
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Backend 503 logging (Q1): one warning line per such request on the backend's stderr, naming the request path and `HSM_SIGNING_SECRET`, never the value.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
