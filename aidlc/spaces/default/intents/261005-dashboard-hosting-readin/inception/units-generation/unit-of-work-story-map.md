# Unit-to-Story Map — Dashboard Hosting Readiness

## Sources

- `inception/user-stories/stories.md`; `unit-of-work.md`

## Story Map

| Story | Title | Unit | Directory |
|-------|-------|------|-----------|
| US1.1 | Secret read when used, not at import | U1 | u1-secret-fail-closed |
| US1.2 | Missing or short secret refused clearly | U1 | u1-secret-fail-closed |
| US1.3 | Burned secret gone in one commit | U1 | u1-secret-fail-closed |
| US1.4 | Tests bring their own secret | U1 | u1-secret-fail-closed |
| US2.1 | Dev-secret script | U1 | u1-secret-fail-closed |
| US2.2 | Backend refuses to start without a secret | U1 | u1-secret-fail-closed |
| US2.3 | Publish hook denies without a secret | U1 | u1-secret-fail-closed |
| US2.4 | MCP tools report a missing secret | U1 | u1-secret-fail-closed |
| US2.6 | Secret files never committed | U1 | u1-secret-fail-closed |
| US8.4 | Reasons on broad catches | U1 | u1-secret-fail-closed |
| US3.1 | Dashboard runs with its own backend | U2 | u2-embedded-backend |
| US3.2 | Only one backend per process | U2 | u2-embedded-backend |
| US3.3 | Backend failure is explained plainly | U2 | u2-embedded-backend |
| US3.4 | Separate backend still works for local tools | U2 | u2-embedded-backend |
| US2.5 | Hosted secrets reach the app | U3 | u3-sign-in-gate |
| US4.1 | Nothing shows before sign-in | U3 | u3-sign-in-gate |
| US4.2 | Allowed visitor gets in with Google | U3 | u3-sign-in-gate |
| US4.3 | Refused visitor sees a neutral refusal | U3 | u3-sign-in-gate |
| US4.4 | Gate fails closed | U3 | u3-sign-in-gate |
| US4.5 | Decision is a pure, tested function | U3 | u3-sign-in-gate |
| US4.6 | Signed-in block in the sidebar | U3 | u3-sign-in-gate |
| US4.7 | Refusals logged without the email | U3 | u3-sign-in-gate |
| US4.8 | Existing dashboard tests run through the gate | U3 | u3-sign-in-gate |
| US8.1 | New packages through the locks | U3 | u3-sign-in-gate |
| US5.1 | See which build is running | U4 | u4-build-and-banner |
| US5.2 | Fingerprint fallback without git | U4 | u4-build-and-banner |
| US6.1 | Reset notice above the tabs | U4 | u4-build-and-banner |
| US7.1 | Check a deployed app by hand | U5 | u5-postdeploy-check |
| US7.2 | Check fails loudly | U5 | u5-postdeploy-check |
| US7.3 | Check never signs in or writes | U5 | u5-postdeploy-check |
| US7.4 | Run the check from GitHub | U5 | u5-postdeploy-check |
| US8.2 | Browser tests run locally against a fake identity | U5 | u5-postdeploy-check |
| US8.3 | Browser check can't pass without testing | U5 | u5-postdeploy-check |
| US9.1 | Staging app created and proven | U6 | u6-staging-app |
| US10.1 | Docs match the new setup | U1 | u1-secret-fail-closed |

## Cross-Cutting Stories

- **US10.1 (docs):** owned by U1, which writes the secret-setup docs. U2, U3 and U5 each update the docs for their own change (start command, sign-in, the check) in the same pull request (AC10.1.3).
- **US8.1 (Authlib and Playwright):** owned by U3 for Authlib in the runtime lock. U5 adds Playwright to the dev lock under US8.2.
- **US3.3 (Screen 4):** built in U2. Its "Sign out" criterion (AC3.3.2) passes once U3 lands.

## Implementation Order Within Each Unit

- **U1:** US1.4 → US1.1 → US1.2 → US2.3 (deny test first) → US2.4 → US2.2 → US2.1 → US2.6 → US8.4 → US10.1 (secret setup) → US1.3 (the literal goes last, M1).
- **U2:** US3.1 → US3.2 → US3.4 → US3.3.
- **U3:** US8.1 → US4.5 → US2.5 → US4.4 → US4.1 → US4.2 → US4.3 → US4.6 → US4.7 → US4.8.
- **U4:** US5.2 → US5.1 → US6.1.
- **U5:** US7.1 → US7.3 → US7.2 → US8.2 → US8.3 → US7.4.
- **U6:** US9.1.

## Coverage Verification

- Stories: 35. Every story is assigned to exactly one owning unit.
- Units: 6. Every unit has at least one story (U1 11, U2 4, U3 10, U4 3, U5 6, U6 1).

## Assumptions & Open Questions

None.
