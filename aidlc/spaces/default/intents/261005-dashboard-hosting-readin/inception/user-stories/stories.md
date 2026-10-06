# User Stories — Dashboard Hosting Readiness

## Sources

- `inception/requirements-analysis/requirements.md` (FR1–FR10, NFR1–NFR7)
- `personas.md` (P1 owner/developer, P2 visitor)
- `user-stories-questions.md` Q1–Q6 (Q6 is the mob follow-up on the post-deploy check)
- Mob contributions: `contributions/aidlc-design-agent.md`, `aidlc-developer-agent.md`, `aidlc-quality-agent.md`
- `ideation/rough-mockups/wireframes.md`; `memory/team.md`; `memory/project.md` (M1, M2, F1, F2)

All stories are **Must** (scope Q1/Q8). Groups 5–7 (build ID, banner, post-deploy check) rank lower within Must; that orders the work but drops nothing. Criteria marked **(R-03)** close the pass conditions that requirements-review finding R-03 flagged. Criteria marked **(evidence)** are checked by inspecting a process record, not by an automated test.

**Q6 narrows FR7.1 and FR7.2.** The post-deploy check no longer asserts the build identifier, because the identifier is shown only to signed-in, allowed visitors and the check never signs in (F1). The owner confirms the build on staging by signing in and reading the sidebar caption (US9.1).

**Test seam.** Streamlit 1.64's `AppTest` cannot set a signed-in user. So `dashboard/auth_gate.py` exposes a thin identity seam, `current_identity()`, `sign_in()` and `sign_out()`, which the app calls and the tests patch. "A fake identity" below means patching that seam.

---

## US1 — Signing secret from configuration (FR1)

### US1.1 — Secret read when used, not at import
As the developer, I want the signing secret read from `HSM_SIGNING_SECRET` each time a token is minted or verified, so that tests and processes can set it after import.
- **AC1.1.1** Given `HSM_SIGNING_SECRET` is unset, when `mock_hsm.auth` is imported, then no error is raised.
- **AC1.1.2** Given a valid secret is set after import, when a token is minted and then verified, then verification succeeds.
- **AC1.1.3** Given `mock_hsm/auth.py`, when its imports are checked by a test, then it imports only the standard library and `mock_hsm`.
- Depends on: none.

### US1.2 — Missing or short secret refused clearly
As the developer, I want minting and verifying to fail with a clear error when the secret is missing or shorter than 32 bytes, so that nothing runs on a weak or absent key.
- **AC1.2.1** Given the variable is unset, when a token is minted, then an error is raised whose message names `HSM_SIGNING_SECRET`.
- **AC1.2.2** Given a secret of 31 UTF-8 bytes, when a token is minted or verified, then the same kind of error is raised. A secret of exactly 32 UTF-8 bytes is accepted.
- **AC1.2.3** Given any refused secret value, when the error message is inspected, then it does not contain the value.
- Depends on: US1.1.

### US1.3 — Burned secret gone in one commit
As the owner, I want the burned literal and its scan exclusion removed together, so that the burned-secret check guards the code with no exception.
- **AC1.3.1** Given the change, when `scripts/check_burned_secret.py` runs, then it passes with `TEMPORARY_EXCLUSIONS` empty.
- **AC1.3.2** Given the repository, when it is searched for the burned value, then it appears nowhere except the permanent gitleaks allowlist entries in `.gitleaks.toml` and the check script's own stand-in test value.
- **AC1.3.3 (evidence)** Given the commit, when it is inspected, then the literal removal, the exclusion removal and the regression tests are in the same commit (M1).
- Depends on: US1.1, US1.2, US1.4, US2.1, US2.2, US2.3, US2.4, US2.6. Removing the literal is only safe once every entry point fails closed and local development has a secret path (requirements finding R-01).

