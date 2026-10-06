# Project-Level Rules

> Project-specific specialisation and corrections. Loaded after `org.md` and
> `team.md` as strict-additive guidance; contradictions with broader policy
> are rejected. Populated by practices-discovery and the self-learning loop.
>
> Use sparingly: most teams don't need a project layer. Reach for it
> only when this specific project needs stable, durable guidance beyond the
> team practice (for example, package-specific release checks or an additional
> regression suite for a legacy component).

## Way of Working

<!-- Project-specific specialisation. Example: -->
<!-- This monorepo requires package-scoped branch names and a package owner -->
<!-- review in addition to the team's normal merge policy. -->

## Walking Skeleton

<!-- Project-specific specialisation. Example: -->
<!-- The walking skeleton must exercise the legacy service adapter as well -->
<!-- as the new service boundary. -->

## Testing Posture

<!-- Project-specific specialisation. -->

- With no requirements or NFR artifacts in this workflow, the target inventory was built from the Testing Contract and the unit-test instructions' coverage targets, and cross-unit traceability used the plan's own R1-R8. (learned 2026-10-04) <!-- cid:261004-dashboard-writes:build-and-test:44aa729367b9658c5887f1bb2952628fffdf77ce96009fae17226300c0a072dd -->

- Initial CI floors are set with headroom below the local measurement (coverage floor 95.00 against 96%, test floor 745 against 811 passing) so runner differences don't fail the first run; floors only ever rise afterwards. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:ci-pipeline:f237f82629ea60733499491f4798e5a7bfc6dd31603591d48d1541d2adbbf4a3 -->

- When an intent's main pull request has to merge before its hosted work (such as creating the staging app), Build and Test raises the test and coverage floors in a small follow-up pull request, which becomes the intent's final one. (learned 2026-10-06) <!-- cid:261005-dashboard-hosting-readin:build-and-test:440a263bf19e56df495795646f2e6d11fe1095978ff6d3975acc878707beed64 -->

- A whole-app hosted target that no unit's NFR record owns (such as the 30-second cold start from a sleeping app) goes to performance-validation, and Build and Test surfaces it as open rather than counting it in its own target matrix. (learned 2026-10-06) <!-- cid:261005-dashboard-hosting-readin:build-and-test:e95e9940887fa3030094f163d00a6a876f5dfd00f5e759decc08d55363fac9d9 -->

- When floors are raised, the test floor is set about 8% below the measured passing count and the coverage floor about 1 point below measured coverage, so runner differences don't fail CI. (learned 2026-10-06) <!-- cid:261005-dashboard-hosting-readin:build-and-test:412f75ce68b314c956e979f1a4abd03daa2a0c2bce16919f5dc38026b579e69c -->

- A hosted cold-start target such as NFR2's 30 seconds from waking is measured after an owner-triggered reboot of the Streamlit app, because a reboot restarts the container just as a wake does and can be repeated on demand. (learned 2026-10-06) <!-- cid:261005-dashboard-hosting-readin:performance-validation:b67b989e5a4877517cac15b35fb4a0e42f4bd42262b8d87aab30cf4fabfc719e -->

- The signed-in part of a hosted timing check runs from Google returning the visitor to the app until the dashboard shows its tabs, so time spent in Google's own sign-in screens is not counted against the app. (learned 2026-10-06) <!-- cid:261005-dashboard-hosting-readin:performance-validation:dac06fc4e1393d5911c8c90a1ac8934322da540d14b9f11a088c0c623af9042b -->

## Guard Policy

<!-- Project-specific. Mode: strict, relaxed, or off. Strict here holds for every intent and cannot be changed from chat. A section under the retired Change Control heading, written by an earlier release, is still read. -->

## Deployment

<!-- Project-specific specialisation. -->

- Hosted Streamlit Cloud apps are kept public and gated by in-app st.login plus an email allowlist rather than private viewer-allowlisted apps, because the free tier limits private-app slots. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:requirements-analysis:42217273a0f73eab297c19e42e566cf9dd6ab6b36ed7e8f450486d80686b4514 -->

