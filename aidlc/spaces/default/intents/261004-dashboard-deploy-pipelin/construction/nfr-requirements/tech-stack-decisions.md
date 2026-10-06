# Tech Stack Decisions — Dashboard Deployment Pipeline

## Sources

- `requirements.md` constraints, FR1, FR9, NFR1 and NFR5 [requirements]
- Affirmed team practices: GitHub, Streamlit Community Cloud, ruff, pytest, TDD, Python 3.10+ [memory:M1]
- NFR questions NQ3 (Playwright), NQ4 (deploy key), NQ5 (scanner thresholds), NQ7 (universal lock)

## Decisions

| ID | Area | Decision | Alternatives rejected (why) |
|---|---|---|---|
| **TS1** | CI/CD platform | GitHub Actions: workflows `ci.yml` (PR and `main`), `staging-check.yml` (after a merge to `main`), `promote.yml` (manual, `production` Environment) and `prod-check.yml` (every 6 h and on demand). | CircleCI or other hosted CI: the repository is on GitHub, and Environments plus rulesets are needed for the promotion gate. |
| **TS2** | Hosting | Streamlit Community Cloud: two **public** apps, staging tracking `main` and production tracking `production`, gated in-app by `st.login` (security NFR1.1). | Private Cloud apps: free-tier slot limits, superseded by requirements Q2. A container host: rejected in practices discovery. |
| **TS3** | Python versions | CI matrix **3.10 and 3.14**. The hosted apps run the **newest Python Streamlit Cloud offers**. If that version is neither 3.10 nor 3.14, it is added as a third matrix leg [NQ7]. | Pinning hosted to 3.14: Cloud may not offer it yet. A single version: the code claims 3.10+ and must be tested there. |
| **TS4** | Dependency locking | **uv** compiles `requirements.in` → `requirements.txt` (runtime, which Streamlit Cloud installs) and `requirements-dev.in` → `requirements-dev.txt` (lint, test, coverage and security tools). Both use `uv pip compile --universal --generate-hashes`, so one lockfile resolves for every Python from 3.10 to 3.14. CI installs with `pip install --require-hashes` [NQ7, requirements FR9]. | One lockfile per version: duplicated maintenance (NQ7 B). Floating versions: rejected in practices discovery. Poetry or PDM: a heavier toolchain, and Cloud reads `requirements.txt` natively. |
| **TS5** | Lint and format | ruff, with the version pinned in `requirements-dev.txt`: `ruff check .` and `ruff format --check .`. The local commit hook uses the same `.venv`, so both run the same version [requirements NFR5]. | Black: a second tool, rejected in practices discovery. |
| **TS6** | Tests and retry | pytest; `pytest-rerunfailures` with `--reruns 1`; serial run (no xdist), because ports 8772/8773 are fixed [reliability NFR4.1]. | xdist: port collisions. Unlimited retries: they hide flakiness. |
| **TS7** | Coverage | coverage.py with subprocess measurement enabled (`[run] patch = subprocess` in coverage 7.x, or `COVERAGE_PROCESS_START` with a `.pth` hook). Sources: `agents`, `dashboard`, `mock_hsm`, `mcp_server`, `.claude/hooks` [reliability NFR3.1]. | `pytest-cov` alone: it under-reports subprocess-run code (the MCP server and hooks). |
| **TS8** | Secret scanning | gitleaks (pinned release binary, checksum-verified, or a SHA-pinned Action) over full history, plus GitHub push protection [security NFR1.10]. | trufflehog: either would work; gitleaks has the simpler config-file allowlist needed for NFR1.11. |
| **TS9** | Dependency audit | pip-audit against both lockfiles, failing on high or critical [security NFR1.12]. | Dependabot alerts only: not a blocking gate. |
| **TS10** | SAST | bandit as a separate job, failing on high severity [security NFR1.13]. | ruff `S` rules: they would change every commit's lint output (practices discovery). CodeQL: heavier, and it can be added later. |
| **TS11** | Anonymous browser check | Playwright for Python (Chromium, headless), run only in the check workflows, never in the default PR suite. Its version is pinned in the dev lockfile [NQ3]. | Selenium: heavier setup. A plain HTTP check: it cannot see websocket-rendered content (product lead finding R-01). |
| **TS12** | Sign-in | Streamlit's built-in `st.login` (OIDC) with Google as the provider. Settings live in `[auth]` in `st.secrets`. The allowlist is a list of emails in `st.secrets` [security NFR1.1, NFR1.2]. | A reverse proxy with auth: not possible on Streamlit Cloud. A custom OAuth flow: needless when `st.login` exists. |
| **TS13** | Production branch control | A repository ruleset on `production` whose only bypass is a deploy key held in the `production` Environment's secrets [security NFR1.7, NFR1.8]. | Branch protection with "restrict who can push": available only to organisations. The default `GITHUB_TOKEN`: blocked by the ruleset by design. |
| **TS14** | Workflow lint | actionlint, plus a small script that checks SHA pins and `permissions` on all workflow files [security NFR1.9]. | Manual review only: not enforceable. |
| **TS15** | Container image scanning | **Not applicable.** No image is built in this piece of work, so Trivy (agreed in practices discovery) has nothing to scan. It applies the moment any image is introduced. | Building an image just to scan it: no consumer. |

## Reproducibility requirements

| ID | Requirement | Verify |
|---|---|---|
| **NFR5.1** | Two installs from the same lockfile on the same Python version resolve identical package versions and hashes. | CI installs with `--require-hashes`, which fails on any unhashed or mismatched package. |
| **NFR5.2** | The ruff version used by CI equals the version the local commit hook runs: both come from `requirements-dev.txt` installed into `.venv`. | The CI log prints `ruff --version`, and the runbook's local-setup steps install from the same lockfile. |
| **NFR5.3** | The lockfiles are regenerated only by the documented `uv pip compile` command, and CI fails if `requirements*.txt` is out of date with its `.in` file. | A CI step re-runs the compile in check mode and diffs the result. |

## Assumptions & Open Questions

- [assumption] Streamlit Community Cloud installs a hash-pinned `requirements.txt` successfully. If it rejects `--hash` lines, NFR Design must define a hash-free runtime export generated from the same lock, so the versions stay identical.
- [assumption] `uv` can be installed in CI from a pinned, checksum-verified release.
- None.
