# Requirements — Dashboard Deployment Pipeline

## Sources

- Initial description: "set up a deployment pipeline for the dashboard" [desc]
- Workflow-selected scope: infra [scope]
- Affirmed practices in `inception/practices-discovery/team-practices.md` (team-practices), promoted to `aidlc/spaces/default/memory/team.md`, and the hard rules in `discovered-rules.md`, promoted to `project.md` [memory:M1]
- Answers in `requirements-analysis-questions.md`, Q1 to Q12 [Q1]–[Q12]
- Repository facts checked on 2026-10-04 at commit `1586133`:
  - Streamlit 1.64.0 provides `st.login`.
  - The backend bind address is hard-coded at `mock_hsm/server.py:720`.
  - The signing-secret literal is at `mock_hsm/auth.py:23`.
  - The repo `SaadsProjects/hsm-claude-code-cli` is public.
  - The suite baseline is 757 collected, 745 passed and 12 perf skipped.

## Intent Analysis

The goal is to make the HSM Streamlit dashboard safely reachable on the internet, and to keep every change to it gated by automated checks [desc]. Today:
- nothing runs the checks except a local, opt-in commit hook;
- the dashboard has no sign-in;
- the backend's token-signing secret is public in a public repository.

Success means:
- every change reaches `main` only through a pull request whose CI passes;
- a merge redeploys a sign-in-protected staging app and proves it with a read-only check;
- production moves only on your explicit approval, to a commit that already passed staging.

**Type:** new infrastructure plus targeted application changes (secret handling, in-process backend start, sign-in). **Scope:** multi-component (CI, dashboard, `mock_hsm`). **Complexity:** standard.

## Functional Requirements

### FR1 — Continuous integration on every pull request and on `main`
- **FR1.1** CI shall run `ruff check .` and `ruff format --check .` with the ruff version pinned in the dev lockfile. Either failure fails the run [memory:M1] [Q14 of practices].
- **FR1.2** CI shall run the test suite with plain `python -m pytest tests/`, never with an unrelated `-m` expression, on Python 3.10 and 3.14. Both matrix legs must pass [memory:M1].
  - The `perf`-marked tests shall never run in CI.
  - A failing test may be retried once. A test that fails its retry fails the run.
  - The suite runs serially (no `-n`).
- **FR1.3** CI shall measure line coverage over `agents/`, `dashboard/`, `mock_hsm/`, `mcp_server/` and `.claude/hooks/`, with `tests/` excluded and subprocess-run code measured.
  - The first delivery reports the baseline without gating.
  - The gate then fails any run below 80%.
  - The floor and the measured package set are never lowered to pass a run [memory:M1].
- **FR1.4** CI shall run the security checks below. Each failure fails the run [memory:M1]:
  - secret scanning with gitleaks, with GitHub push protection enabled;
  - a dependency audit (`pip-audit`) against the lockfile;
  - bandit as its own job.

  The gitleaks configuration shall carry one documented allowlist entry for the burned historical secret (see FR3.4), scoped to that exact value in history only [Q10].
- **FR1.5** CI shall not export `HSM_BASE_URL`, `HSM_ACTIVE_USER` or `HSM_AUDIT_PATH`. Test audit trails go to temp files through `tests/conftest.py` [memory:M1].

### FR2 — Protected trunk
- **FR2.1** `main` shall be protected:
  - The FR1 checks are required status checks.
  - Merging is by pull request only, with squash-merge as the only allowed merge method.
  - Direct pushes are refused, including admin bypass [memory:M1].
- **FR2.2** The production branch (named `production`) shall be protected so that only the promotion workflow (FR7) can update it. Nobody commits to it directly [memory:M1] [Q5].

### FR3 — Signing secret out of source
- **FR3.1** `mock_hsm/auth.py` shall read the token-signing secret from the environment (`HSM_SIGNING_SECRET`) or, when running under Streamlit, from Streamlit secrets. The source contains no secret literal [Q4 of practices] [Q10].
- **FR3.2** When no secret is configured, minting or verifying a token shall fail closed with a clear error naming the missing setting. This applies locally as well; there is no built-in fallback [Q6].
- **FR3.3** The test suite shall supply its own generated secret through `tests/conftest.py`, so tests never depend on a developer's local secret [Q6].
- **FR3.4** The previously committed secret value shall never be used again by any environment. Hosted apps use newly generated values, and staging and production use different values [Q10].