### US1.4 — Tests bring their own secret
As the developer, I want each test run to generate its own throwaway secret, so that no fixed secret is ever committed.
- **AC1.4.1** Given a test run, when `tests/conftest.py` loads, then `HSM_SIGNING_SECRET` holds a freshly generated value of at least 32 bytes before any server or subprocess starts.
- **AC1.4.2** Given the conftest's secret generator, when it is called twice, then the two values differ.
- **AC1.4.3** Given a subprocess-based test (the hooks, the MCP server), when it runs, then it inherits the secret and passes.
- Depends on: US1.1.

---

## US2 — Supplying the secret and failing closed (FR2)

### US2.1 — Dev-secret script
As the developer, I want a script that writes a strong secret into a git-ignored `.env.local`, so that local setup takes one command.
- **AC2.1.1** Given no `.env.local`, when the script runs, then `.env.local` holds `HSM_SIGNING_SECRET` with a value of at least 32 bytes.
- **AC2.1.2** Given an existing `.env.local` with a secret, when the script runs without its overwrite option, then it exits non-zero and leaves the file unchanged.
- **AC2.1.3** Given the generated file, when `git check-ignore .env.local` runs, then it reports the file ignored.
- Depends on: US2.6.

### US2.2 — Backend refuses to start without a secret
As the developer, I want the backend, run either way, to refuse to start without a valid secret, so that I never run an ungated backend.
- **AC2.2.1** Given no secret, when the start script runs, then it exits non-zero with a message naming `HSM_SIGNING_SECRET` and starts no server.
- **AC2.2.2** Given no secret, when `python3 -m mock_hsm.server` (`server.run()`) runs, then it exits non-zero with the same message instead of serving requests that fail.
- **AC2.2.3** Given `.env.local` exists and the variable is unset in the shell, when the start script runs, then it loads `.env.local` and starts.
- **AC2.2.4** Given a valid secret, when the start script runs in a test, then the backend starts on a free port chosen by the test, never the fixed port 8770.
- Depends on: US1.2, US2.1.

### US2.3 — Publish hook denies without a secret
As the developer, I want the publish hook to deny explicitly when it can't get the secret, so that a crash can never let a publish through.
- **AC2.3.1** Given no secret, when the hook receives a `publish_schedule` call, then it returns a deny decision with a reason naming the missing secret. This test is written first.
- **AC2.3.2** Given a valid secret and a compliant schedule, when the hook runs, then it falls through as today.
- Depends on: US1.2.

### US2.4 — MCP tools report a missing secret
As the developer, I want the MCP tools to return a clear error when the secret is missing, so that I know how to fix my shell.
- **AC2.4.1** Given no secret, when any `mcp__hsm__*` tool is called, then it returns a tool error naming `HSM_SIGNING_SECRET`.
- **AC2.4.2** Given `.mcp.json`, when it is inspected by a test, then it contains no secret value.
- Depends on: US1.2.

### US2.5 — Hosted secrets reach the app (R-03)
As the owner, I want the dashboard to copy the signing secret from Streamlit secrets into the environment, so that the hosted app can mint tokens.
- **AC2.5.1** Given Streamlit secrets that contain `HSM_SIGNING_SECRET` (in an `AppTest` run), when the app starts, then a token can be minted and verified.
- **AC2.5.2** Given Streamlit secrets without it and no environment value, when the app starts, then it fails closed (no tab renders) and the log names the missing setting.
- **AC2.5.3** Given `mock_hsm/`, when it is checked by a test, then it contains no Streamlit import; the bridge lives in `dashboard/`.
- **AC2.5.4** Given a signing secret equal to the sign-in cookie secret, when the app starts, then it fails closed and the log names both settings, without either value.
- Depends on: US1.2.

### US2.6 — Secret files never committed (R-03)
As the owner, I want explicit ignore lines for secret files, so that a secret can't be committed by accident.
- **AC2.6.1** Given the repository, when `git check-ignore` is run on `.streamlit/secrets.toml`, `.env`, `.env.local` and `.env.production`, then all four are ignored.
- **AC2.6.2** Given `.gitignore`, when a test inspects it, then those lines sit outside the AI-DLC-managed block (F2).
- Depends on: none.

---

## US3 — Backend inside the dashboard (FR3)

