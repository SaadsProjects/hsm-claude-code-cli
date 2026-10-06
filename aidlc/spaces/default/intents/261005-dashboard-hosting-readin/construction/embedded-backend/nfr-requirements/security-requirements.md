# Security Requirements — U2 embedded-backend

## Sources

- `inception/requirements-analysis/requirements.md` NFR1, NFR3, NFR4, NFR5, NFR7
- `construction/embedded-backend/functional-design/rules.md` (BR1.1–BR6.1) and `functional-spec.md` (W1–W4)
- `inception/contract-design/contract-summary.md` C2, C3
- `nfr-requirements-questions.md` Q1–Q3; `memory/project.md` Forbidden (backend never reachable outside the process); `memory/team.md` Deployment

## Threat Model (STRIDE, scoped to U2)

| Asset or flow | Threat | Mitigation (requirement) |
|---------------|--------|--------------------------|
| The embedded backend's listening socket | Spoofing and tampering from outside the app (another host reaching the API) | NFR1.11 |
| A start without a usable secret | Spoofing (tokens minted with no key) | NFR1.12 |
| The audit trail file and its directory | Tampering or disclosure by another local user; damage to a shared directory's permissions | NFR1.13 |
| Start-failure causes and replacement warnings | Information disclosure (secret value, paths or addresses on screen) | NFR1.14, NFR4.2 |
| Embedded module imports | Supply-chain or framework coupling inside the shared `mock_hsm` package | NFR7.2 |

## Requirements

| ID | Requirement | Pass condition | Source |
|----|-------------|----------------|--------|
| NFR1.11 | The embedded backend listens on `127.0.0.1` only and is never reachable from outside the app process's host. Residual risk: other processes on the same host can reach loopback; every route still requires a signed persona token, which is the control for that case, consistent with team.md Deployment (loopback only) | A test asserts the bound host is `127.0.0.1` for every start, including an explicit port | NFR1, BR1.1, project.md Forbidden |
| NFR1.12 | A start without a valid signing secret binds nothing and reports a failed start | A test with the variable empty shows status failed, a cause naming `HSM_SIGNING_SECRET`, and no listener | NFR1, BR3.1 |
| NFR1.13 | The default audit path is in a directory the app creates with owner-only access (mode 0700) under the system temp directory; the audit file is never placed directly in a shared directory. If the directory already exists, the start fails (status failed, a cause naming the audit directory problem) unless it is a real directory (not a symlink) owned by the current user with no group or other access; the app never changes the mode of a directory it did not create | Tests with `HSM_AUDIT_PATH` unset: a fresh start creates the directory with mode 0700 and leaves the shared temp directory's mode unchanged; a pre-existing directory with group or other access fails the start; a symlink in its place fails the start; a directory owned by another user fails the start where the platform allows creating one (skipped otherwise) | BR3.2; functional-design review R-01 |
| NFR1.14 | The secret value never appears in any log line, screen or error raised by this unit. The screen (Screen 4) additionally shows no error type, stack trace, path or address; the log may contain the technical cause, including a path, as NFR4.2 requires | Tests capture the log and assert the secret value is absent; tests capture the rendered failure screen and assert the value, path, address and an exception name are all absent | NFR1, NFR4, BR5.1, BR5.2 |
| NFR7.2 | The embedded module imports only the standard library and `mock_hsm`; the unit adds no dependency | An AST import test on the module; `lock-check` and `audit` green on the pull request | NFR7, BR1.2 |

## Assumptions & Open Questions

None.
