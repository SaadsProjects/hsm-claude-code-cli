# User Stories Plan and Questions — Dashboard Hosting Readiness

## Sources

- `inception/requirements-analysis/requirements.md` (FR1–FR10, NFR1–NFR7) and its accepted review findings R-01 to R-06
- `ideation/rough-mockups/wireframes.md` and `user-flow.md`
- `aidlc/spaces/default/codekb/hsm-claude-code-cli/business-overview.md`, `component-inventory.md`
- `memory/team.md` (Testing Posture: test-first, Given/When/Then-friendly)

## Story Plan

- **Format:** "As a [persona], I want [goal], so that [benefit]", with INVEST checks, IDs `US{group}.{seq}`, and Given/When/Then acceptance criteria with IDs `AC{group}.{seq}.{n}`.
- **Priority:** MoSCoW. Every capability is a Must (scope Q1/Q8). Build identifier, reset banner and post-deploy check rank lower within Must, which orders the work but drops nothing.
- **Mob:** after the draft, the designer (experience), developer (implementability and sizing) and quality engineer (testability) each review it separately.

## Q1. Which personas should the stories use?

A. Three: you as owner and developer; an allowlisted viewer; a visitor who is refused
B. Two: you as owner and developer; any other visitor (allowed or refused)
C. Only you
X. Other (please specify)

[Answer]: B

## Q2. How should the stories be grouped?

A. By requirement area (one group per FR1–FR10)
B. By journey: signing in, using the dashboard, being refused, things failing, plus a developer-tooling group and a deploy group
C. By delivery chunk: what ships in the first pull request, then the rest
X. Other (please specify)

[Answer]: A

## Q3. How should developer-facing behaviour (every tool refusing to run without the secret) be written?

A. As stories for you as developer ("As the developer, I want the hook to deny when the secret is missing, so that…")
B. As acceptance criteria inside a few broader stories
X. Other (please specify)

[Answer]: A

## Q4. How small should stories be?

A. Small: one story per behaviour, about 20–30 stories
B. Medium: one story per capability with several criteria, about 10–14 stories
X. Other (please specify)

[Answer]: A

## Q5. Should the acceptance criteria close the requirements review's missing pass conditions (finding R-03)?

R-03 found no observable pass condition for: the secrets bridge, the `.gitignore` lines, the backend-failure screen, refusal logging, the build-ID fallback, staging "created", and the docs updates.

A. Yes: each of those gets an observable acceptance criterion in its story
B. No: leave them as accepted risk
X. Other (please specify)

[Answer]: A

## Q6. Mob follow-up: how does the post-deploy check confirm the build without signing in?

All three reviewers found that the check (US7.1) must confirm the running build, but the build identifier is shown only to signed-in, allowed visitors (US5.1), and the check may never sign in (rule F1). The designer and developer recommend option A.

A. Show the small build caption before sign-in too (on the sign-in, refusal and backend-failure screens), as non-focusable text the check reads through `dashboard/markers.py`; update Screen 1 in Refined Mockups
B. Put a non-visual marker (hidden from visitors) on the sign-in screen that only the check reads
C. Drop the build assertion from the check; it only confirms that the app answers and refuses visitors who aren't signed in
X. Other (please specify)

[Answer]: C

## Consolidated Summary Confirmation

- Personas (Q1): two. You as owner and developer, and any other visitor, whether allowed or refused.
- Grouping (Q2): by requirement area, one story group per FR1 to FR10.
- Developer-facing behaviour (Q3): written as developer stories (for example, the hook denying when the secret is missing).
- Size (Q4): small, one story per behaviour, about 20 to 30 stories.
- Pass conditions (Q5): the acceptance criteria give each requirement flagged in review finding R-03 an observable pass condition.
- Post-deploy check and the build (Q6, mob follow-up): the check no longer asserts the build. It confirms only that the app answers and refuses visitors who aren't signed in. The build identifier stays visible only to signed-in, allowed visitors. This narrows requirement FR7.1 and FR7.2, which named an expected build. Confirming the build on staging (US9.1) becomes the owner reading the sidebar caption after signing in.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
