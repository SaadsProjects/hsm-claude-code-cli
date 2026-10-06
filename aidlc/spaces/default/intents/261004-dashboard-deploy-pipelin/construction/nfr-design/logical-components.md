# Logical Components — Dashboard Deployment Pipeline

## Sources

- The NFR Design documents in this directory: security SD1 to SD7, reliability RD1 to RD6, performance PD1 to PD3, scalability SC1 to SC3, observability OD1 to OD3
- `construction/nfr-requirements/tech-stack-decisions.md` [tech-stack-decisions]

## Component inventory

| # | Component | Kind | Location | Responsibility | Failure domain | Blast radius |
|---|---|---|---|---|---|---|
| C1 | Sign-in gate | app module | `dashboard/auth_gate.py` (+ `dashboard/markers.py`) | Banner, build ID, `st.login`, allowlist, `email_verified` (SD1) | Per app process | That app shows nothing (fails closed) |
| C2 | Secrets bridge | app module | `dashboard/secrets_bridge.py` | Copies Streamlit secrets into the environment (SD2) | Per app process | Backend and tokens unavailable; config error shown |
| C3 | Backend runtime | app module | `dashboard/backend_runtime.py` | One in-process loopback backend per process (RD5, SC1) | Per app process | Data unavailable; the existing error is shown |
| C4 | Signing-key loader | library | `mock_hsm/auth.py` (`_signing_key`) | Stdlib-only, fail-closed secret read; burned-digest refusal (SD2) | Every token user | Token mint and verify fail; hook denies; MCP errors |
| C5 | Loopback server entry | library | `mock_hsm/server.py` (`serve_in_thread`) | Refuses a non-loopback bind (SD4) | Per process | None outside the process |
| C6 | Build identifier | library | `agents/build_info.py` | `sha:` or `fp:` identifier, shared by app and check (SD6) | App and check | Checks fail on a mismatch (safe direction) |
| C7 | Post-deploy check | script | `scripts/postdeploy_check.py` | Read-only Playwright check, steps 0, a, b, c (RD1) | Per run | Promotion and staging evidence blocked |
| C8 | Promotion preconditions | script | `scripts/promote_preconditions.py` | Target resolution, checks, tag rule, floor (RD3) | Per run | Promotion refused |
| C9 | CI gates | scripts | `scripts/check_workflows.py`, `check_burned_secret.py`, `check_exceptions.py`, `filter_audit.py`, `coverage_gate.py`, `test_floor.py`, `job_summary.py` | Policy checks and summaries (SD2, SD5, SD7, RD6, OD1) | Per run | The PR can't merge |
| C10 | Dev secret helper | script | `scripts/dev-secret.sh`, `scripts/start_mock_server.sh` | Local secret contract (SD3) | Developer machine | Local services refuse to start (with a clear message) |
| C11 | Workflows | GitHub config | `.github/workflows/{ci,staging-check,promote,prod-check}.yml`, `.github/dependabot.yml` | Orchestration (PD1, RD2 to RD4) | GitHub Actions | Pipeline stops; no deploy |
| C12 | Repository controls | GitHub settings (documented, applied by hand) | Rulesets on `main` and `production`; `production` Environment; push protection | Single-writer production, required checks (SD5) | Repository | Misconfiguration weakens gates; the runbook has a verification checklist |
| C13 | Hosted apps | Streamlit Community Cloud | Staging (tracks `main`), production (tracks `production`) | Run C1 to C6 with per-environment secrets | Per app | One environment at a time |
| C14 | Config and lock files | repo files | `requirements*.in/.txt`, `.coverage-floor`, `.test-floor`, `security-exceptions.toml`, `.gitleaks.toml`, `.gitignore` (`.env.local`) | Reproducibility and policy data (TS4, RD6, SD7) | Repository | CI fails closed on bad data |
| C15 | Runbook | docs | `docs/DEPLOYMENT.md`, plus updates to `CLAUDE.md` and `README.md` | Setup, secrets, promotion, rollback, rotation, settings checklist (requirements FR10) | — | — |

## Isolation and dependencies

```
C13 ──runs──▶ C2 ─▶ C1 ─▶ C3 ─▶ C5
                         │        └─ C4 (tokens)
C1, C7 ──use──▶ C6, markers
C11 ──runs──▶ C7, C8, C9 ; C8 ─▶ C12 (deploy key, Environment)
C10 ─▶ C4 (local)
```

Text fallback:
- The hosted app runs, in order: the secrets bridge, then the gate, then the backend runtime, then the loopback server. Token functions come from the signing-key loader.
- The gate and the post-deploy check share the build identifier and the marker list.
- The workflows run the check, the promotion preconditions and the CI gate scripts. Promotion relies on the repository controls.
- The dev secret helper feeds the signing-key loader locally.

**Shared resources:**
- `HSM_SIGNING_SECRET`: one per environment, and one per developer locally.
- `dashboard/markers.py`: shared by the app, the unit tests and the check.
- `agents/build_info.py`: shared by the app and the check.

No component depends on a hosted service other than GitHub, Streamlit Cloud, the OIDC provider and the OSV API (C9, which fails closed).

## Assumptions & Open Questions

- [assumption] Repository settings (C12) are applied by hand and verified with the runbook checklist. Codifying them, for example with Terraform's GitHub provider, is out of scope.
- None.
