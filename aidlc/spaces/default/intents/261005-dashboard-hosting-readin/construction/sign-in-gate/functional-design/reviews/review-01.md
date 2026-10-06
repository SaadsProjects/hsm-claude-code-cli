## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-05T23:54:43Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/sign-in-gate/functional-design/frontend-components.md > SignOutButton behaviour; functional-spec.md > W4; rules.md > BR5.1 vs BR7.1 | W4 and SignOutButton put the whole sequence (end the backend session, clear dashboard state, Google sign-out) inside the seam's `sign_out`. BR7.1 and the user stories' test seam say tests patch the seam. A test that patches `sign_out` then skips the state clearing, so AC4.6.3 (no persona pre-selected after sign-out) cannot be verified through AppTest, and BR7.1 ("the seam is the only code that touches Streamlit's sign-in API") is blurred by non-Streamlit logic living in the seam. | Split the sign-out. A plain, Streamlit-state-only `end_visitor_session()` does steps 1 and 2 and is tested directly. The seam's `sign_out` wraps only `st.logout()`. The button calls the first, then the seam. State this split in W4 and frontend-components, and note how it fits C4's "clears the persona session, then st.logout()" wording. | New |
| R-02 | Minor | functional-spec.md > W1 steps 2-4 and 7 vs W2 Screen 5 row, rules.md > BR4.3 | Steps 2-4 jump straight to step 7, so the identity is never read (step 5) on the secret, settings and allowlist failure paths. W2 and BR4.3 show "Sign out" on Screen 5 only if the seam reports a signed-in identity. The spec does not say whether the seam is read on those paths, or what happens if `st.user` or `st.logout` is unusable when `[auth]` is the broken part. A signed-in visitor could lose the way out that the project rule requires on every refusal screen. | Say explicitly that Screen 5 reads `current_identity()` inside its own guarded call on every path, and that a failed read means no Sign out button, with "Reload the page" as the way out. Say what Sign out does when the sign-in settings are broken. | New |
| R-03 | Minor | functional-spec.md > W4 step 2; frontend-components.md > State Design; dashboard/actions.py `log_out` | W4 says to clear "all dashboard state, including any notice". The existing `actions.log_out` sets a "logged out" notice and drops held writes, so it can't be reused as is. The spec does not say how it composes with that function. `session.client_for` also raises `embedded.BackendNotRunning` when no backend is running, for example when sign-out is chosen from Screen 4, and "best effort" does not name that case. | Name the exact reuse: for example `actions.log_out` plus a notice clear, or a new `clear_all` helper that enumerates `login`, `notice`, the scoped items, form keys and the pending retry. List `BackendNotRunning`, `HsmUnavailable` and `HsmApiError` as the swallowed failures. | New |
| R-04 | Minor | functional-spec.md > State Machine table | The table and diagram have no transition for `Unavailable` (signed in) to `Allowed` or `Refused` once the settings, secret or allowlist are fixed. The diagram only has `Unavailable` to `SignedOut`. | Add rows for the missing transitions (the checks pass and an identity is present, from any state). | New |
| R-05 | Minor | entities.md > PersonaSession; rules.md > BR5.1 | PersonaSession "belongs to the identity that was allowed when it was opened", but no rule binds it to that identity. If the Google session expires mid-tab and a different allowlisted account signs in without using the Sign out button, the first account's persona login survives, because only an explicit sign-out clears it. The team accepts that every allowlisted user has full access, so the impact is low. | Either record the identity email (never logged) with the persona login and clear on mismatch, or record it as an accepted limitation in Assumptions & Open Questions. | New |
| R-06 | Minor | frontend-components.md > Component Hierarchy and Components; dashboard/app.py `_page_header` | The spec does not say which code calls `st.set_page_config` and renders the single h1 on gate screens. In the current code `_page_header()` does both and runs after `embedded.start()`. Streamlit requires `set_page_config` to be the first Streamlit call, so the gate screens (which now run first) need a defined header step. | Add one line saying the shared header helper runs first on every path, so each screen has exactly one h1 (BR4.4). | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| aidlc engine sensor-traceability (functional-design, traceability.json) | pass: true; gaps, orphans, missing and invalid entries all empty | All 27 ACs for US2.5, US4.1-US4.8 and US8.1 are enumerated. AC4.8.2 and AC8.1.1 are Deferred with a stated owner. |
| Manual cross-check: BR ids in traceability.json against rules.md | PASS | Every BR id cited (BR1.1-BR1.5, BR2.1-BR2.3, BR3.1-BR3.7, BR4.1-BR4.7, BR5.1, BR6.1-BR6.3, BR7.1) exists in rules.md. |
| Manual cross-check against C4, C6, C7, the mockups and Q1-Q4 | PASS | Outcomes and reasons match C4. All 10 marker names are used consistently. The five C7 keys match BR2.1. Screen 1, 2 and 5 copy and the "Acting as" caption match the mockups. Q1 A, Q2 A, Q3 A and Q4 B are reflected in W4, BR6.2, BR2.1 and BR3.2. |
| Design-stage check | PASS | No implementation code, only illustrative workflows and rule logic. |

### Summary

The design is traceable and consistent with the contracts, the mockups and the confirmed answers. One Major gap, in sign-out testability (R-01), is worth fixing before the design is approved. The Minor findings are clarifications a developer would otherwise have to guess at; none block implementation.