- Hosted builds identify themselves by commit SHA with a source-fingerprint fallback, so post-deploy checks do not depend on .git being present in the Streamlit Cloud checkout. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:nfr-requirements:ff32013fc9c421424e06f52333d3f45e656036c35c07d8fdb60ba499337190b3 -->

## Code Style

<!-- Project-specific specialisation. -->

- Keep mock_hsm/auth.py standard-library only; framework-specific bridges (such as copying Streamlit secrets into the environment) belong in the dashboard, because auth.py is shared with the MCP server and hooks. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:nfr-requirements:a577daca271fa1bb192e057a407e220c20be1192f7fa869909c9ce1b265a2bdc -->

## Tech Stack

<!-- Technology choices locked for this project. -->

## Decided

<!-- Decisions made in earlier stages that should not be re-asked. -->
<!-- Format: DECIDED: [decision] (Stage [slug], [date]) -->

## Scope Overrides

<!-- Custom scope rules for this project. -->

## Forbidden

<!-- Populated by practices-discovery affirmation gate. -->
<!-- Format: NEVER [behavior] (affirmed [date]) -->
<!-- Example: NEVER throw exceptions across service layer boundaries (affirmed 2026-05-17) -->

- NEVER bypass the `lint_before_commit.py` gate, for example by committing outside `/commit`, using `--no-verify`-style workarounds, or using `git -C`/`GIT_INDEX_FILE` to dodge the check. *(group A; source: `CLAUDE.md` § "Committing changes to this project", `.claude/commands/commit.md`)* (affirmed 2026-10-04)

- NEVER call `publish_schedule` or `submit_purchase_order` from a pipeline, smoke check, or deploy step unless the human explicitly asks for it. *(group A; source: `CLAUDE.md` § "Non-negotiable rules")* (affirmed 2026-10-04)

- NEVER give the dashboard a publish-schedule or submit-PO path; outside "Manage data", the dashboard's only POST is the side-effect-free `/labor/rules/validate`. *(group A; source: `CLAUDE.md` dashboard paragraph, enforced by a test)* (affirmed 2026-10-04)

- NEVER run the `perf`-marked timing tests in CI or let them block a merge or deploy; they are machine-dependent by design. *(group B; source: `tests/conftest.py`, interview Q11)* (affirmed 2026-10-04)

- NEVER lower the coverage floor, or narrow the measured package set, to make a pipeline run pass. *(group B; source: `org.md` § Testing Posture, "may not be weakened to make a step pass")* (affirmed 2026-10-04)

- NEVER expose the dashboard beyond loopback or a private network without a sign-in layer in front of it. *(group C, R-SEC-1; source: devsecops review, interview Q1)* (affirmed 2026-10-04)

- NEVER make the mock backend reachable from outside the dashboard's own host, container or process. *(group C, R-SEC-2; source: devsecops review)* (affirmed 2026-10-04)

- NEVER deploy beyond localhost with the hard-coded signing secret in `mock_hsm/auth.py`; hosted deploys read it from the environment and fail closed when it is missing. *(group C, R-SEC-3; source: devsecops review, interview Q4)* (affirmed 2026-10-04)

- NEVER store long-lived cloud access keys as repository secrets. *(group C, R-SEC-5; source: devsecops review)* (affirmed 2026-10-04)

- NEVER let the post-deploy check sign in as an allowlisted user, or store identity-provider sign-in credentials in CI. *(F1; source: interview Q11)* (affirmed 2026-10-05)

- NEVER commit `.streamlit/secrets.toml`, `.env`, `.env.local` or any other `.env.*` file; ignore them with explicit `.gitignore` lines outside the AI-DLC-managed block. *(F2; source: interview Q11, CQ-9)* (affirmed 2026-10-05)

## Mandated

<!-- Populated by practices-discovery affirmation gate. -->
<!-- Format: ALWAYS [behavior] (affirmed [date]) -->
<!-- Example: ALWAYS use Result<T,E> for fallible operations in service layer (affirmed 2026-05-17) -->

- ALWAYS commit through `/commit`, so the `code-reviewer` subagent reviews the staged diff before `git commit` runs. *(group A; source: `CLAUDE.md` § "Committing changes to this project", `.claude/commands/commit.md`)* (affirmed 2026-10-04)

