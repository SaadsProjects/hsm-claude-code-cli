**Collaborator:** aidlc-design-agent

## Contribution

Review focus: user experience and persona fidelity in the stories a visitor sees (US3.3, US4.1–US4.7, US5.1, US6.1, and US7.1 where it depends on what a signed-out visitor sees). I checked them against `ideation/rough-mockups/wireframes.md` (Screens 1–4), `ideation/rough-mockups/user-flow.md`, the rough-mockups review findings R-01 to R-04, NFR5, and the project correction "Every error or refusal screen in the dashboard keeps a way out (Sign out or reload)".

### What already matches the wireframes

- **Screen 1 (signed out):** AC4.1.1 and AC4.1.2 match it: the title, "Access to this demo is by invitation.", "Sign in", and nothing from the dashboard.
- **Screen 2 (refused):** AC4.3.3 matches it: "This account doesn't have access", the signed-in email, "Sign out", the same wording for every reason, and no allowlist content. Together with AC4.7.2 (no email in the log), nothing about who is allowed leaks.
- **Screen 3 (allowed):**
  - the signed-in block is first in the sidebar (AC4.6.1);
  - the reset notice sits above the tabs, with text and an icon (AC6.1.1, AC6.1.2);
  - the build caption sits next to the backend caption (AC5.1.2).
- **Screen 4 (backend failure):** AC3.3.1 and AC3.3.2 match it: the exact plain message, "Sign out" still present, and no error type, stack trace or address.

### Gaps and proposed acceptance criteria (for the lead to integrate)

**G1. Signed-out visitors can't see the build, but the post-deploy check needs it (US5.1, US7.1, FR5.2, FR7.1).**

- AC7.1.1 has the check confirm the build while not signed in, and F1 forbids it from signing in.
- AC5.1.2 and wireframe Screen 3 show the build caption only to an allowed visitor. Screen 1 shows no build at all.
- As written, US7.1 can't pass. The owner needs to decide one of these:
  - **(a) Recommended:** show a small, muted "Build: `<id>`" caption at the bottom of Screens 1, 2 and 4 as well as Screen 3. It is text only, isn't focusable, and comes after the action button in reading order, so the keyboard entry point doesn't move. The repository is public, so a commit SHA or source fingerprint reveals nothing new.
  - **(b)** Expose the build through a non-visual marker (from `dashboard/markers.py`) on the sign-in screen only.
- Either way, Refined Mockups has to update Screen 1. Proposed AC (option a):
  - **AC5.1.3** Given a visitor who isn't signed in, when the sign-in screen renders, then it shows the build identifier as a caption below the "Sign in" button, and still shows no tab, persona picker or backend data.

**G2. The fail-closed refusal screen isn't specified, and has no defined way out (US4.4, FR4.5, project correction).**

- AC4.4.1 and AC4.4.2 say the gate "refuses", but not what the visitor sees.
- Missing sign-in settings can leave no signed-in user, so Screen 2 ("Signed in as …", "Sign out") may not apply, and a "Sign in" button that can't work would be a dead end. Proposed:
  - **AC4.4.4** Given any fail-closed refusal (missing or broken sign-in settings, an empty or malformed allowlist, or a gate error), when the screen renders, then it shows no tab, no persona picker and no technical detail. It shows Screen 2's neutral wording when a visitor is signed in, and otherwise a plain line such as "Sign-in isn't available right now. Reload the page or try again later."
  - **AC4.4.5** Given the same refusals, when the screen renders, then it offers a way out: "Sign out" when a visitor is signed in, or the reload instruction when none is.
- Refined Mockups settles the exact wording. The origin is FR4.5 plus the project correction above, so this adds no new requirement.

**G3. Signing out must also drop the persona session (US4.6).**

- The persona login keeps its own session inside the app. If "Sign out" clears only the Google sign-in, the next account to sign in on the same browser tab could inherit the previous persona. That would confuse the visitor and quietly weaken the gate.
- **AC4.6.3** Given an allowed visitor who has picked a persona, when they choose "Sign out" and a different allowed account signs in, then no persona is selected and the persona login starts empty.

**G4. A cancelled sign-in and an ended session aren't covered (US4.1, user-flow error paths, mockups R-03).**

- **AC4.1.3** Given a visitor who starts sign-in and cancels it, or whose sign-in fails, when they return to the app, then the sign-in screen (AC4.1.1) shows, with no error detail.
- **AC4.1.4** Given a visitor whose sign-in has ended (cookie expired or cleared) while a dashboard tab is open, when the app next reruns, then the sign-in screen shows and no tab or persona picker renders.

