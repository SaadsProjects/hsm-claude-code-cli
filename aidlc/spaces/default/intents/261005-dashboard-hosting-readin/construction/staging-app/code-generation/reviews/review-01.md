## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T11:21:12Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | docs/staging-app.md > section 1 step 1 and section 4 step (d); code-generation-plan.md > S7 (d) | The runbook tells the owner to put the OAuth consent screen in testing mode with only the owner as a test user. In testing mode Google blocks every other account at its own consent step ("Access blocked"), so the step (d) sign-in with a verified non-allowlisted account never reaches the gate. The gate's refusal screen ("This account doesn't have access.", REFUSED_TEXT in dashboard/auth_gate.py) would go unproven, and team.md's Walking Skeleton requires proving exactly that refusal. | In step 1 and step (d), say the second Google account must also be added as a test user (or the consent screen published), so Google lets it through and the gate itself refuses it. Add one line saying that a Google "Access blocked" page does not count as passing (d). | New |
| R-02 | Minor | docs/staging-app.md > section 4 Timing (NFR2) | NFR2 asks for "usable within 30 seconds of waking", but scripts/postdeploy_check.py prints no elapsed time. The runbook says to "note how long it took" without saying how. A brand-new app is not asleep, so "leave the app asleep first" gives no instruction for getting it asleep. | Tell the owner to wrap the command in `time`, and to stopwatch the sign-in in (c). Say to wait until Streamlit shows the sleep page (or reboot the app) before the NFR2 run. | New |
| R-03 | Minor | docs/staging-app.md > sections 2 and 3 | Section 2 tells the owner to enter the secrets in Advanced settings, but they are generated and defined in section 3. The order is circular for someone following it top to bottom. | Move secret generation before app creation, or have section 2 refer forward explicitly. | New |
| R-04 | Minor | tests/test_staging_runbook.py > test_runbook_names_every_secret_key, test_runbook_says_signing_and_cookie_secrets_differ | The key-name test passes on a bare mention of a key (`f"{key} =" in text`). It does not check the layout that the prose calls load-bearing: the two top-level keys before `[auth]`, and `redirect_uri` and `cookie_secret` under `[auth]`. A reorder of the fenced TOML would still pass. The test is meaningful for drift in key names. | Add a test that extracts the first fenced toml block, checks `HSM_SIGNING_SECRET` and `HSM_ALLOWED_EMAILS` appear before `[auth]`, and checks that `[auth.google]` holds the three provider keys. Parse it with tomllib on Python 3.11+, or by line order on 3.10. | New |
| R-05 | Minor | docs/staging-app.md > section 4; code-generation-plan.md > S7 | team.md's hosted-app skeleton is "merge to main, CI, automatic deploy, check". The proof sequence runs against an app created after the merge, so it never shows that a later merge redeploys staging automatically. The CI security checks are shown only through PR #7's required checks. | Add an optional step (e) that confirms a later merge to main redeploys staging (the Build caption changes), or record that the redeploy is left unproven. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| ruff check . | PASS (.venv/bin/ruff) | No lint issues. |
| ruff format --check . | PASS (547 files formatted) | No formatting issues. |
| pytest tests/test_staging_runbook.py -q | 14 passed | The tests are not always-pass. They read the key set from secrets.toml.example and have a self-test for the key reader. Layout coverage is thin (R-04). |
| Manual cross-check against dashboard/auth_gate.py, scripts/postdeploy_check.py, .github/workflows/postdeploy.yml and .gitignore | Consistent | Keys match C7 (`[auth]` holds `redirect_uri` and `cookie_secret`; `[auth.google]` holds `client_id`, `client_secret` and `server_metadata_url`). The redirect URI `/oauth2callback` is correct for st.login. The refusal and unavailable strings match the code. The `Build <sha7>` and `Build src-<8>` captions match BuildInfo. Exit codes 0/1/3/4 match. The check never signs in (F1 holds). `.streamlit/secrets.toml` is git-ignored (F2). The runbook holds only placeholders. |

### Summary

The runbook and its tests are consistent with the gate, the post-deploy check and the secrets schema. Nothing sensitive is committed, and following it would give a correctly secured staging app. The one real gap is R-01: with Google's testing-mode consent screen, step (d) cannot reach the gate's refusal as written. The other four findings are minor.
