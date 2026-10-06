# Observability Requirements — Dashboard Deployment Pipeline

## Sources

- `requirements.md` NFR7 (visibility) and the Out of Scope item on monitoring [requirements]
- NFR questions NQ11 (scheduled check) and NQ13 (a deliberate, small scope addition that supersedes the "no alerting" exclusion for this one check)

## Requirements

| ID | Requirement | Verify |
|---|---|---|
| **NFR7.1** | Each workflow run (CI, staging check, promotion, scheduled check) writes a GitHub job summary with: the result; the commit SHA; for checks, the observed build identifier, whether a wake click was needed, and which steps (0), (a), (b) and (c) of reliability NFR6.2 passed or were skipped; for CI, the test counts (passed, skipped, rerun) and coverage %. | Inspection of the summary at the skeleton checkpoint. The summary-writing helper is unit-tested. |
| **NFR7.2** | A failed run marks the commit status or the run as failed, so it shows on the commit and the PR. | GitHub default behaviour, confirmed at the skeleton checkpoint. |
| **NFR7.3** | **Scheduled production check** [NQ11, NQ13]: a workflow on `schedule` (cron every 6 h) and `workflow_dispatch` runs the read-only post-deploy check against production, comparing against the commit at the head of `production`. A failure fails the run, which notifies the owner through GitHub's standard failed-workflow email. It is a correctness probe, **not** an availability SLO: no uptime percentage is computed or targeted. | The workflow file exists with the cron. A manually dispatched run passes at the skeleton checkpoint. |
| **NFR7.4** | Logs never contain secrets or the signed-in email in plain text, except the email in the app's own UI (security NFR1.6). | Same evidence as NFR1.6. |
| **NFR7.5** | The app logs startup configuration problems (missing secret, missing allowlist, failed backend start) at ERROR level to stdout, so they appear in Streamlit Cloud's app logs. The log names the missing setting, never its value. | Unit tests: each missing-setting path emits one ERROR record naming the setting. |

## Out of scope

- Metrics dashboards, tracing, uptime percentages, paging, and external monitoring services. NFR7.3 is the only scheduled probe.

## Assumptions & Open Questions

- [assumption] GitHub sends failed-scheduled-workflow notifications to the owner. Scheduled workflows are disabled after 60 days without repository activity; the runbook notes how to re-enable them.
- None.
