# CI/CD Pipeline — Dashboard Deployment Pipeline

## Sources

- `construction/nfr-design/performance-design.md` PD1 and PD2 [performance-design]
- `construction/nfr-design/security-design.md` SD2, SD3, SD5 and SD7 [security-design]
- `construction/nfr-design/reliability-design.md` RD1 to RD6 [reliability-design]
- `construction/nfr-design/observability-design.md` OD1 and OD2 [observability-design]
- `construction/nfr-design/logical-components.md` C7 to C14 [logical-components]
- Infrastructure questions IQ1 to IQ3, plus the reviewer items carried from NFR Design: R-05 (pip-audit exit handling) and R-10 (`browser` marker)

## Delivery model

Streamlit Community Cloud **pulls**: each app redeploys when its tracked branch moves. So the pipeline never "deploys" to staging. It gates what reaches `main`, verifies what staging is running, and moves `production` only through the approval-gated promotion.

```
PR ──ci.yml──▶ (required checks green) ──squash──▶ main ──Cloud redeploys staging──▶ staging-check.yml ──status──▶ commit
                                                    │
                    promote.yml: preflight ─(approval)─▶ deploy (push production + tag) ─▶ verify
                                                    │
                       production ──Cloud redeploys prod──▶ prod-check.yml every 6 h (+ issue on failure)
```

Text fallback:
1. A PR runs `ci.yml`. With all required checks green it can be squash-merged into `main`.
2. Cloud redeploys staging from `main`. `staging-check.yml` verifies it and posts a commit status.
3. `promote.yml` runs preflight, waits for approval, moves `production` and tags it, then verifies.
4. Cloud redeploys production. `prod-check.yml` re-verifies it every 6 hours.

## Common conventions (all workflows)

| Convention | Value |
|---|---|
| Runner | `ubuntu-24.04` (pinned, not `ubuntu-latest`), for reproducibility (NFR5.1) |
| Default permissions | Top-level `permissions: {}`; jobs add only what they need (SD5) |
| Action pins | Full 40-hex SHA with a `# vX.Y.Z` comment; Dependabot updates them (SD5, DQ4) |
| Python setup | `actions/setup-python` with pip cache keyed on `requirements-dev.txt`. Installs use `pip install --require-hashes -r requirements-dev.txt` (TS4) |
| uv | Pinned release, SHA-256 verified before use. Used only by `lock-check` |
| Secrets in steps | Through `env:` only, never on a `run:` command line (SD5, enforced by `check_workflows.py`) |
| Timeouts | Every job has `timeout-minutes` (PD1 and PD2) |

## Workflow 1 — `ci.yml`

**Triggers:** `pull_request` (all branches into `main`), `push` to `main`, `schedule: '0 3 * * *'` (nightly browser tests), `workflow_dispatch`.

**Concurrency:** `group: ci-${{ github.ref }}`, with `cancel-in-progress` true for PRs and false for `main`.

