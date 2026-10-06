# Refined Mockups — Dashboard Hosting Readiness

## Sources

- Rough mockups: `ideation/rough-mockups/wireframes.md` (Screens 1–4), `user-flow.md`, review findings R-01 to R-04 carried forward
- User stories: `inception/user-stories/stories.md` (US3.3, US4.1–US4.8, US5.1, US6.1) and the designer's mob contribution
- Requirements: `inception/requirements-analysis/requirements.md` (FR3.4, FR4, FR5.2, FR6, NFR5)
- Answers Q1–Q5 in `refined-mockups-questions.md`
- Current layout: `dashboard/app.py` (title, sidebar with the persona login and site picker, backend caption, five tabs)

Mid fidelity, with the real copy. Five screens: the four from the rough mockups, plus Screen 5 for when sign-in itself is unavailable (US4.4, AC4.4.3). The existing tab content is unchanged and not redrawn.

## Screen 1 — Signed out (US4.1, AC4.1.1–AC4.1.5)

```
+----------------------------------------------------------------+
|  HSM labor & inventory                                     (h1)|
|                                                                |
|  Access to this demo is by invitation.                         |
|                                                                |
|  [ Sign in with Google ]                                       |
|                                                                |
+----------------------------------------------------------------+
```

- **Copy:** title "HSM labor & inventory"; body "Access to this demo is by invitation."; button "Sign in with Google" (Q3).
- **Hidden:** the sidebar content, the tabs, the persona login and the site picker. No backend call is made.
- **States:** default only. A cancelled or failed Google sign-in, or an ended session, returns here (AC4.1.3).
- **Markers:** the screen carries the `markers.SIGN_IN_SCREEN` marker that the post-deploy check reads (US7.1).

## Screen 2 — Signed in but not allowed (US4.3, AC4.3.1–AC4.3.3)

```
+----------------------------------------------------------------+
|  HSM labor & inventory                                     (h1)|
|                                                                |
|  This account doesn't have access.                             |
|  Signed in as: someone@example.com                             |
|                                                                |
|  [ Sign out ]                                                  |
|                                                                |
+----------------------------------------------------------------+
```

- **Copy:** "This account doesn't have access." then "Signed in as: " followed by the email as literal text, so any markup in it is not rendered, then the button "Sign out".
- The wording is the same for every refusal reason (not verified, not on the allowlist). Nothing reveals allowlist content.

## Screen 3 — Signed in and allowed (US4.6, US5.1, US6.1)

```
+--------------------------+-------------------------------------+
| SIDEBAR                  | HSM labor & inventory          (h1) |
|                          |                                     |
| Account           (h3)   | (i) Demo data: changes you make are |
| you@example.com          |     reset periodically.             |
| [ Sign out ]             |                                     |
| ------------------------ | Site name · site_id · GA · tz       |
| Demo persona      (h3)   |                                     |
| (existing persona login) | [Overview][Labor][Inventory]        |
| Acting as Name (Role)    | [Manage data][Audit]                |
| (existing site picker)   |                                     |
|                          |   (existing tab content, unchanged) |
| ...                      |                                     |
| Backend: local · cached  |                                     |
| Build abc1234            |                                     |
+--------------------------+-------------------------------------+
```

- **Account section (Q2):** headed "Account", showing the signed-in email and "Sign out", at the top of the sidebar (AC4.6.1).
- **Divider:** a divider, then the "Demo persona" section (Q2), which holds the existing persona login and site picker, unchanged apart from its heading.
- **Persona caption:** the existing persona caption "Logged in as {name} ({persona})" becomes "Acting as {name} ({persona})". This keeps "signed in" for the account and "acting as" for the persona, which closes rough-mockups finding R-02.
- **Banner (Q1):** "Demo data: changes you make are reset periodically.", rendered once with an info icon above the tabs, so it shows on every tab (AC6.1.1).
- **Build caption (Q4):** at the bottom of the sidebar, under the backend caption: "Build abc1234" (the first 7 characters of the commit), or "Build src-1a2b3c4d" for a source fingerprint. The caption carries the `markers.BUILD_CAPTION` marker.
- **Environment label (Q5):** none for now.

## Screen 4 — Backend didn't start (US3.3, AC3.3.1–AC3.3.3)

```
+--------------------------+-------------------------------------+
| SIDEBAR                  | HSM labor & inventory          (h1) |
|                          |                                     |
| Account           (h3)   | The demo backend didn't start.      |
| you@example.com          | Reload the page or try again later. |
| [ Sign out ]             |                                     |
|                          |                                     |
| Build abc1234            |                                     |
+--------------------------+-------------------------------------+
```

- Shown to a signed-in, allowed visitor when the in-process backend isn't running.
- The sidebar shows only the Account section and the build caption. The Demo persona section, the site picker, the tabs and the banner are hidden, because nothing behind them works.
- No error type, stack trace or address appears. The cause goes to the log.
- The sidebar is now drawn, with "Sign out" as a keyboard-reachable way out. This closes rough-mockups finding R-01.

## Screen 5 — Sign-in unavailable (US4.4, AC4.4.3)

```
+----------------------------------------------------------------+
|  HSM labor & inventory                                     (h1)|
|                                                                |
|  Sign-in isn't available right now.                            |
|  Reload the page or try again later.                           |
|                                                                |
|  [ Sign out ]   (only if someone is signed in)                 |
+----------------------------------------------------------------+
```

- Shown when the gate's own settings are missing or broken, the allowlist is empty or malformed, or the gate errors. This is not the visitor's fault, so it doesn't use the "doesn't have access" wording.
- "Sign out" appears only when an identity is present; otherwise the reload line is the way out.

## Screen-to-Story Map

| Screen | Stories and criteria |
|--------|----------------------|
| 1 Signed out | US4.1 (AC4.1.1–AC4.1.5), US4.2 (AC4.2.2), US7.1 |
| 2 Refused | US4.3 (AC4.3.1–AC4.3.3), US8.2 (AC8.2.3) |
| 3 Allowed | US4.6, US5.1, US6.1, US4.8 |
| 4 Backend failed | US3.3 |
| 5 Sign-in unavailable | US4.4 |

## Responsive Behaviour

Desktop first (NFR5). On phones, Streamlit collapses the sidebar behind its menu button. The banner and the main-area messages stay at the top of the page. No custom breakpoints.

## Assumptions & Open Questions

- [assumption] Renaming the persona caption to "Acting as …" is a designer decision made to settle rough-mockups finding R-02 alongside the two labelled sections (Q2). It changes one existing string.
- The environment label is deferred to the parked deploy work (Q5).
