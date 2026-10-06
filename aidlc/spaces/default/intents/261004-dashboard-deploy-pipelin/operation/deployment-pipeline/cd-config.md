# CD Configuration — Dashboard Deployment Pipeline (staging only)

## Sources

- `construction/infrastructure-design/cicd-pipeline.md` — delivery model, Workflow 2 `staging-check.yml`, common conventions [cicd-pipeline]
- `construction/infrastructure-design/infrastructure-specification.md` — the staging app and the GitHub services [infrastructure-specification]
- `construction/ci-pipeline/ci-config.md` — `ci.yml` and its 10 required checks [ci-config]
- `construction/ci-pipeline/quality-gates.md` — merge gates and the "Not gates (yet)" row for the staging check [quality-gates]
- `deployment-pipeline-questions.md` Q1–Q4 (all A), confirmed 2026-10-06
- Plan change of 2026-10-06: production removed; environment provisioning, deployment execution and observability setup skipped
- Existing repository state: `.github/workflows/postdeploy.yml` (manual check), `scripts/postdeploy_check.py` (contract C8), `docs/staging-app.md`, staging app `https://hsm-stg.streamlit.app` tracking `main`

## What changed from the infrastructure design

The infrastructure design planned four workflows for two environments [cicd-pipeline]. With production removed, only the staging half remains:

| Designed item | Now |
|---|---|
| `ci.yml` (merge gates) | Unchanged; already live with 10 required checks [ci-config] |
| `staging-check.yml` (check after each merge) | **Built here**, simplified: no commit status, no `--commit` flag (see below) |
| `promote.yml` (approval-gated production move) | Dropped |
| `prod-check.yml` (6-hourly production check) | Dropped |
| `production` GitHub Environment, `PROD_DEPLOY_KEY`, `production` ruleset, `PROD_URL` | Dropped; nothing to create [infrastructure-specification] |
| `postdeploy.yml` (manual check) | Unchanged; stays the way to check any URL by hand |

## Delivery model

Streamlit Community Cloud pulls: the staging app redeploys whenever `main` moves. The pipeline therefore never deploys anything. It gates what reaches `main`, then checks what staging serves.

```
PR ──ci.yml (10 required checks)──▶ squash merge ──▶ main ──Cloud redeploys staging
                                                       │
                                                       └──push──▶ staging-check.yml: wait 3 min ─▶ post-deploy check ─▶ pass / fail (email on fail)
```

Text fallback:
1. A pull request runs `ci.yml`. With all 10 required checks green it can be squash-merged into `main`.
2. Streamlit Community Cloud sees `main` move and redeploys staging.
3. The same push starts `staging-check.yml`. It waits 3 minutes, then runs the read-only post-deploy check against staging.
4. A failure shows as a red run on that commit, and GitHub emails the person who merged.

## Workflow `staging-check.yml`

| Setting | Value | Why |
|---|---|---|
| Trigger | `push` to `main` only | Q1 A. Manual checks keep using `postdeploy.yml` |
| Concurrency | group `staging-check`, `cancel-in-progress: true` | A newer merge supersedes an older check; staging only serves the latest commit |
| Permissions | top-level `{}`; job `contents: read` | No commit status or issue write is needed (Q3 A) |
| Secrets | none | The check never signs in (FR8.3) |
| Runner | `ubuntu-24.04`, `timeout-minutes: 20` | Team convention [cicd-pipeline] |
| URL | repository variable `STAGING_URL` = `https://hsm-stg.streamlit.app`, passed through `env` | Keeps the address out of code; the job fails with a clear message when the variable is unset |
| Wait | `sleep 180` before the check | Q2 A. Streamlit gives no "redeploy finished" signal, and the check can't read the build caption |
| Check | `python scripts/postdeploy_check.py "$URL" --timeout 600` | FR8.2: up to 10 minutes for a sleeping or waking app |
| Install | same pinned `setup-python`, dev lock, and Playwright Chromium cache as `postdeploy.yml` | One way to install the check |

Steps, in order: checkout (no persisted credentials) → setup Python 3.14 with pip cache → `pip install --require-hashes -r requirements-dev.txt` → read the Playwright version → restore the Chromium cache → `playwright install --with-deps chromium` → fail if `STAGING_URL` is empty → wait 180 s → run the check.

**Simplified from the design.** The design's `staging-check.yml` passed `--commit`, `--checkout` and `--report` and posted a `staging-check` commit status for promotion to read [cicd-pipeline]. The check that shipped (contract C8) takes only a URL and `--timeout`, and with no promotion nothing reads a status. So the job's own pass or fail is the record.

**What the check proves, and what it can't.** It proves staging answers and turns away a visitor who isn't signed in. It cannot prove staging already runs the merged commit, because the build caption only shows after sign-in. The 3-minute wait makes that likely, not certain. The owner confirms the build by signing in and reading the sidebar caption (project correction, 2026-10-05).

## Repository settings (owner, once)

- *Settings → Secrets and variables → Actions → Variables:* add `STAGING_URL` = `https://hsm-stg.streamlit.app`.
- No ruleset change. `staging-check` runs after the merge, so it can't be a required check on the pull request.

## Gates

| Gate | Where | Blocks |
|---|---|---|
| The 10 required checks | `ci.yml` | Merge into `main` [quality-gates] |
| Staging post-deploy check | `staging-check.yml` | Nothing automatically. A failure means the deploy isn't done and the owner acts (see `rollback-runbook.md`) |

## Tests

`tests/test_staging_check_workflow.py` reads the workflow as text, like `tests/test_postdeploy_workflow.py`, and asserts: triggered by `push` to `main` only; permissions `{}` plus `contents: read`; no secrets; every action pinned and `scripts/check_workflows.py` clean; the URL reaches the shell through `env`, never spliced; the wait comes before the check; the check runs with `--timeout 600`.

## What was built (branch `staging-check`, not yet committed)

| Path | Change |
|---|---|
| `.github/workflows/staging-check.yml` | New workflow, as above |
| `tests/test_staging_check_workflow.py` | 10 tests: 8 written first and failing before the workflow existed, plus 2 from the commit review (credentials not kept; the job limit covers install + wait + check) |
| `tests/test_postdeploy_workflow.py` | Commit review: also refuses a blanket `read-all` / `write-all` grant (the same assertion is in the new file) |
| `tests/test_staging_runbook.py` | 1 new test: the runbook says to set `STAGING_URL` |
| `docs/staging-app.md` | New § 5 "Turn on the automatic check"; the rollback bullet now mentions `staging-check` |
| `CLAUDE.md` | CI section names `staging-check.yml` |

Verified locally on 2026-10-06: the full suite gives 1206 passed and 23 skipped (floor 1100), `scripts/check_workflows.py` is clean for all 3 workflows, and ruff is clean. actionlint isn't installed locally; the required `workflow-lint` job runs it on the pull request. The workflow's first real run happens on the merge of its own pull request, once `STAGING_URL` is set.

## Assumptions & Open Questions

- [assumption] Three minutes covers a typical Streamlit Community Cloud redeploy of this app. The cold starts measured on 2026-10-06 were 15–18 s, but redeploys also reinstall dependencies.
- [assumption] GitHub emails the merger about a failed `push`-triggered run with the account's default notification settings.
- None.
