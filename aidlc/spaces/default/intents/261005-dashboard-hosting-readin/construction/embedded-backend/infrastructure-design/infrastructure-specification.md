# Infrastructure Specification — U2 embedded-backend

## Sources

- `nfr-design/` (security S1–S5, performance P1–P3, scalability SC1–SC3, reliability R1–R6, observability O1–O4, logical-components)
- `inception/domain-design/components.md`; `inception/contract-design/contract-summary.md` C2, C3
- `memory/team.md` Deployment; `infrastructure-design-questions.md` Q1, Q2 (both A)

## Deployment

| Facet | Choice | Rationale |
|-------|--------|-----------|
| Compute model | One Streamlit Community Cloud app process per environment; the mock backend runs inside it in a daemon thread | Streamlit Cloud runs a single process; team.md Deployment |
| Networking | The backend binds `127.0.0.1` on a free port chosen by the OS; only the dashboard in the same process calls it; no ingress to the backend | NFR1.11; project.md Forbidden (backend never reachable from outside) |
| Storage | Demo data in `mock_hsm.db` process memory; audit trail at `<temp>/hsm-demo-<user id>/audit.jsonl` on the app's own disk, directory mode 0700 | NFR1.13; Q1 A; resets with the app as the banner states |
| Environments | Local (developer machine), staging app (tracks `main`), production app (tracks the promotion pointer); same code and defaults in each | team.md Deployment |
| Configuration | `HSM_SIGNING_SECRET` from the environment (Streamlit secrets when hosted, via U3's bridge); `HSM_AUDIT_PATH` left unset on hosted apps; `HSM_BASE_URL` not read by the dashboard | C2; Q1 A; BR4.1 |
| IaC approach | None: Streamlit Cloud apps are created by hand once U1–U3 have merged (team.md Deployment order) | No cloud resources to declare |
| Resource sizing | Streamlit Cloud's free-tier limits; no tuning | Demo load: a short allowlist of visitors |

## Infrastructure Services

| Service | Role | Configuration | Notes |
|---------|------|---------------|-------|
| Embedded mock backend | API for the dashboard (in-process) | `ThreadingHTTPServer` on `127.0.0.1:<free port>`, one per process | No external service |
| Local disk | Audit trail storage | Private temp subdirectory; file mode 0600 | Ephemeral on Streamlit Cloud |

No database, cache, queue, search, CDN, DNS or load balancer is added.

## Assumptions & Open Questions

None.
