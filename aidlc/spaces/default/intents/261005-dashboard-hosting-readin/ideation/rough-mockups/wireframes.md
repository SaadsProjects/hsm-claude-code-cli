# Wireframes — Dashboard Hosting Readiness

## Sources

- Answers Q1–Q7 in `ideation/rough-mockups/rough-mockups-questions.md`
- Scope document and intent backlog: `ideation/scope-definition/`
- Current dashboard layout: `dashboard/app.py`

Low fidelity: boxes and labels only. Only the screens this work adds or changes are shown; the existing tabs are unchanged.

## Screen 1 — Signed out (Q1)

```
+--------------------------------------------------------------+
|                                                              |
|   HSM labor & inventory                                      |
|                                                              |
|   Access to this demo is by invitation.                      |
|                                                              |
|   [ Sign in ]                                                |
|                                                              |
+--------------------------------------------------------------+
```

- No sidebar content, no tabs, no data. Nothing from the dashboard loads before sign-in.
- States: the only state is the default. A sign-in that is cancelled or fails returns here.
- Accessibility: the title is the h1; the main landmark holds the text and the button; keyboard entry is the "Sign in" button (first focusable element).

## Screen 2 — Signed in but not allowed (Q2)

```
+--------------------------------------------------------------+
|                                                              |
|   HSM labor & inventory                                      |
|                                                              |
|   This account doesn't have access.                          |
|   Signed in as: someone@example.com                          |
|                                                              |
|   [ Sign out ]                                               |
|                                                              |
+--------------------------------------------------------------+
```

- Shown for an email not on the allowlist and for an email that isn't verified. The wording is the same for both, so the screen reveals nothing about who is allowed.
- No dashboard content loads.
- Accessibility: the title is the h1; the refusal is plain text (not colour alone); keyboard entry is the "Sign out" button.

## Screen 3 — Signed in and allowed (Q3, Q4, Q5)

```
+--------------------+-----------------------------------------+
| SIDEBAR            | HSM labor & inventory                   |
|                    |                                         |
| Signed in as       | +-------------------------------------+ |
| you@example.com    | | (i) Demo data: changes you make     | |
| [ Sign out ]       | |     are reset periodically.         | |
| ------------------ | +-------------------------------------+ |
| Persona login      |                                         |
| (existing)         | Site name · site_id · jurisdiction · tz |
| Site picker        |                                         |
| (existing)         | [Overview][Labor][Inventory]            |
|                    | [Manage data][Audit]                    |
| ...                |                                         |
| Backend: local ·   |   (existing tab content, unchanged)     |
|   cached Ns        |                                         |
| Build: <id>        |                                         |
+--------------------+-----------------------------------------+
```

- **Signed-in block (Q5):** the email and "Sign out" at the top of the sidebar, above the existing persona login. The persona picker stays a selector inside the signed-in app.
- **Reset banner (Q3):** a slim notice at the top of the main area, above the tabs, on every page and always visible. It carries an info icon and text, so it doesn't rely on colour.
- **Build identifier (Q4):** a small caption at the bottom of the sidebar, next to the existing backend caption.
- The banner text above is a placeholder. The final wording is settled in Refined Mockups.
- Accessibility: the title is the h1; the sidebar is navigation and the tabs area is main; keyboard entry is "Sign out" in the sidebar, then the persona login.

## Screen 4 — Backend failed to start (Q6)

```
+--------------------------------------------------------------+
|                                                              |
|   HSM labor & inventory                                      |
|                                                              |
|   The demo backend didn't start.                             |
|   Reload the page or try again later.                        |
|                                                              |
+--------------------------------------------------------------+
```

- Shown to a signed-in, allowed visitor when the in-process backend isn't running. There are no technical details: no error type, stack trace or address.
- The "Sign out" block stays in the sidebar, so the visitor isn't trapped.
- Accessibility: the title is the h1; the message is plain text in the main landmark.

## Devices and Accessibility (Q7)

- Desktop browsers first. Phones get Streamlit's default layout.
- Streamlit's built-in accessibility is kept. The banner, the refusal and the error states all use text, not colour alone.

## Assumptions & Open Questions

None.
