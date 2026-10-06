# Personas — Dashboard Hosting Readiness

## Sources

- `user-stories-questions.md` Q1 (two personas)
- Intent capture Q2, Q5, Q6 (you are the sole owner, builder and approver)
- `ideation/rough-mockups/wireframes.md` (screens seen by visitors)
- `memory/team.md` Deployment (allowlist kept by the repository owner)

## P1 — Saad, owner and developer

- **Role:** owns the repository, builds and reviews every change, keeps the allowlist, creates the staging app, and approves releases.
- **Goals:**
  - unblock the parked deploy work by making the dashboard safe to host;
  - keep every gate (CI, the hooks, sign-in) failing closed;
  - see at a glance which build is running.
- **Pain points:**
  - the burned secret sits in a public repository;
  - nothing stops anyone from picking any persona;
  - a crashed hook fails open;
  - the backend can't run as a separate process on Streamlit Cloud.
- **Tech comfort:** high (feasibility Q3).
- **Frequency:** daily while this work runs.
- **Appears in stories as:** "the owner" (operating and hosting) or "the developer" (local tooling, tests and CI).

## P2 — Visitor

- **Role:** anyone who opens the hosted app's address. This persona covers two cases:
  - **allowed visitor:** signed in with Google, verified email, on the allowlist; uses the demo dashboard and may pick any persona inside it;
  - **refused visitor:** not signed in, unverified, or not on the allowlist; must see nothing of the dashboard.
- **Goals:**
  - (allowed) use the demo without setup, and know the data is demo data that resets;
  - (refused) understand they have no access, and leave cleanly.
- **Pain points:** confusing errors, dead-end screens.
- **Tech comfort:** medium.
- **Frequency:** occasional.

## Priority

P1 is primary: every change serves the owner's goal of hosting safely. P2 is the audience the sign-in gate protects and serves.

## Assumptions & Open Questions

None.