- ALWAYS fix ruff lint errors and re-stage when the lint gate blocks a commit, and install `ruff` rather than working around a missing one. *(group A; source: `CLAUDE.md` § Commands, `.claude/hooks/lint_before_commit.py`)* (affirmed 2026-10-04)

- ALWAYS point the test audit trail at a temporary file (`HSM_AUDIT_PATH` via `tests/conftest.py`), including in CI, so no test or pipeline run writes the real `mock_hsm/audit/audit.jsonl`. *(group A; source: `CLAUDE.md` audit-trail paragraph, `tests/conftest.py`)* (affirmed 2026-10-04)

- ALWAYS keep the two write tools, `publish_schedule` and `submit_purchase_order`, behind `ask` rules in `.claude/settings.json`, and re-add those rules after any `aidlc config --force`. *(group A; source: `CLAUDE.md` § Architecture, "Gating of writes")* (affirmed 2026-10-04)

- ALWAYS run the CI test suite with plain `python -m pytest tests/` (or an explicit `-m "not perf"`), never with an unrelated `-m` expression. *(group B; source: `tests/conftest.py::pytest_collection_modifyitems`, which only skips `perf` when no `-m` is given)* (affirmed 2026-10-04)

- ALWAYS pin third-party GitHub Actions by full commit SHA and give every workflow least-privilege `permissions`. *(group C, R-SEC-4; source: devsecops review)* (affirmed 2026-10-04)

- ALWAYS authenticate pipeline deploys and any cloud access from CI with short-lived OIDC credentials. *(group C, R-SEC-5; source: devsecops review)* (affirmed 2026-10-04)

- ALWAYS run lint, the test suite, the secret scan and the dependency audit in CI as required status checks before any deploy; the local commit hook stays, but CI is the authoritative gate. *(group C, R-SEC-6; source: devsecops review, `.claude/settings.local.json.example` shows the local hook is opt-in)* (affirmed 2026-10-04)

- ALWAYS remove the burned signing-secret literal from `mock_hsm/auth.py` and its `TEMPORARY_EXCLUSIONS` entry in `scripts/check_burned_secret.py` in the same commit, with regression tests that the burned-secret check passes, that a missing secret raises a clear error, and that the secret is read at call time. *(M1; source: interview Q11, CQ-2, scope decision D9)* (affirmed 2026-10-05)

- ALWAYS change a required CI job's name and the `main_branch_protection` ruleset's required-check list in the same piece of work, because a required check that never reports blocks every pull request. *(M2; source: interview Q11)* (affirmed 2026-10-05)

## Corrections

