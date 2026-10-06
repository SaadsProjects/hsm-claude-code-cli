## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T03:05:00Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | dashboard/auth_gate.py > `log.setLevel(logging.INFO)` and `_log_refusal_once` | The gate logger is set to INFO, but with no root handler configured Python's last-resort handler prints only WARNING and above, so the `not_verified` and `not_listed` refusal lines may never reach hosted logs. The developer disclosed this in code-summary.md. The WARNING-level failure signals are unaffected, and this does not weaken the gate. | Track it as a follow-up for Build and Test or the hosting work: configure a handler, or confirm the lines show in Streamlit Cloud logs. | New |
| R-02 | Minor | dashboard/secrets_bridge.py > `bridge_signing_secret`; code-summary.md open items | Streamlit copies top-level string secrets into `os.environ` itself and can overwrite an exported value. "An exported value always wins" therefore holds only while `secrets.toml` has no `HSM_SIGNING_SECRET` key. The committed example keeps the key as a comment and hosted apps export nothing, so the design is safe today. | Keep the caveat in the dashboard README. No code change is needed. | New |
| R-03 | Minor | tests/gate_app.py and tests/test_auth_gate.py > seam bodies `current_identity`, `sign_in`, `sign_out` | The three seam bodies are the only code in `auth_gate.py` that touches `st.user`, `st.login` and `st.logout`, and no automated test reaches them. Whether `email_verified` arrives as a boolean is unconfirmed until a real Google sign-in is tried. An unconfirmed value is refused, so this fails closed. | The human performs the real sign-in check recorded as an open item. The browser-test unit covers the seam path with its test double. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| `ruff check .` | PASS | No lint findings. |
| `ruff format --check .` | PASS (509 files formatted) | Formatting is clean. |
| Unit command (7 test files) | 217 passed, 5 skipped | Matches the developer's claim. |
| `bandit -r dashboard -ll` | exit 0, no medium or high findings | No findings. |
| `grep` for `nosec`, `pragma` in the three new dashboard modules | no matches | No suppressions. |
| `git diff` on `.coverage-floor`, `.test-floor`, `.coveragerc`, `.gitignore`, `scripts`, `.github` | empty | Floors and the measured set are untouched. |
| Fresh `uv pip compile` of `requirements.in` against `requirements.txt` | identical | Runtime lock matches its input. The edit is limited to `streamlit[auth]` in `requirements.in`. |
| Fresh `uv pip compile` of `requirements-dev.in` against `requirements-dev.txt` | one difference, `filelock` 4.0.12 against 4.0.10 | Not caused by this unit. A fresh resolve picks a newer upstream release and the lock keeps its pinned version. The authlib and joserfc additions are hash-pinned. |
| Mutation run (14 mutants) in a scratch copy of the repo | 14 of 14 killed by `test_auth_gate`, `test_dashboard_gate` and `test_secrets_bridge` | The tests do depend on the implementation. The mutants covered: truthy `email_verified`, dropped lower-casing, suffix match, an allowlist bypass, no account binding, no state clearing at sign-out, an email in a log line, no cookie-secret conflict check, the bridge overwriting an exported value, a skipped settings check, Screen 5 not drawn, and a blank allowlist entry accepted. |
| Source trace | `st.user`, `st.login` and `st.logout` appear only in the `auth_gate.py` seam. `run()` calls `_page_header()`, then `gate()`, then `st.stop()` unless allowed, and only then `embedded.start()`. | The seam is the single caller. Nothing renders and no backend starts before allow. The gate's `except Exception` does not catch `st.stop` or `st.rerun`, which are `BaseException` subclasses. |
| Changed paths against `source-manifest.json` | All changed non-record paths are claimed | No unclaimed changes. |

### Summary

The gate fails closed on every path I traced, including a thrown identity reader, a broken settings file and a broken allowlist, and each of these lands on Screen 5. The email is shown through `st.text` and never reaches a log line. Sign-out clears state and an account change drops the previous persona login. The tests killed all 14 mutants I tried, the floors and `.coveragerc` are untouched, and the locks are consistent. The three Minor items are disclosed or fail closed, so none blocks.
