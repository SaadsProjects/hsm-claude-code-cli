# Bolt Plan — Dashboard Hosting Readiness

## Sources

- `inception/units-generation/unit-of-work.md`, `unit-of-work-dependency.md`, `unit-of-work-story-map.md`
- `inception/contract-design/contract-summary.md` (C1–C9; open points and accepted findings R-01, R-02)
- Answers Q1–Q4 in `delivery-planning-questions.md`; units Q2–Q4; scope Q4, Q5, Q9
- `memory/team.md` Way of Working, Walking Skeleton, Testing Posture

A **Bolt** is one build pass over a piece of the work, ending in something that runs and is checked. There is one Bolt per unit (Q1). They are built one at a time in this order: B1 (U1), B2 (U2), B3 (U3), B4 (U5), B5 (U4), B6 (U6) (Q2). The **walking skeleton** is the first Bolt, a minimal version that runs the whole way through and is built first to prove the pieces connect.

Every Bolt is finished when its pull request's CI run passes all 10 required checks (team.md). B1 has its own pull request. B2 to B5 share one pull request, opened as a draft when B2 starts so that every push gets a full CI run (Q4).

## B1 — U1 secret-fail-closed (walking skeleton)

- **Units:** U1.
- **Definition of Done:**
  - pull request 1 merges with all 10 required checks green;
  - the burned value and its scan exclusion are gone in one commit (M1);
  - every entry point refuses to run without a valid secret: `python3 -m mock_hsm.server`, the start script, the publish hook (an explicit deny) and the MCP tools;
  - tests generate their own secret;
  - the secret-setup docs are updated.
- **Confidence hypothesis:** the secret can leave the code without leaving any process ungated, or any test or developer stranded.
- **Expected demo:**
  - run the start script without a secret and see it refuse;
  - run the dev-secret script, start again and see it work;
  - see the hook deny a publish with the secret unset;
  - see CI green on the pull request.
- **What it proves:** the secret handling across four separate processes, and the full CI gate set on a security change.
- **Skeleton note:**
  - The skeleton checkpoint covers U1 only (units Q2).
  - The second half of the team's local slice is checked when B3 finishes: the dashboard starting locally with its own backend and showing the sign-in screen.

## B2 — U2 embedded-backend

- **Units:** U2.
- **Definition of Done:**
  - the backend starts inside the dashboard on loopback, one per process, including under concurrent starts and after the thread dies;
  - the dashboard client uses the embedded address (contract C3);
  - the hosted audit path defaults to a temp directory (C2);
  - Screen 4 shows on a start failure;
  - the separate-process backend still works;
  - the draft pull request is green.
- **Confidence hypothesis:** Streamlit's reruns and threads don't break a single in-process backend (risk R2).
- **Expected demo:** `streamlit run dashboard/app.py` with no separate backend, and data loads.
- **Must settle first (Functional Design):**
  - when the dashboard embeds a backend versus using `HSM_BASE_URL`;
  - `client_for` behaviour when no backend is running;
  - the failed or dead instance transitions (contract-design findings R-01 and R-04).

## B3 — U3 sign-in-gate

- **Units:** U3.
- **Definition of Done:**
  - the gate shows before anything else;
  - Screens 1, 2 and 5 match the refined mockups;
  - the decision function is fully unit-tested;
  - the existing dashboard tests pass through the gate;
  - refusals are logged without the email;
  - the secrets bridge fails closed;
  - Authlib is in the runtime lock;
  - the draft pull request is green;
  - you have tried a real Google sign-in locally with your own OAuth client (Q3).
- **Confidence hypothesis:** Streamlit's sign-in with Google reports a verified email, and behaves the same with the test stand-in and with real Google locally (risk R1).
- **Expected demo:**
  - a local sign-in with real Google: allowed with your email;
  - refused with an email that isn't listed;
  - the dashboard starts locally with its own backend and shows the sign-in screen (the second half of the walking-skeleton slice).
- **Must settle first (Functional Design):** how markers appear in the page, and how `AppTest` and Playwright find them (contract-design finding R-02).

## B4 — U5 postdeploy-check

- **Units:** U5.
- **Definition of Done:**
  - `scripts/postdeploy_check.py` passes against a local app and fails with the right exit code in each error case (C8);
  - it handles a sleeping host;
  - the manual workflow passes lint;
  - the `browser-tests` job installs a cached Chromium, runs real browser tests (including the refusal of an unlisted and of an unverified visitor through the stand-in) and can no longer pass on "no tests ran";
  - the draft pull request is green.
- **Confidence hypothesis:** a real browser in CI can prove the gate, so the required browser check means something (risk R3).
- **Expected demo:** the `browser-tests` job running real tests on the draft pull request, and the check exiting 0 against a local app.

## B5 — U4 build-and-banner

- **Units:** U4.
- **Definition of Done:**
  - the build caption reads "Build abc1234", or "Build src-…" without git;
  - the fingerprint is stable, and ignores files the app writes at runtime;
  - `python -m agents.build_info` prints the same value;
  - the reset banner sits above the tabs on every tab;
  - the draft pull request is green and is marked ready, then merges.
- **Confidence hypothesis:** a hosted build can be identified without `.git`.
- **Expected demo:** the signed-in dashboard showing the banner and the build caption.

## B6 — U6 staging-app

- **Units:** U6.
- **Definition of Done:**
  - with the U2–U5 pull request merged, you create the staging app tracking `main` with its own secrets (contract C7);
  - the post-deploy check exits 0 against it;
  - you sign in and see a build caption that matches the `main` commit;
  - the URL, the check output and the commit are recorded.
- **Confidence hypothesis:** the hosted app behaves like the local one, including sign-in (risk R1 on the real host) and its cold start (NFR2).
- **Expected demo:** the staging URL refusing a visitor who isn't signed in, and letting you in.

## Construction Settings (recorded, unchanged)

- **Checkpoints:** enabled. Each unit's design stages and code finish before the next unit starts, and each ends with a checked completion checkpoint.
- **Iteration:** unit-major.
- **Execution:** serial (one at a time).
- **Engine walk order:** the order follows the unit dependency graph. U4 and U5 are both unblocked after U3, so the plan's preference for U5 first (Q2) is applied when the workflow offers the next unit.

## Assumptions & Open Questions

- [assumption] The workflow lets you pick U5 before U4 when both are ready. If it walks U4 first, building U4 first costs little, because neither depends on the other.
