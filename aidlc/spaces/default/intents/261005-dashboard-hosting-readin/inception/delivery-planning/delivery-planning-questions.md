# Delivery Planning Questions — Dashboard Hosting Readiness

## Sources

- `inception/units-generation/unit-of-work.md`, `unit-of-work-dependency.md`, `unit-of-work-story-map.md` (six units; U1 is the thin slice)
- `inception/contract-design/contract-summary.md` (open contract points; accepted findings R-01 and R-02 to be settled in U2 and U3 design)
- `memory/team.md` Way of Working, Walking Skeleton, Deployment; `memory/project.md`
- Earlier decisions: scope Q4/Q5/Q9 (burned secret first, then risk-first), units Q2–Q4 (U1 is the secret pull request only; one unit at a time; U1 ships alone and U2–U5 ship together)

Already settled, so not asked again: build the riskiest parts first after the secret removal; one unit at a time; no formal scoring model; no other team to wait on; the main worries are feasibility risks R1–R4.

A **Bolt** is one build pass over a piece of the work, ending in something that runs and is checked.

## Q1. How big is each Bolt?

A. One Bolt per unit: six Bolts, U1 to U6
B. Bundle the two small dashboard units (U4 build-and-banner with U5 postdeploy-check) into one Bolt: five Bolts
X. Other (please specify)

[Answer]: A

## Q2. After the sign-in gate (U3), which comes next?

U4 and U5 don't depend on each other. Risk-first favours U5, because it retires risk R3 (no browser in CI) and proves the gate in a real browser sooner.

A. U5 postdeploy-check first, then U4 build-and-banner
B. U4 build-and-banner first, then U5
X. Other (please specify)

[Answer]: A

## Q3. When should the real Google sign-in client be set up?

Tests use a stand-in for Google throughout. Only the staging app (U6) needs a real Google OAuth client. Setting one up earlier would let you try real sign-in locally and retire risk R1 (sign-in behaving differently locally and on Streamlit Cloud, including the verified-email flag) before U6.

A. During U3: create a Google OAuth client for local use and try a real sign-in before U3 is done
B. Only at U6, when the staging app is created
X. Other (please specify)

[Answer]: A

## Q4. How does U2–U5 work get CI runs before the final pull request?

The proof that a unit is finished is the pull-request CI run with all 10 required checks green. But U2–U5 ship together as one pull request at the end.

A. Open the U2–U5 pull request as a draft as soon as U2 starts, so every push gets a full CI run; mark it ready after U5
B. Open the pull request only at the end, and verify U2–U4 with the local test suite instead
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Bolt size (Q1): one Bolt per unit, six Bolts.
- Order after the sign-in gate (Q2): U5 postdeploy-check first, then U4 build-and-banner. The full order is U1, U2, U3, U5, U4, U6.
- Real Google sign-in client (Q3): set up during U3 for local use, so you can try a real sign-in and retire risk R1 before U3 is done.
- CI runs for U2–U5 (Q4): open the U2–U5 pull request as a draft as soon as U2 starts, so every push gets a full CI run, and mark it ready after U5.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