### US3.1 — Dashboard runs with its own backend
As the owner, I want the dashboard to start its own backend inside its process, so that the demo can run on Streamlit Cloud's single-process host.
- **AC3.1.1** Given only the dashboard is started, when an allowed visitor opens a tab, then data loads from a backend bound to `127.0.0.1`.
- **AC3.1.2** Given the in-process start, when it runs, then the audit trail is configured, and `session.client_for` passes the start function's returned address to the client as `base_url`. The code doesn't rely on `HSM_BASE_URL` being set before import.
- Depends on: US1.1.

### US3.2 — Only one backend per process
As the owner, I want at most one backend per app process, so that Streamlit's reruns and parallel sessions never start duplicates or port clashes.
- **AC3.2.1** Given the start function is called twice in one process, when the running servers are counted, then exactly one exists.
- **AC3.2.2** Given repeated `AppTest` reruns of the dashboard, when they complete, then still only one backend exists.
- **AC3.2.3** Given two threads call the start function at the same moment, when both return, then exactly one backend exists and both got the same address.
- Depends on: US3.1.

### US3.3 — Backend failure is explained plainly (R-03)
As a visitor, I want a plain message if the demo backend didn't start, so that I'm not shown a crash.
- **AC3.3.1** Given the backend start is forced to fail in a test, when an allowed visitor loads the app, then the main area shows exactly "The demo backend didn't start. Reload the page or try again later." and no tab, persona login or site picker renders.
- **AC3.3.2** Given the same failure, when the screen is inspected, then "Sign out" is still present and no error type, stack trace or address is shown.
- **AC3.3.3** Given the same failure, when the app log is captured, then it contains the technical cause.
- Depends on: US3.1, US4.6.

### US3.4 — Separate backend still works for local tools
As the developer, I want `python3 -m mock_hsm.server` to keep working as its own process, so that the MCP tools and hooks still run locally.
- **AC3.4.1** Given a valid secret, when the server runs as its own process, then the existing MCP and hook tests pass unchanged.
- Depends on: US1.1, US2.2.

---

## US4 — Sign-in gate (FR4)

### US4.1 — Nothing shows before sign-in
As a visitor who isn't signed in, I want to see only a sign-in screen, so that no demo data or controls are exposed.
- **AC4.1.1** Given no signed-in user (fake identity), when the app renders, then it shows the title, "Access to this demo is by invitation." and a "Sign in" button.
- **AC4.1.2** Given the same state, when the render tree is inspected, then no tab, no persona picker and no backend call exists.
- **AC4.1.3** Given a visitor cancels sign-in at Google, or their session ends, when they return, then they see the sign-in screen again.
- **AC4.1.4** Given the sign-in, refusal and backend-failure screens, when each is inspected, then it has exactly one h1 (the app title) and states its message in plain text, not by colour alone.
- **AC4.1.5** Given those screens in the browser tests, when the visitor presses Tab, then focus reaches "Sign in" or "Sign out", and Enter activates it.
- Depends on: US4.5.

### US4.2 — Allowed visitor gets in with Google
As an allowed visitor, I want to sign in with Google and get in when my verified email is on the allowlist, so that I can use the demo.
- **AC4.2.1** Given a verified email that matches an allowlist entry after trimming and lower-casing (for example ` Saad@Example.com ` against `saad@example.com`), when the gate decides, then it allows.
- **AC4.2.2** Given the sign-in seam, when "Sign in" is chosen, then it calls `st.login("google")`; and a committed `.streamlit/secrets.toml.example` shows the `[auth.google]` settings with placeholder values only.
- Depends on: US4.5.

### US4.3 — Refused visitor sees a neutral refusal
As a refused visitor, I want a clear "no access" screen with a way out, so that I understand and can leave.
- **AC4.3.1** Given a signed-in identity whose `email_verified` is false, missing, or the string `"false"`, when the gate decides, then it refuses.
- **AC4.3.2** Given a verified email that is not on the allowlist (including a domain-only match such as `x@example.com` against `example.com`), when the gate decides, then it refuses.
- **AC4.3.3** Given a refusal of a signed-in visitor, when the screen renders, then it shows "This account doesn't have access", the signed-in email as literal text (any markup in it is not rendered) and "Sign out", with the same wording for every reason and no allowlist content.
- Depends on: US4.5.

