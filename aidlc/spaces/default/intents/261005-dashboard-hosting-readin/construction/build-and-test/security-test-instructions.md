# Security Test Instructions — Dashboard Hosting Readiness

## Sources

- `construction/secret-fail-closed/nfr-requirements/security-requirements.md` (NFR1.1–NFR1.10, STRIDE)
- `construction/embedded-backend/nfr-requirements/security-requirements.md` (NFR1.11–NFR1.14, NFR7.2)
- `construction/sign-in-gate/nfr-requirements/security-requirements.md` (NFR1.21–NFR1.28, NFR4.11, NFR7.11)
- `memory/team.md` Deployment and Code Style; `memory/project.md` Forbidden and Mandated
- `.github/workflows/ci.yml` (the `secrets`, `audit`, `sast` and `lock-check` jobs)

## Automated Security Gates (each a required CI check)

| Gate | Tool | Pass condition | Local command |
|------|------|----------------|---------------|
| Secret scan | gitleaks 8.30.1 over full history, plus the burned-secret check | No finding; `TEMPORARY_EXCLUSIONS` empty | `gitleaks git --config .gitleaks.toml --redact --no-banner .` (if installed) and `python3 scripts/check_burned_secret.py` |
| Dependency audit | pip-audit on the hash-pinned locks, filtered | No high or critical finding without a `security-exceptions.toml` entry | `python scripts/check_exceptions.py security-exceptions.toml && sh scripts/run_pip_audit.sh audit.json && python scripts/filter_audit.py audit.json --exceptions security-exceptions.toml` |
| SAST | bandit `--ignore-nosec` over `agents dashboard mcp_server mock_hsm .claude/hooks scripts`, filtered | No high-severity finding | `bandit -q --ignore-nosec -r agents dashboard mcp_server mock_hsm .claude/hooks scripts -f json -o bandit.json; python scripts/filter_bandit.py bandit.json --exceptions security-exceptions.toml` |
| Supply chain | Lockfiles match their inputs; actions SHA-pinned; least-privilege `permissions` | `lock-check` and `workflow-lint` green | Lock check in `build-instructions.md`; `python3 scripts/check_workflows.py .github/workflows` |

## Security Behaviour Tests (in the ordinary suite)

| Area | Targets | Command |
|------|---------|---------|
| Signing secret: no fallback, ≥ 32 bytes, burned value refused, never echoed | NFR1.1–NFR1.10 | `python3 -m pytest tests/test_signing_secret.py tests/test_secret_entry_points.py tests/test_hooks.py -q` |
| Loopback only; 0700 audit directory; no secret on screen or in logs | NFR1.11–NFR1.14, NFR7.2 | `python3 -m pytest tests/test_embedded_backend.py tests/test_dashboard_embedded.py -q` |
| Gate: nothing before allow; verified, exact allowlist; fail closed; no identity in logs; literal email; sign-out clears the persona | NFR1.21–NFR1.28, NFR4.11 | `python3 -m pytest tests/test_auth_gate.py tests/test_secrets_bridge.py tests/test_dashboard_gate.py -q` |
| Refusal in a real browser (unlisted and unverified identities) | AC8.2.3 | `python3 -m pytest tests/test_postdeploy_browser.py -m browser -q` |
| The check is read-only: no input, no sign-in, no publish or PO call | AC7.3.1, NFR6 | `python3 -m pytest tests/test_postdeploy_check.py -q` |

## Manual Security Checks Against Staging (owner, once)

- An allowlisted, verified Google account gets in.
- A verified Google account that isn't on the allowlist, added as a consent-screen test user, sees "This account doesn't have access."
- Recorded in `construction/staging-app/code-generation/code-summary.md` § Staging Evidence.

## Out of Scope Here

- DAST against staging. The post-deploy check covers the unauthenticated surface, and the parked deploy intent owns any further hosted scanning.
- Container scanning (Trivy). No image is built (team.md Deployment).
