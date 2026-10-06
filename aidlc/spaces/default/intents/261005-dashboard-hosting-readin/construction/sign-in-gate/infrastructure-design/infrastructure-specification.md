# Infrastructure Specification — U3 sign-in-gate

## Sources

- `nfr-design/security-design.md` S4 (secrets bridge), S8 (dependency); `nfr-design/performance-design.md` P2 (no I/O); `nfr-design/logical-components.md` (components, shared resources)
- `functional-design/functional-spec.md` W1 (startup order), W3 (sign-in)
- `inception/domain-design/components.md` (SecretsBridge, SignInGate, DashboardShell)
- `inception/contract-design/contract-summary.md` C1 (TokenAuth), C7 (hosted secrets schema)
- `infrastructure-design-questions.md` Q1 A, Q2 A (summary confirmed)
- `memory/team.md` Deployment (host, sign-in gate, allowlist, per-environment secrets, order); `memory/project.md` Forbidden (no exposure without a sign-in layer; never commit `.streamlit/secrets.toml` or `.env.*`)

## Deployment

| Facet | Choice | Rationale |
|-------|--------|-----------|
| Compute model | Unchanged: one Streamlit Community Cloud process per app, with the gate, the bridge and the embedded backend inside it | team.md Deployment; U3 adds code to the dashboard process only |
| Networking | Ingress unchanged: Streamlit Cloud's HTTPS front door to the app. The only new egress is Streamlit's own OpenID Connect traffic to Google (`accounts.google.com`), started by the visitor's sign-in | `st.login` owns the flow (tech-stack-decisions). The gate itself opens no connection (P2) |
| Sign-in callback | `redirect_uri` per app: `https://<app>.streamlit.app/oauth2callback` hosted, `http://localhost:8501/oauth2callback` for a real local sign-in | C7. Each Google OAuth client lists only its own app's redirect |
| Storage | None new. Access is recomputed on every rerun and nothing about it is stored. Browser-session state holds only the refusal log marks and the account binding (logical-components) | No access cache (P1) |
| Environments | Local, staging and production. Each has its own signing secret, cookie secret and OAuth client (team.md). The two hosted apps are created only after this work merges (team.md Order, U6) | No hosted app exists yet, so nothing is exposed before the gate lands |
| IaC approach | None: Streamlit Community Cloud is configured in its console. U3's configuration surface is the committed `.streamlit/secrets.toml.example` (placeholders only) and the dependency lockfiles | No IaC tooling exists for this host |
| Sizing | No change. The gate adds constant-cost work per rerun (P1) | NFR2.11 |

## Signing-Secret Sources (Q1 A)

The bridge sets `HSM_SIGNING_SECRET` from the first source that has it, then the gate runs `require_secret()` (C1):

| Order | Source | When it applies | Behaviour |
|-------|--------|-----------------|-----------|
| 1 | Exported environment variable | Local runs that export it; CI never does (team.md) | Always wins; never overwritten |
| 2 | Streamlit secrets (`HSM_SIGNING_SECRET`, C7) | Hosted apps; local runs with the key in `.streamlit/secrets.toml` | Copied only when the variable is unset or empty (S4) |
| 3 | `.env.local` via `mock_hsm.auth.load_local_secret()` | Local runs only; a hosted checkout has no such file | Reads only the `HSM_SIGNING_SECRET=` line, never overrides a variable that is present, and is a no-op when the file is missing |

- `.env.local` is read at most once per process, because the variable is set afterwards and `load_local_secret` returns early. This is a read of the app's secrets, which NFR2.12 allows. P2's socket test is unaffected.
- An unreadable `.env.local` (for example, a permission error) is an unexpected error, so the gate's boundary turns it into Screen 5 and `gate_error` (S3).
- CLAUDE.md drops the "export it in that shell first" instruction for `streamlit run dashboard/app.py`. The other entry points already read `.env.local` themselves.

## Infrastructure Services

| Service | Role | Configuration | Notes |
|---------|------|---------------|-------|
| Google OpenID Connect | Identity provider (dns/auth) | One OAuth client per environment; `server_metadata_url` is Google's discovery document (C7) | Reached only by Streamlit's sign-in flow. The gate trusts only a boolean `email_verified` (S2) |
| Streamlit secrets | Configuration store | Keys per C7: `HSM_SIGNING_SECRET`, `HSM_ALLOWED_EMAILS`, `[auth]` `redirect_uri` and `cookie_secret`, `[auth.google]` `client_id`, `client_secret` and `server_metadata_url` | Entered by the owner in U6, never committed. Locally, the git-ignored `.streamlit/secrets.toml` |
| `streamlit[auth]==1.64.0` | Runtime dependency (Authlib) | Pinned with hashes in `requirements.txt`, and through it in `requirements-dev.txt` | S8. `lock-check` and `audit` gate it |

## Local Run

| Step | Result |
|------|--------|
| `scripts/dev-secret.sh` once, then `cp .streamlit/secrets.toml.example .streamlit/secrets.toml` with the placeholders left in place | The signing secret comes from `.env.local`, because the example sets none and the placeholder cookie secret differs from it. The settings check passes because every key is non-empty, so `streamlit run dashboard/app.py` shows Screen 1. This is the team's local slice (team.md Walking Skeleton) |
| No `.streamlit/secrets.toml` | Screen 5 (`settings_missing`), the fail-closed result |
| A local Google OAuth client with the localhost redirect filled in, and the developer's email in `HSM_ALLOWED_EMAILS` | A real local sign-in reaches Screen 3. This is how Code Generation confirms the `email_verified` type (security-design residual risk) |

`.streamlit/config.toml` keeps `address = "127.0.0.1"`, so a local run stays on loopback.

## Shared Infrastructure

| Shared Resource | Owner Unit | Consumer Units | Access Boundary |
|-----------------|------------|----------------|-----------------|
| `HSM_SIGNING_SECRET` in the process environment | U1 (C1 contract) | U2 (backend start), U3 (bridge writes it once, gate checks it) | Written only when absent; read at call time; never logged |
| Streamlit secrets of each app | U6 (enters values) | U3 (reads the C7 keys) | Read-only for the app |
| `.streamlit/secrets.toml.example` | U3 | U6 (owner's template), developers | Placeholders only. `HSM_SIGNING_SECRET` is present only as a comment, so a local copy never shadows `.env.local` (source 3) with a placeholder. A test parses the file and asserts it sets no `HSM_SIGNING_SECRET` and that every other value is an obvious placeholder |
| Runtime and dev lockfiles | U3 (adds `streamlit[auth]`) | U5 (adds Playwright to the dev lock) | Edited only through the `.in` files and `uv pip compile` (team.md Code Style) |

## Assumptions & Open Questions

- [assumption] Streamlit Community Cloud lets each app's OAuth redirect be its own `*.streamlit.app` URL. U6 confirms this when creating the apps.
- [assumption] Streamlit 1.64.0 serves the callback at `/oauth2callback` on the app's own origin, as C7 states.