| # | Job (required check name) | Permissions | Steps | Gate |
|---|---|---|---|---|
| 1 | `lint` | `contents: read` | `ruff --version`; `ruff check .`; `ruff format --check .` | Any finding fails |
| 2 | `workflow-lint` | `contents: read` | `actionlint`; `python scripts/check_workflows.py` | Unpinned `uses:`, missing `permissions`, a secret on a `run:` line, a `promote.yml` without its ref guard, or a job grant beyond the documented set all fail |
| 3 | `secrets` | `contents: read` | Full-history checkout (`fetch-depth: 0`); `gitleaks detect` with `.gitleaks.toml`; `python scripts/check_burned_secret.py` | Any finding fails |
| 4 | `audit` | `contents: read` | `scripts/run_pip_audit.sh` (see below), then `filter_audit.py`, then `check_exceptions.py` | High/critical, or an expired or malformed exception, fails |
| 5 | `sast` | `contents: read` | `bandit -r agents dashboard mcp_server mock_hsm .claude/hooks -lll` | A high finding fails |
| 6 | `lock-check` | `contents: read` | `uv pip compile` both `.in` files into temp files, then diff them against the committed `.txt` files | Any diff fails (NFR5.3) |
| 7 | `matrix` (helper, not required) | none | Builds the Python list: `["3.10","3.14"]`, plus `vars.HOSTED_PYTHON` if that is set and not already in the list (TS3) | — |
| 8 | `tests (<py>)` | `contents: read` | Install; `python -m pytest tests/ -q --reruns 1 --junitxml=junit.xml` (step `timeout-minutes: 5`). On 3.14 only, it runs under `coverage run` with subprocess measurement. Then `python scripts/test_floor.py junit.xml` | Any failure after retry, passed below `.test-floor`, or a lowered `.test-floor` in the PR diff fails (RD6) |
| 9 | `coverage-gate` | `contents: read` | `needs: tests`. Downloads the 3.14 `coverage.json` artifact; `python scripts/coverage_gate.py` | Below `.coverage-floor`, below 80 once the floor is at least 80, or a lowered `.coverage-floor` in the diff, fails (NFR3.1) |
| 10 | `browser-tests` | `contents: read` | **Always runs**, so it can be a required check. A GitHub required check that never reports would block every PR. A first step decides whether the tests are needed: always on `schedule` and `workflow_dispatch`, and on PRs only when the diff touches `scripts/postdeploy_check.py`, `dashboard/markers.py`, `dashboard/auth_gate.py`, `agents/build_info.py` or `tests/**browser**`. If they are not needed, the job ends successfully with a summary line saying so. If they are needed: `playwright install --with-deps chromium`; `python -m pytest tests/ -m browser` | Any failure fails |
| 11 | `summary` | `contents: read` | `if: always()`; `python scripts/job_summary.py ci` from the JUnit and coverage artifacts | — |

**pip-audit exit handling (reviewer item R-05).** `scripts/run_pip_audit.sh` runs `pip-audit … --format json --output audit.json` and captures its exit code:
- **0:** no findings.
- **1:** findings present. The script continues to `filter_audit.py`, which decides pass or fail by severity.
- **Any other code:** a tool error. The script fails the job with the exit code in the message.

The step therefore never uses `continue-on-error`. Only exit code 1 is tolerated, and only so the filter can run. The wrapper's three branches are unit-tested with a stub `pip-audit`.

**Browser tests stay out of plain CI (reviewer item R-10).** `tests/conftest.py` registers a `browser` marker. Its `pytest_collection_modifyitems` skips `browser` tests unless the `-m` expression names `browser`. This mirrors the existing `perf` handling, which skips `perf` when there is no `-m`. Without any `-m`, both `perf` and `browser` tests are skipped, so the team rule of running plain `python -m pytest tests/` holds. The `browser-tests` job is the only place that runs `-m browser`. A unit test in `tests/test_conftest_markers.py` asserts both skip behaviours.

## Workflow 2 — `staging-check.yml`

**Triggers:** `push` to `main`, `workflow_dispatch`. **Concurrency:** `staging-check`, `cancel-in-progress: true`.

| Job | Permissions | Steps |
|---|---|---|
| `check` | `contents: read`, `statuses: write` | Check out `github.sha`. Install the runtime and dev lock, plus Chromium. `python scripts/postdeploy_check.py --url ${{ vars.STAGING_URL }} --commit ${{ github.sha }} --checkout . --report report.json`. Post commit status `staging-check` = success or failure, with the failing step in the description and `target_url` set to the run. Write the job summary. Upload the Playwright trace and screenshot **for staging only**. |

The status is posted with `if: always()`, so a crash also leaves a `failure` status rather than none.

## Workflow 3 — `promote.yml`

**Trigger:** `workflow_dispatch`, with inputs `mode` (`promote` | `rollback`) and `commit` (optional). **Concurrency:** `promote`, `cancel-in-progress: false`, so promotions queue rather than race.

