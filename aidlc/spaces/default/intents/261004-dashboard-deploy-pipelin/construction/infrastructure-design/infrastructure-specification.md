# Infrastructure Specification — Dashboard Deployment Pipeline

## Sources

- `construction/nfr-design/logical-components.md` C1 to C15 [logical-components]
- `construction/nfr-design/security-design.md`, `reliability-design.md`, `scalability-design.md` [security-design, reliability-design, scalability-design]
- Infrastructure questions IQ1 (app names), IQ2 (one OIDC client per environment), IQ3 (published consent screen)

## Deployment

| Facet | Choice | Rationale |
|---|---|---|
| Compute model | Streamlit Community Cloud: one managed Python process per app, running `dashboard/app.py`, with the mock backend in-process on loopback (RD5) | Approved host. The backend can't be a separate service (SD4, hard rule) |
| Apps | Staging, `hsm-dashboard-staging.streamlit.app`, tracking branch `main`. Production, `hsm-dashboard.streamlit.app`, tracking branch `production` (IQ1) | Two environments with manual promotion (requirements FR6, FR7) |
| Networking | Public HTTPS from Streamlit Cloud's front end, with TLS terminated by the platform. The backend binds `127.0.0.1:8770` inside the process, with no ingress | Sign-in is in-app (SD1). The backend is never reachable from outside (NFR1.5) |
| Storage | None persistent. The audit trail goes to a temp file, and data is in memory; both reset on restart (deferred gap, banner NFR6.11) | Persistence is a separate follow-up (requirements Out of Scope) |
| Environments | Local (developer machine, `.env.local`), CI (ephemeral GitHub runners), staging, production | Staging and production share the code and differ only in secrets and branch (environment parity) |
| IaC approach | No IaC tool. Repository settings (rulesets, Environment, variables, push protection) and the Cloud app configuration are applied by hand from a **settings checklist** in `docs/DEPLOYMENT.md`, verified once and re-verified on change | Two managed platforms with no IaC provider in scope (logical-components C12 assumption). The checklist makes the drift visible |
| Python runtime | Hosted: the newest version Streamlit Cloud offers at app creation, recorded as repository variable `HOSTED_PYTHON`. CI: 3.10 and 3.14, plus `HOSTED_PYTHON` | TS3 |
| Dependencies | Cloud installs the hash-pinned `requirements.txt` (runtime lock). CI installs `requirements-dev.txt` | TS4 |
| Sizing | Free tier, with no sizing knobs | One allowlisted user (NFR6.4) |

## Infrastructure Services

| Service | Role | Configuration | Notes |
|---|---|---|---|
| Streamlit Community Cloud | app hosting | Two public apps; Python = `HOSTED_PYTHON`; main file `dashboard/app.py`; per-app secrets (below) | Apps sleep when idle. The check wakes them (RD1 step 0) |
| GitHub Actions | CI/CD runner | `ubuntu-24.04`, four workflows (see `cicd-pipeline.md`) | Free minutes for public repos |
| GitHub Environment `production` | deployment gate | Required reviewer = owner. Deployment branch policy = `main` only. Secret `PROD_DEPLOY_KEY` | SD5, NFR1.19 |
| GitHub ruleset `main` | trunk protection | Require PR; required checks = `lint`, `workflow-lint`, `secrets`, `audit`, `sast`, `lock-check`, `tests (3.10)`, `tests (3.14)` (+ `tests (HOSTED_PYTHON)` when set; the ruleset is updated in the same change that sets the variable), `coverage-gate`, `browser-tests`; squash only; no bypass | Way of Working practice |
| GitHub ruleset `production` | single writer | Restrict creation, update and deletion; block force push; bypass = deploy keys only | SD5, NFR1.7 |
| Deploy key | production writer | ED25519, write access. Public half on the repo, private half only in the `production` Environment. Rotated every 180 days (calendar entry in the runbook) | NFR1.8 |
| Secret scanning and push protection | leak prevention | Enabled in repository security settings | NFR1.10 |
| Google Cloud project (`hsm-dashboard-auth`) | OIDC identity provider | Two OAuth "Web application" clients, one per app (IQ2). Redirect URIs `https://<app>.streamlit.app/oauth2callback`. Consent screen **published** (IQ3). Scopes `openid email` | Access is controlled by the in-app allowlist plus `email_verified` (SD1). Google does not restrict who may sign in |
| OSV API | vulnerability severity lookup | `api.osv.dev`, read-only, 10 s timeout, fail-closed (SD7) | No credentials |
| Dependabot | pin freshness | `github-actions` and `uv`, weekly | DQ4 |

## Secrets layout

| Secret / setting | Staging app (Cloud secrets) | Production app (Cloud secrets) | Local (`.env.local` / `.streamlit/secrets.toml`, gitignored) | GitHub |
|---|---|---|---|---|
| `HSM_SIGNING_SECRET` | Own random value | Own random value (different) | Own random value from `dev-secret.sh` | — |
| `[auth]` `client_id`, `client_secret`, `redirect_uri`, `cookie_secret`, `server_metadata_url` | Staging OAuth client | Production OAuth client | A local OAuth client or the staging client with a `http://localhost:8501/oauth2callback` redirect, documented in the runbook | — |
| `auth_allowlist` | `["<owner email>"]` | `["<owner email>"]` | `["<owner email>"]` | — |
| `HSM_INPROCESS_BACKEND` | `"1"` | `"1"` | unset (local uses the separately started mock) | — |
| `PROD_DEPLOY_KEY` | — | — | — | `production` Environment secret |

Every secret value is generated fresh, with at least 32 random bytes where it is ours to generate (SD2). The burned value is refused by digest at startup.

## Shared Infrastructure

Not applicable. There is a single unit and no multi-unit shared resources. The only cross-environment shared item is the Google Cloud project, which holds **separate** clients per environment.

## Assumptions & Open Questions

- [assumption] A Streamlit Community Cloud app can be set to a chosen branch and to a Python version at creation. Changing the Python version later means recreating the app, which the runbook covers.
- [assumption] With a published consent screen limited to `openid email` scopes, Google requires no app verification.
- None.