### FR4 — Dashboard runs its backend in-process on hosted apps
- **FR4.1** The mock backend's bind host and port shall be configurable. The defaults stay `127.0.0.1:8770` so local workflows are unchanged.
- **FR4.2** On a hosted app, the dashboard shall start the mock backend once per process, in a background thread bound to `127.0.0.1` only, before the first backend call. A rerun of the Streamlit script shall not start a second server [memory:M1].
- **FR4.3** The backend shall not be reachable from outside the app's own process or host [memory:M1] [Q11].

### FR5 — Sign-in in front of all dashboard content
- **FR5.1** The dashboard shall require sign-in with Streamlit's built-in OpenID Connect sign-in (`st.login`) before it renders any data, tab or persona picker [Q2].
- **FR5.2** After sign-in, the dashboard shall check the signed-in email against an allowlist read from Streamlit secrets. The initial allowlist contains only the owner's email. A signed-in user who is not on it sees an access-denied message and no data [Q3].
- **FR5.3** An anonymous visitor shall see only the sign-in prompt. No dashboard data, site names, personas or backend URL appear [Q2] [Q7].
- **FR5.4** Once signed in and allowed, the existing persona picker shall behave as today. Any persona can be chosen [Q4].

### FR6 — Staging deployment
- **FR6.1** A Streamlit Community Cloud app ("staging") shall track `main` and redeploy automatically after each merge [memory:M1].
- **FR6.2** After each merge to `main`, a workflow shall run the post-deploy check (FR8) against the staging URL. It records the result against that commit so promotion (FR7) can require it [memory:M1].

### FR7 — Production promotion and rollback
- **FR7.1** A manually started GitHub Actions workflow shall promote a chosen commit to production. It runs in a protected GitHub Environment whose required reviewer is the owner, so it pauses until approved [Q5].
- **FR7.2** The promotion workflow shall refuse a commit unless that commit is on `main`, passed every FR1 check, and passed the staging post-deploy check (FR6.2) [Q5].
- **FR7.3** On approval, the workflow shall move the `production` branch to the chosen commit. A Streamlit Community Cloud app ("production") tracks that branch. The workflow then runs the post-deploy check (FR8) against the production URL [Q5].
- **FR7.4** Rollback shall use the same workflow and the same approval to move `production` back to a previously promoted commit. It is the one case where the move is not a fast-forward [memory:M1].

### FR8 — Read-only post-deploy check
- **FR8.1** The post-deploy check shall pass only when both of these hold:
  - the app's health endpoint answers successfully;
  - an anonymous request receives the sign-in prompt and no dashboard data [Q7].
- **FR8.2** The check shall wait for the app to wake or finish redeploying, polling for up to 10 minutes, then fail with a message stating which condition was not met [Q8].
- **FR8.3** The check shall never sign in, write data, or call `publish_schedule` or `submit_purchase_order` [memory:M1].
- **FR8.4** The check script shall have its own tests: the happy path, the app being unreachable until the timeout, and data being visible to an anonymous visitor [memory:M1].

### FR9 — Reproducible dependencies
- **FR9.1** Dependencies shall be split into runtime requirements (what the hosted app installs) and dev requirements (lint, test, coverage and security tools). Both are compiled into hash-pinned lockfiles, and CI installs from them [memory:M1].
- **FR9.2** The hosted apps shall install from the runtime lockfile only.

### FR10 — Runbook
- **FR10.1** The repository shall document how to:
  - create the two Cloud apps and their secrets (signing secret, OIDC settings, allowlist);
  - run locally with a local secret;
  - promote;
  - roll back;
  - rotate the signing secret.

## Non-Functional Requirements

- **NFR1 Security.**
  - Every third-party GitHub Action is pinned by full commit SHA.
  - Every workflow declares least-privilege `permissions`.
  - No long-lived cloud credentials are stored as repository secrets. Any future cloud access uses short-lived OIDC.
  - Secrets exist only in GitHub or Streamlit secret stores and are never printed in logs [memory:M1].
- **NFR2 CI feedback time.** A pull request's full CI run, all jobs with the matrix in parallel, completes within 15 minutes. The measured suite is about 87 s per leg.
- **NFR3 Coverage.** Line coverage across the FR1.3 package set is at least 80% once the gate is switched on [memory:M1].
- **NFR4 Regression baseline.** The existing suite stays green: no fewer than 745 passing tests at the recorded baseline, on both matrix legs.
- **NFR5 Reproducibility.** Two installs from the same lockfile resolve identical versions. The ruff version used by CI equals the one used by the local commit hook.
- **NFR6 Reliability (best effort).** There is no uptime target for staging or production. A deploy counts as successful when the post-deploy check passes within 10 minutes [Q8].
- **NFR7 Visibility.**
  - Each CI, staging-check and promotion run writes a job summary with its result and the commit SHA.
  - A failed post-deploy check marks the run failed, so it is visible on the commit.

