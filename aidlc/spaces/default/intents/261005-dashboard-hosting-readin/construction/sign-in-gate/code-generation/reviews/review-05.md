## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T12:58:29Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | dashboard/app.py > module docstring | The paragraph now wraps evenly (rewritten in a later edit); no uneven reflow remains. ruff check and ruff format --check pass. | None. | Resolved |
| R-02 | Minor | docs/staging-app.md > step 2, paragraph before the secrets block ("TOML files any key under the last table above it") | The sentence is garbled. It reads as if "files" were a verb. The technical claim is correct: a top-level key pasted below an `[auth]` table becomes part of that table, so `HSM_ALLOWED_EMAILS` would be missed. The block itself puts both top-level keys first. | Reword to "TOML assigns any key to the last table above it". Not blocking. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| ruff check . | PASS (All checks passed) | Clean. |
| ruff format --check . | PASS (550 files already formatted) | Clean. |
| pytest test_auth_gate, test_secrets_bridge, test_dashboard_gate, test_gate_app | PASS: 142 passed, 1 skipped | Gate decision, bridge, AppTest wiring and fake-identity seam are green on the current tree. |

### Guarantee check on the current tree

- **Gate runs first and before the backend.** In `dashboard/app.py`, `run()` calls `_page_header()`, then `auth_gate.gate()`, then `st.stop()` unless the outcome is `ALLOW`. Only after that does it call `embedded.start()` and `main(...)`. Nothing renders and no backend starts on a refusal.
- **Fails closed.** `_evaluate` checks in a fixed order: signing secret, cookie/signing-secret conflict, the five `[auth]` keys, allowlist parse, and only then the identity. Any exception in `gate()` becomes `REFUSE_UNAVAILABLE`/`gate_error` and Screen 5, never the persona picker. An empty allowlist raises `AllowlistInvalidError`, so `[]` refuses everyone. This matches the runbook's rollback claim.
- **Verified and exact allowlist.** `decide` requires `identity.email_verified is True`, so `"true"`, `1` and a missing claim all refuse. The email is trimmed and lower-cased and must be an exact member of the allowlist. There is no domain rule. A blank email is treated as a gate error. This is consistent with the new evidence: the allowlisted account got in, and a verified, non-allowlisted Gmail account got the `not_listed` refusal screen.
- **No email in logs.** Every `log.*` call in `auth_gate.py` and `secrets_bridge.py` is built from constants, setting names or `type(exc).__name__`. `Identity.email` and `Decision.identity` are excluded from `repr`, and `Decision.identity` is also excluded from equality.
- **Sign-out clears the persona.** `end_visitor_session` ends the backend session on a best-effort basis. In a `finally` block it clears `LOGIN`, `NOTICE`, the form-key prefix, the scoped defaults and the gate's own keys. `_sign_out_clicked` then calls `st.logout()` even if the clearing failed, and reruns. `_bind_account` also resets the persona when a different allowed account arrives.
- **Docs.** Each gate claim in `docs/staging-app.md` matches the code:
  - Equal signing and cookie secrets give "Sign-in isn't available right now."
  - Missing secrets give the same neutral screen.
  - The refusal text is "This account doesn't have access." with Sign out and no tab.
  - The five keys and the exact-address allowlist match `AUTH_KEYS` and `parse_allowlist`.
  - The `CLAUDE.md` and `README.md` additions are one-line links only, and the runbook says the check never signs in.
- **Source-state note.** Local `HEAD` shows `e1ddc16`; `23396d7` was not resolvable in the local log. The gate files read and tested are the current working tree, and `git status` shows no uncommitted changes outside `aidlc/`. This does not affect the verdict.

### Summary

All five gate guarantees still hold on the current tree, and nothing since iteration 1 weakens them. The only new item is a Minor wording slip in the runbook. READY.