| Job | Environment | Permissions | Steps |
|---|---|---|---|
| `preflight` | — | `contents: read`, `statuses: read`, `checks: read` | Ref guard (`refs/heads/main`). `python scripts/promote_preconditions.py --mode … --commit …` resolves the target: newest green commit, a named commit, or a tagged rollback target. It requires every required CI check run plus the `staging-check` status to be `success`, and `.coverage-floor` ≥ 80.00 at the target. It reads the current `production` SHA, writes the target, mode, previous SHA and check results to the job summary, and outputs `target` and `prev`. |
| `deploy` | `production` (required reviewer = owner; branch policy = `main` only) | `contents: read` | **Waits for approval before any step.** Then: the ref guard again; load `PROD_DEPLOY_KEY` into `ssh-agent`; `git push --force-with-lease=production:${prev} git@github.com:<repo>.git ${target}:refs/heads/production`; create and push the annotated tag `prod-<UTC yyyymmddThhmmssZ>`; write the summary. |
| `verify` | — | `contents: read` | Check out `target`, then `postdeploy_check.py --url ${{ vars.PROD_URL }} --commit ${target} --checkout .`. No trace or screenshot upload for production. Write the summary. |

**Rollback procedure.**
1. Run `promote.yml` with `mode=rollback` and `commit=<sha with a prod-* tag>`.
2. Preflight confirms the tag and the floors.
3. Approve.
4. `deploy` force-moves `production` (lease-guarded) and tags it again with a new `prod-*` tag recording `mode=rollback`.
5. `verify` confirms the old build is live.

No other path moves `production`. The ruleset blocks everything except the deploy key.

## Workflow 4 — `prod-check.yml`

**Triggers:** `schedule: '17 */6 * * *'`, `workflow_dispatch`.

| Job | Permissions | Steps |
|---|---|---|
| `check` | `contents: read` | Check out the `production` branch head, then `postdeploy_check.py --url ${{ vars.PROD_URL }} --commit <head> --checkout .`. Write the summary. |
| `report-failure` | `issues: write` | `needs: check`, `if: failure()`. Find the open issue labelled `prod-check-failure`: comment on it if one exists, otherwise open "Production check failing" with the label and a link to the run (RD4). |

## Dependabot — `.github/dependabot.yml`

| Ecosystem | Directory | Schedule | Grouping |
|---|---|---|---|
| `github-actions` | `/` | weekly (Mon) | One group for all minor and patch updates |
| `uv` (lockfile inputs `requirements.in`, `requirements-dev.in`) | `/` | weekly (Mon) | One group for minor and patch; majors as separate PRs |

Every Dependabot PR runs the full `ci.yml`, including `lock-check`, which verifies that the regenerated lockfiles match. If Dependabot's uv support doesn't regenerate the hashed `.txt` files, the runbook says to regenerate them locally on that PR with the documented `uv pip compile` command.

## Stage → gate summary

| Gate | Where | Blocks |
|---|---|---|
| Lint, format, workflow lint | `ci.yml` jobs 1–2 | Merge |
| Secret scan, burned-secret digest | `ci.yml` job 3 | Merge |
| Dependency audit (high/critical), exceptions | `ci.yml` job 4 | Merge |
| SAST (high) | `ci.yml` job 5 | Merge |
| Lock freshness | `ci.yml` job 6 | Merge |
| Tests on each Python leg, test floor | `ci.yml` job 8 | Merge |
| Coverage ratchet and 80% | `ci.yml` job 9 | Merge; promotion (floor ≥ 80) |
| Staging post-deploy check | `staging-check.yml` | Promotion of that commit |
| Owner approval | `production` Environment | Production move |
| Production post-deploy check | `promote.yml` `verify` | Marks the promotion failed (rollback is your decision) |

## Secrets and variables used by the pipeline

| Name | Kind | Scope | Used by |
|---|---|---|---|
| `PROD_DEPLOY_KEY` | Secret | `production` Environment only | `promote.yml` `deploy` |
| `STAGING_URL` = `https://hsm-dashboard-staging.streamlit.app` | Variable | Repository | `staging-check.yml` |
| `PROD_URL` = `https://hsm-dashboard.streamlit.app` | Variable | Repository | `promote.yml` `verify`, `prod-check.yml` |
| `HOSTED_PYTHON` | Variable | Repository | `ci.yml` `matrix` |

The CI test jobs use no secret. `tests/conftest.py` generates the signing secret per session (SD3).

## Assumptions & Open Questions

- [assumption] Dependabot's `uv` ecosystem supports `requirements.in`-style inputs. The fallback is the documented local regeneration on the Dependabot PR.
- [assumption] The Streamlit Cloud wrapper URL serves the app inside an iframe that Playwright can enter. The check is frame-aware either way (RD1).
- None.
