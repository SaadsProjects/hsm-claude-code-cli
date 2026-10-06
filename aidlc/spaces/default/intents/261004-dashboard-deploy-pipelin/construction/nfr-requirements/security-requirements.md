# Security Requirements — Dashboard Deployment Pipeline

## Sources

- `inception/requirements-analysis/requirements.md`: NFR1 (security), FR2, FR3, FR5, FR7, FR8 [requirements]
- The NFR questions file, `nfr-requirements-questions.md`, answers NQ1 to NQ13. "NQ" marks this stage's questions, to keep them apart from the requirements stage's Q1 to Q12.
- Hard rules in `aidlc/spaces/default/memory/project.md` (`## Mandated`, `## Forbidden`) [memory:M1]
- Repository facts checked at `1586133`:
  - `mock_hsm/auth.py:23` holds a secret literal.
  - `dashboard/session.py` imports `mint_token`.
  - `dashboard/app.py` imports `mock_hsm.db.USERS`.
  - The repo is public (`gh repo view`: `PUBLIC`).
  - Streamlit 1.64.0 provides `st.login`.

## Scope and data classification

- **Data:** all hosted data is synthetic, seeded demo data. There are no real staff, wages or vendors. **Classification: Internal** [NQ12].
- **Personal data:**
  - The owner's sign-in email, held in Streamlit secrets as the allowlist.
  - The signed-in email returned by the identity provider, shown in the app session.

  No other personal data is collected or stored. No regulatory framework (GDPR data-subject processing beyond the owner's own account, PCI, HIPAA, SOC 2) applies.
- **Secrets in scope:**
  - The token-signing secret (one per environment).
  - The OIDC client secret and cookie secret for `st.login` (one set per environment).
  - The production deploy key.

## Threat model (STRIDE, condensed)

Trust boundaries:
- (1) internet → Streamlit Cloud app;
- (2) app process → in-process mock backend on `127.0.0.1`;
- (3) GitHub repo/Actions → Streamlit Cloud (branch tracking);
- (4) promotion workflow → `production` branch.

| # | Threat | Boundary | Risk before | Mitigation (requirement) | Risk after |
|---|---|---|---|---|---|
| T1 | Spoofing: anyone mints an admin token with the public, committed signing secret | 2 | Critical | NFR1.3, NFR1.4: new per-environment secrets; the old value is never used | Low |
| T2 | Spoofing / info disclosure: an anonymous visitor reaches dashboard data | 1 | High | NFR1.1, NFR1.2: sign-in before any render, plus an allowlist re-checked on every interaction | Low |
| T3 | Elevation: a signed-in non-allowlisted user reaches data | 1 | High | NFR1.2 | Low |
| T4 | Spoofing: an external caller reaches the backend port and forges requests | 2 | Medium | NFR1.5: the backend binds to loopback only, in-process | Low |
| T5 | Tampering: someone pushes untested code to `production`, including through a modified promotion workflow on another branch | 4 | High | NFR1.7, NFR1.8, NFR1.19: ruleset, an approval-gated deploy key, and an Environment that deploys from `main` only | Low |
| T6 | Tampering: a compromised third-party Action exfiltrates secrets | 3 | Medium | NFR1.9: SHA pins and least-privilege `permissions` | Low |
| T7 | Info disclosure: a secret leaks into a commit or log | 3 | Medium | NFR1.6, NFR1.10, NFR1.11 | Low |
| T8 | Tampering: a vulnerable dependency ships | 3 | Medium | NFR1.12, NFR1.13 | Low |
| T9 | Repudiation: who promoted what is unknown | 4 | Low | NFR1.8: Environment approval history plus the job summary (NFR7) | Low |
| T10 | DoS: the free-tier app is exhausted | 1 | Low | Accepted: demo with no availability target (requirements NFR6) | Low (accepted) |

## Requirements

Each row is testable. "Verify" names the pass/fail evidence.

| ID | Requirement | Verify |
|---|---|---|
| **NFR1.1** | The dashboard calls `st.login` and renders **nothing** except the sign-in prompt, the build SHA (NFR7.1) and the demo banner until `st.user.is_logged_in` is true. This applies **everywhere: hosted apps and local runs** [NQ1]. | Unit test using Streamlit AppTest: with no user, the app renders no element whose text matches any data marker (NFR1.15). Playwright anonymous check against staging (reliability NFR6.2). |
| **NFR1.2** | After sign-in, the app checks two things. First, if the provider supplies the `email_verified` claim, it must be true. Second, `st.user.email` must match an entry of the allowlist in `st.secrets` (initially the owner only), compared case-insensitively and exactly. Allowlist entries must be non-empty strings containing exactly one `@`. An empty allowlist, or any malformed entry, makes the app fail closed with a configuration error and no data. On a mismatch, or when `email_verified` is false, it shows "Access denied" and stops rendering. The check runs on **every script run (interaction)**, not only at sign-in, so removing an email takes effect on that user's next interaction [NQ10]. | Unit tests: an allowlisted, verified email renders data. A non-allowlisted email renders the denial and no data markers. `email_verified: false` renders the denial. A missing or empty allowlist, or a malformed entry, fails closed with a configuration error and no data. |
| **NFR1.3** | `mock_hsm/auth.py` stays **standard-library only** and contains no secret literal. It reads only the `HSM_SIGNING_SECRET` environment variable. An absent or empty value, or one shorter than 32 bytes, raises an explicit configuration error the first time a token is minted or verified. There is no default anywhere, locally included. The **dashboard**, not `mock_hsm`, bridges Streamlit secrets: at startup, before the in-process backend starts and before any token is minted, it copies `st.secrets["HSM_SIGNING_SECRET"]` into `os.environ` if the environment variable is unset [requirements FR3, Q6]. | Unit tests: a missing, empty, or too-short value each raises, and a valid value round-trips. A test asserts `mock_hsm/auth.py` imports no third-party module. A dashboard test asserts the bridge sets the variable from secrets only when it is unset. A CI `grep`: the old literal does not occur in tracked files other than `.gitleaks.toml` (NFR1.11). |
| **NFR1.4** | Staging and production each use a freshly generated signing secret (at least 32 random bytes, from `secrets.token_urlsafe(32)` or equivalent). The two differ, and neither equals the burned value. Rotation is documented in the runbook [requirements FR3.4]. The burned value is refused at startup by comparing the **SHA-256 digest** of the configured secret with a stored digest constant. The plain burned literal never appears in source or tests. | A unit test monkeypatches the stored digest constant to the digest of a test-generated value and asserts that value is refused. The real constant is checked in a test to be 64 hex characters. Runbook step for generating and rotating secrets. |
| **NFR1.5** | The in-process backend binds only to `127.0.0.1`. Its host and port come from `HSM_BACKEND_HOST`/`HSM_BACKEND_PORT`, which default to `127.0.0.1:8770`. A non-loopback host is refused when the dashboard starts the backend in-process [requirements FR4, hard rule]. | Unit test: starting the in-process backend with host `0.0.0.0` raises. Integration test: the backend thread answers on loopback. |
| **NFR1.6** | No secret value appears in workflow logs, job summaries, Playwright traces or screenshots, or app error messages. Workflows pass secrets only through `${{ secrets.* }}` and environment variables, never as command-line arguments. | Review of the workflow YAML in CI (actionlint, plus a grep check that no `secrets.` reference sits on a `run:` command line). Playwright artifacts are not uploaded for production runs. |
| **NFR1.7** | A repository ruleset on `production` blocks creation by others, updates, force-pushes and deletion. Its **only** bypass actor is a deploy key [NQ4]. | Settings check documented in the runbook. A negative test: a push to `production` with the default `GITHUB_TOKEN` is rejected (manual check at setup, recorded in the runbook). |
| **NFR1.8** | The deploy key's private half is stored **only** as a secret of the `production` GitHub Environment. That Environment requires the owner's approval, so the key is unavailable until a promotion run is approved. The key is a repository-scoped GitHub SSH key with write access, not a cloud credential. Its use is limited to the promotion workflow's push step, and it is rotated at least every 180 days [NQ4]. | Environment settings documented. The promotion workflow references the key only in the job bound to `environment: production`. |
| **NFR1.9** | Every third-party Action is pinned to a full 40-character commit SHA, with a version comment. Every workflow sets top-level `permissions: {}` (or `contents: read`) and grants more per job only where needed [hard rule]. | A CI check fails on any `uses:` that lacks a 40-hex SHA or any workflow without a `permissions` key. |
| **NFR1.10** | Secret scanning: gitleaks runs over the full git history on every PR and on `main`, and GitHub push protection and secret scanning are enabled on the repository [requirements FR1.4]. | A gitleaks finding fails the job. A settings check is recorded in the runbook. |
| **NFR1.11** | The gitleaks configuration carries exactly one allowlist entry for the burned secret. The entry matches that literal value only, has a comment with the reason and date, and is limited to the commits that contain it [requirements FR1.4, Q10]. | Unit-style test: gitleaks on a fixture containing a *different* secret-shaped string still fails. |
| **NFR1.12** | Dependency audit: `pip-audit` runs against both the runtime and dev lockfiles and fails on any vulnerability rated **high or critical** [NQ5]. | A CI job fails on a seeded known-vulnerable pin in a fixture test. |
| **NFR1.13** | SAST: bandit scans `agents/`, `dashboard/`, `mock_hsm/`, `mcp_server/` and `.claude/hooks/`, and fails on **high**-severity findings [NQ5]. | The CI job fails on a fixture containing a high-severity pattern. |
| **NFR1.14** | Exceptions: a pip-audit or bandit finding that can't be fixed may be listed in a checked-in ignore file. Each entry needs an ID, a reason and an expiry date at most 90 days after it was added. An expired entry fails the build [NQ5]. | Unit test of the expiry checker: valid, expired and missing-date entries. |
| **NFR1.15** | A fixed **data-marker list** (site names from `mock_hsm/db.py`, persona display names, tab titles) is kept in one module and shared by the AppTest unit tests and the Playwright check, so both test the same definition of "data" [NQ3]. | Both suites import the list. A test asserts the list is non-empty and that every site name in `db.SITES` is on it. |
| **NFR1.16** | Dashboard tests get a signed-in user only through a test-only hook that no setting or environment variable can enable in a running app. Examples: a function injected by the test harness, or AppTest's `st.user` mocking [NQ1]. | Unit test: setting any environment variable or secret does not bypass sign-in. A grep check finds no production code path that reads a "skip auth" flag. |
| **NFR1.17** | `user_dev_tester` stays selectable after sign-in, as approved (requirements FR5.4). Because the allowlist admits only the owner, this does not widen access. | None needed. Recorded as accepted. |
| **NFR1.18** | **Local secret contract.** Every local process that mints or verifies tokens gets the secret from the same `HSM_SIGNING_SECRET` environment variable: the mock server, the MCP server, the `require_no_violations.py` hook, the dashboard and `scripts/start_mock_server.sh`. The developer exports it in the shell before starting the mock server and `claude`, just as `HSM_ACTIVE_USER` is exported today. The runbook and `CLAUDE.md` document this, including a one-line command to generate a dev secret. When the variable is unset: `scripts/start_mock_server.sh` exits non-zero with a message naming it; the MCP tools return an error naming it; the publish gate hook **denies** with a reason naming it (consistent with its fail-closed design); and the dashboard shows the configuration error. `tests/conftest.py` generates a fresh random secret once per session and sets it in `os.environ` before any test server or subprocess starts, so every subprocess inherits it and the suite needs no developer secret [review R-01]. | The suite passes with `HSM_SIGNING_SECRET` unset in the invoking shell (CI does not set it; NFR4.1). Unit tests: the start script without the variable exits non-zero; the hook without the variable denies with the variable's name in the reason; an MCP tool without the variable returns an error naming it. |
| **NFR1.19** | **Production Environment branch policy.** The `production` GitHub Environment has a deployment branch policy that allows **only `main`**. `promote.yml` also fails its first step unless `github.ref == 'refs/heads/main'`. A modified workflow on any other branch therefore cannot reach the Environment's secrets (the deploy key), even with an approval. Together with the required reviewer, this makes FR7.2's checks tamper-resistant: they run only from the reviewed workflow on `main` [review R-04]. | Environment settings documented in the runbook. A manual negative check at setup: dispatching `promote.yml` from a non-`main` branch is refused by the Environment (recorded in the runbook). The workflow's ref guard is checked by the workflow-lint script (TS14). |

## Supersessions recorded

- **Private apps → public apps with in-app sign-in.** The affirmed team practice (team.md, Deployment) says both apps are private with a viewer allowlist. Requirements Q2: A replaced that with public apps plus `st.login` and an allowlist checked in the app (NFR1.1, NFR1.2). That team-practice wording is now out of date, and a project-level learning records the change (product lead finding R-05).

## Assumptions & Open Questions

- [assumption] `st.login` on Streamlit Community Cloud works with the OIDC provider, the cookie secret and the redirect URI supplied through app secrets, and `st.user.email` is populated by that provider (for example Google).
- [assumption] A deploy key can be a bypass actor in a repository ruleset on a personal public repository. If GitHub does not allow it, NFR Design must choose an equivalent single-writer control without weakening NFR1.7. The fallback is a fine-grained personal access token held only in the `production` Environment.
- None of the other items remain open.
