**Collaborator:** aidlc-devsecops-agent

## Contribution

Scope of this review: lint/format rules, SAST/DAST, secret and dependency scanning, supply-chain controls for the new CI/CD pipeline, and the exposure that comes from deploying the dashboard. Every finding below was checked against the source at commit `1586133`. Nothing here is affirmed practice. Each item is a candidate for the lead to integrate or turn into an interview question.

### 1. Verified facts the lead draft should carry (security-relevant)

| # | Fact | Source |
|---|---|---|
| F1 | **The dashboard process holds the token-signing secret.** `dashboard/session.py` imports `mock_hsm.auth.mint_token` and signs a token for whatever `user_id` the login selectbox returns. So the dashboard and backend form **one trust domain**. Moving the secret "to the backend only" is impossible without a code change. | `dashboard/session.py:23,51-54`, `mock_hsm/auth.py:23` |
| F2 | **Login is a persona picker with no credential.** `_login_panel()` lists every key of `USERS`, including `user_dev_tester` (a Regional Manager-scoped test identity), and logs in on a button click. Anyone who can load the page can act as any listed persona and write through "Manage data". | `dashboard/app.py:300-307`, `mock_hsm/db.py:38-49` |
| F3 | **The HMAC secret is a literal in tracked source** (`demo-shared-secret-not-for-production`). Anyone with repository read access can mint arbitrary claims, including `persona: SYSTEM_ADMIN`. The server's scope checks pass that persona through unconditionally (`site_allowed`, `region_allowed`, `server.py:170`). If the GitHub repo is public, any backend reachable from a network is fully forgeable. | `mock_hsm/auth.py:23,70-79` |
| F4 | Backend and client use plain HTTP (`ThreadingHTTPServer`, `http://127.0.0.1:8770`), and both bind loopback by default. That is safe only while both stay on one host or in one network namespace. | `mock_hsm/server.py:720-726`, `agents/hsm_client.py:21` |
| F5 | Audit writes fail closed: if `HSM_AUDIT_PATH` is unwritable, gated writes return 503. A container with a read-only or ephemeral filesystem either breaks writes or loses the audit trail on each redeploy (a repudiation gap). | `CLAUDE.md` audit paragraph |
| F6 | The lint gate is **local-only and opt-in**. `lint_before_commit.py` is registered only in the gitignored `settings.local.json`, so a fresh clone or a GitHub web edit has no gate. The `ruff` **version** is unpinned (`requirements.txt: ruff`), so the hook and a future CI job can disagree when ruff ships rule changes. | `.claude/settings.local.json.example`, `requirements.txt`, `.gitignore` |
| F7 | No security tooling exists: no SAST (the ruff `S`/flake8-bandit group is not selected), no secret scanner, no dependency audit, no lockfile, no Dependabot, no `.github/`. | `ruff.toml`, repo root |
| F8 | Existing app-layer controls to keep: Markdown/HTML escaping of untrusted text (`dashboard/safe_text.py`), a 2 MB upload cap (`.streamlit/config.toml`), per-session write quotas and a session sweep (`mock_hsm/writes.py`). Streamlit's default XSRF protection is on, and nothing in the repo turns it off. | listed files |

### 2. Threat summary for "deploy the dashboard" (STRIDE, brief)

The risk depends almost entirely on **reachability** (lead Q8).

- **Spoofing / Elevation (Critical if network-reachable):** F2 and F3 together mean no authentication at the dashboard, and a backend whose signing key is public to every repo reader. Any exposure beyond loopback needs an authenticating layer *in front of* Streamlit, plus a backend that is not reachable from outside the dashboard's host or task.
- **Tampering:** anyone who reaches the dashboard can perform writes (F2). The CI pipeline itself also becomes a tamper path: actions that are not pinned, or a deploy credential with broad scope.
- **Repudiation:** the audit trail records a `user_id`, but with F2 that id is self-asserted, and with F5 it may not survive a redeploy.
- **Information disclosure:** the data is mock/seeded, but this needs confirming (see SQ4). Plain HTTP between components is acceptable only on loopback.
- **DoS:** Streamlit has no rate limiting, and the backend is single-process and in-memory. Exposing either to the internet without a proxy-level rate limit is a risk.