## Constraints

- **Host:** Streamlit Community Cloud. It runs a single Streamlit process per app and deploys by tracking a GitHub branch. There is no deploy API [memory:M1].
- **CI platform:** GitHub Actions, since the repository is on GitHub [memory:M1].
- **Hard rules from `project.md`:**
  - commit via `/commit`;
  - never bypass the lint gate;
  - no publish or submit from a pipeline or check;
  - no exposure without a sign-in layer;
  - the backend is never reachable from outside;
  - no hosted deploy with the hard-coded secret;
  - SHA-pinned Actions and OIDC-only cloud credentials;
  - CI is the authoritative gate [memory:M1].
- **Testing:**
  - TDD ordering for new code.
  - Python 3.10 compatibility for all code, because CI runs 3.10 [memory:M1].
- **Single-process limit:** the in-memory backend means one backend per app process [desc].

## Assumptions

- [assumption] Streamlit Community Cloud supports `st.login` (OpenID Connect) with credentials supplied through app secrets, and can install from a hash-pinned `requirements.txt`. Owner: the NFR Requirements stage, to confirm.
- [assumption] Google is the OpenID provider for the owner's sign-in. Any provider `st.login` supports satisfies FR5.
- [assumption] Public Streamlit Cloud apps are acceptable because FR5 enforces sign-in in-app. Private-app slots are not needed [Q2].
- [assumption] No container image is built in this piece of work, so the agreed Trivy scan has nothing to scan. It applies if an image is introduced later.

## Out of Scope

- **Persistence of data and the audit log across redeploys.** This is a known, deferred gap. Staging and production reset to seeded data, with an empty audit trail, on every deploy or restart, until a follow-up piece of work adds a datastore. The team practice "data and audit log both survive a redeploy" remains the goal [Q1] [Q12].
- **A hosted backend reachable by the local MCP server.** Only the dashboard is deployed. The MCP server, subagents and slash commands stay local and CI-tested [Q9] [Q11].
- **Rewriting git history** to remove the old secret [Q10].
- **Binding signed-in emails to fixed personas, and hiding `user_dev_tester`** [Q4].
- **Uptime monitoring, alerting, or an availability target** [Q8].

## Assumptions & Open Questions

- **Local development sign-in.** FR5 requires sign-in, and `st.login` needs OIDC settings. Should local runs (`streamlit run dashboard/app.py` on localhost) also require sign-in, using a local `secrets.toml`, or should there be a local-only exemption? Q6 chose "no fallback" for the secret. The NFR Requirements stage must decide this explicitly, without weakening FR5 for hosted apps.
- **Proving the new commit is live.** Streamlit Cloud gives no deploy API or commit marker. FR6.2 and FR7.3 need a way to know the redeploy finished before checking, for example a build identifier shown on the sign-in page. To be decided in NFR Design.
- **The health endpoint on Streamlit Cloud.** Confirm that `/_stcore/health` is reachable from GitHub Actions for a Cloud app. If not, FR8.1 falls back to checking the sign-in page alone.
- **Free-tier limits.** Confirm that two public Cloud apps from one repository on different branches are allowed.

## Traceability

| ID | Source |
|----|--------|
| FR1, FR2 | [desc], team practices (Way of Working, Testing Posture, Code Style), Q6/Q9/Q10/Q11/Q13/Q14 of practices |
| FR3 | practices Q4, Q6, Q10, hard rule "no hosted deploy with the hard-coded secret" |
| FR4 | practices Q2 (Streamlit Cloud, single process), Q11, hard rule "backend never reachable from outside" |
| FR5 | Q2, Q3, Q4, Q7, hard rule "no exposure without a sign-in layer" |
| FR6, FR7 | [desc], practices Q3, Q5 |
| FR8 | Q7, Q8, hard rule "no publish/submit from a pipeline or check" |
| FR9 | practices Q12 |
| FR10 | [desc], Q5, Q6, Q10 |
| NFR1–NFR7 | team practices, hard rules, Q8 |
