# Refined Mockups Questions — Dashboard Hosting Readiness

## Sources

- `ideation/rough-mockups/wireframes.md` and `user-flow.md`, including the rough-mockups review findings R-01 to R-04 carried forward
- `inception/user-stories/stories.md` (US3.3, US4.1–US4.8, US5.1, US6.1) and the designer's contribution
- `inception/requirements-analysis/requirements.md`; `memory/team.md`

Already settled, so not asked again: which screens exist and where each element sits, the refusal and failure wording, desktop first, text not colour alone, and a way out on every screen.

## Q1. What should the reset banner say?

A. "Demo data: changes you make are reset periodically."
B. "This is a demo. Data resets whenever the app restarts or is redeployed, so don't enter anything you need to keep."
C. "Demo data resets on restart."
X. Other (please specify)

[Answer]: A

## Q2. How should the signed-in account be told apart from the persona you act as (rough-mockups finding R-02)?

A. Two labelled sidebar sections: "Account" (your email, Sign out) and "Demo persona" (the existing persona login), separated by a divider
B. Keep one block, but rename the persona login to "Act as persona"
C. Both: the two labelled sections, and the persona login renamed "Act as persona"
X. Other (please specify)

[Answer]: A

## Q3. What does the sign-in button say?

A. "Sign in with Google"
B. "Sign in"
X. Other (please specify)

[Answer]: A

## Q4. How is the build identifier shown?

A. Short form: "Build abc1234" (first 7 characters of the commit), or "Build src-1a2b3c4d" when it's a source fingerprint
B. The full commit SHA or fingerprint
X. Other (please specify)

[Answer]: A

## Q5. Should the app show which environment it is (rough-mockups finding R-03)?

Only the staging app exists in this work.

A. Not now: revisit when the production app is created in the parked deploy work
B. Yes: show "Staging" next to the build caption, taken from the app's settings
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Reset banner (Q1): "Demo data: changes you make are reset periodically."
- Account versus persona (Q2): two labelled sidebar sections, "Account" (your email and Sign out) and "Demo persona" (the existing persona login), separated by a divider.
- Sign-in button (Q3): "Sign in with Google".
- Build identifier (Q4): the short form, "Build abc1234" (the first 7 characters of the commit), or "Build src-1a2b3c4d" when it's a source fingerprint.
- Environment label (Q5): not now; revisit when the production app is created in the parked deploy work.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
