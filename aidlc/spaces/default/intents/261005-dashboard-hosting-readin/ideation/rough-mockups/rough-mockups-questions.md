# Rough Mockups Questions — Dashboard Hosting Readiness

## Sources

- Intent statement: `ideation/intent-capture/intent-statement.md`
- Scope document and intent backlog: `ideation/scope-definition/`
- Current dashboard layout (`dashboard/app.py`): a title, a sidebar with the persona login and site picker, a backend caption at the bottom of the sidebar, and five tabs (Overview, Labor, Inventory, Manage data, Audit).

The user-facing parts of this work are the sign-in gate, the reset banner, the build identifier, and what a visitor sees if the in-process backend fails.

## Q1. What does a visitor who isn't signed in see first?

A. A sign-in screen: the app title, one line explaining that access is by invitation, and a single "Sign in" button. Nothing else from the dashboard is shown.
B. The dashboard title, with a sign-in button in the sidebar and the main area empty
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q2. What does a signed-in visitor who isn't allowed in see (not on the allowlist, or email not verified)?

A. A plain "This account doesn't have access" message showing the email they signed in with, plus a "Sign out" button. Nothing reveals who is allowed.
B. The same, plus a line saying who to contact for access
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q3. Where does the "demo data resets" banner go?

A. A slim notice at the top of every page, above the tabs, always visible
B. In the sidebar
C. Shown on first visit and dismissible after that
D. Not yet defined
X. Other (please specify)

[Answer]: A

## Q4. Where does the build identifier go?

A. A small caption at the bottom of the sidebar, next to the existing backend caption
B. A footer line at the bottom of the main page
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q5. Once signed in, where do the signed-in email and "Sign out" go, relative to the existing persona login?

The persona picker stays as a selector inside the sign-in layer, not as the sign-in itself.

A. At the top of the sidebar, above the existing persona login
B. At the bottom of the sidebar, with the captions
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q6. What does a visitor see if the in-process backend fails to start?

A. A clear message ("The demo backend didn't start. Reload the page or try again later.") and no technical details
B. The same message plus a short technical reason, such as the error type
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q7. Which devices and accessibility level must this support?

A. Desktop browsers first, with Streamlit's default behaviour on phones. Keep Streamlit's built-in accessibility, and make sure the banner and error states use text, not colour alone.
B. Must also work well on phones, and meet WCAG 2.1 AA explicitly
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Signed out (Q1): a sign-in screen only: the app title, one line saying access is by invitation, and a single "Sign in" button. Nothing from the dashboard is shown.
- Refused (Q2): "This account doesn't have access", the email they signed in with, and a "Sign out" button. Nothing reveals who is allowed.
- Reset banner (Q3): a slim notice at the top of every page, above the tabs, always visible.
- Build identifier (Q4): a small caption at the bottom of the sidebar, next to the backend caption.
- Signed in (Q5): the signed-in email and "Sign out" at the top of the sidebar, above the existing persona login.
- Backend failed to start (Q6): a plain message ("The demo backend didn't start. Reload the page or try again later.") with no technical details.
- Devices and accessibility (Q7): desktop first, Streamlit defaults on phones, Streamlit's built-in accessibility; the banner and error states use text, not colour alone.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