### US4.4 — Gate fails closed
As the owner, I want the gate to refuse whenever its settings are missing, broken or erroring, so that a misconfiguration never opens the app.
- **AC4.4.1** Given an empty allowlist, a malformed allowlist (anything other than a list of strings, for example a single plain string) or missing sign-in settings, when the gate decides, then it refuses.
- **AC4.4.2** Given an exception inside the gate, when the app renders, then it refuses and never shows the persona picker.
- **AC4.4.3** Given a refusal caused by settings or an error (not by the visitor), when the screen renders, then it shows "Sign-in isn't available right now. Reload the page or try again later." with no technical detail, plus "Sign out" if someone is signed in.
- Depends on: US4.5.

### US4.5 — Decision is a pure, tested function
As the developer, I want the allow/refuse decision as a pure function, so that every rule is unit-tested without Streamlit.
- **AC4.5.1** Given `dashboard/auth_gate.py`, when its decision function is called with an identity and an allowlist, then it returns allow or refuse with a reason, and makes no Streamlit call.
- **AC4.5.2** Given the unit tests, when they run, then they cover allow, unverified (including `"false"`), not listed, domain-only, empty list, malformed list and error.
- Depends on: none.

### US4.6 — Signed-in block in the sidebar
As an allowed visitor, I want my email and "Sign out" at the top of the sidebar, above the persona login, so that I know who I am signed in as.
- **AC4.6.1** Given an allowed visitor, when the app renders, then the sidebar's first element shows the email and "Sign out", above the existing persona login.
- **AC4.6.2** Given "Sign out" is chosen (through the seam), when the app reruns, then the sign-in screen (US4.1) shows.
- **AC4.6.3** Given a visitor had picked a persona, when they sign out and another account signs in on the same browser tab, then no persona is pre-selected; the persona session was cleared at sign-out.
- Depends on: US4.2.

### US4.7 — Refusals logged without the email (R-03)
As the owner, I want each refusal logged with its reason and no email, so that I can see refusals without holding visitors' addresses.
- **AC4.7.1** Given a refusal for each reason (not verified, not on the allowlist, gate error), when the log is captured, then it contains that reason.
- **AC4.7.2** Given the same captured log, when it is searched for the email used, then the email is not found.
- Depends on: US4.5.

### US4.8 — Existing dashboard tests run through the gate
As the developer, I want the existing dashboard `AppTest` suite to run through the gate and the in-process start, with a shared fake allowed identity, so that no existing test is lost and `.test-floor` holds.
- **AC4.8.1** Given a shared fixture that signs in a fake allowed identity, when the existing dashboard tests run, then they pass through the gate.
- **AC4.8.2** Given the full suite after the gate lands, when CI runs, then the passing-test count is at or above `.test-floor` on every Python leg.
- Depends on: US4.2, US3.1.

---

## US5 — Build identifier (FR5)

### US5.1 — See which build is running
As the owner, I want the running build's commit shown in the sidebar, so that I know what's deployed.
- **AC5.1.1** Given a checkout with `.git`, when the build identifier is computed, then it equals the current commit SHA.
- **AC5.1.2** Given an allowed visitor, when the app renders, then the sidebar's bottom caption shows the build identifier next to the backend caption.
- **AC5.1.3** Given `python -m agents.build_info`, when it runs, then it prints the same identifier the app shows.
- Depends on: US4.2.

### US5.2 — Fingerprint fallback without git (R-03)
As the owner, I want a source fingerprint when there's no `.git`, so that hosted builds are still identifiable.
- **AC5.2.1** Given a copy of the source without `.git`, when the identifier is computed twice, then both results are equal and marked as a fingerprint.
- **AC5.2.2** Given one tracked source file changed, when it is computed again, then the result differs.
- **AC5.2.3** Given files the app writes while running (the audit file, `__pycache__`, `.pyc`), when they change, then the fingerprint does not.
- **AC5.2.4** Given `agents/build_info.py`, when its imports are checked, then it has no Streamlit import.
- Depends on: none.

