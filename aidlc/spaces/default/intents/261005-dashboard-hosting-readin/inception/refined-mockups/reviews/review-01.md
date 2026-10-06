## Review

**Verdict:** READY
**Reviewer:** aidlc-product-lead-agent
**Date:** 2026-10-05T12:27:49Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/refined-mockups/mockups.md > Screen 1 (button copy "Sign in with Google", Q3) vs aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/user-stories/stories.md > AC4.1.1, AC4.1.5 | The approved copy is "Sign in with Google" (Q3), but AC4.1.1 and AC4.1.5 still say a "Sign in" button. A test written from the stories and one written from the mockup would assert different labels. | Before Code Generation, align AC4.1.1 and AC4.1.5 to "Sign in with Google", or state that tests match on the marker and not on the label. | New |
| R-02 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/refined-mockups/mockups.md > Screen 3 and interaction-spec.md > AccountSection vs stories.md > AC4.6.1 | AC4.6.1 says the sidebar's first element shows the email and "Sign out". The refined design puts an "Account" h3 heading first (Q2). Strictly read, the AC fails against the design. Q2 also puts the "Demo persona" heading and divider in the sidebar, which no story criterion covers. | Reword AC4.6.1 to "the first sidebar section, headed Account". Add a criterion for the "Demo persona" heading and the divider. | New |
| R-03 | Minor | mockups.md > Screen 1 > Markers; interaction-spec.md; design-system-mapping.md | Only `markers.SIGN_IN_SCREEN` and `markers.BUILD_CAPTION` are named. The post-deploy check must tell the sign-in screen from the refusal and sign-in-unavailable screens, and Screens 2, 4 and 5 get no marker. | State whether Screens 2, 4 and 5 carry markers. If not, say the check relies only on the sign-in marker. | New |
| R-04 | Minor | accessibility-checklist.md > A1; stories.md > AC4.1.4 | A1 claims an h1 test on Screens 1–5, but AC4.1.4 covers only the sign-in, refusal and backend-failure screens. Screen 5 has no testable criterion. | Extend AC4.1.4 to Screen 5, or limit A1's scope. | New |
| R-05 | Minor | accessibility-checklist.md > A11 | The 200% zoom check is "manual check before the staging app is created". It has no owner, no pass criterion and no record of the result. | Name who runs it and what passing means (for example no clipped controls or horizontal scroll on Screens 1 and 3), and where the result is recorded. | New |
| R-06 | Minor | mockups.md > Screen 3 | The existing unsaved-write banner (`dashboard/app.py` around line 402, drawn above the tabs) is not placed relative to the new reset banner. The vertical order and the combined behaviour are unspecified. | Say which banner is on top and whether both can show at once. | New |
| R-07 | Minor | mockups.md > Sources, Screen 3 (Q5) | The Sources section lists rough-mockups findings R-01 to R-04. The mockup closes R-01 and R-02 explicitly and defers R-03 (environment label, Q5). R-04 is not mentioned. | State R-04's disposition (closed, deferred or dropped). | New |

### Summary

The package is implementable. Five screens cover the stories, each has real copy, states and a way out, and the interaction spec follows the component template. No Critical findings. R-01 and R-02 are Major wording conflicts between the approved mockup and the story criteria, and each has a clear workaround. Fix both before Construction so tests are not written against conflicting strings. The rest are minor.
