# Observability Design — Dashboard Deployment Pipeline

## Sources

- `construction/nfr-requirements/observability-requirements.md` NFR7.1 to NFR7.5 [observability-requirements]
- NFR Design answer DQ6 (issue on a failed production check)

## OD1 — Job summaries (NFR7.1)

`scripts/job_summary.py` is a pure formatter with unit tests. Each workflow calls it with structured inputs and appends its Markdown to `$GITHUB_STEP_SUMMARY`:

| Workflow | Fields |
|---|---|
| `ci.yml` | commit SHA; Python leg; passed/skipped/failed counts and rerun test names (from JUnit XML); coverage % and current `.coverage-floor` (3.14 leg) |
| `staging-check.yml`, `prod-check.yml`, `promote.yml` | target URL; expected and observed build identifier; `wake_clicked`; per-step result for steps 0, a, b and c (pass, skip, fail); the commit status posted (staging only) |
| `promote.yml` | mode; target commit; previous `production` SHA; tag created |

The formatter never receives secret values. Its inputs are counts, SHAs, URLs and step results.

## OD2 — Failure visibility (NFR7.2, NFR7.3, DQ6)

- A failed job fails the run, which GitHub shows on the commit or PR and emails to the owner.
- `staging-check` also posts a failing commit status (RD2), so the commit shows the failure next to CI.
- `prod-check.yml` job 2 opens the `prod-check-failure` issue, or comments on the open one (RD4).
- The runbook notes that GitHub disables scheduled workflows after 60 days without repository activity, and how to re-enable them.

## OD3 — App logs (NFR7.4, NFR7.5)

- The dashboard configures Python `logging` at INFO to stdout, where Streamlit Cloud captures it.
- These conditions log at ERROR level, each naming the setting and never its value:
  - missing or invalid `HSM_SIGNING_SECRET`
  - missing or malformed `auth_allowlist`
  - backend start failure
  - missing `[auth]` settings
- On a denied sign-in, the app logs at WARNING the fact of the denial and the email's domain only (for example `denied: user at gmail.com`). The full address is not logged.
- Unit tests capture log records for each path and assert the setting name is present and no secret value is.

## Out of scope

- Metrics, tracing, dashboards and uptime computation, as stated in the observability requirements.

## Assumptions & Open Questions

- [assumption] Streamlit Community Cloud keeps app stdout logs viewable by the app owner.
- None.
