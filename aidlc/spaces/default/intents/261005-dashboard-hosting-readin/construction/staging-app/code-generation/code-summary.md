# Code Summary — U6 staging-app

## Files

| File | Change | What it holds |
|------|--------|---------------|
| `docs/staging-app.md` | Created | The owner's runbook. It covers: before you start (PR #7 merged, checks green); creating the Google OAuth client (a web application with one redirect URI, `https://<staging-app>.streamlit.app/oauth2callback`); creating the app (`main`, `dashboard/app.py`, Python version per S5); entering the secrets (all seven keys, fresh values from `secrets.token_urlsafe(48)`); proving it (S7 a–d, with the NFR2 timing note); and rollback (S9). Placeholders only |
| `tests/test_staging_runbook.py` | Created | 14 tests: the runbook exists; the key reader returns exactly the seven keys from `.streamlit/secrets.toml.example`; a `tmp_path` self-test pins what the reader picks up; one test per key (7) that the runbook names it; the signing and cookie secrets must differ; the main file and branch; the check command and redirect path; and a placeholders-only guard |
| `README.md` | Modified | One line under "Post-deploy check" linking the runbook |
| `CLAUDE.md` | Modified | One line after the `postdeploy.yml` paragraph linking the runbook |

## Key Implementation Decisions

- S1–S9 are implemented as planned. No file under `dashboard/`, `agents/`, `mock_hsm/` or `scripts/` changed.
- The key reader uses the line pattern from the test instructions, because Python 3.10 has no `tomllib`. It includes the commented `HSM_SIGNING_SECRET` and skips prose and table headers.
- **Extra test beyond the instructions:** a placeholders-only guard. The only email allowed is `your-email@example.com`, no `*.apps.googleusercontent.com` client id may appear, and no non-placeholder `*.streamlit.app` host may appear. It backs S1 and project.md F2.
- **Runbook claims checked against `dashboard/auth_gate.py`:**
  - Equal signing and cookie secrets show "Sign-in isn't available right now." The app doesn't refuse to start.
  - An empty `HSM_ALLOWED_EMAILS = []` fails closed, because `parse_allowlist` rejects it. S9 relies on this.
- The secrets block notes that the two top-level keys must come before `[auth]`. Otherwise TOML would file them under that table.

## Test Coverage Summary

| Measure | Result |
|---------|--------|
| Runner check (Step 1, `tests/test_postdeploy_check.py`) | 37 passed |
| Unit command (`tests/test_staging_runbook.py`) | 14 passed (re-run by the conductor) |
| Full suite | 1188 passed, 23 skipped (baseline 1174 passed, 23 skipped; `.test-floor` 745) |
| Coverage | Unchanged: no measured file changed |
| `ruff check .` / `ruff format --check .` | All checks passed / 546 files already formatted (re-run by the conductor) |

### Red evidence (TDD)

| Step | Failing command | Failure |
|------|-----------------|---------|
| 2 | `python3 -m pytest tests/test_staging_runbook.py -q` | `12 failed, 2 passed`. Every runbook test failed with `FileNotFoundError: … docs/staging-app.md`. The 2 passes were the key-reader self-tests, which read only the example file |

## Deviations from the Plan

- One test more than planned: the placeholders-only guard (14 tests, against at least 6 planned).
- None otherwise.

## Fixes from the Unit Review

The architecture review was READY with one Major and four Minor findings. The human chose to fix all five, test first, before committing. Five tests were added, and four of them failed before the runbook changed (`4 failed, 15 passed`).

- **R-01 (Major): the refusal proof was blocked by Google.** In testing mode, Google stops any account that isn't a test user before it reaches the app. Section 1 now adds the not-allowlisted account from step 4 (d) as a test user too, and says why. Step (d) points back to it. Test: `test_runbook_makes_the_refused_account_a_test_user_too`.
- **R-02: NFR2 had no way to be timed.** The timing note now explains how to get the app asleep (wait for the sleep page, or reboot for a cold start). It times the check with `time python3 scripts/postdeploy_check.py …` and the sign-in with a stopwatch. Test: `test_runbook_times_the_check_from_a_sleeping_app`.
- **R-03: secrets were used before they were made.** The sections are now OAuth client, then preparing the secrets, then creating the app (which pastes the block from step 2), then the proof. Test: `test_runbook_generates_the_secrets_before_creating_the_app`.
- **R-04: the TOML layout was untested.** A new test reads the fenced TOML block. It checks that both top-level keys come before `[auth]`, that `redirect_uri` and `cookie_secret` sit under `[auth]`, and that the three Google keys sit under `[auth.google]`. The test passed on its first run, because the layout was already right; it guards against a reorder. Test: `test_runbook_secrets_block_has_the_c7_layout`.
- **R-05: the automatic redeploy was never shown.** A new step (e) checks after the next merge to `main` that staging redeploys by itself (the `Build` caption changes), then re-runs the check. It stays open, and is recorded as not yet proven, until a later merge happens. Test: `test_runbook_checks_a_later_merge_redeploys_staging`.
- The plan's S7 (d) wording was left as approved. The runbook carries the test-user prerequisite.

