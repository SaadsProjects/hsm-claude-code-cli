# Security Design — Dashboard Deployment Pipeline

## Sources

- `construction/nfr-requirements/security-requirements.md`: NFR1.1 to NFR1.19 [security-requirements]
- `construction/nfr-requirements/tech-stack-decisions.md`: TS1, TS4, TS8 to TS14 [tech-stack-decisions]
- The NFR Design questions file, `nfr-design-questions.md`, answers DQ1 to DQ6
- The carried reviewer item R-10 from NFR Requirements: check the burned secret by digest, and define the fingerprint by globs
- Code at `1586133`:
  - `dashboard/app.py` imports `mock_hsm.db.USERS`
  - `dashboard/session.py` imports `mint_token`
  - `mock_hsm/server.py:720` is `run(host, port)`
  - `scripts/start_mock_server.sh` runs the server in the foreground

## Trust boundaries and controls

```
 Internet ──(1)──▶ Streamlit Cloud app process ──(2)──▶ in-process mock backend (127.0.0.1)
                        │  sign-in gate (st.login + allowlist)      │ HMAC tokens (HSM_SIGNING_SECRET)
 GitHub repo ──(3)──▶ Streamlit Cloud (branch tracking: main → staging, production → prod)
 promote.yml ──(4)──▶ production branch (ruleset; deploy-key bypass held in `production` Environment)
```

Text fallback for the diagram:
- Boundary 1 is guarded by the sign-in gate.
- Boundary 2 is loopback-only and HMAC-signed.
- Boundary 3 is branch tracking on Streamlit Cloud.
- Boundary 4 is the ruleset plus the approval-gated deploy key, with the Environment restricted to deploying from `main`.

## Design decisions

### SD1 — Sign-in gate is the first thing `app.py` runs (NFR1.1, NFR1.2, NFR1.16)

A new module, `dashboard/auth_gate.py`, exposes `require_signed_in_allowlisted_user() -> str`. `app.py` calls it immediately after `st.set_page_config` and before it imports or calls anything that reads backend data. The gate's order:

0. **Sign-in configuration present (review R-06).** If reading `st.secrets` raises (no secrets file) or the `[auth]` section is missing or lacks `client_id`, `client_secret`, `redirect_uri`, `cookie_secret` or `server_metadata_url`, log an ERROR naming the missing key (never a value), show a configuration error, and call `st.stop()`. Local runs need the same `[auth]` section in a gitignored `.streamlit/secrets.toml` (NQ1).
1. Render the demo banner (reliability NFR6.11) and the build identifier (SD6) as plain text, `st.caption(f"Build: {identifier}")`, which the post-deploy check locates by text pattern (reliability RD1).
2. Load the allowlist from `st.secrets["auth_allowlist"]`. Validate it: a non-empty list of strings, each with exactly one `@`. On failure, log an ERROR naming `auth_allowlist`, show a configuration error, and call `st.stop()`.
3. If `st.user.is_logged_in` is false, show `st.button("Sign in", on_click=st.login)` and call `st.stop()`.
4. If `st.user` has `email_verified` and it is not `True`, deny.
5. If `st.user.email.casefold()` is not in the casefolded allowlist, show "Access denied", offer `st.logout`, and call `st.stop()`.
6. Return the email.

Streamlit reruns the whole script on every interaction, so the gate runs on every interaction (NFR1.2) without needing a separate mechanism.

**Test seam (NFR1.16).** The gate reads the current user through a function parameter, `user_provider`, that defaults to `lambda: st.user`. Tests pass a fake provider through Streamlit's `AppTest`, using a test-only wrapper script under `tests/`. No environment variable, secret or query parameter can replace the provider in a running app, and a test greps `dashboard/` for any such flag.

### SD2 — Secret loading stays stdlib-only (NFR1.3, NFR1.4, NFR1.18)