---

## US6 — Demo-data reset banner (FR6)

### US6.1 — Reset notice above the tabs
As an allowed visitor, I want a notice that the demo data resets, so that I don't rely on changes persisting.
- **AC6.1.1** Given an allowed visitor (`AppTest`), when the app renders, then the reset notice is rendered once, before and outside the tabs container, so it shows on every tab.
- **AC6.1.2** Given the notice, when it is inspected, then it carries text and an icon, not colour alone.
- Depends on: US4.2.

---

## US7 — Post-deploy check (FR7, narrowed by Q6)

### US7.1 — Check a deployed app by hand
As the owner, I want one command that checks an app's URL, so that I know a deploy is up and gated.
- **AC7.1.1** Given a running app (in tests, a local app with a fake identity provider), when `scripts/postdeploy_check.py <url>` runs, then it confirms the app answers and a visitor who isn't signed in sees only the sign-in screen, and exits 0. It does not check the build (Q6).
- **AC7.1.2** Given the check's selectors, when they are inspected, then they come from `dashboard/markers.py`.
- Depends on: US4.1, US8.1.

### US7.2 — Check fails loudly
As the owner, I want the check to exit non-zero on any failure, so that a bad deploy isn't marked done.
- **AC7.2.1** Given an app without the sign-in gate (a test double that renders tabs), when the check runs, then it exits non-zero.
- **AC7.2.2** Given a page that answers but isn't the dashboard (no sign-in marker), when the check runs, then it exits non-zero.
- **AC7.2.3** Given an address that doesn't answer, when the check runs, then it exits non-zero within its timeout.
- Depends on: US7.1.

### US7.3 — Check never signs in or writes
As the owner, I want the check to stay read-only, so that it can safely run against any environment.
- **AC7.3.1** Given the check's source, when a test inspects it, then it contains no sign-in action, no credentials, and no call to `publish_schedule` or `submit_purchase_order` (F1, NFR6).
- Depends on: US7.1.

### US7.4 — Run the check from GitHub
As the owner, I want a manually triggered workflow that runs the check against a URL, so that I can check from anywhere.
- **AC7.4.1** Given the workflow file, when `actionlint` and `scripts/check_workflows.py` run, then they pass, with `workflow_dispatch` only, `permissions: contents: read`, SHA-pinned actions and no secrets.
- **AC7.4.2 (evidence)** Given a manual run with a URL, when it completes, then its result matches the by-hand check.
- Depends on: US7.1.

---

## US8 — Dependencies and CI (FR8)

### US8.1 — New packages through the locks
As the developer, I want Authlib and Playwright added through the `.in` files and recompiled locks, so that every gate keeps passing.
- **AC8.1.1** Given the pull request, when `lock-check` and `audit` run, then both pass, with `streamlit[auth]` in the runtime lock and `playwright` in the dev lock.
- Depends on: none.

### US8.2 — Browser tests run locally against a fake identity
As the developer, I want browser tests in CI to run against a local app with a stand-in for Google sign-in and a cached Chromium, so that they prove the gate and need no secrets.
- **AC8.2.1** Given the `browser-tests` job, when it runs, then it installs Chromium through Playwright with a cache key that includes the Playwright version, holds no secrets, and has `contents: read`.
- **AC8.2.2** Given a pull request, when browser tests run, then they target an app on loopback with the stand-in identity provider.
- **AC8.2.3** Given the stand-in signs in a verified email that isn't on the allowlist, and then an unverified email, when each browser test runs, then each sees the refusal screen. This is the browser proof the intent's success metric asks for.
- Depends on: US7.1, US4.3.

