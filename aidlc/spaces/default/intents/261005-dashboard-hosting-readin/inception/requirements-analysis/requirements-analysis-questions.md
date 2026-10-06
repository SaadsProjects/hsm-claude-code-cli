# Requirements Analysis Questions — Dashboard Hosting Readiness

## Sources

- Initial description (`project-description.json`)
- Ideation record: intent statement, feasibility, scope document and intent backlog, rough mockups, decision log
- Code knowledge base: `aidlc/spaces/default/codekb/hsm-claude-code-cli/` (findings CQ-1 to CQ-12)
- Affirmed practices: `aidlc/spaces/default/memory/team.md` and `project.md` (affirmed 2026-10-05)

Already settled, so not asked again: the eight changes and their order, hosted apps created last, sign-in gate rules (verified email, exact allowlist match, fail closed), no fallback secret, 32-byte minimum, per-environment secrets, data resets with a tested banner, file placement, browser-test rules, floors, and the PR plan.

## Q1. Which sign-in provider will the hosted apps use?

Streamlit's sign-in works with any OpenID Connect provider. The "verified email" check depends on the provider reporting it.

A. Google
B. Another OpenID Connect provider (name it under Other)
C. Decide during design
X. Other (please specify)

[Answer]: A

## Q2. How quickly should the dashboard be usable after a cold start?

Streamlit Cloud apps sleep and wake; the backend now starts inside the app.

A. No specific target
B. Within 10 seconds of the app waking, for a signed-in visitor
C. Within 30 seconds
X. Other (please specify)

[Answer]: C

## Q3. How is the post-deploy check run in this work?

Creating the hosted apps is part of this work; the automated deploy pipeline stays with the parked deploy intent.

A. By hand from your machine (one command per environment) for now; the parked deploy work wires it into a pipeline later
B. From a manually-triggered GitHub Actions workflow added in this work
C. Both
X. Other (please specify)

[Answer]: C

## Q4. When is "create the hosted apps" done?

A. Both apps (staging and production) are created with their own secrets, and the post-deploy check passes against each
B. Only staging is created and checked now; production is created by the parked deploy work
X. Other (please specify)

[Answer]: B

## Q5. Should the out-of-date docs be updated in this work?

`CLAUDE.md`, `README.md` and `dashboard/README.md` still describe starting with no secret and no sign-in (CQ-11).

A. Yes, update them in the same pull requests as the changes they describe
B. Yes, but as one docs-only change at the end
C. No, leave docs for later
X. Other (please specify)

[Answer]: A

## Q6. Should the app record sign-in refusals?

A. Log each refusal to the app's log with the reason (not verified, not on allowlist, gate error), without the email address
B. Log each refusal with the email address
C. No logging of refusals
X. Other (please specify)

[Answer]: A

## Q7. Should CI test on the Python version the hosted apps run on?

CI already supports adding a version through the `HOSTED_PYTHON` repository variable.

A. Yes: pick the hosted Python when creating the apps and set `HOSTED_PYTHON` to it
B. No: 3.10 and 3.14 are enough
X. Other (please specify)

[Answer]: B

## Q8. Follow-up to Q4: does the production app move back to the parked deploy work?

Q4 creates only the staging app now. But the scope decision (Q10 in Scope Definition, D10) moved creating both apps into this work and out of the parked deploy intent's plan.

A. Yes: this work creates and checks staging only; production creation goes back into the parked deploy intent's plan
B. No: create both apps here after all (Q4 option A)
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Sign-in provider (Q1): Google.
- Cold start (Q2): the dashboard is usable within 30 seconds of the app waking.
- Post-deploy check (Q3): it can run both by hand from your machine (one command per environment) and from a manually-triggered GitHub Actions workflow added in this work.
- Hosted apps (Q4, Q8): this work creates and checks the staging app only. Creating the production app goes back into the parked deploy intent's plan; this narrows scope decision D10.
- Docs (Q5): `CLAUDE.md`, `README.md` and `dashboard/README.md` are updated in the same pull requests as the changes they describe.
- Refusal logging (Q6): each sign-in refusal is logged with its reason (not verified, not on allowlist, gate error), never with the email address.
- Hosted Python in CI (Q7): no; CI stays on 3.10 and 3.14.

Does this all look correct before I generate the requirements artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