- `mock_hsm/auth.py` gets `_signing_key() -> bytes`. It reads `os.environ["HSM_SIGNING_SECRET"]` each time it is called, so tests can set the variable after import. It raises `SigningSecretError` (a subclass of `RuntimeError`) when the value is missing, empty, or shorter than 32 bytes. It also raises when `hashlib.sha256(value).hexdigest()` equals `_BURNED_SECRET_SHA256`, a 64-hex constant. `mint_token` and `verify_token` call it. The module imports only stdlib modules (enforced by a test that inspects its imports).
- **The bridge** is `dashboard/secrets_bridge.py`: `ensure_env_from_streamlit_secrets()`. For each key in a fixed tuple, it copies the value from `st.secrets` into `os.environ` when the variable is unset and the secret is present. The keys are `HSM_SIGNING_SECRET`, `HSM_INPROCESS_BACKEND`, `HSM_BACKEND_HOST` and `HSM_BACKEND_PORT` (review R-07). It never overwrites a variable that is already set, and it runs in `app.py` before the gate and before the backend starts.
- **Burned-value checks without the literal (R-10, review R-08):** the CI source check is a small script, `scripts/check_burned_secret.py`. It scans every tracked text file (`*.py`, `*.sh`, `*.toml`, `*.json`, `*.yml`, `*.yaml`, `*.md`, `*.txt`). For each run of 20 or more characters from `[A-Za-z0-9_-]`, it compares the SHA-256 digest with `_BURNED_SECRET_SHA256`. The literal itself appears nowhere in the code or CI config. Two path exclusions are documented in the script:
  - `.gitleaks.toml`, which holds the value-scoped allowlist;
  - the AI-DLC record tree `aidlc/spaces/*/intents/**`, whose audit evidence quotes the already-public value and must not be rewritten.

  The same two paths are covered by the gitleaks allowlist. Anything else containing the value fails CI.

### SD3 — Local secret contract (NFR1.18, DQ5)

- `scripts/dev-secret.sh` creates `.env.local` (gitignored, mode 600) containing `export HSM_SIGNING_SECRET=<token_urlsafe(32)>`, but only if the file doesn't already exist. It then prints `source .env.local`. Running it again never overwrites an existing secret.
- `scripts/start_mock_server.sh` exits with status 2 and the message `HSM_SIGNING_SECRET is not set; run scripts/dev-secret.sh and source .env.local` when the variable is unset.
- `.claude/hooks/require_no_violations.py` catches `SigningSecretError` and **denies** with that message. This fits its existing fail-closed handling.
- `mcp_server/hsm_tools.py`'s `_client()` catches `SigningSecretError` and returns a tool error with the same message.
- `tests/conftest.py` adds a session-scoped autouse fixture, set up first, that puts `secrets.token_urlsafe(32)` into `os.environ["HSM_SIGNING_SECRET"]` before any server or subprocess fixture starts. Subprocesses inherit it.

### SD4 — Backend binding (NFR1.5)

`mock_hsm/server.py` adds `serve_in_thread(host, port) -> ThreadingHTTPServer`. It raises `ValueError` unless `ipaddress.ip_address(host).is_loopback` is true. The dashboard reads `HSM_BACKEND_HOST`/`HSM_BACKEND_PORT` (defaults `127.0.0.1`/`8770`) only when it starts the backend in-process (see the scalability design). The standalone `python3 -m mock_hsm.server` keeps today's behaviour.

### SD5 — GitHub controls (NFR1.6 to NFR1.10, NFR1.19)

| Control | Design |
|---|---|
| Ruleset on `production` | Target `refs/heads/production`. It restricts creations, updates and deletions and blocks force pushes. The bypass list is **deploy keys only**. |
| Ruleset on `main` | Requires a PR, the required status checks from `ci.yml` (lint, tests on each Python leg, coverage, gitleaks, pip-audit, bandit, workflow-lint) and linear history (squash). There is no bypass. |
| `production` Environment | Required reviewer: the owner. Deployment branch policy: `main` only. Secret: `PROD_DEPLOY_KEY`. No other environment holds this key. |
| `promote.yml` | Three jobs (reliability RD3, review R-01). `preflight` has no environment and is keyless, with `contents: read`, `statuses: read`, `checks: read` (review R-02). It resolves and verifies the target and shows it to the approver. `deploy` is bound to `environment: production` with `contents: read`. It pauses for approval, then only pushes and tags using the deploy key over SSH, not the `GITHUB_TOKEN`. `verify` has no environment, with `contents: read`, and runs the post-deploy check. Both `preflight` and `deploy` fail unless `github.ref == 'refs/heads/main'`. |
| Workflow permissions | Top-level `permissions: {}`. Each job is granted only what it needs: `contents: read` for CI; `contents: read`, `statuses: write` for `staging-check.yml`; the `promote.yml` grants above; `issues: write` only for `prod-check.yml`'s failure-report job (DQ6). |
| Action pins | Every `uses:` is a 40-hex SHA with a `# vX.Y.Z` comment. Dependabot keeps them current (DQ4). |
| Workflow lint | `actionlint` plus `scripts/check_workflows.py`, which fails on an unpinned `uses:`, a missing `permissions`, `${{ secrets.* }}` on a `run:` line, or a `promote.yml` without the ref guard. |
| Log hygiene | Secrets are passed through `env:` only. Playwright traces and screenshots are uploaded only for staging runs, never for production. |

