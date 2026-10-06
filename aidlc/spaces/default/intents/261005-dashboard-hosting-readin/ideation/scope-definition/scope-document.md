# Scope Document — Dashboard Hosting Readiness

## Sources

- Intent statement: `ideation/intent-capture/intent-statement.md`
- Feasibility assessment and constraint register: `ideation/feasibility/`
- Answers Q1–Q10 in `ideation/scope-definition/scope-definition-questions.md`

## Goal

Make the HSM dashboard safe to host, then host it: deliver the eight application changes the earlier design specified, and only then create the two hosted apps. (Intent statement; Q1, Q6, Q10)

## In Scope

| # | Capability | Outcome | Source |
|---|-----------|---------|--------|
| 1 | Secret from config | The signing secret comes from configuration. The burned value and its temporary scan exclusion are removed in the same change. | Intent; Q3 |
| 2 | Secrets bridge and dev-secret script | Hosted secrets reach the app, and a developer can generate a local secret. | Intent; Q3 |
| 3 | Fail-closed tools | The hooks, the tool server and the start scripts refuse to run without a secret. | Intent; Q3 |
| 4 | In-process backend | The backend runs inside the dashboard, reachable only locally, with at most one copy. | Intent; Q3 |
| 5 | Sign-in gate | Only verified emails on the allowlist get in. | Intent; Q3 |
| 6 | Build identifier | The app shows which build is running. | Intent; Q2 |
| 7 | Reset banner | Viewers are told that the demo data resets. | Intent; Q2 |
| 8 | Post-deploy check | A read-only browser check proves a deployed app works and turns away non-allowlisted visitors. | Intent; Q2 |
| 9 | Hosted apps | The two Streamlit Cloud apps (staging and production) are created and their secrets entered, only after items 1–8 are merged. | Q6, Q10 |

All of items 1–8 are required before any hosted app exists (Q1, Q8).

## Out of Scope

| Item | Where it lives | Source |
|------|----------------|--------|
| The remaining deploy work: the deployment pipeline and production promotion, deployment execution and observability | The parked deploy intent `261004-dashboard-deploy-pipelin`. Its environment-provisioning step moves into this work (item 9). | Q10 |
| Any publish-schedule or submit-PO path from the dashboard, the check or a pipeline | Forbidden by project rules | `project.md` Forbidden |

## Boundary Rules

- No hosted app is created, and nothing is exposed beyond loopback, until the sign-in gate and the secret handling are merged. (`project.md` Forbidden; Q10)
- The post-deploy check is read-only. (`team.md` Deployment)
- The test floor (745) and the coverage floor (95.00) only rise. (Constraint register C-Q2)

## Value Stream

```mermaid
flowchart LR
  A[Secret out of the code] --> B[Tools fail closed]
  B --> C[Backend in-process]
  C --> D[Sign-in gate]
  D --> E[Build ID and reset banner]
  E --> F[Post-deploy check]
  F --> G[Hosted apps created]
  G --> H[Parked deploy work resumes]
```

Text version: secret out of the code → tools fail closed → backend in-process → sign-in gate → build ID and reset banner → post-deploy check → hosted apps created → the parked deploy work resumes.

## Timeline

The target is within a week for the whole (feasibility Q9). The burned-secret removal lands first and sooner than the rest (Q5, Q9). The full process is kept, and the date may slip (Q7).

## Assumptions & Open Questions

- Moving the environment-provisioning step out of the parked deploy intent's plan is an action on that intent. It has to be made there when that intent resumes; this work does not edit it. (Q10)
