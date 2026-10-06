# Monitoring Design — U2 embedded-backend

## Sources

- `nfr-design/observability-design.md` O1–O4
- `nfr-requirements/observability-requirements.md` NFR4.2–NFR4.4, NFR5.1

## Metrics & KPIs

| Metric | Source | Threshold | Why it matters |
|--------|--------|-----------|----------------|
| Backend start outcome | `mock_hsm.embedded` log lines (INFO started, WARNING failed) | Any WARNING "failed to start" | The app shows Screen 4 to every visitor while it lasts |
| Backend replacements | WARNING "embedded backend replaced" lines | More than one per hour | Points to a server thread dying repeatedly |

No metrics backend exists for the demo; these are read from the Streamlit Cloud app log.

## Alerts

| Alert | Condition | Severity | Routes to |
|-------|-----------|----------|-----------|
| None automated | — | — | The owner reads the app log; the post-deploy check (U5) is the deployment health signal |

## SLIs / SLOs

| SLI | SLO target | Measurement window |
|-----|------------|--------------------|
| Backend start time | Under 2 seconds (NFR2.1) | Each start, checked by a CI test |
| Cold start to usable page | Under 30 seconds (NFR2) | The post-deploy check's run against staging (U5) |

## Logs & Tracing

- Logger `mock_hsm.embedded`, standard `logging`, no handler added by the module; Streamlit Cloud's app log captures WARNING and above.
- Log lines carry the technical cause (which may include a path) and never the secret value (NFR1.14).
- No tracing: one process, one in-process HTTP hop.
- No dashboards beyond the existing sidebar backend caption, which shows the live backend's address (NFR4.4).

## Assumptions & Open Questions

None.
