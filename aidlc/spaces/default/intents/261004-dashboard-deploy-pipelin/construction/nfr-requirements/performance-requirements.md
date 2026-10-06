# Performance Requirements — Dashboard Deployment Pipeline

## Sources

- `requirements.md` NFR2 (CI feedback time) [requirements]
- NFR questions NQ9 (page speed) and NQ3 (headless check). The page-speed target is new at this stage: requirements had no page-speed NFR, so NQ9 is its origin, and it is filed under NFR2 as the only performance requirement.
- Measured suite baseline: 757 tests collected, 745 passed, 86.7 s on Python 3.14.7 (practices-discovery evidence).

## Requirements

| ID | Metric | Target | Condition | Measurement / pass-fail |
|---|---|---|---|---|
| **NFR2.1** | Wall time of a pull request's full CI run | ≤ 15 min | All jobs, with the 3.10/3.14 matrix legs run in parallel (plus a third leg if tech-stack decision TS3 adds one), on GitHub-hosted runners | GitHub run duration. Each job sets `timeout-minutes` (test job 15, others 10), so a slow job fails rather than hangs. |
| **NFR2.2** | Test-suite wall time per matrix leg | ≤ 5 min | Serial run (no `-n`), coverage on | The pytest step sets a step-level `timeout-minutes: 5`, so exceeding it fails the step. Step timing appears in the job summary [review R-05]. |
| **NFR2.3** | Time from an awake app to the signed-in user's first dashboard view | At most **1 of 20** consecutive loads exceeds 5 s [NQ9, review R-06] | Staging app already awake (cold start excluded); owner signed in; default persona | Measured manually at the walking-skeleton checkpoint over 20 page loads, from browser devtools "load" to the first data element. Recorded in the runbook. Not automated, because the automated checks never sign in (requirements FR8.3). |
| **NFR2.4** | Post-deploy check duration | ≤ 10 min of waking and waiting for the redeploy (including the single wake click, reliability NFR6.2 step 0), then ≤ 2 min for the checks themselves | Staging or production | The script's own timeout. When the wait runs out, it fails and says which step was unmet (see reliability NFR6.2). |
| **NFR2.5** | Scheduled production check duration | ≤ 12 min | Every 6 h | `timeout-minutes: 15` on the job. |

## Out of scope

- Load or throughput targets for the dashboard. It serves one allowlisted user (see scalability).

## Assumptions & Open Questions

- [assumption] GitHub-hosted `ubuntu-latest` runners run the suite in about the same time as the measured local baseline (86.7 s), within a factor of 2.
- None.
