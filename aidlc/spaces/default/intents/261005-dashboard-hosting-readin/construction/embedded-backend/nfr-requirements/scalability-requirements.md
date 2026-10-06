# Scalability Requirements — U2 embedded-backend

## Sources

- `inception/requirements-analysis/requirements.md` FR3.2, NFR2
- `construction/embedded-backend/functional-design/rules.md` BR2.1
- `nfr-requirements-questions.md` Q3 (answered A)

## Requirements

| ID | Requirement | Pass condition | Source |
|----|-------------|----------------|--------|
| NFR2.4 | One embedded backend serves every visitor session in the app process; there is never more than one per process | Tests: two start calls, repeated `AppTest` reruns, and two concurrent threads all leave exactly one backend | FR3.2, BR2.1 |
| NFR2.5 | The single backend handles 10 concurrent requests from separate threads without error; no new cap on request threads is added | A test sends 10 concurrent authenticated requests to one instance and asserts all succeed | Q3 |

## Load Context

The hosted app is a single-process demo for a short allowlist of people. Scaling out (more processes or hosts) is out of scope; each process would have its own backend and its own in-memory data, which the demo-data reset banner already tells visitors.

## Assumptions & Open Questions

None.
