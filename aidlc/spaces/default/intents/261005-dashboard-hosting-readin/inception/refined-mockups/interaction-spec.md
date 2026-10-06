# Interaction Specification — Dashboard Hosting Readiness

## Sources

- `mockups.md` (Screens 1–5); `stories.md` (US3.3, US4.1–US4.8, US5.1, US6.1, US7.1)
- `.claude/knowledge/aidlc-design-agent/component-spec-template.md` (format)
- Answers Q1–Q5 in `refined-mockups-questions.md`

## Flow and State Rules

1. The gate runs first on every rerun. Until it allows, only Screen 1, 2 or 5 renders, and no backend call happens (US4.1).
2. Gate outcomes:
   - not signed in → Screen 1;
   - signed in but refused (unverified or not listed) → Screen 2;
   - settings missing, broken or erroring → Screen 5;
   - allowed → continue.
3. After the gate allows, the in-process backend is started or reused: not running → Screen 4; running → Screen 3.
4. "Sign out" (Screens 2, 3, 4 and 5 when signed in) clears the Demo persona session as well as the sign-in, then shows Screen 1 (AC4.6.2, AC4.6.3).
5. "Sign in with Google" goes through the identity seam to `st.login("google")`. Cancelling at Google returns to Screen 1 (AC4.1.3).

## SignInScreen

| Field | Value |
|---|---|
| Component | SignInScreen |
| Description | The only content shown to a visitor who isn't signed in |
| Category | layout |

### States

| State | Description | Trigger |
|---|---|---|
| default | Title, invitation line, "Sign in with Google" | No identity |
| focus | Button focused | Tab key |
| loading | Streamlit's redirect to Google | Button activated |

### Props / Inputs

| Prop | Type | Required | Default | Description |
|---|---|---|---|---|
| on_sign_in | callable | yes | the seam's `sign_in` | Starts Google sign-in |

### Accessibility

| Requirement | Implementation |
|---|---|
| ARIA role | Native button (Streamlit `st.button`) |
| Keyboard interaction | Tab to focus, Enter or Space to activate |
| Label / aria-label | Visible text "Sign in with Google" |
| Contrast ratio | Streamlit default theme (WCAG AA) |
| Screen reader | Reads h1, then the invitation line, then the button |
| Focus management | First focusable element on the page |

## RefusalScreen

| Field | Value |
|---|---|
| Component | RefusalScreen |
| Description | Neutral "no access" for a signed-in visitor the gate refuses |
| Category | feedback |

### States

| State | Description | Trigger |
|---|---|---|
| default | Refusal line, "Signed in as: {email}", "Sign out" | Gate refuses for the visitor's reason |
| error | Not used; gate errors go to SignInUnavailableScreen | — |

### Props / Inputs

| Prop | Type | Required | Default | Description |
|---|---|---|---|---|
| email | string | yes | — | Shown as literal text (markup not rendered) |
| on_sign_out | callable | yes | the seam's `sign_out` | Clears sign-in and persona session |

### Accessibility

| Requirement | Implementation |
|---|---|
| Keyboard interaction | Tab to "Sign out", Enter activates |
| Screen reader | Plain text; no colour-only signal |
| Focus management | "Sign out" is the only focusable control |

## SignInUnavailableScreen

| Field | Value |
|---|---|
| Component | SignInUnavailableScreen |
| Description | Shown when the gate's own settings or code fail |
| Category | feedback |

### States

| State | Description | Trigger |
|---|---|---|
| default | "Sign-in isn't available right now. Reload the page or try again later." | Missing or broken settings, empty or malformed allowlist, gate error |
| signed-in | Adds "Sign out" | An identity is present |

### Accessibility

| Requirement | Implementation |
|---|---|
| Keyboard interaction | Tab to "Sign out" when shown |
| Screen reader | Plain text; no technical details |

## AccountSection

| Field | Value |
|---|---|
| Component | AccountSection |
| Description | Top sidebar section for the signed-in account (Q2) |
| Category | navigation |

### States

| State | Description | Trigger |
|---|---|---|
| default | h3 "Account", email, "Sign out" | Gate allows |
| backend-failed | Same; shown with Screen 4 | Backend not running |

### Accessibility

| Requirement | Implementation |
|---|---|
| Label | Visible heading "Account" |
| Keyboard interaction | "Sign out" reachable by Tab before the persona login |

## DemoPersonaSection

| Field | Value |
|---|---|
| Component | DemoPersonaSection |
| Description | The existing persona login and site picker under the heading "Demo persona" (Q2); the caption reads "Acting as {name} ({persona})" |
| Category | input |

### States

| State | Description | Trigger |
|---|---|---|
| default | Existing behaviour | Gate allows and backend running |
| cleared | No persona selected | After "Sign out" (AC4.6.3) |
| hidden | Not rendered | Screens 1, 2, 4 and 5 |

## ResetBanner

| Field | Value |
|---|---|
| Component | ResetBanner |
| Description | "Demo data: changes you make are reset periodically." (Q1) |
| Category | feedback |

### States

| State | Description | Trigger |
|---|---|---|
| default | Info notice with an icon, above the tabs | Screen 3 |
| hidden | Not rendered | Screens 1, 2, 4 and 5 |

### Accessibility

| Requirement | Implementation |
|---|---|
| Contrast ratio | Streamlit `st.info` (WCAG AA) |
| Screen reader | Read as text; the icon is decorative |
| Non-colour cue | Info icon plus the words "Demo data" |

## BuildCaption

| Field | Value |
|---|---|
| Component | BuildCaption |
| Description | "Build abc1234", or "Build src-1a2b3c4d" for a fingerprint (Q4) |
| Category | display |

### States

| State | Description | Trigger |
|---|---|---|
| git | First 7 characters of the commit SHA | `.git` present |
| fingerprint | "src-" plus the first 8 characters of the fingerprint | No `.git` |
| hidden | Not rendered | Screens 1, 2 and 5 |

### Accessibility

| Requirement | Implementation |
|---|---|
| ARIA role | Plain caption text, not focusable |

## BackendFailureScreen

| Field | Value |
|---|---|
| Component | BackendFailureScreen |
| Description | "The demo backend didn't start. Reload the page or try again later." |
| Category | feedback |

### States

| State | Description | Trigger |
|---|---|---|
| default | Message in main; Account section and build caption in sidebar | Backend start failed |

### Accessibility

| Requirement | Implementation |
|---|---|
| Keyboard interaction | Tab reaches "Sign out" in the sidebar |
| Screen reader | Plain text; no error details |

## Assumptions & Open Questions

None.
