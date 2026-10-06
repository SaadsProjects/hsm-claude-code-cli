# RAID Log — Dashboard Hosting Readiness

## Sources

- Answers Q1–Q9 in `ideation/feasibility/feasibility-questions.md`
- Intent statement: `ideation/intent-capture/intent-statement.md`

## Risks

| ID | Risk | Likelihood | Impact | Mitigation | Source |
|----|------|------------|--------|------------|--------|
| R1 | Streamlit's sign-in behaves differently locally and on Streamlit Cloud, including the verified-email flag, so the allowlist check passes in tests but not when hosted (or the reverse). | Medium | High: a gap here exposes the dashboard without sign-in. | Prove parity early with a small spike. Keep the check failing closed when the flag is missing. | Q7 |
| R2 | The backend started inside the dashboard misbehaves across Streamlit reruns or restarts: a second copy starts, or it fails to start. | Medium | High: the dashboard has no data. | Test the single-instance guard and restart behaviour directly. | Q7 |
| R3 | No browser is available for browser tests in CI, so the post-deploy check can't be proven there. | Medium | Medium: the sign-in refusal success metric can't be shown in CI. | Settle how CI provides a browser before relying on it. | Q7 |
| R4 | The one-week target slips. The full feature process still has many stages ahead, and every change is test-first. | High | Medium: the parked deploy work stays blocked longer. | Keep later stages proportionate. Revisit the remaining process if the date matters more than the ceremony. | Q9; intent capture Q8 |

## Assumptions

None.

## Issues

| ID | Issue | Source |
|----|-------|--------|
| I1 | The old signing secret in the public repository is burned and still present in the code. This work removes it. | Intent statement |

## Dependencies

| ID | Dependency | Source |
|----|------------|--------|
| D1 | The parked deploy work (intent `261004-dashboard-deploy-pipelin`) depends on this work landing first. | Intent capture Q4 |
| D2 | Streamlit Community Cloud's secrets store supplies the signing secret and sign-in settings when hosted. | Q1/Q8 |
| D3 | The existing GitHub Actions CI and its required checks gate every change. | Q1/Q8 |

## Assumptions & Open Questions

None.
