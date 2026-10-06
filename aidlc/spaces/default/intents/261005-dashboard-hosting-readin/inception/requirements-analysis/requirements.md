# Requirements — Dashboard Hosting Readiness

## Sources

- Initial description: `project-description.json` [desc]
- Ideation: intent statement, feasibility (constraint register, RAID log), scope document and intent backlog, rough mockups (wireframes, user flow), decision log D1–D15
- Code knowledge base at commit `825a0f8`: `aidlc/spaces/default/codekb/hsm-claude-code-cli/` (business-overview, architecture, code-structure, findings CQ-1 to CQ-12 in code-quality-assessment)
- Affirmed practices: `inception/practices-discovery/team-practices.md`, promoted to `memory/team.md`; hard rules in `memory/project.md` (including M1, M2, F1, F2 affirmed 2026-10-05)
- Answers Q1–Q8 in `requirements-analysis-questions.md`

## Intent Analysis

**Goal.** Make the HSM dashboard safe to put on the internet, then put a staging copy up behind sign-in. Today the dashboard has no sign-in (anyone can pick any persona, CQ-3), the token-signing secret is a burned value in a public repository (CQ-1, CQ-2), and the backend runs as a separate process that Streamlit Community Cloud can't host (CQ-4). The parked deploy work waits on these changes.

**Type:** enhancement with security hardening, plus creating one hosted environment. **Scope:** multi-component: `mock_hsm`, `dashboard`, `agents`, the project hooks, the MCP server, `scripts`, CI and the lockfiles. **Complexity:** standard. **Depth:** Standard.

**Success** (intent statement):
- every change reaches `main` through a pull request with all 10 required checks green;
- the burned-secret check passes with its exclusion removed;
- the test and coverage floors hold and are raised at the end;
- a browser test proves that a visitor who isn't allowlisted is turned away.

## Functional Requirements

### FR1 — Signing secret from configuration

- **FR1.1** The system shall read the token-signing secret from the environment variable `HSM_SIGNING_SECRET` each time a token is minted or verified, never at module import. (CQ-1; team.md Deployment)
  - Pass: importing `mock_hsm.auth` with the variable unset raises nothing.
  - Pass: minting or verifying with it unset raises the error in FR1.2.
- **FR1.2** When the secret is missing, or shorter than 32 bytes, minting and verifying shall fail with an error that names `HSM_SIGNING_SECRET` and never contains the secret value. There is no fallback secret anywhere, including local development. (team.md Deployment; practices Q15)
- **FR1.3** The burned literal in `mock_hsm/auth.py` and its `TEMPORARY_EXCLUSIONS` entry in `scripts/check_burned_secret.py` shall be removed in the same commit. That commit carries regression tests showing that the burned-secret check passes, that a missing secret raises a clear error, and that the secret is read at call time. (M1; CQ-2)
- **FR1.4** `tests/conftest.py` shall generate a throwaway secret of at least 32 bytes per test run and place it in `os.environ` before any server or subprocess starts. No fixed test secret is committed. (team.md Testing Posture)
- **FR1.5** `mock_hsm/auth.py` shall import only the standard library and `mock_hsm`. (team.md Code Style)

### FR2 — Supplying the secret, and failing closed everywhere

- **FR2.1** When it runs under Streamlit, the dashboard shall copy the signing secret from Streamlit secrets into the environment before any token is minted. This bridge lives in `dashboard/`. (team.md Code Style; intent)
- **FR2.2** A dev-secret script shall generate a secret of at least 32 bytes into a git-ignored `.env.local` for local development. It refuses to overwrite an existing secret unless asked. (intent; team.md Deployment)
- **FR2.3** The local start script shall refuse to start, with a non-zero exit and a message naming `HSM_SIGNING_SECRET`, when the secret is missing or too short. (CQ-7)
- **FR2.4** The `require_no_violations.py` hook shall deny `publish_schedule` explicitly when it cannot obtain the secret, proven by a failing test written first. A crashed hook fails open, so an explicit deny is required. (team.md Testing Posture)
- **FR2.5** The MCP server shall return a clear tool error naming `HSM_SIGNING_SECRET` when the secret is missing. It inherits the secret from the shell; the secret is never written into `.mcp.json` or any committed config. (team.md Deployment; CQ-7)
- **FR2.6** `.gitignore` shall ignore `.streamlit/secrets.toml`, `.env`, `.env.local` and `.env.*` with explicit lines outside the AI-DLC-managed block. (F2; CQ-9)

### FR3 — Backend inside the dashboard's process

- **FR3.1** The dashboard shall start the mock backend inside its own process through an imported, standard-library-only function in `mock_hsm/`, bound to `127.0.0.1` only. (team.md Deployment and Code Style; CQ-4)
- **FR3.2** At most one backend shall run per process, however many times Streamlit re-runs `dashboard/app.py`. A test proves that two starts in one process leave one backend. (team.md Deployment; CQ-4)
- **FR3.3** The in-process start shall configure the audit trail as `run()` does today, and shall make the dashboard's client reach the backend at its actual address (by setting `HSM_BASE_URL` before the client is first imported, or by passing `base_url`). (CQ-4)
- **FR3.4** If the backend fails to start, a signed-in, allowed visitor shall see the plain "The demo backend didn't start. Reload the page or try again later." screen, with no technical details, and "Sign out" stays available. (wireframes Screen 4; project correction: a way out on every error screen)
- **FR3.5** The existing local workflow (`mock_hsm.server` as its own process for the MCP tools and hooks) shall keep working, subject to FR1–FR2.