### 3. Candidate pipeline security gates (for Q11 / CI design)

Sized for a solo, Python-only, GitHub-hosted repo. Each gate uses free tooling.

| Stage | Control | Blocking? (proposed) |
|---|---|---|
| PR / push | `ruff check` with a **pinned ruff version** matching the local hook | Block |
| PR / push | SAST: add ruff `S` (flake8-bandit) rules, **or** run `bandit -r agents dashboard mcp_server mock_hsm` | Block on High; `S105` on `auth.py:23` needs a documented `# noqa` with a reason, or the secret moves to the environment (see R-SEC-3) |
| PR / push | Secret scan: `gitleaks` over the diff and full history, plus GitHub secret scanning and push protection | Block; the demo secret is allowlisted explicitly with a justification, never by a blanket rule |
| PR / push | Dependency audit: `pip-audit` against a **hash-pinned lock** (`pip-compile --generate-hashes` or `uv lock`) | Block on Critical/High with a fix available |
| Build (if container) | Non-root user, slim base, `trivy image` scan, SBOM (`syft`/`trivy`) attached to the artifact, image tagged by git SHA | Block on Critical |
| Workflow hygiene | GitHub Actions pinned by **full commit SHA**, top-level `permissions: contents: read`, no `pull_request_target`, Dependabot for both `pip` and `github-actions` | Policy |
| Deploy | Cloud credentials via **GitHub OIDC** with a role per environment, never long-lived keys in repo secrets. Production behind a GitHub Environment with required reviewers (matches the org `## Deployment` default) | Block |
| Post-deploy (staging only) | Smoke check on `/_stcore/health`. OWASP ZAP baseline **only if** staging is network-reachable (Streamlit's websocket UI limits what ZAP finds, so treat it as advisory) | Advisory |

Waivers should be time-boxed and in code (a suppression file or inline `# noqa: Sxxx` with a reason and date), never set in the CI UI.

### 4. Candidate discovered rules (security), for the lead to add as "pending human confirmation"

- R-SEC-1 NEVER expose the dashboard beyond loopback or a private network without an authenticating layer in front of it (reverse-proxy auth, an identity-aware proxy, or a VPN/tailnet). *(source: F2, `dashboard/README.md` "trusted network" wording)*
- R-SEC-2 NEVER make the mock backend (`:8770`) reachable from outside the dashboard's own host, container or task. *(source: F3, F4)*
- R-SEC-3 NEVER deploy beyond localhost with the hardcoded `_SECRET`. Read it from an environment variable sourced from a secrets store, and fail closed when it is unset outside local dev. *(source: F3; operation-phase guardrail "never hardcode credentials")*. Note: this is a code change in `mock_hsm/auth.py`, which is in scope for this intent only if the human agrees.
- R-SEC-4 ALWAYS pin third-party GitHub Actions by commit SHA and give workflows least-privilege `permissions`.
- R-SEC-5 ALWAYS authenticate deploys with short-lived OIDC credentials. NEVER store cloud access keys as repository secrets.
- R-SEC-6 ALWAYS run lint, the test suite, secret scan and dependency audit in CI as required status checks before deploy. The local hook stays, but CI is the authoritative gate (F6).

### 5. Gaps the interview must resolve (add to the lead's question list)

- **SQ1 Repository visibility.** Is `SaadsProjects/hsm-claude-code-cli` public? If so, F3 already means the signing key is public, so R-SEC-2 and R-SEC-3 stop being hardening and become prerequisites.
- **SQ2 Authentication in front (refines Q8).** If the dashboard is reachable beyond localhost, which layer authenticates: a cloud load balancer with OIDC/Cognito, an identity-aware proxy, a tailnet/VPN only, or HTTP basic auth at a reverse proxy? Should the persona picker stay as an *authorization-within-the-demo* selector behind that layer? Should `user_dev_tester` be hidden in deployed environments?
- **SQ3 Gate thresholds.** Which severities block: Critical/High (proposed) or Critical only? Is a time-boxed waiver acceptable for a solo maintainer, and who approves it?
- **SQ4 Data classification.** Is every record synthetic/seeded (no real staff names, wages or vendor data)? That decides whether encryption-at-rest, TLS-everywhere and log redaction requirements apply.
- **SQ5 Audit persistence (refines Q9).** Must the audit trail survive redeploys (a persistent volume for `HSM_AUDIT_PATH`), or is reset-on-deploy acceptable for a demo?
- **SQ6 Branch protection (refines Q2).** Once CI exists, should `main` require the CI checks, with admin bypass disabled? For a solo developer this is the only control that makes the pipeline gate non-optional.
- **SQ7 Dependency pinning (split out of Q11).** Should a hash-pinned lockfile be adopted, and the ruff version pinned to match `.venv` (0.16.8)? This is supply-chain, not code style, and it is a prerequisite for meaningful `pip-audit` results and reproducible images.
- **SQ8 SAST choice.** Should ruff `S` rules be added to `ruff.toml` (one tool, already gated, but it changes lint output for every commit), or should bandit run as a separate CI-only job? Should CodeQL be enabled (free for public repos)?

## Positions

- AGREE: Evidence inference 4 ("security posture of the deploy target is the dominant risk") — the source confirms it and it is worse than drafted. The dashboard itself signs tokens with the shared secret (F1), so the risk cannot be contained by protecting the backend alone.
- AGREE: Deployment section must not be affirmed until Q6 to Q10 are answered — correct. Reachability (Q8/SQ2) should be answered **first**, because it decides whether R-SEC-1 to R-SEC-3 are prerequisites or hardening.
- OBJECT: Deployment section's provisional "merges to `main` deploy to a non-production environment automatically" — as written, this could put the unauthenticated, write-capable dashboard on a reachable host from the first pipeline run. The provisional text should be qualified: automatic deploy-on-merge applies only to a target that is loopback, private-network or authenticated-proxy-only until SQ2 is answered.
- OBJECT: Walking Skeleton's slice ("dashboard into one target environment where a smoke check reaches it") — the slice should also prove the minimum security gates (pinned-version ruff, secret scan, dependency audit as required checks) and that the backend port is not externally reachable. Without that, the skeleton validates a path that later security units have to retrofit.
- OBJECT: Q11 bundles "pin dependency versions or add a lockfile" under CI platform and code style — dependency pinning is a supply-chain control and a prerequisite for dependency scanning and reproducible artifacts. It should be its own question (SQ7) and, if confirmed, a Mandated rule, not a style preference.
- OBJECT: `discovered-rules.md` has no security-pipeline candidates — every candidate restates existing `CLAUDE.md` rules, but this intent introduces new attack surface (a CI workflow, deploy credentials, a network listener). R-SEC-1 to R-SEC-6 should be added as candidates pending confirmation so the interview can accept or drop them explicitly.
- AGREE: Code Style "lint runs today only through the fail-closed local commit hook; the pipeline should add that" — correct, and stronger than drafted. The hook is gitignored and opt-in (F6), so CI must be the authoritative gate, with the ruff version pinned so both give the same answer.
- AGREE: Forbidden candidate "NEVER call `publish_schedule` or `submit_purchase_order` from a pipeline, smoke test, or deploy step" — it also bounds the smoke test: post-deploy checks should use `/_stcore/health` and read-only GETs only.
- AGREE: Mandated candidate on `HSM_AUDIT_PATH` pointing at a temp file in CI — it also keeps CI from needing a writable persistent volume. Deployed environments need the opposite decision (SQ5).
