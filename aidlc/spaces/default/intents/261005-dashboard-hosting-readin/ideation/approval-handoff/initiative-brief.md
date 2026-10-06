# Initiative Brief — Dashboard Hosting Readiness

## Sources

- Intent statement and stakeholder map: `ideation/intent-capture/`
- Feasibility assessment, constraint register and RAID log: `ideation/feasibility/`
- Scope document and intent backlog: `ideation/scope-definition/`
- Wireframes and user flow: `ideation/rough-mockups/`
- Answers Q1–Q2 in `ideation/approval-handoff/approval-handoff-questions.md`

## Intent and Problem

The HSM dashboard can't be hosted safely yet. It has no sign-in, its signing secret is public and burned, and its backend runs as a separate process. The parked deploy work waits on these app changes. You are the beneficiary, the only stakeholder and the decision-maker.

## Market Validation

Not applicable. Market Research was skipped with your confirmation, because this is an internal tool whose design was already decided.

## Feasibility and Risk Highlights

- **Feasible.** It is all Python and Streamlit work in this repo, using familiar tools. There are no paid services, no AWS, no regulatory regime and no outside blockers.
- **Risks (all accepted, Q1):**
  - R1: sign-in behaves differently locally and on Streamlit Cloud.
  - R2: the in-process backend misbehaves across reruns or restarts.
  - R3: no browser is available for browser tests in CI.
  - R4: the one-week target slips under the full process.
- **Key constraints:**
  - the secret is never in source code;
  - the backend is never reachable from outside;
  - work is test-first;
  - the test and coverage floors (745 / 95.00) only rise;
  - free tier only;
  - every change goes through a PR and CI.

## Scope Boundary

- **In scope:** eight required changes, then creating the two hosted apps after they merge. The changes, in order:
  1. secret from config (the burned value removed first);
  2. secrets bridge, dev-secret script and fail-closed tools;
  3. in-process backend;
  4. sign-in gate;
  5. build identifier;
  6. reset banner;
  7. post-deploy check.
- **Out of scope:** the deploy pipeline, promotion, deployment and observability. These stay with the parked deploy intent, whose provisioning step moves here.

## Concept Visuals

Four screens are in `ideation/rough-mockups/wireframes.md`: signed out, refused, signed in (with the reset banner and build ID), and backend failed. The flow is in `user-flow.md`. Four minor findings carry into Refined Mockups.

## Team Plan

Solo. You build, review and approve. Team Formation was skipped with your confirmation.

## Go/No-Go Recommendation

**Go (Q2).** Proceed to Inception as scoped, with all four risks accepted.

## Assumptions & Open Questions

- When the parked deploy intent resumes, its environment-provisioning step must be dropped, because it moved into this work (scope Q10).
