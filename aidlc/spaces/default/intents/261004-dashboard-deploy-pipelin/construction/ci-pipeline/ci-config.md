# CI Configuration — Dashboard Deployment Pipeline

## Sources

- `construction/infrastructure-design/cicd-pipeline.md` (Workflow 1 `ci.yml`, conventions, Dependabot) [cicd-pipeline]
- `construction/nfr-design/security-design.md` SD2, SD5, SD7; `reliability-design.md` RD6 [security-design, reliability-design]
- `ci-pipeline-questions.md` CQ1 to CQ3 and the scope decision (application changes split into a follow-up)
- The workspace's own build and test setup (`ruff.toml`, `tests/conftest.py`, the measured suite). Code Generation and Build & Test are skipped by the infra scope, and their summaries are absent as expected.

## What was built (branch `ci-pipeline`, not yet committed)

| Path | Purpose |
|---|---|
| `.github/workflows/ci.yml` | The CI workflow: 10 jobs. Every job except `matrix` is a required check. |
| `.github/dependabot.yml` | Weekly grouped updates for Actions SHA pins and the uv lock inputs |
| `requirements.in` → `requirements.txt` | Runtime lock, hash-pinned and universal for 3.10–3.14 (`streamlit==1.64.0` and its dependencies). Streamlit Cloud installs it. |
| `requirements-dev.in` → `requirements-dev.txt` | Dev/CI lock: runtime plus `mcp[cli]==1.30.0`, `ruff==0.16.8`, `pytest==9.1.1`, `pytest-rerunfailures`, `coverage`, `bandit`, `pip-audit`, `cvss`, and `tomli` (3.10 only) |
| `.coveragerc` | Measured set `agents`, `dashboard`, `mock_hsm`, `mcp_server`, `.claude/hooks`, with `patch = subprocess` |
| `.test-floor` (`745`), `.coverage-floor` (`95.00`) | Ratcheting floors; a PR that lowers either one fails |
| `security-exceptions.toml` | Empty exceptions register (format documented in the file) |
| `.gitleaks.toml` | Default rules plus one value-scoped allowlist entry for the burned secret |
| `scripts/floor_ratchet.py`, `test_floor.py`, `coverage_gate.py` | Floor gates (NFR3.1, NFR4.1) |
| `scripts/check_burned_secret.py` | Digest-based scan, with permanent exclusions (`.gitleaks.toml`, AI-DLC record tree) and **one temporary exclusion (`mock_hsm/auth.py`) that fails once the literal is gone** (CQ1) |
| `scripts/check_workflows.py` | SHA pins plus version comments, top-level `permissions`, no secrets on `run:` lines, and the `promote.yml` main guard |
| `scripts/check_exceptions.py`, `filter_audit.py`, `filter_bandit.py`, `run_pip_audit.sh` | Dependency and SAST gates: OSV severity lookup with fail-closed, exit-code-1-only tolerance |
| `scripts/job_summary.py` | Job-summary formatter: counts, coverage, rerun names. It never reads the environment. |
| `tests/conftest.py` | Adds the `browser` marker and a pure `skip_reason()` (skipped unless `-m browser`) |
| `tests/ci_scripts.py`, `tests/test_ci_*.py`, `tests/test_conftest_markers.py` | 66 new tests for the above |
| `CLAUDE.md` | Commands now install from the dev lock; new "Continuous integration" section |

## Workflow `ci.yml` jobs

