# External Dependency Map — Dashboard Hosting Readiness

## Sources

- Feasibility Q1/Q8 (outside systems: Streamlit Cloud secrets, GitHub Actions CI); requirements Q1 (Google)
- `bolt-plan.md`; `inception/contract-design/contract-summary.md` C7 and C9
- Delivery Q3

A **Bolt** is one build pass over a piece of the work, ending in something that runs and is checked. Every dependency below is something you control; no other team is involved.

| Dependency | Owner | Lead time | Needed by | If it slips |
|------------|-------|-----------|-----------|-------------|
| GitHub Actions CI with the 10 required checks | You (repository) | Already in place | Every Bolt | Nothing can merge; fix CI first |
| Google OAuth client for local use | You (Google Cloud console) | About 15 minutes | B3 (try a real sign-in; delivery Q3) | B3 finishes on the test stand-in alone, and risk R1 moves to B6 |
| Playwright's Chromium download in CI | Playwright and Microsoft's CDN | Minutes; cached after the first run | B4 | The browser-tests job fails; retry, or wait for the CDN |
| Streamlit Community Cloud account and app slot (free tier) | You | Minutes | B6 | Staging is delayed; nothing else is affected |
| Google OAuth client for staging, with its redirect URI | You (Google Cloud console) | About 15 minutes, after the staging URL exists | B6 | Staging sign-in fails closed (Screen 5) until it is set |

## Assumptions & Open Questions

None.
