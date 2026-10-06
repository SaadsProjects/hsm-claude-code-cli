## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T00:11:04Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/sign-in-gate/nfr-design/security-design.md > S6 (end_visitor_session) | Step 1 of `end_visitor_session` swallows only `BackendNotRunning` and `HsmApiError`. It reaches the backend through `session.client_for(user_id)`, which calls `mint_token`. In the repo, `mint_token` calls `_secret_bytes()` and raises `SecretMissingError`, a `RuntimeError` that is not an `HsmApiError` (`mock_hsm/auth.py`; `agents/hsm_client.py`). A broken or short signing secret while a persona is logged in therefore escapes step 1. Step 2 (state clearing) is not protected by a `finally`, so the persona and scoped items survive, and `sign_out()` is never reached. That breaks NFR1.28 and traps the visitor. The existing `actions.log_out` uses `try/finally` for this reason. | Put the state clearing in a `finally`, or run it before the best-effort backend call. Add `SecretMissingError` (and `ValueError` from `mint_token`) to the named, logged exceptions. Add a test where the secret is broken at sign-out and the state is still cleared. | New |
| R-02 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/sign-in-gate/nfr-design/security-design.md > S1 vs S3 pseudo-code; logical-components.md > DashboardShell row and Screens and Accessibility | The page header has two owners. S1 and the DashboardShell row say `app.py` calls `gate()` "straight after the page header". The S3 pseudo-code and Screens and Accessibility have `gate()` call `render_page_header()` first, "outside the boundary". If both do it, `st.set_page_config` runs twice. Streamlit raises on the second call, so every rerun becomes Screen 5, or the page shows two h1 elements (NFR5.11). A developer has to guess. Today `app.py` lines 455-456 hold `set_page_config` and `st.title`. | State one owner. Either `gate()` renders the header and `app.py` drops its own `set_page_config` and `st.title` calls, or `app.py` renders it and `gate()` does not. Make S1, S3 and the logical-components table agree. | New |
| R-03 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/sign-in-gate/nfr-design/security-design.md > S5 (Literal email test) | `escape_md` backslash-escapes `.`, `-`, `<`, `>` and `*`. The element value for `*a*@example.com` is therefore `\*a\*@example\.com`. The test is specified as "the rendered value holds the literal string and no markup element", which is ambiguous about the stored string versus the displayed text. | Say whether the assertion compares the escaped Markdown source, or use a non-Markdown element such as `st.text` for the email. Pin the expected value in the test. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/sign-in-gate/nfr-design/security-design.md > S3 | The boundary wraps `_render_screen`. If a screen renders some elements and then raises, the handler adds Screen 5 below them, so a refused visitor may see two gate screens. S1 says `gate()` renders only "its own screen container", but S3 does not tie the boundary to that container. | Render each gate screen into one container, or an `st.empty`, that Screen 5 replaces. Add a test that raises mid-render. | New |
| R-05 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/sign-in-gate/nfr-design/security-design.md > S6 (Account binding) | The design does not say how the bound email is compared with the identity's email. It also does not say whether the first allow only binds. If the comparison is case-sensitive, a casing change from the provider clears a persona needlessly. | Specify that the comparison uses the trimmed, lower-cased email, and that the first allow only binds. | New |
| R-06 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/sign-in-gate/nfr-design/logical-components.md > Assumptions | The shared test helper depends on `AppTest` accepting nested `[auth.google]` secrets. This is unverified: shell execution of Streamlit was blocked in this review. A fallback is described, so the risk is low. | Confirm during Code Generation by writing the helper test first. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| traceability (manual) | PASS | `traceability.json` lists all 15 NFR IDs (NFR1.21-1.28, 2.11-2.13, 3.11, 4.11, 5.11, 7.11), and each targets a real section. |
| StopException ancestry (Streamlit 1.64.0) | PASS | `StopException` and `RerunException` derive from `BaseException`, so S3's claim holds. |
| Repo cross-checks | Mixed | `escape_md`, `session.SCOPED_DEFAULTS` and `FORM_KEY_PREFIX` exist as claimed. `SecretMissingError` is not an `HsmApiError` (R-01). |

### Summary

The design traces cleanly to the requirements and its Streamlit and repo claims check out. Two Major gaps remain: sign-out can skip state clearing when the signing secret is broken (R-01), and the page-header ownership contradicts itself (R-02). That is two Majors and no Critical, so the verdict is READY. Both Majors should be fixed before Code Generation.
