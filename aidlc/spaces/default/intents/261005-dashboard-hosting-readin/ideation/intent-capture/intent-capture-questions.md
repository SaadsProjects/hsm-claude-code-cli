# Intent Capture Questions — Dashboard Hosting Readiness

## Sources

- [desc] Initial description: "Implement the dashboard application changes required before any hosted deploy, as designed in intent 261004-dashboard-deploy-pipelin (construction/nfr-design and infrastructure-design): st.login sign-in gate with email allowlist and email_verified check; HSM_SIGNING_SECRET loader in mock_hsm/auth.py with the burned literal removed (and its TEMPORARY_EXCLUSIONS entry in scripts/check_burned_secret.py removed in the same change), Streamlit-secrets bridge, dev-secret script, fail-closed hook/MCP/start-script; in-process loopback backend with single-instance guard; build identifier (git SHA with source-fingerprint fallback); demo-data reset banner; read-only Playwright post-deploy check with browser tests. Test-first."
- [scope] Workflow-selected scope: `feature`.
- [memory:M1] `aidlc/spaces/default/memory/project.md#Forbidden`: "NEVER expose the dashboard beyond loopback or a private network without a sign-in layer in front of it. *(group C, R-SEC-1; source: devsecops review, interview Q1)* (affirmed 2026-10-04)"
- [memory:M2] `aidlc/spaces/default/memory/project.md#Forbidden`: "NEVER deploy beyond localhost with the hard-coded signing secret in `mock_hsm/auth.py`; hosted deploys read it from the environment and fail closed when it is missing. *(group C, R-SEC-3; source: devsecops review, interview Q4)* (affirmed 2026-10-04)"

## Q1. What problem does this piece of work solve?

The description lists the app changes that the earlier deploy-pipeline design said must exist before the dashboard is hosted. This question pins down which problem matters most, so the intent statement leads with it.

A. The dashboard can't be hosted safely yet (no sign-in, a public signing secret, a backend that runs as a separate process), so the parked deploy work is blocked until these changes land
B. Mainly the burned signing secret: getting it out of the code is the priority, and hosting is secondary
C. Mainly getting a hosted dashboard that people can try out
D. Not yet defined
X. Other (please specify)

[Answer]: A

## Q2. Who benefits from this work, and how?

This sets the "target customer" section. The hosted app will sit behind a sign-in with an email allowlist, so there may be people besides you who use it.

A. Me, as the repo owner and developer: it unblocks the deploy work
B. The allowlisted viewers who will sign in to the hosted dashboard
C. Both of the above
D. Not identified
X. Other (please specify)

[Answer]: A

## Q3. What would tell you this work succeeded? (select all that apply)

These become the measurable success metrics.

A. Every change reaches `main` through a pull request with all required CI checks passing
B. The burned-secret check passes with its temporary exclusion removed
C. Test count and coverage stay at or above their current floors
D. A browser test shows a visitor who is not on the allowlist gets turned away
E. Not yet defined
X. Other (please specify)

[Answer]: A, B, C, D

## Q4. Why now?

This fills in the "initiative trigger" section.

A. The deploy-pipeline work is parked until these app changes exist
B. Security: the repository is public and the old signing secret in it is burned
C. Both of the above
D. Not identified
X. Other (please specify)

[Answer]: A

## Q5. Who are the stakeholders, and what does each care about?

This fills in the stakeholder map. Only people you name here will appear in it.

A. Just me: I build, review and approve everything
B. Me, plus the allowlisted viewers, who care about being able to sign in and use the dashboard
C. Me, plus other people (name them and their interests under Other)
D. Not identified
X. Other (please specify)

[Answer]: A

## Q6. Who decides scope and priority, and who influences those decisions?

This separates decision-makers from influencers in the stakeholder map.

A. I decide, and nobody else influences it
B. I decide; viewers or reviewers influence it through their feedback
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q7. Are there any communication or reporting needs?

A. None: the approval steps in this workflow and the pull request descriptions are enough
B. Pull request descriptions, plus a short note when the dashboard is ready to host
C. Not applicable
X. Other (please specify)

[Answer]: B

## Q8. Does the selected scope match what you want to build?

This workflow was started with the `feature` scope [scope], which runs the full 33-step process: market research, feasibility, mockups, user stories, design, build, tests, CI, and the deployment and operations steps. The description covers only the app changes the earlier design already specified.

A. Confirm: the `feature` scope and its full process match what I want
B. Different boundary: just the listed app changes; the full process is more than this needs, and I'll want it trimmed after this step
C. Different boundary: the listed app changes plus actually creating the hosted apps
D. Not yet defined
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Problem (Q1): the dashboard can't be hosted safely yet (no sign-in, a public signing secret, a separate-process backend), so the parked deploy work waits on these app changes.
- Who benefits (Q2): you, as repo owner and developer; it unblocks the deploy work.
- Success (Q3): every change lands through a PR with all required CI checks passing; the burned-secret check passes with its temporary exclusion removed; test count and coverage stay at or above their floors; a browser test shows a non-allowlisted visitor is turned away.
- Why now (Q4): the deploy-pipeline work is parked until these app changes exist.
- Stakeholders (Q5): just you; you build, review and approve everything.
- Decisions (Q6): you decide, and nobody else influences it.
- Communication (Q7): PR descriptions, plus a short note when the dashboard is ready to host.
- Scope (Q8): the `feature` scope and its full process are confirmed.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
