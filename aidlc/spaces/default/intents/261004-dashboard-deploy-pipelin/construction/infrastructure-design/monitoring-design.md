# Monitoring Design — Dashboard Deployment Pipeline

## Sources

- `construction/nfr-design/observability-design.md` OD1 to OD3 [observability-design]
- `construction/nfr-design/reliability-design.md` RD1, RD2, RD4 [reliability-design]
- `construction/nfr-design/performance-design.md` PD1 to PD3 [performance-design]

## Metrics & KPIs

| Metric | Source | Threshold | Why it matters |
|---|---|---|---|
| PR CI wall time | GitHub run duration | ≤ 15 min (job timeouts enforce it) | Feedback speed (NFR2.1) |
| Test step time per leg | Step timing in the summary | ≤ 5 min (step timeout) | NFR2.2 |
| Passed tests per leg | JUnit XML via `test_floor.py` | ≥ `.test-floor` (745), 0 failures | Regression floor (NFR4.1) |
| Rerun tests | JUnit XML via `job_summary.py` | Listed by name; no threshold | Makes flakiness visible (NFR4.1) |
| Line coverage | `coverage.json` | ≥ `.coverage-floor`; ≥ 80 for promotion | NFR3.1 |
| Post-deploy wait time | `postdeploy_check.py` report | ≤ 10 min (timeout) | NFR2.4 |
| Staging and production check result | Commit status, job result | Must be success | Deploy correctness (NFR6.2) |

## Alerts

| Alert | Condition | Severity | Routes to |
|---|---|---|---|
| CI failure | Any required `ci.yml` job fails on a PR or on `main` | Ticket-level | GitHub failed-run email to the owner; red check on the PR or commit |
| Staging check failure | `staging-check.yml` fails | Ticket-level | Failed-run email; `staging-check` commit status = failure |
| Promotion verify failure | `promote.yml` `verify` fails | High (production is serving something unverified) | Failed-run email; you decide whether to roll back |
| Production check failure | `prod-check.yml` `check` fails | High | Failed-run email, plus a `prod-check-failure` issue opened or commented (RD4) |
| Nightly browser tests failure | `ci.yml` `browser-tests` on schedule fails | Ticket-level | Failed-run email |
| Expiring security exception | `check_exceptions.py` warns when an entry expires within 14 days | Info | Shown in the `audit` job summary |

## SLIs / SLOs

| SLI | SLO target | Measurement window |
|---|---|---|
| — (deliberately none) | No availability SLO (requirements Q8, NQ13) | — |

The production check is a **correctness probe**: does the right build serve only the sign-in page to anonymous visitors? It is not an uptime measure. No percentage is computed.

## Logs & Tracing

| Concern | Design |
|---|---|
| App logs | Python `logging` at INFO to stdout, viewable in the Streamlit Cloud app logs. ERROR lines name a missing setting and never its value. A denied sign-in logs only the email domain (OD3) |
| Workflow logs | GitHub Actions run logs, retained under GitHub's default retention. Secrets are masked and never on command lines (SD5) |
| Check artifacts | Playwright traces and screenshots, staging only, retained 7 days |
| Tracing | None. The system is a single process |
| Dashboards | None. Each workflow's job summary is its dashboard (OD1). The repository's Actions tab and the commit statuses give the history |

## Assumptions & Open Questions

- [assumption] The owner's GitHub notification settings email on failed workflow runs (the default for runs the owner triggered, or for scheduled workflows on repos they own).
- None.
