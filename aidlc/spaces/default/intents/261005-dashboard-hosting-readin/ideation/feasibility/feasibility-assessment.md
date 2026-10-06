# Feasibility Assessment — Dashboard Hosting Readiness

## Sources

- Intent statement: `ideation/intent-capture/intent-statement.md`
- Answers Q1–Q9 in `ideation/feasibility/feasibility-questions.md`
- Rules in force: `aidlc/spaces/default/memory/{org,team,project}.md`
- Repository facts checked on 2026-10-05: Streamlit 1.64.0 is installed; `.test-floor` is 745 and `.coverage-floor` is 95.00.

## Verdict

**Feasible, with three technical risks to retire early and one schedule risk.** All the work is Python and Streamlit changes inside the existing repository, and every tool it needs is familiar (Q3). It needs no new paid service (Q4), no AWS (Q6) and no compliance regime (Q2). Nothing outside the work blocks it (Q5). The design was already settled in intent `261004-dashboard-deploy-pipelin`, so the remaining uncertainty is about how the hosting platform behaves, not about what to build.

## Technical Viability

| Area | Assessment | Basis |
|------|------------|-------|
| Sign-in gate | Viable. Streamlit 1.64.0 provides built-in sign-in. Whether it behaves the same locally and on Streamlit Cloud, including the verified-email flag, is unproven. | Q7 (risk A); installed version |
| Secret out of the code | Viable, and the rules require it: hosted deploys must read the secret from configuration and refuse to start without it. The Cloud secrets store is the hosted source. | Q1/Q8; `project.md` Forbidden |
| Backend inside the dashboard's process | Viable in principle. Streamlit Cloud runs one process, so the backend has to start inside it, reachable only locally, with only one copy running. How this behaves across Streamlit reruns and restarts is unproven. | Q7 (risk B); `team.md` Deployment |
| Build identifier and reset banner | Low risk: small, self-contained display changes. | Intent statement |
| Post-deploy check with browser tests | Viable. CI already has a browser-test job that always reports. Making a browser available to it in CI is unproven. | Q1/Q8; Q7 (risk C); `CLAUDE.md` CI section |
| Quality floors | Must hold: the test floor is 745 and the coverage floor is 95.00. Both may only rise. New code ships with tests, written test-first. | `team.md` Testing Posture; repo floor files |

## Platform View (cloud)

No AWS account or service is involved (Q6). Hosting is Streamlit Community Cloud on the free tier (Q4). No cloud credentials are needed, so the OIDC-only credential rule is satisfied by default.

## Compliance View

No regulatory framework applies (Q2). The data is seeded demo data. The only personal data the change introduces is viewers' email addresses, used to check them against the allowlist; the answers record that these need no special handling (Q2). The signing secret is the sensitive item, and its handling is governed by the project's security rules rather than by a regulation.

## Schedule

The target is within a week, on the free tier (Q4, Q9). The workflow runs the full feature process (intent capture Q8), with several design and operations stages still ahead, and every change is test-first. Schedule is therefore the most likely constraint to slip; see the RAID log.

## Assumptions & Open Questions

None.
