# Units of Work — Dashboard Hosting Readiness

## Sources

- `inception/domain-design/components.md` and `decisions.md` (ADR-001 to ADR-007)
- `inception/user-stories/stories.md` (US1.1–US10.1) and its delivery notes
- `inception/requirements-analysis/requirements.md`
- Answers Q1–Q4 and the plan approval in `units-generation-questions.md`
- `memory/team.md` (Way of Working, Walking Skeleton, Code Style)

## Unit Table

| Unit ID | Directory | Name | Kind | Complexity | Deployment model |
|---------|-----------|------|------|------------|------------------|
| U1 | u1-secret-fail-closed | secret-fail-closed | library | M | Shared: used by every process (dashboard, backend, hook, tool server) |
| U2 | u2-embedded-backend | embedded-backend | service | M | Embedded in the dashboard process; still runnable on its own |
| U3 | u3-sign-in-gate | sign-in-gate | ui | L | Embedded in the dashboard |
| U4 | u4-build-and-banner | build-and-banner | ui | S | Embedded in the dashboard |
| U5 | u5-postdeploy-check | postdeploy-check | library | M | Standalone script and manual GitHub workflow |
| U6 | u6-staging-app | staging-app | packaging | S | Streamlit Community Cloud app tracking `main` |

All of U2–U5 ship inside one application. There is a single deployable app, and the units are pieces of work within it, not separate services (Q4).

## U1 — secret-fail-closed

- **Description:** removes the burned signing secret and makes every entry point fail closed without a valid one. This is the first pull request and the thin slice (Q2).
- **Boundaries:** components TokenAuth, MockBackend (startup check only), PublishHook, McpTools, LocalSecretTooling, BurnedSecretCheck. Also the test fixture in `tests/conftest.py` and `.gitignore`.
- **Responsibilities:**
  - read the secret at call time, with a 32-byte minimum and no fallback, plus `require_secret()`;
  - remove the literal and its exclusion in one commit (M1);
  - tests generate their own secret;
  - the dev-secret script, and a start script that loads `.env.local` and refuses without a secret;
  - `server.run()` refuses without a secret;
  - the hook denies explicitly, and the tool server reports a clear error;
  - explicit `.gitignore` lines (F2);
  - reasons on the two bare `noqa` comments;
  - the secret-setup docs.
- **Delivers:** pull request 1. Its proof is that it merges with all 10 required checks green and every entry point refuses to run without a secret.
- **Notes:**
  - Removing the literal is safe only because the hook, tool server, start script and backend all fail closed in the same pull request (requirements finding R-01).
  - The hook test is written first, because a crashed hook fails open.
  - The suite must stay at or above `.test-floor` on both Python legs.

## U2 — embedded-backend

- **Description:** runs the mock backend inside the dashboard process, one per process.
- **Boundaries:** components EmbeddedBackend (new `mock_hsm/embedded.py`), DashboardShell (startup wiring, backend caption, Screen 4), and the HsmClient call sites (explicit `base_url`).
- **Responsibilities:**
  - a standard-library-only start function that binds loopback;
  - a lock-guarded singleton with a liveness check (domain-design finding R-02);
  - audit configuration with an explicit hosted path (domain-design finding R-03);
  - the address passed as `base_url`, with its holder decided in Functional Design (domain-design finding R-01);
  - a backend caption showing the real address;
  - the Screen 4 failure message;
  - the separate-process backend still working.
- **Notes:** Screen 4's "Sign out" comes from U3. Until U3 lands, Screen 4 renders without the Account section, and the U3 tests add it.

## U3 — sign-in-gate

- **Description:** puts the sign-in gate in front of everything, plus the hosted-secrets bridge.
- **Boundaries:** components SecretsBridge (new `dashboard/secrets_bridge.py`), SignInGate (new `dashboard/auth_gate.py`), DashboardShell (startup order, Account and Demo persona sections, the "Acting as" caption, markers), and the dependency lockfiles (Authlib).
- **Responsibilities:**
  - a pure decision function and the identity seam;
  - allowlist parsing;
  - Screens 1, 2 and 5;
  - refusal logging without the email;
  - a sign-out that clears the persona session;
  - the existing `AppTest` suite moved through the gate with a shared fake identity;
  - `streamlit[auth]` added to the runtime lock;
  - `markers.py` kept as constants only (domain-design finding R-04);
  - the Streamlit dependency recorded for the gate (domain-design finding R-05).
- **Delivers:** the second half of the team's local slice. The dashboard starts locally with its own backend and shows the sign-in screen (Q2).
- **Notes:** this unit carries the highest test burden, and the coverage margin is about one point, so the sign-in wiring must be covered through the seam.

## U4 — build-and-banner

- **Description:** shows which build is running, and warns that the demo data resets.
- **Boundaries:** components BuildInfo (new `agents/build_info.py`) and DashboardShell (build caption, reset banner).
- **Responsibilities:**
  - the commit SHA, or a source fingerprint that ignores files the app writes;
  - the "Build abc1234" or "Build src-…" caption;
  - `python -m agents.build_info`;
  - the reset banner above the tabs.
- **Notes:** framework-free, with no Streamlit import in `build_info.py`.

## U5 — postdeploy-check

- **Description:** a read-only browser check of a deployed app, and the CI that keeps browser tests honest.
- **Boundaries:** component PostDeployCheck (new `scripts/postdeploy_check.py`), a manual GitHub workflow, the `browser-tests` CI job, and the dev lockfile (Playwright).
- **Responsibilities:**
  - the check confirms the app answers and refuses a visitor who isn't signed in, and handles a sleeping or waking host (user-stories finding R-01);
  - it fails loudly, and never signs in or writes;
  - a `workflow_dispatch` workflow with `contents: read`;
  - Chromium cached by Playwright version;
  - browser tests against a local app with an identity stand-in, including the refusal of an allowlisted-but-unverified or non-allowlisted visitor;
  - the watch list extended, a meta-test, at least one test, and a retry.
- **Notes:** the "no tests ran" pass goes away in this same unit (AC8.3.3).

## U6 — staging-app

- **Description:** creates the staging app after U2–U5 merge, and proves it.
- **Boundaries:** hosting configuration only. This is the owner's console action, not code (requirements finding R-04).
- **Responsibilities:**
  - an app tracking `main`;
  - its own signing secret, cookie secret, Google OAuth client and allowlist;
  - the post-deploy check passing against it;
  - the owner signing in and confirming that the build caption matches `main`.
- **Notes:** production stays with the parked deploy intent.

## Assumptions & Open Questions

- [assumption] U2 can render Screen 4 without the Account section until U3 lands. Because U2–U5 ship as one pull request, no visitor sees the interim state.
