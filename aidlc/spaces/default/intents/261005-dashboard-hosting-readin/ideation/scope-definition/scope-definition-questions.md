# Scope Definition Questions — Dashboard Hosting Readiness

## Sources

- Intent statement: `ideation/intent-capture/intent-statement.md`
- Feasibility assessment, constraint register and RAID log: `ideation/feasibility/`
- Rules in force: `aidlc/spaces/default/memory/{org,team,project}.md`

The intent lists eight changes. They're referred to below by these short names:

- **Sign-in gate**: only verified emails on an allowlist get in.
- **Secret from config**: the signing secret is read from configuration; the burned value and its temporary scan exclusion are removed together.
- **Secrets bridge and dev-secret script**: copy hosted secrets into the environment, and generate a local development secret.
- **Fail-closed tools**: the hooks, the tool server and the start scripts refuse to run without a secret.
- **In-process backend**: the backend runs inside the dashboard, local-only, with one copy at most.
- **Build identifier**: the app shows which build is running.
- **Reset banner**: the app tells viewers that the demo data resets.
- **Post-deploy check**: a read-only browser check of a deployed app, with browser tests.

## Q1. What is the smallest scope that still makes hosting safe?

The project's rules forbid hosting without the sign-in gate and with the hard-coded secret, so some of these are non-negotiable.

A. All eight changes: hosting shouldn't start without any of them
B. Only the security-critical ones (sign-in gate, secret from config, secrets bridge, fail-closed tools, in-process backend); the build identifier, reset banner and post-deploy check can follow later
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q2. Which changes, if any, are "should have" rather than "must have"? (select all that apply)

Anything picked here ranks below the must-haves in the backlog and is the first to drop if the week runs short.

A. Build identifier
B. Reset banner
C. Post-deploy check and browser tests
D. None: all eight are must-haves
X. Other (please specify)

[Answer]: A, B, C

## Q3. Is this the right dependency order between the changes?

Proposed: secret from config first (everything signs tokens with it), with the secrets bridge, dev-secret script and fail-closed tools alongside; then the in-process backend; then the sign-in gate; then the build identifier and reset banner; and the post-deploy check last, because it exercises the rest.

A. Yes, that order
B. A different order (describe it under Other)
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q4. How should the work be sequenced?

A. Risk-first: retire the three technical risks early (sign-in parity, in-process backend, a browser in CI)
B. Dependency-first: follow the order in Q3 strictly
C. Value-first: get the burned secret out of the code first, then the rest
D. Not yet defined
X. Other (please specify)

[Answer]: A

## Q5. Are any capabilities tied to a deadline of their own?

The whole piece of work targets within a week.

A. None beyond the one-week target for the whole
B. The burned-secret removal should land sooner than the rest
C. Not yet defined
X. Other (please specify)

[Answer]: B

## Q6. Is creating the hosted apps in or out of this work?

The intent review noted this was never settled. Creating the two Streamlit Cloud apps and entering their secrets is hosting work, which the parked deploy intent was planned to do.

A. Out: this work only makes the app ready; creating the apps stays with the parked deploy work
B. In: this work also creates the hosted apps
C. Not yet defined
X. Other (please specify)

[Answer]: B

## Q7. How should the one-week target and the full process be reconciled?

Feasibility flagged that the target is likely to slip under the full feature process (risk R4).

A. Keep the full process and accept that the date may slip
B. Keep the date, and trim the later process stages (I'll propose which ones after this step for your approval)
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q8. Follow-up to Q1 and Q2: must the should-haves land before hosting?

Q1 says hosting shouldn't start without all eight changes, but Q2 ranks the build identifier, the reset banner and the post-deploy check as should-haves that drop first if the week runs short. Both can't hold if time runs out.

A. All eight are required before hosting; the Q2 ranking only orders the work, and nothing is dropped
B. The three should-haves may be dropped or deferred; hosting can start without them
C. Some of the three are required before hosting (name which under Other)
D. Not yet defined
X. Other (please specify)

[Answer]: A

## Q9. Follow-up to Q4 and Q5: what goes first, risk spikes or the secret removal?

Q4 asks for risk-first (sign-in parity, in-process backend, a browser in CI), and Q5 asks for the burned-secret removal to land sooner than the rest.

A. Secret removal first as its own early change, then risk-first for the rest
B. Risk spikes first, with the secret removal right after them
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Q10. Follow-up to Q6: how should creating the hosted apps fit in?

Q6 brings creating the two Streamlit Cloud apps into this work. The parked deploy intent also planned that step, and the rules forbid exposing the dashboard before the sign-in gate and the secret handling are in place.

A. Create the apps only after all the required changes are merged; take this step out of the parked deploy intent's plan
B. Create the apps only after all the required changes are merged; the parked deploy intent keeps its own provisioning step and reuses the apps
C. Not yet defined
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- In scope (Q1, Q6, Q8): all eight changes, every one required before hosting, plus creating the two Streamlit Cloud apps and entering their secrets.
- Priority (Q2, Q8): the build identifier, the reset banner and the post-deploy check rank below the other five, but this only orders the work; none is dropped.
- Dependency order (Q3): secret from config (with the secrets bridge, the dev-secret script and the fail-closed tools), then the in-process backend, then the sign-in gate, then the build identifier and reset banner, then the post-deploy check.
- Sequencing (Q4, Q5, Q9): the burned-secret removal lands first as its own early change; after that, risk-first (sign-in parity, the in-process backend, a browser in CI).
- Hosted apps (Q10): created only after all the required changes are merged. This step moves into this work and out of the parked deploy intent's plan.
- Timeline (Q5, Q7): one-week target for the whole. The full process is kept, and the date may slip.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
