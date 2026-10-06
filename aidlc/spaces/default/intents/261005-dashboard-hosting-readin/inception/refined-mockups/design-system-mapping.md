# Design System Mapping — Dashboard Hosting Readiness

## Sources

- `mockups.md`, `interaction-spec.md`
- Current dashboard conventions in `dashboard/app.py` (Streamlit default theme; `st.subheader`, `st.caption`, `st.info`, `st.warning`, `st.error`)
- `memory/team.md` Code Style (keep Streamlit calls thin; decisions in plain functions)

The dashboard uses Streamlit's built-in components and default theme; there is no custom design system. New elements reuse the same components the app already uses.

| Element | Streamlit component | Notes |
|---------|---------------------|-------|
| App title (h1) | `st.title` | Already present: "HSM labor & inventory" |
| Invitation, refusal, unavailable and backend-failure messages | `st.markdown` with plain text, escaped | Literal text; the email goes through the existing `escape_md` helper |
| "Sign in with Google", "Sign out" | `st.button` | Labels as specified; actions call the identity seam |
| Account and Demo persona headings (h3) | `st.subheader` inside `st.sidebar` | Matches the existing sidebar style |
| Divider | `st.divider` | Between the Account and Demo persona sections |
| Reset banner | `st.info(..., icon="ℹ️")` | Rendered once before `st.tabs` |
| Build caption | `st.caption` | Placed after the existing backend caption |
| Markers for the check | Stable element keys or labels defined in `dashboard/markers.py` | Shared by the app, the tests and the post-deploy check |

No colours, fonts or spacing are customised.

## Assumptions & Open Questions

None.