### SD6 — Build identifier (reliability NFR6.1, R-10 file set)

`agents/build_info.py` is a pure function used by both the app and the check script. It is placed in `agents/` because it is a deterministic calculation shared outside the dashboard.

- **Primary:** `git rev-parse HEAD` in the repository root, run with a 2 s timeout, returns `sha:<40 hex>`.
- **Fallback:** the fingerprint is computed over every file matching the globs `agents/**/*.py`, `dashboard/**/*.py`, `mock_hsm/**/*.py`, `.streamlit/config.toml` and `requirements.txt`, excluding `**/__pycache__/**` and `*.pyc`. Paths are sorted as POSIX strings, and each one is fed to SHA-256 as `path\0` followed by the file's bytes and a `\0`. The result is `fp:<64 hex>`.
- If both fail, the identifier is `unknown`.
- The check script computes the expected identifier from the checked-out commit under test using the same function. When it receives `fp:`, it uses the fingerprint form.

### SD7 — Scanner thresholds and exceptions (NFR1.12 to NFR1.14)

- bandit runs as `bandit -r agents dashboard mcp_server mock_hsm .claude/hooks -lll`, which reports only high severity.
- pip-audit runs as `pip-audit -r requirements.txt -r requirements-dev.txt --require-hashes --format json`. pip-audit has no severity gate and its JSON carries no severity, so `scripts/filter_audit.py` looks up each finding's ID (and its aliases) in the OSV API (`api.osv.dev/v1/vulns/<id>`, read-only). It derives severity in this order (review R-05):
  1. The advisory label `database_specific.severity`. `HIGH` or `CRITICAL` fails the build; `MODERATE` or `LOW` passes.
  2. Otherwise, the highest CVSS v3.x or v4.0 vector in `severity[]`, scored to a base score with the `cvss` library pinned in the dev lock. A score of 7.0 or more fails.
  3. Otherwise, **fail closed** and treat it as high. This also covers a lookup that errors or times out after 10 s.

  Unit-tested with OSV fixtures for each branch.
- Exceptions live in `security-exceptions.toml`. Each entry carries `id`, `tool`, `reason` and `expires` (an ISO date at most 90 days after `added`). `scripts/check_exceptions.py` fails on an expired or malformed entry. The filters drop only findings whose IDs are in a valid entry.

## Threat-to-design mapping

| Threat | Design |
|---|---|
| T1 forged tokens | SD2, SD3 |
| T2 and T3 unauthenticated or unlisted access | SD1 |
| T4 external backend access | SD4 |
| T5 untested code reaching production | SD5 (rulesets, Environment, ref guard) |
| T6 compromised Action | SD5 (SHA pins, permissions) |
| T7 secret leakage | SD2, SD5 (log hygiene), gitleaks |
| T8 vulnerable dependencies | SD7, plus Dependabot |
| T9 repudiation | `prod-*` annotated tags (DQ3) and Environment approval history |

## Assumptions & Open Questions

- [assumption] `st.user` exposes `email` and, for Google, `email_verified`, and `st.login`/`st.logout` behave the same locally and on Cloud when `[auth]` is configured in secrets.
- [assumption] A deploy key can be a ruleset bypass actor on a personal public repository. The fallback is a fine-grained token held only in the `production` Environment (security NFR1.8). It is verified during environment setup.