<!-- Project-specific corrections from human feedback. -->
<!-- Format: NEVER/ALWAYS [behavior] (learned [date]) -->
- The human's "build on a189674 instead of starting fresh" was read as a byte-for-byte restore of that commit plus hand merges of CLAUDE.md and .gitignore; the commit and its tests stand in for the skipped requirements and unit artifacts. (learned 2026-10-04) <!-- cid:261004-dashboard-writes:code-generation:1bf2bd8234743109f24b9845024125488de55d2048591b008c325705be523d21 -->
- The OIDC-only deploy-credential rule was kept even though Streamlit Cloud pulls from GitHub and needs no cloud credentials; it is vacuously satisfied today and binds if a cloud host is added later. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:practices-discovery:92c66895277f866d697307d3e77dc13f5bbdadb0655c8020cd1c4f03f076e4b2 -->
- The rule bundle was passed to delegated agents by file path (org.md, project.md, phases/inception.md) instead of pasted verbatim; the files are its exact source, so path delivery keeps briefs small without changing content. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:practices-discovery:6b08d003d6c4cd7fb0b42ce68bd48592e83e2843cbbef6e794544bc93b20409b -->
- When an interview answer conflicts with a just-approved hard rule, ask a follow-up and treat the follow-up answer as superseding it, keeping both answers visible in the questions file (Q11 dashboard-only superseded Q9 hosted backend). (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:requirements-analysis:6872505eaaef713c5b01ea04660aec23e05cf1f8c4cc34ec782b800c04ed4f50 -->
- Before presenting an unanswered question, reword an option that would contradict an earlier answer in the same stage (Q10 option A was reworded so the burned secret was not a local test default, matching Q6). (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:requirements-analysis:71192a24805dfae18e36fafd53ecf7bd001392e03795814950d07827946709c3 -->
- Write AI-DLC stage artifacts with the Write/Edit tools, never shell heredocs; the write hook only records tool writes, and an unrecorded artifact blocks the review request until it is re-saved. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:nfr-requirements:fbe3b6f43db16d9ebe4237431403b6b9599679adcb5b25e024bb5bed223ae429 -->
- Never rewrite approved AI-DLC record files to satisfy a source scan; exclude the record tree (aidlc/spaces/*/intents/**) by documented path instead, because those files are audit evidence. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:nfr-design:c1662a6ead69b7796ac9a4f1d7e7e36201254c457ef74f81d43f07c134c820db -->
- A GitHub required status check must always report: conditional jobs run every time and no-op successfully when not needed, because a required check that never reports blocks every PR. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:infrastructure-design:28ef61e3892763a4a9c663d5c210742059ac9845c52135e6098b1a2582c07c38 -->
- security-exceptions.toml applies to both pip-audit and bandit through report filters (filter_audit.py, filter_bandit.py); do not suppress findings with inline nosec comments instead of a register entry with a reason and expiry. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:ci-pipeline:3f63e3b60a24d4fb64e7d566f8aa8e9dedd07dd801476d2507ca260365d5447f -->
- The infra scope has no code-generation or build-and-test stage; when its designs require application code changes, check that before CI Pipeline and plan them as a separate piece of work with code generation and tests. (learned 2026-10-04) <!-- cid:261004-dashboard-deploy-pipelin:ci-pipeline:8f7d0cfacb7684c3f6bfaa8fa44f1e44ecf7c35bac7e5896c156e61a79951ea7 -->
- When an intent's description lists changes already designed in an earlier intent, the ideation artifacts restate each change in plain outcome terms tagged [desc] rather than carrying the implementation detail. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:intent-capture:2239b45fc5e7680d74ed041feb756af2be155acbe12ca847132fdda00c22bbed -->
- When a multi-select answer combines a None or Not-applicable option with real options, treat it as a contradiction and resolve it with a follow-up question rather than guessing. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:feasibility:877b6494bd96939e6e91e60ed5a2674682195770538bdff6a7df2123343c89e2 -->
- Every error or refusal screen in the dashboard keeps a way out (Sign out or reload) so a visitor is never trapped. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:rough-mockups:771fa48c2a9808a57e7b69040cdc44c0a60b620b5c5e56f5ffdf4220b81b07cf -->
- Mockups for a change wireframe only the screens the change adds or alters; unchanged existing screens are referenced, not redrawn. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:rough-mockups:80103b869d73731f558705dcbc3a0d72e44c048c71fbc5bb48afe757690b0a6d -->
- At Approval & Handoff, ask only what earlier ideation stages left open (typically risk acceptance and go/no-go); topics already settled or skipped are cited, not re-asked. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:approval-handoff:78de112fab7a40c2f403672185d9a5014defe5dbc02206aa4db2849c80b64a3c -->
- Code scans treat AI-DLC framework files (aidlc/, .claude framework dirs) as tooling and skip them, but analyze the project's own .claude hooks, subagents, commands and settings as project code. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:reverse-engineering:2eedf4a8d95be316d250f52641b0c1754b053a7ec6b0400cf03f413302ec66ec -->
- On a practices-discovery re-run, interview only on what the lead draft and the three reviews left open; carry forward points all three reviewers agree on without asking. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:practices-discovery:dadd65b0156595079df2e38d1874a15bdab25dbea2592979bfa0d30d8850bcf8 -->
- When a lead folds a practice into the drafts that the human did not explicitly confirm, flag it by name at the approval gate instead of letting it pass silently. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:practices-discovery:2681bf63a524960f6a131d520a2a36e3db68c3bc154e861a77d07446077da478 -->
- The post-deploy check does not assert the build identifier (it never signs in, and the build caption shows only after sign-in); the owner confirms the build on an environment by signing in and reading the sidebar caption. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:user-stories:456f013b3d8045cc4e8106d2a9347e700795d9f9d79042b09cf13a0c1bb770b7 -->
- A refusal caused by the system (broken sign-in settings or a gate error) gets its own neutral screen, separate from the screen for a visitor who isn't allowed, so the wording never blames the visitor. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:refined-mockups:532e7f11797319953b00f189c2b9003cecc156ed4d5f52ceca4fee486db3fb1c -->
- Brownfield domain designs catalogue only the components a piece of work adds or changes; test fixtures, repository config, lockfiles and docs are marked N/A in traceability rather than modelled as components. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:domain-design:631933185e089898af19522a14f7dff7ca6a84874db7af2274745f3512357d92 -->
- In the dashboard hosting work the first unit is the secret-removal pull request alone; the walking-skeleton proof at its checkpoint is that pull request merging green with every entry point failing closed, and the local sign-in-screen half of the slice is checked when the sign-in-gate unit completes. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:units-generation:efa0364e2bb0a90884647d6e4a2bb4298dee50cbaa5277bfacf9fd557c8e38d4 -->
- When units share a process and no network API sits between them, contract design specifies in-process Python interfaces, settings schemas (environment and Streamlit secrets), shared constants modules and command lines in fenced YAML or TOML blocks instead of OpenAPI. (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:contract-design:e919a86f87aa69782e88496f810168965a7a923dee5efb3d9daa20dcd97bbd4f -->
- Because a finished unit is proven by its pull request's CI run with all required checks green, work that ships as one pull request opens it as a draft at the start, so each unit checkpoint can read the branch's required checks (gh pr checks --required). (learned 2026-10-05) <!-- cid:261005-dashboard-hosting-readin:delivery-planning:ccfcc6befe50370516d90c1545d560ab54c74fe33ffd4eb11acd8c6d16674983 -->
- Per-unit code-generation traceability.json files also cite the parent FR and NFR IDs a unit implements, not only story ACs and NFRx.y IDs, so the Build and Test cross-unit gate passes without patching already-reviewed records. (learned 2026-10-06) <!-- cid:261005-dashboard-hosting-readin:build-and-test:2ee61e14277862d20a338dff246b31977b6af399e0f44ce024f370a9d3e7926f -->
- When an answer gives a vague quantity (such as "wait a fixed few minutes"), propose a concrete value in the consolidated summary so the human confirms the number (the staging check's wait was set to 180 seconds that way). (learned 2026-10-06) <!-- cid:261004-dashboard-deploy-pipelin:deployment-pipeline:6ff90fc6be74671b745e9708f4b989f92ed60e348fda105b0a9f6f8d7ffa4c3d -->
- When the human removes an environment mid-workflow, the workflow is re-fitted by skipping the stages that only served it, and its pieces (workflows, GitHub Environment, deploy key, branch ruleset) are dropped from the remaining design; the approved requirement and design records that mention it stay as written. (learned 2026-10-06) <!-- cid:261004-dashboard-deploy-pipelin:deployment-pipeline:95e006230369e4dcdceae7170729f9399886ebcb5e0d43aac899e09b3acd5cd9 -->
- A pipeline workflow calls the post-deploy check with only the arguments its shipped contract (C8) defines, a URL and --timeout; flags or commit statuses from an earlier design are dropped when nothing consumes them. (learned 2026-10-06) <!-- cid:261004-dashboard-deploy-pipelin:deployment-pipeline:9dba8f6affa9df76a006f69dea612f064eeb5dc2a987a1cb6da883e9e7a8d606 -->
- An automatic run of an existing manual workflow goes in its own push-triggered workflow file rather than adding a trigger to the manual one, so the manual workflow keeps its tested dispatch-only contract. (learned 2026-10-06) <!-- cid:261004-dashboard-deploy-pipelin:deployment-pipeline:bce008e5db759b47d62323a73091ab725031231be2777ffa841c487324c47ff6 -->
