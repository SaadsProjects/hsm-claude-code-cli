## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T04:33:19Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | dashboard/app.py > module docstring | The line "Inside the gate the user acts as a demo persona ... Every read and write goes through HsmClient with a token minted for" is a short line followed by a long wrapped line, so the docstring paragraph reflows unevenly after the edit. It is cosmetic: ruff check and ruff format --check both pass. | Re-wrap the paragraph at the next touch of this file. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| ruff check . | All checks passed | Lint is clean. |
| ruff format --check . | 512 files already formatted | Formatting is clean. |
| pytest (the 7 unit-scope test files) | 219 passed, 5 skipped | Gate, bridge, app and embedded tests are green. The skips are the browser-marked tests. |
| git diff 6f9b4ce fa3264b on .coverage-floor, .test-floor, .coveragerc | No diff | The floors and the measured package set are untouched (95.00 and 745). |

### Verification of the three commit-review fixes

- **Per-run `drawn` set:** `gate()` creates `drawn = set()` per run. `_sign_out_button` returns early when the key is already in `drawn` and otherwise registers it. Screen 5 therefore never re-registers the Sign out widget key after Screen 2 drew it. `render_account_section` is only reached on the allow path, where `gate` drew nothing, so the key cannot be registered twice.
- **`sign_out()` in a `finally`:** `_sign_out_clicked` calls `end_visitor_session` inside `try`. `sign_out()` runs in the `finally`, and its own failure is logged by error type only. `st.rerun()` follows outside both blocks. `RerunException` is a BaseException, so it is not swallowed by the `except Exception` clauses.
- **Docs and secrets bridge:** the `secrets_bridge.py` docstring says a `secrets.toml` line replaces an exported value, which matches the stated Streamlit behaviour. `bridge_signing_secret` never overwrites an exported value itself.

### Architecture checks

- **Fail-closed order:** `_evaluate` runs the signing secret, the cookie-secret conflict, the settings, the allowlist, and only then the identity. `gate()` wraps all of it in a catch-all that renders Screen 5 and never the persona picker.
- **Decision rules:** `decide` requires `email_verified is True` and an exact trimmed, lower-cased match. It has no domain wildcards.
- **Run order:** `run()` calls `st.stop()` on any non-allow outcome before `embedded.start()`, so the backend does not start until the gate allows.
- **Layer boundary:** `mock_hsm/auth.py` is untouched, and the Streamlit bridge lives in `dashboard/secrets_bridge.py`.
- **Dependencies:** `requirements.in` moves to `streamlit[auth]`, and both lockfiles changed in the same commit.
- **Logging:** log lines are built only from reason constants, error types and setting names. `Identity.email` is excluded from `repr`.
- **Visitor state:** a different account starts with no persona login, and sign-out clears every dashboard key.

### Summary

The unit is implementable and consistent with its contracts, and all three commit-review fixes are present and correct. Lint, format and tests pass, and the floors are unchanged. The only note is a cosmetic docstring reflow.