### FR4 — Sign-in gate

- **FR4.1** The sign-in gate (`dashboard/auth_gate.py`) shall run before anything else renders and before the backend is reached. No tab and no persona picker renders until it allows entry. (team.md Deployment and Testing Posture)
- **FR4.2** Visitors shall sign in through Streamlit's `st.login` with Google as the identity provider. (Q1)
- **FR4.3** The gate shall admit only a visitor whose identity provider reports the email as verified. (team.md Deployment)
- **FR4.4** The gate shall compare the email, trimmed and lower-cased, for an exact match against the allowlist held in the app's Streamlit secrets, with no domain wildcards. (team.md Deployment; practices Q5)
- **FR4.5** The gate shall fail closed. Missing or broken sign-in settings, an empty or malformed allowlist, or any error inside the gate refuses entry and never falls back to the persona picker. (team.md Deployment)
- **FR4.6** The allow/refuse decision shall be a pure function, unit-tested without Streamlit. The screen wiring is tested with Streamlit's `AppTest` using a fake identity. (team.md Testing Posture)
- **FR4.7** A visitor who isn't signed in shall see only the sign-in screen: the app title, one line saying access is by invitation, and a "Sign in" button. (wireframes Screen 1)
- **FR4.8** A signed-in visitor who isn't allowed shall see "This account doesn't have access", the email they signed in with, and a "Sign out" button. The wording is the same for every refusal reason, and nothing reveals who is allowed. (wireframes Screen 2)
- **FR4.9** An allowed visitor shall see their email and "Sign out" at the top of the sidebar, above the existing persona login. The persona picker works as today, inside the gate. (wireframes Screen 3)
- **FR4.10** Each refusal shall be written to the app's log with its reason (not verified, not on the allowlist, or gate error) and never with the email address. (Q6)

### FR5 — Build identifier

- **FR5.1** `agents/build_info.py` shall identify the running build by its git commit SHA. When no `.git` is present, it falls back to a fingerprint of the source files. It contains no Streamlit code. (intent; team.md Code Style)
- **FR5.2** The dashboard shall show the build identifier as a small caption at the bottom of the sidebar, next to the backend caption. (wireframes Screen 3)

### FR6 — Demo-data reset banner

- **FR6.1** Every page of the signed-in dashboard shall show a slim notice above the tabs, always visible, saying the demo data resets. It uses text and an icon, not colour alone. (wireframes Screen 3; practices Q4)
- **FR6.2** A test shall prove that the banner appears on every tab. (team.md Testing Posture)

### FR7 — Post-deploy check

- **FR7.1** `scripts/postdeploy_check.py` shall check a deployed app in a real browser (Playwright). It confirms that the app answers, that it shows the expected build identifier, and that a visitor who isn't signed in is refused. It is read-only: it never signs in, never writes data, and never calls `publish_schedule` or `submit_purchase_order`. (team.md Deployment; F1)
- **FR7.2** The check shall run by hand with one command per environment, taking the app URL and the expected build as inputs. It exits non-zero on any failed assertion. (Q3)
- **FR7.3** A manually triggered GitHub Actions workflow shall run the same check against a given URL. It has least-privilege `permissions` (`contents: read`), SHA-pinned actions, and no identity-provider credentials or other secrets. (Q3; project.md Mandated; F1)
- **FR7.4** The check shall have its own tests: the happy path plus at least two error cases (for example, the wrong build, or the gate missing). (team.md Testing Posture)
- **FR7.5** Selectors the check relies on shall come from `dashboard/markers.py`, shared by the app and the check. (team.md Code Style)

### FR8 — Dependencies and CI

- **FR8.1** `streamlit[auth]` (Authlib) shall be added to `requirements.in` and `playwright` to `requirements-dev.in`, both locks recompiled with the commands at the top of each `.in` file, and both committed together. (CQ-6; team.md Code Style)
- **FR8.2** The `browser-tests` job shall install Chromium with Playwright, cached under a key that includes the Playwright version, only in a job that holds no secrets and has `contents: read`. (team.md Deployment)
- **FR8.3** The `browser-tests` watch list shall add `requirements-dev.txt` and `.github/workflows/ci.yml`. A meta-test fails when a browser test file, or a source file it imports, is off the list. (team.md Testing Posture)
- **FR8.4** Once the first browser test exists, `browser-tests` shall stop accepting "no tests ran" as a pass, shall require at least one test, and shall get the same single retry as the `tests` jobs. (team.md Testing Posture)
- **FR8.5** Browser tests on a pull request shall run only against an app started inside the job on loopback, with the identity provider replaced by a test double. (team.md Testing Posture)
- **FR8.6** Any rename of a required CI job shall change the ruleset's required-check list in the same piece of work. (M2)
- **FR8.7** The two `noqa: BLE001` comments without a reason, in `lint_before_commit.py` and `require_no_violations.py`, shall get reasons. (CQ-10; practices)

