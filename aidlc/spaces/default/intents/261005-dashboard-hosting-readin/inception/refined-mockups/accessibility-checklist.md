# Accessibility Checklist — Dashboard Hosting Readiness

## Sources

- `requirements.md` NFR5; `stories.md` AC4.1.4, AC4.1.5, AC6.1.2
- `mockups.md`, `interaction-spec.md`
- `.claude/knowledge/aidlc-design-agent/accessibility-wcag.md`

Target: Streamlit's built-in accessibility, desktop first, with the specific checks below (NFR5). Rows marked "test" are covered by an automated test named in the stories.

| # | Check | Screens | How it is verified |
|---|-------|---------|--------------------|
| A1 | Exactly one h1 (the app title) | 1–5 | test (AC4.1.4) |
| A2 | Messages stated in text, not colour alone | 1, 2, 4, 5 | test (AC4.1.4) |
| A3 | Banner carries text plus an icon, not colour alone | 3 | test (AC6.1.2) |
| A4 | "Sign in with Google" and "Sign out" reachable by Tab and activated by Enter | 1, 2, 3, 4, 5 | browser test (AC4.1.5) |
| A5 | "Sign out" comes before the persona login in Tab order | 3 | browser test (AC4.1.5 with AC4.6.1) |
| A6 | A way out on every refusal and error screen | 2, 4, 5 | test (AC4.3.3, AC3.3.2, AC4.4.3) |
| A7 | No technical detail on error screens | 4, 5 | test (AC3.3.2, AC4.4.3) |
| A8 | Visible labels on buttons (no icon-only buttons) | all | review |
| A9 | Sidebar sections have headings ("Account", "Demo persona") | 3, 4 | test (AC4.6.1) |
| A10 | Default Streamlit theme contrast (WCAG AA) kept; no custom colours | all | review |
| A11 | Layout works at 200% browser zoom on desktop | 1, 3 | manual check before the staging app is created |

## Assumptions & Open Questions

None.
