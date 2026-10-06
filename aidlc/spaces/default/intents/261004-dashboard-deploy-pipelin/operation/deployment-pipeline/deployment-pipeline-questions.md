# Deployment Pipeline — Questions

Production was removed from this work on 2026-10-06, so the pipeline only has to look after staging, `https://hsm-stg.streamlit.app`. Staging already tracks `main` and redeploys itself after every merge. The read-only post-deploy check (`scripts/postdeploy_check.py`) exists, but today it only runs when you start the `postdeploy` workflow by hand. These questions settle what, if anything, the pipeline adds on top of that.

Already settled elsewhere, so not asked again: rollback is a revert on `main` followed by a re-run of the check (team rules, Deployment); the check never signs in and cannot see the build caption (project correction, 2026-10-05); every workflow keeps SHA-pinned actions and least-privilege permissions (project rules, Mandated).

## Q1. Should the post-deploy check run against staging automatically after each merge?

The approved requirement says a workflow runs the check after every merge to `main` (FR6.2). Part of its reason was to let a production release depend on it, and production is gone. The team rules still say a deploy isn't done until the check passes.

A. Yes — run it automatically after every merge to `main`, plus by hand when wanted (Recommended)
B. No — keep it manual only; the owner runs the `postdeploy` workflow after merges that matter
C. Run it on a schedule (for example daily) and by hand, but not on every merge
X. Other (please specify)

[Answer]: A

## Q2. How should an automatic check handle staging still redeploying?

Streamlit gives no signal that the redeploy has finished, and the check can't read which build is running (that caption only shows after sign-in). If it checks straight away, it may test the previous build. This only applies if Q1 is A or C.

A. Wait a fixed few minutes after the merge, then check (the check already waits up to its timeout for a sleeping or waking app) (Recommended)
B. Check straight away; accept that it sometimes tests the previous build
C. Not applicable (Q1 is B)
X. Other (please specify)

[Answer]: A

## Q3. How should you hear that the automatic check failed?

GitHub already emails the person who triggered a run when it fails. For a run started by a merge, that is the person who merged — you.

A. GitHub's failed-run email is enough; no extra notification (Recommended)
B. Also open (or comment on) a GitHub issue when it fails, which needs the workflow to have permission to write issues
C. Not applicable (Q1 is B)
X. Other (please specify)

[Answer]: A

## Q4. Is a pull-request revert fast enough as the staging rollback?

`main` refuses direct pushes and has no bypass, so a revert goes through a pull request and all 10 required checks, which takes about 5–10 minutes before staging redeploys. Staging is a demo with resetting data behind a sign-in gate.

A. Yes — a normal revert pull request is the rollback; no faster path is needed (Recommended)
B. Also document an emergency stop: reboot or delete the staging app from the Streamlit console while the revert goes through
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