### FR9 — Staging app

- **FR9.1** After FR1–FR8 have merged to `main`, a staging Streamlit Community Cloud app tracking `main` shall be created. (scope Q10, narrowed by Q4/Q8)
- **FR9.2** The staging app shall have its own signing secret, sign-in cookie secret, Google OAuth client and allowlist in its Streamlit secrets. The signing secret and the cookie secret are different values. (team.md Deployment)
- **FR9.3** The post-deploy check (FR7) shall pass against staging, including the refusal of a visitor who isn't signed in. (Q4)

### FR10 — Documentation

- **FR10.1** `CLAUDE.md`, `README.md` and `dashboard/README.md` shall be updated in the same pull request as the change they describe: the secret setup, the start command, the sign-in and the in-process backend. (CQ-11; Q5)

## Non-Functional Requirements

- **NFR1 — Security (fail closed).** Every entry point refuses to run without a valid secret (FR1.2, FR2.3–FR2.5). The gate refuses on any error (FR4.5). No secret value appears in source, committed config, logs or error messages. The backend is never reachable outside the app's process (`project.md` Forbidden).
- **NFR2 — Cold start.** A signed-in, allowed visitor can use the dashboard within 30 seconds of the staging app waking. This is measured by the post-deploy check's timing against staging. (Q2)
- **NFR3 — Quality.** Work is test-first. The suite stays green on Python 3.10 and 3.14. `.test-floor` and `.coverage-floor` never drop, and Build and Test raises both, with headroom, in the final pull request. Coverage is measured over the existing packages, and `scripts/` stays unmeasured. (team.md Testing Posture; Q7)
- **NFR4 — Observability.** Sign-in refusals are logged with a reason and no email address (FR4.10). Backend start failures are logged with their technical cause, which never reaches the screen (FR3.4).
- **NFR5 — Accessibility.** Desktop first, with Streamlit's defaults on phones. The banner, the refusal and the error states use text, not colour alone. Each new screen has an h1 title and a keyboard entry point as in the wireframes.
- **NFR6 — Read-only checks.** The post-deploy check and any smoke check never write data and never call `publish_schedule` or `submit_purchase_order`. (`project.md` Forbidden)
- **NFR7 — Supply chain.** New dependencies come only through the hash-pinned locks and pass `pip-audit`. Any exception goes in `security-exceptions.toml` with a reason and an expiry. Actions are SHA-pinned. (team.md Code Style; `project.md` Mandated)

## Constraints

- Every change reaches `main` through a pull request with all 10 required checks green. The burned-secret removal (FR1.3 with FR1.1, FR1.2 and FR1.4) ships first as its own pull request; the rest ships as one pull request at the end. (team.md Way of Working)
- Walking skeleton: the first pull request merges green, and the dashboard starts locally with the in-process backend and shows the sign-in screen. (team.md Walking Skeleton)
- Free tier only: Streamlit Community Cloud and Google sign-in. (feasibility Q4)
- File placement is fixed by CI's watch list: `dashboard/auth_gate.py`, `dashboard/markers.py`, `agents/build_info.py`, `scripts/postdeploy_check.py`, `tests/test_*browser*.py`. (CQ-8)
- No staging app exists until the sign-in gate and the secret handling have merged. (team.md Deployment)
- Target: about a week; the date may slip. (feasibility Q9; scope Q7)

## Assumptions

- `st.user` exposes the email and an `email_verified` flag for Google, and `st.login` behaves the same locally and on Streamlit Cloud. This is feasibility risk R1, to be proven early; FR4.5 refuses entry if the flag is missing.
- Streamlit Community Cloud runs a single process and gives the app a writable local disk for the audit file. (team.md Deployment)

## Out of Scope

- The production app, including its secrets and its check. Creating it moves back to the parked deploy intent `261004-dashboard-deploy-pipelin`. (Q4, Q8)
- The automated deploy pipeline, production promotion, deployment execution and observability, which stay with the parked deploy intent.
- A persistent datastore: data and the audit trail reset on redeploy. (practices Q4)
- Adding the hosted Python version to the CI matrix. (Q7)
- Any publish-schedule or submit-PO path in the dashboard or the checks. (`project.md` Forbidden)

## Open Questions

- Re-measure the suite's pass count, skip count and run time at the start of Code Generation (practices evidence).
- Confirm that GitHub secret scanning, push protection and Dependabot security alerts are on, and whether Streamlit Cloud enforces the hashes in `requirements.txt` (practices evidence).
- Final wording of the reset banner, and the Refined Mockups carry-overs from rough-mockups review findings R-01 to R-04.
- The parked deploy intent's plan must take production creation back, and drop its staging provisioning, when it resumes. (scope Q10 as narrowed by Q8)

## Assumptions & Open Questions

- [assumption] `st.user` reports `email_verified` for Google accounts (feasibility R1). The gate refuses entry when the flag is absent.
- The open questions are listed in the section above.