After the fixes: 19 runbook tests pass, the full suite gives 1193 passed and 23 skipped, and `ruff check` and `ruff format --check` are clean.

## Fixes from the Commit Review

The `/commit` code reviewer found no blocking problems. It confirmed every runbook claim against the code. It raised four minor issues, and the human chose to fix all four before committing.

1. **The hosted Python version went untested.** Section 3 now says to set the repository variable `HOSTED_PYTHON` when staging's Python is neither 3.10 nor 3.14. Red: `test_runbook_says_when_to_set_hosted_python` failed first.
2. **The paste-ready block could miss a key.** `test_runbook_secrets_block_holds_exactly_the_example_keys` compares the fenced TOML block's keys with the example's. It passed on its first run, because the block is complete; it guards against drift.
3. **The key-order explanation was wrong.** It now says that TOML files a key under the last table above it.
4. **The OAuth secret rotation order was wrong.** Rollback now says to put the new secret in the app and reboot it before deleting the old secret.

After the fixes: 21 runbook tests pass, the full suite gives 1195 passed and 23 skipped, and `ruff check` and `ruff format --check` are clean.

## Staging Evidence (plan Steps 5–7)

- **Step 5:** commit `e1ddc16` was pushed to PR #7, and all 10 required checks passed. PR #7 was marked ready and squash-merged into `main` as `23396d7` on 2026-10-06, with the human's go-ahead at each step.
- **Step 6:** the human created the app at `https://hsm-stg.streamlit.app` (branch `main`, `dashboard/app.py`).
  - The first deploy failed: the `SaadsProjects` organization restricts third-party OAuth app access. The owner granted Streamlit access to the organization and kept the restriction on for every other app.
  - The secrets were generated into `~/hsm-stg-secrets.toml`, outside the repository, mode 600, and never printed. Only the human added the email and the OAuth client values.
- **Step 7 (a):** `python3 scripts/postdeploy_check.py https://hsm-stg.streamlit.app --timeout 180` gave exit 0, PASS, in 8.5 s wall time. The app answered, the sign-in screen showed, and no dashboard tab showed. The app was freshly deployed and awake, so this run is not the NFR2 measurement.
- **Step 7 (b):** the `postdeploy` workflow, run 37464999295 on `main`, passed with the same three lines and PASS.
- **Step 7 (c):** the owner signed in with the allowlisted Google account and reached the dashboard. The sidebar caption read `Build 23396d7`, the head of `main`. This is the first real Google sign-in through the gate: `email_verified` came back true and the allowlist matched (feasibility R1 confirmed). The host's checkout has `.git`, so the caption shows the commit, not a fingerprint.
- **Step 7 (d):** the owner signed in with a newly created Gmail account. It was verified and listed as a consent-screen test user, but not on the allowlist. The app's own refusal screen showed ("This account doesn't have access." with Sign out), not Google's "Access blocked" page. This is the team.md Walking Skeleton proof that the sign-in layer turns away a verified email that isn't allowlisted.
- **Python:** 3.14, which CI already tests, so `HOSTED_PYTHON` is not set (S5).
- **Still open:** the NFR2 timing from a sleeping app, and step (e), the automatic redeploy on a later merge to `main`. Both are recorded as not yet proven.

## Still to Do (plan Steps 5–7)

- **Step 5:** commit "Add the staging app runbook" through `/commit`, staging exactly `docs/staging-app.md`, `tests/test_staging_runbook.py`, `README.md` and `CLAUDE.md`. Then push to PR #7, wait for the 10 required checks, mark it ready and squash-merge. Each step needs the human's go-ahead.
- **Step 6:** the owner creates the OAuth client and the app and enters the secrets. The Python version chosen is recorded here then.
- **Step 7:** run the check against staging, locally and through the `postdeploy` workflow. The owner signs in with an allowlisted account and with one that isn't on the allowlist. The evidence and the NFR2 timings are recorded here.
- Step 4 (e), the automatic redeploy on a later merge, stays open until that merge happens.
- FR9.1, FR9.3 and NFR2 are marked `Deferred` in `traceability.json` until Step 7's evidence exists.
