# Units Generation Questions — Dashboard Hosting Readiness

## Sources

- `inception/domain-design/components.md` (13 building blocks) and `decisions.md` (ADR-001 to ADR-007)
- `inception/user-stories/stories.md` (35 stories) and its delivery notes (first pull request contents, from requirements finding R-01)
- `inception/requirements-analysis/requirements.md`
- `memory/team.md` Way of Working (secret removal ships first as its own pull request; the rest as one pull request) and Walking Skeleton (a local slice for this work)

## Proposed decomposition (for Q1)

| Unit | Contents (stories) | Kind |
|------|--------------------|------|
| U1 secret-fail-closed | Secret read at call time and refused when missing or short; burned value and exclusion removed; tests' own secret; dev-secret and start scripts; hook and tool server failing closed; `.gitignore` lines; `noqa` reasons; secret-setup docs (US1.1–US1.4, US2.1–US2.4, US2.6, US8.4, part of US10.1) | library |
| U2 embedded-backend | Backend inside the dashboard, one per process, failure screen, separate backend still working (US3.1–US3.4) | service |
| U3 sign-in-gate | Secrets bridge, the gate and its screens, refusal logging, existing tests through the gate, Authlib dependency (US2.5, US4.1–US4.8, US8.1) | ui |
| U4 build-and-banner | Build identifier and reset banner (US5.1, US5.2, US6.1) | ui |
| U5 postdeploy-check | The check, its GitHub workflow, the browser-tests job hardening (US7.1–US7.4, US8.2, US8.3) | library |
| U6 staging-app | Create the staging app and prove it (US9.1) | packaging |

Docs (US10.1) travel with each unit's change.

## Q1. How should the work be split into units?

A. The six units above
B. Fewer, coarser units: U1 secret-fail-closed, one unit for all the app changes (U2–U5), and U6 staging-app
C. Finer units (say which to split under Other)
X. Other (please specify)

[Answer]: A

## Q2. What does the first unit (the thin slice) cover?

The team rule for this work says the slice is the first pull request (the secret removal) merging with all 10 checks green, plus the dashboard starting locally with its own backend and showing the sign-in screen. But the sign-in screen and the in-process backend belong to later units, and the secret removal should land soon on its own.

A. U1 is the secret pull request only. Its proof is that pull request merging green with every entry point refusing to run without a secret. "The dashboard starts locally and shows the sign-in screen" is checked when U3 finishes.
B. U1 also carries a minimal in-process start and the sign-in screen, matching the team rule exactly. The first pull request gets bigger and lands later.
X. Other (please specify)

[Answer]: A

## Q3. May independent units be built in parallel?

Once U3 is done, U4 and U5 don't depend on each other.

A. No: build one unit at a time (solo work)
B. Yes, where the dependencies allow
X. Other (please specify)

[Answer]: A

## Q4. How do the units ship?

A. U1 ships as its own pull request; U2–U5 build on one working branch and ship together as one pull request; U6 is a hosting step after that merges
B. Every unit as its own pull request
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Split (Q1): six units. U1 secret-fail-closed (library), U2 embedded-backend (service), U3 sign-in-gate (ui), U4 build-and-banner (ui), U5 postdeploy-check (library) and U6 staging-app (packaging). Docs travel with each unit.
- First unit and thin slice (Q2): U1 is the secret pull request only. Its proof is that pull request merging with all 10 checks green and every entry point refusing to run without a secret. "The dashboard starts locally and shows the sign-in screen" is checked when U3 finishes.
- Parallel work (Q3): no; one unit at a time.
- Shipping (Q4): U1 ships as its own pull request. U2–U5 build on one working branch and ship together as one pull request. U6 is a hosting step after that merges.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