| Job | Runs | Key commands |
|---|---|---|
| `lint` | Python 3.14 | `ruff --version`, `ruff check .`, `ruff format --check .` |
| `workflow-lint` | — | actionlint 1.7.12 (SHA-256 verified), `scripts/check_workflows.py` |
| `secrets` | full history | gitleaks 8.30.1 (SHA-256 verified) with `.gitleaks.toml`, `scripts/check_burned_secret.py` |
| `audit` | Python 3.14 | `check_exceptions.py`, `run_pip_audit.sh`, `filter_audit.py` |
| `sast` | Python 3.14 | `bandit -f json` (exit 1 tolerated), `filter_bandit.py` |
| `lock-check` | uv 0.12.15 | Recompile both locks and `diff` against the committed files |
| `matrix` | — | `["3.10","3.14"]`, plus `vars.HOSTED_PYTHON` |
| `tests (<py>)` | each leg | `pytest tests/ -q --reruns 1 --junitxml`, with coverage on 3.14; `test_floor.py` (with `--base-ref` on PRs); job summary. Step timeout 5 min, job 15 min |
| `coverage-gate` | — | `coverage_gate.py` against `.coverage-floor`, with `--base-ref` on PRs |
| `browser-tests` | conditional body | Always reports. It runs `pytest -m browser` on schedule or dispatch, or when a browser-check file changes. Exit code 5 ("no tests") passes until the follow-up adds the tests |

**Conventions:** `ubuntu-24.04`; top-level `permissions: {}` with `contents: read` per job; every `uses:` pinned to a 40-hex SHA with a version comment; PR runs cancel superseded runs, `main` runs never do.

## Verified locally (2026-10-04, Python 3.14.7, macOS)

| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| Full suite `pytest tests/ -q --reruns 1` | 811 passed, 12 skipped, 88 s. `test_floor.py`: ok (floor 745) |
| Coverage baseline (`coverage run` with subprocess patch) | **96%** total (`mcp_server/hsm_tools.py` 89% and `.claude/hooks/*` 93–94%, measured in their subprocesses). Floor set to 95.00 to absorb runner differences, so the 80% gate is on from the first run |
| bandit plus `filter_bandit.py` | ok (no high-severity findings; 2 medium and 3 low, which don't block) |
| pip-audit plus `filter_audit.py` | ok (no known vulnerabilities) |
| gitleaks over history | 16 commits, no leaks |
| `check_burned_secret.py` | ok |
| `check_workflows.py` and actionlint | ok |

**Not yet verified:** the workflow running on GitHub itself. That happens on the PR.

## Landing and enforcement (CQ2)

1. **Formatting-only commit first.** `ruff format .` reformats 36 existing files. The team practice is to introduce the formatter in its own commit, kept apart from feature or pipeline changes.
2. **CI commit**, through `/commit` (code-reviewer plus lint hook).
3. Push `ci-pipeline` and open a PR to `main`. Merge (squash) once every job is green.
4. **You apply the ruleset change.** This is the settings checklist:
   - *Settings → Rules → Rulesets → `main_branch_protection`.* Its target list is currently empty, so it protects nothing.
     - Target branches: **Include default branch** (`main`).
     - Keep: restrict deletions; block force pushes.
     - Add: **Require a pull request before merging**, with allowed merge method **Squash** only.
     - Add: **Require status checks to pass**: `lint`, `workflow-lint`, `secrets`, `audit`, `sast`, `lock-check`, `tests (3.10)`, `tests (3.14)`, `coverage-gate`, `browser-tests`. Tick "require branches to be up to date".
     - Bypass list: **empty**.
   - *Settings → General → Pull Requests:* allow squash merging only.
   - *Settings → Code security:* enable **Secret scanning** and **Push protection**.
   - *Settings → Secrets and variables → Actions → Variables:* leave `HOSTED_PYTHON` unset until the Streamlit apps exist.
5. Once the ruleset is active, check it with `gh api repos/SaadsProjects/hsm-claude-code-cli/rulesets/24043060`.

## Handed to the follow-up piece of work (application changes)

- Remove the literal from `mock_hsm/auth.py` and remove its `TEMPORARY_EXCLUSIONS` entry together (CI enforces this).
- Add the browser tests (`-m browser`), Playwright in the dev lock, and the post-deploy check script.
- Then raise `.test-floor` to the new passing count. Floors may only rise.

## Assumptions & Open Questions

- [assumption] The suite takes about the same time on `ubuntu-24.04` runners as locally (88 s), within the 5-minute step timeout.
- [assumption] Dependabot's `uv` ecosystem raises PRs for `requirements*.in`. Infrastructure reviewer finding R-01 says this is unverified. If no Python PRs appear within two weeks, add a scheduled lock-refresh workflow. That is tracked in `quality-gates.md`.
- None.
