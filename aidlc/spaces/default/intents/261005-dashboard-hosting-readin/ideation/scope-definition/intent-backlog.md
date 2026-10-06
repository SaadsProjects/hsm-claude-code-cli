# Intent Backlog — Dashboard Hosting Readiness

## Sources

- Scope document: `ideation/scope-definition/scope-document.md`
- RAID log: `ideation/feasibility/raid-log.md`
- Answers Q1–Q10 in `ideation/scope-definition/scope-definition-questions.md`

## Prioritization Method

MoSCoW for importance and dependency order for sequence, adjusted as you directed:
- The burned-secret removal goes first, as its own early change (Q5, Q9).
- After that, the work is risk-first: the items that retire the feasibility risks move as early as their dependencies allow (Q4).

Every item is a **Must**: all eight changes are required before hosting (Q1, Q8). Items 6–8 rank lower within Must, but that only orders them; none is dropped (Q2, Q8).

## Backlog

| Order | Proto-unit | MoSCoW | Depends on | Risk retired | Done when | Source |
|-------|-----------|--------|------------|--------------|-----------|--------|
| 1 | Secret from config, burned value and scan exclusion removed | Must (first) | — | Issue I1 | The burned-secret check passes with the exclusion removed, and the app reads its secret from configuration | Q3, Q5, Q9 |
| 2 | Secrets bridge, dev-secret script and fail-closed tools | Must | 1 | — | Hosted secrets reach the app; the tools refuse to run without a secret | Q3 |
| 3 | In-process backend with a single-instance guard | Must | 1 | R2 | The backend runs inside the dashboard, is reachable only locally, and never runs twice | Q3, Q4 |
| 4 | Sign-in gate (allowlist and verified email) | Must | 1, 3 | R1 | A non-allowlisted or unverified visitor is turned away, locally and on Cloud | Q3, Q4 |
| 5 | Build identifier | Must (lower rank) | 3 | — | The running build is visible in the app | Q2, Q3 |
| 6 | Reset banner | Must (lower rank) | 3 | — | Viewers see that the demo data resets | Q2, Q3 |
| 7 | Post-deploy check and browser tests | Must (lower rank) | 4, 5, 6 | R3 | A read-only browser check passes against a running app and proves the sign-in refusal; it runs in CI | Q2, Q3, Q4 |
| 8 | Create the two hosted apps and enter their secrets | Must (after merge) | 1–7 merged | — | Staging and production apps exist behind the sign-in gate | Q6, Q10 |

Risk-first note: risks R1 (sign-in parity) and R2 (in-process backend) are retired by items 3 and 4, straight after the secret work. Risk R3 (a browser in CI) is retired by item 7, which comes last because it depends on the rest. Proving that a browser is available in CI can be pulled forward without building the check itself.

## Success Metrics Covered

| Metric (intent statement) | Backlog items |
|---------------------------|---------------|
| Changes go through CI | All |
| Burned secret gone | 1 |
| Quality floors held | All |
| Sign-in enforced | 4, 7 |

## Assumptions & Open Questions

- Pulling the "browser available in CI" proof ahead of item 7 is a sequencing suggestion, not a confirmed decision. Delivery Planning settles it.
