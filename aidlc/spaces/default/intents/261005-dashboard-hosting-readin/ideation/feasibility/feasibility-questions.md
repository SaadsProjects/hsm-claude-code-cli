# Feasibility Questions — Dashboard Hosting Readiness

## Sources

- Intent statement: `aidlc/spaces/default/intents/261005-dashboard-hosting-readin/ideation/intent-capture/intent-statement.md`
- Market Research was skipped: this is an internal tool, and its design was already decided in intent `261004-dashboard-deploy-pipelin`.
- Rules in force: `aidlc/spaces/default/memory/{org,team,project}.md`, `phases/ideation.md`

## Q1. Which outside systems does this work have to fit with? (select all that apply)

The sign-in, the secret handling and the post-deploy check each lean on something outside the repo. This sets the integration constraints.

A. Streamlit's built-in sign-in, with Google as the identity provider
B. Streamlit Community Cloud's secrets store (for the signing secret and sign-in settings)
C. The existing GitHub Actions CI and its required checks
D. None beyond the repository itself
X. Other (please specify)

[Answer]: B, C, D

## Q2. Do any regulatory or compliance rules apply?

The dashboard shows seeded demo data. The only personal data the sign-in adds is viewers' email addresses.

A. None: demo data only, and sign-in emails need no special handling
B. Yes (name them under Other)
C. Not identified
X. Other (please specify)

[Answer]: A

## Q3. How familiar is the tech this work needs?

The work stays in Python and Streamlit, but adds sign-in through an identity provider and browser-driven tests.

A. All familiar: Python, Streamlit, sign-in and browser testing
B. Python and Streamlit are familiar; the sign-in setup and/or browser testing are new
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q4. What are the budget and timeline limits?

A. Free tier only (Streamlit Community Cloud, free Google sign-in), and no deadline
B. Free tier only, with a target date (give it under Other)
C. Some spending is allowed (say how much under Other)
D. Not yet defined
X. Other (please specify)

[Answer]: B

## Q5. Is anything outside the work itself likely to block or delay it?

For example a change freeze or a competing priority. (The parked deploy work depends on this one; that is already recorded.)

A. None
B. Yes (describe it under Other)
C. Not identified
X. Other (please specify)

[Answer]: A

## Q6. Are any AWS accounts or services involved?

A. None: hosting is Streamlit Community Cloud, and no AWS account is used
B. Yes (name them under Other)
C. Not applicable
X. Other (please specify)

[Answer]: A

## Q7. Which technical uncertainties worry you most? (select all that apply)

These become the main risks in the risk log.

A. Whether Streamlit's sign-in behaves the same locally and on Streamlit Cloud, including the verified-email flag
B. Running the backend inside the dashboard's single process on Streamlit Cloud
C. Running browser tests in CI (getting a browser available there)
D. None worth flagging
X. Other (please specify)

[Answer]: A, B, C

## Q8. Follow-up to Q1: which outside systems, given "None" was picked alongside two others?

Q1 came back with "None beyond the repository" selected together with the Cloud secrets store and GitHub Actions CI, which contradict each other. Google sign-in was not selected, but the sign-in gate from the intent needs some identity provider.

A. Cloud secrets store and GitHub Actions CI only; the identity provider is not a constraint to record here
B. Cloud secrets store, GitHub Actions CI, and Google as the sign-in identity provider
C. Cloud secrets store, GitHub Actions CI, and a different identity provider (name it under Other)
D. None beyond the repository itself
X. Other (please specify)

[Answer]: A

## Q9. Follow-up to Q4: what is the target date?

Q4 says free tier only, with a target date, but no date was given.

A. Within a week
B. Within two weeks
C. Within a month
D. No firm date after all
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Outside systems (Q1, clarified by Q8): the Streamlit Community Cloud secrets store and the existing GitHub Actions CI with its required checks. The identity provider is not recorded as a constraint here.
- Regulatory (Q2): none; demo data only, and sign-in emails need no special handling.
- Familiarity (Q3): Python, Streamlit, sign-in and browser testing are all familiar.
- Budget and timeline (Q4, Q9): free tier only, with a target of within a week.
- Outside blockers (Q5): none.
- AWS (Q6): none; hosting is Streamlit Community Cloud.
- Main technical risks (Q7): sign-in parity between local and Streamlit Cloud (including the verified-email flag); running the backend inside the dashboard's single process on Streamlit Cloud; getting a browser available for browser tests in CI.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