### US8.3 — Browser check can't pass without testing
As the developer, I want `browser-tests` to fail if it would run nothing, so that the required check always means something.
- **AC8.3.1** Given the watch list, when it is inspected, then it includes `requirements-dev.txt`, `.github/workflows/ci.yml` and `dashboard/app.py` (the app the browser tests launch).
- **AC8.3.2** Given a browser test file, or a source file it imports or launches, that is off the watch list, when the meta-test runs, then it fails.
- **AC8.3.3** Given the first browser test exists, when the job runs with no tests selected, then it fails instead of passing on "no tests ran", and it retries a failure once. This lands in the same pull request as the first browser test.
- **AC8.3.4 (evidence)** Given any required job is renamed, when its pull request is prepared, then the ruleset's required-check list is changed in the same piece of work (M2).
- Depends on: US8.2.

### US8.4 — Reasons on broad catches
As the developer, I want reasons on the two bare `noqa: BLE001` comments, so that the code matches the team's rule.
- **AC8.4.1** Given `lint_before_commit.py` and `require_no_violations.py`, when they are searched for `noqa: BLE001` without `--`, then nothing is found.
- Depends on: none.

---

## US9 — Staging app (FR9)

### US9.1 — Staging app created and proven (R-03, R-04)
As the owner, I want a staging app that tracks `main`, with its own secrets, created only after all the changes merge, so that the hosted demo is safe from day one.
- **AC9.1.1 (evidence)** Given FR1–FR8 merged to `main`, when the owner creates the app in the Streamlit Cloud console, then it tracks `main`, and its secrets hold its own signing secret, cookie secret, Google OAuth client and allowlist. The app's startup check (AC2.5.4) proves the signing secret differs from the cookie secret.
- **AC9.1.2 (evidence)** Given the staging URL, when the post-deploy check runs against it, then it exits 0. The owner then signs in and confirms the sidebar build caption matches the `main` commit SHA. The URL, the check output and the SHA seen are recorded as the closing evidence.
- Depends on: US1–US8 merged.

---

## US10 — Documentation (FR10)

### US10.1 — Docs match the new setup (R-03)
As the developer, I want the docs to describe the secret setup, the start command, the sign-in and the in-process backend, so that a fresh clone works by following them.
- **AC10.1.1** Given `CLAUDE.md`, `README.md` and `dashboard/README.md`, when they are read, then each has a section on setting `HSM_SIGNING_SECRET` with the dev-secret script, including how the `claude` shell gets the same value, and none says there is no password.
- **AC10.1.2** Given a fresh clone with `.env.local` created by the dev-secret script, when the documented start command is run, then it starts successfully.
- **AC10.1.3 (evidence)** Given each docs update, when its pull request is inspected, then it ships with the change it describes. The secret-setup part ships in the first pull request.
- Depends on: the change each doc describes.

---

## Dependencies and Delivery Notes

- **First pull request (requirements finding R-01, the developer's recommendation; Delivery Planning decides):** US1.1–US1.4, US2.1, US2.2, US2.3, US2.4, US2.6, and the secret-setup part of US10.1. US8.4 can join, since it touches the same hook file. Together these let the burned value go while every entry point fails closed.
- **Walking skeleton:** the first pull request merged green, plus US3.1 and US4.1 working locally on the intent branch (the dashboard starts with its own backend and shows the sign-in screen).
- Order: US1 → US2 → US3 → US4 → US5, US6 → US8.1 → US7 → US8.2, US8.3 → US9. US10 goes alongside each change.
- **Coverage risk (quality):** the margin is about one point. Browser tests don't count toward coverage, so sign-in and sign-out wiring must be covered by ordinary or `AppTest` tests through the seam.

## Maintained Dissent

- **Designer and developer:** they recommended showing a small build caption before sign-in, so that the post-deploy check could confirm the build. **Your decision (Q6 C):** drop the build assertion from the check. The owner confirms the build on staging by signing in (AC9.1.2).

## Assumptions & Open Questions

- [assumption] Google reports `email_verified` through `st.user` (feasibility R1). AC4.3.1 refuses entry when it is missing or false.
- The 30-second cold-start target (NFR2) has no story-level pass condition, because the post-deploy check can't sign in (requirements finding R-02, accepted). It is deferred to NFR Requirements.
- Settled in Refined Mockups: telling "Signed in as" apart from the persona section, and whether the button reads "Sign in with Google".
