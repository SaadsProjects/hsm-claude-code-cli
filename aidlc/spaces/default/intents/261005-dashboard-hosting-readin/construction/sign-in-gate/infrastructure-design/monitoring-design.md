# Monitoring Design — U3 sign-in-gate

## Sources

- `nfr-design/security-design.md` S5 (no disclosure in logs), S7 (refusal logging); `nfr-design/performance-design.md` P1 (advisory budget)
- `nfr-requirements/security-requirements.md` NFR4.11; `performance-requirements.md` NFR2.11
- `infrastructure-design-questions.md` Q1 A, Q2 A (summary confirmed)
- `memory/team.md` Deployment (smoke checks; the app log on Streamlit Cloud); `memory/project.md` Corrections (the post-deploy check never signs in)

## Approach

The hosted demo has no metrics backend, alerting service or tracing (team.md Deployment). Its monitoring surface is the app log, which Streamlit Community Cloud shows to the owner, plus the post-deploy check (U5) after each deploy. U3 adds one logger, `dashboard.auth_gate`, and adds no infrastructure.

## Metrics & KPIs

| Metric | Source | Threshold | Why it matters |
|--------|--------|-----------|----------------|
| `settings_missing` lines | App log, WARNING | Any line on a hosted app | The app's secrets are incomplete or the signing secret equals the cookie secret, so every visitor sees Screen 5 |
| `allowlist_invalid` lines | App log, WARNING | Any line on a hosted app | `HSM_ALLOWED_EMAILS` is malformed, so every visitor sees Screen 5 |
| `gate_error` lines (with the exception type) | App log, WARNING | Any line | An unexpected failure in the gate or at provider sign-out. The type names the code path to check |
| `not_verified` / `not_listed` lines | App log, INFO | None; informational | Who-was-refused counts without identity data. A rise means someone is trying the app or the owner forgot to list someone |
| Gate time per rerun | `perf`-marked test, run by hand | p95 at most 50 ms | NFR2.11. It never runs in CI, so the budget is advisory (P1) |

## Alerts

| Alert | Condition | Severity | Routes to |
|-------|-----------|----------|-----------|
| Post-deploy check fails | U5's check finds no Screen 1 for a signed-out visitor, or finds a refused visitor let in | Blocks the deploy | Repository owner, through the failed workflow run |
| None automatic for the log | — | — | The owner reads the app log when a visitor reports Screen 5. A free Streamlit Cloud app has no log-based alerting |

## SLIs / SLOs

| SLI | SLO target | Measurement window |
|-----|------------|--------------------|
| Signed-out visitor reaches Screen 1 on a deployed app | Every post-deploy check run passes (U5) | Per deploy |
| A refused visitor never sees tabs or the persona picker | 100%, held by U3's tests (NFR1.21) and U5's refusal check | Per pull request and per deploy |

No availability SLO is set for the demo. Streamlit Community Cloud sleeps idle apps, and the app recomputes access on every rerun with nothing to fail over.

## Logs & Tracing

- **Format:** standard-library `logging` records on `dashboard.auth_gate`, as `gate refusal reason=<reason>`. A `settings_missing` line adds the setting names, and a `gate_error` line adds `error=<ExceptionType>`. No email, secret value, setting value, allowlist entry or exception message is ever logged (S5).
- **Volume:** at most one line per reason per browser session (S7), so at most five lines per session. A signed-out visitor produces none.
- **Retention:** whatever Streamlit Community Cloud keeps. The log resets with the app, as the demo data does.
- **Tracing and dashboards:** none. A single process with no outbound calls of the gate's own has nothing to trace (P2).

## Assumptions & Open Questions

- [assumption] Streamlit Community Cloud's log view shows INFO and WARNING records from the app's own loggers. If it shows only WARNING and above, the INFO refusal counts are lost on hosted apps, but no failure signal is lost.
