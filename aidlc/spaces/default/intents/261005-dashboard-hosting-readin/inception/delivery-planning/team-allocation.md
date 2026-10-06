# Team Allocation — Dashboard Hosting Readiness

## Sources

- Intent capture Q5, Q6 (you are the sole builder, reviewer and approver)
- Team Formation was skipped (solo developer)
- `bolt-plan.md`

A **Bolt** is one build pass over a piece of the work, ending in something that runs and is checked. A **mob** is the group that builds a Bolt together.

Team Formation was skipped, so there are no teams to allocate. Every Bolt is built by the developer agent (AI) in this session. You review and approve each one, and you take the manual steps.

| Bolt | Unit | Built by | Your manual steps |
|------|------|----------|-------------------|
| B1 | U1 secret-fail-closed | developer agent | Review and merge pull request 1 |
| B2 | U2 embedded-backend | developer agent | Review the draft pull request |
| B3 | U3 sign-in-gate | developer agent | Create a local Google OAuth client; try a real sign-in |
| B4 | U5 postdeploy-check | developer agent | Review the browser-tests run |
| B5 | U4 build-and-banner | developer agent | Mark the U2–U5 pull request ready and merge it |
| B6 | U6 staging-app | you (console), helped by the developer agent | Create the staging app and enter its secrets; run the check; sign in and confirm the build |

There is a single team, so no cross-team board is needed.

## Assumptions & Open Questions

None.