**G5. NFR5 accessibility has almost no story-level pass condition (US3.3, US4.1, US4.3, US4.4).**

- Only AC6.1.2 tests NFR5 today. Proposed cross-cutting criteria, each testable with `AppTest` or the existing browser test:
  - **AC4.1.5** Given each of the sign-in, refusal and backend-failure screens, when it renders, then the app title is the only level-1 heading (`st.title`), and the message is plain text. If an alert element is used, it carries text and an icon, so colour alone says nothing.
  - **AC4.1.6** Given the sign-in screen in a real browser, when the visitor moves with Tab, then "Sign in" receives visible focus and Enter starts sign-in. The same holds for "Sign out" on the refusal screen and in the sidebar on the backend-failure screen (mockups R-01).

**G6. The signed-in email must be shown as literal text (US4.3, US4.6).**

- The email comes from the identity provider, so the app should treat it as untrusted text.
- **AC4.3.4** Given a signed-in email that contains Markdown or HTML characters, when the refusal screen or the sidebar block renders it, then it appears literally and isn't interpreted, using the existing `dashboard/safe_text.py` helpers or a plain-text element.

**G7. What renders on Screen 4 (US3.3).**

- Add to AC3.3.1 that the persona login and site picker don't render either, because both lead to controls that would fail without a backend.
- Under G1(a), the build caption still shows, which helps the owner see which build failed to start.

### Persona fidelity

- **US3.1:** this is written for "a visitor" with the benefit "so that the hosted app works on a single-process host". That benefit belongs to the owner (P1). Either reword it as "As the owner, …", or give the visitor's benefit: "so that the demo works as soon as I open it".
- **Everything else:** the stories use P2's two cases faithfully. "a visitor who isn't signed in", "a refused visitor" and "an allowed visitor" line up with the persona's allowed and refused split, and with the "dead-end screens" pain point.

### Carry-overs to Refined Mockups (no story change needed)

- **Mockups R-02, telling the two identities apart:** the signed-in block reads "Signed in as" and the persona section keeps a distinct heading, such as "Demo persona". AC4.6.1 can then check both labels.
- **Mockups R-03, environment label:** not needed now, because only staging exists and production is out of scope. Revisit it in the parked deploy intent.
- **"Sign in" button label:** consider "Sign in with Google", which tells the visitor what to expect before the redirect. The wireframe says "Sign in", so this is the owner's call.
- **Reset-banner wording:** already listed as an open question in the requirements.

## Positions

- OBJECT: US5.1 / AC5.1.2 with US7.1 / AC7.1.1: the build identifier shows only to allowed visitors, but the check must read it without signing in (F1). Add AC5.1.3 (G1), or an equivalent marker, and update Screen 1.
- OBJECT: US4.4 / AC4.4.1–AC4.4.2: the fail-closed refusal screen and its way out are unspecified, which breaks the project's "way out on every refusal screen" correction. Add AC4.4.4 and AC4.4.5 (G2).
- OBJECT: US4.6 / AC4.6.2: "Sign out" doesn't require the persona session to be cleared, so the next account could inherit a persona. Add AC4.6.3 (G3).
- OBJECT: NFR5 has no story-level pass condition for headings, text not colour alone, or keyboard entry on Screens 1, 2 and 4. Add AC4.1.5 and AC4.1.6 (G5).
- AGREE: US4.1 / AC4.1.1–AC4.1.2 match Screen 1. Suggest AC4.1.3 and AC4.1.4 for cancelled sign-in and an ended session (G4); I don't block on these.
- AGREE: US4.3 / AC4.3.3 and US4.7 / AC4.7.2 keep the refusal neutral and leak no allowlist or email information. Suggest AC4.3.4 for literal rendering of the email (G6).
- AGREE: US3.3 / AC3.3.1–AC3.3.3 match Screen 4 and keep "Sign out". Suggest also hiding the persona login and site picker (G7).
- AGREE: US6.1 / AC6.1.1–AC6.1.2 match the banner in Screen 3 (text and icon, above the tabs, on every tab).
- AGREE: US4.6 / AC4.6.1 places the signed-in block as in Screen 3. The label distinction (mockups R-02) is carried to Refined Mockups.
- OBJECT: US3.1: the "visitor" story states the owner's benefit. Change the actor or reword the benefit (minor; persona fidelity).
