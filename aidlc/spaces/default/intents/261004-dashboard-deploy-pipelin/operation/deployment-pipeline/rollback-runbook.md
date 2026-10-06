# Rollback Runbook — Staging

## Sources

- Team rules, Deployment: "revert on `main` (staging) … let Streamlit Cloud redeploy it. Then re-run the post-deploy check."
- `deployment-pipeline-questions.md` Q4 A (a revert pull request is enough; no emergency shortcut)
- `construction/ci-pipeline/quality-gates.md` — no bypass on `main` [quality-gates]
- `construction/infrastructure-design/cicd-pipeline.md` — rollback design, now staging-only [cicd-pipeline]
- `construction/infrastructure-design/infrastructure-specification.md`, `construction/ci-pipeline/ci-config.md` [infrastructure-specification, ci-config]

## When to roll back

- `staging-check.yml` fails on a merge commit and a re-run also fails, or
- the owner signs in and finds staging broken: an error screen, missing tabs, or the wrong build caption after the redeploy should have finished.

A single failed check is first re-run once from the Actions tab, because a slow redeploy can outlast the 3-minute wait.

## Steps

1. **Find the bad commit.** It's the newest squash commit on `main` (`git log --oneline -5 origin/main`), or the commit whose `staging-check` run failed.
2. **Revert it on a branch.**
   ```bash
   git switch main && git pull --ff-only
   git switch -c revert-<short-sha>
   git revert <sha>
   ```
   Commit through `/commit`, as for any change.
3. **Open a pull request** into `main`. The 10 required checks run. There is no bypass, so allow about 5–10 minutes [quality-gates].
4. **Merge** once they're green. Streamlit Community Cloud redeploys staging from the reverted `main`.
5. **Verify.** `staging-check.yml` runs on the revert commit by itself. Then sign in and confirm the sidebar caption shows the revert commit's short SHA.
6. **Follow up.** Fix the original change on a new branch and merge it again through the normal path.

## Not a rollback: a security breach

Q4 covers bad changes, where a revert pull request is fast enough. If the sign-in gate ever lets in someone it shouldn't, or a secret leaks, follow the existing security steps in `docs/staging-app.md` § Rollback instead: delete the app or empty its allowlist first, rotate the affected secret, then investigate.

## If the revert itself fails CI

Fix forward on the revert branch until the checks pass. The floors and gates are never lowered to get a revert through (project rules, Forbidden).

## Escalation

Single owner, single approver: the repository owner (`SaadsProjects`) does every step. There is no on-call rotation for this demo.

## Rollback test

Untested so far. The first real revert, or a deliberate revert of a harmless docs commit, proves it. Record the date and the time from merge to a passing check in `docs/staging-app.md` when that happens.

## Assumptions & Open Questions

- [assumption] Reverting a squash commit cleanly undoes it. That holds while each pull request is one commit on `main` (team rules, Way of Working).
- None.
