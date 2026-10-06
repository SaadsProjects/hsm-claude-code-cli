# Risk and Sequencing Rationale — Dashboard Hosting Readiness

## Sources

- `ideation/feasibility/raid-log.md` (risks R1–R4, issue I1)
- Scope Q4, Q5, Q9; units Q2, Q3; delivery Q1–Q4
- `inception/units-generation/unit-of-work-dependency.md` (the dependency graph)

A **Bolt** is one build pass over a piece of the work, ending in something that runs and is checked. The **walking skeleton** is a minimal version that runs the whole way through, built first to prove the pieces connect.

## Heuristic

The order is **walking-skeleton-first, then risk-first** (Boehm's spiral model), within the dependency graph. No scoring model such as WSJF (value plus urgency divided by size) is used. With one developer, one unit at a time and a fixed graph, a score would only restate the graph.

## Order and Why

| Bolt | Unit | Why it sits here |
|------|------|------------------|
| B1 | U1 secret-fail-closed | Skeleton and value-first: the burned secret (issue I1) is the most urgent fix and lands first, on its own (scope Q5, Q9). Every other unit depends on it. |
| B2 | U2 embedded-backend | Retires risk R2 (the in-process backend misbehaving across reruns and threads). U3 depends on it. |
| B3 | U3 sign-in-gate | Retires risk R1 (sign-in parity), using a real Google client locally (delivery Q3). Completes the team's local slice. |
| B4 | U5 postdeploy-check | Risk-first over U4: retires risk R3 (no browser in CI) and proves the gate in a real browser (delivery Q2). |
| B5 | U4 build-and-banner | Low risk and small; finishes the app changes so the U2–U5 pull request can merge. |
| B6 | U6 staging-app | Must come last: no hosted app may exist until every app change has merged (team.md Deployment). |

## Deviations from the Dependency Graph

None. The graph allows U4 and U5 in either order after U3; this plan picks U5 first.

## Schedule Risk (R4)

Risk R4 (the one-week target slipping) was accepted (handoff Q1). Two things keep it in check:
- the U2–U5 draft pull request runs full CI on every push, so failures surface early;
- each Bolt has a small, testable Definition of Done.

## Assumptions & Open Questions

None.
