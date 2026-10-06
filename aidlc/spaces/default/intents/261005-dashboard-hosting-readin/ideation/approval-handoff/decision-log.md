# Decision Log — Ideation, Dashboard Hosting Readiness

## Sources

- Questions files under `ideation/*/` and the stage approvals recorded in this intent's audit trail.

## Decisions

| # | Date | Stage | Decision | Source |
|---|------|-------|----------|--------|
| D1 | 2026-10-05 | Intent Capture | Problem: hosting is blocked until the app changes land; you are the sole beneficiary, stakeholder and decision-maker | intent-capture Q1, Q2, Q5, Q6 |
| D2 | 2026-10-05 | Intent Capture | Success metrics: CI-gated PRs; burned-secret check clean; test and coverage floors held; non-allowlisted visitor refused | intent-capture Q3 |
| D3 | 2026-10-05 | Intent Capture | Keep the full `feature` process | intent-capture Q8 |
| D4 | 2026-10-05 | Intent Capture | Approved, with 3 minor review findings accepted | Gate |
| D5 | 2026-10-05 | Market Research | Skipped: internal tool, design already decided | Skip question |
| D6 | 2026-10-05 | Feasibility | Outside systems: Cloud secrets store and GitHub Actions CI; no regulation; free tier; target within a week | feasibility Q2, Q4, Q8, Q9 |
| D7 | 2026-10-05 | Feasibility | Main risks: sign-in parity, in-process backend, browser in CI | feasibility Q7 |
| D8 | 2026-10-05 | Scope Definition | All eight changes are required before hosting; build ID, banner and post-deploy check rank lower but are not dropped | scope Q1, Q2, Q8 |
| D9 | 2026-10-05 | Scope Definition | Burned-secret removal goes first, then risk-first within the dependency order | scope Q3, Q4, Q5, Q9 |
| D10 | 2026-10-05 | Scope Definition | Creating the hosted apps moves into this work, after the changes merge; it comes out of the parked deploy intent's plan | scope Q6, Q10 |
| D11 | 2026-10-05 | Scope Definition | Full process kept; the date may slip | scope Q7 |
| D12 | 2026-10-05 | Team Formation | Skipped: solo developer | Skip question |
| D13 | 2026-10-05 | Rough Mockups | Screens: sign-in only; neutral refusal with Sign out; banner above the tabs; build ID in a sidebar caption; email and Sign out at the top of the sidebar; plain backend-failure message; desktop first | rough-mockups Q1–Q7 |
| D14 | 2026-10-05 | Rough Mockups | Approved, with 4 minor review findings carried into Refined Mockups | Gate |
| D15 | 2026-10-05 | Approval & Handoff | All four risks accepted; go to Inception | handoff Q1, Q2 |

## Assumptions & Open Questions

None.
