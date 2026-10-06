# Practices Discovery Evidence

> Lead: `aidlc-pipeline-deploy-agent`, brownfield re-run, lead draft (Step 2) and
> integration (Step 5). Support reviews: `aidlc-quality-agent`,
> `aidlc-developer-agent`, `aidlc-devsecops-agent` (files under
> `contributions/`). Interview: `practices-discovery-questions.md` (Q1–Q15 and
> the Consolidated Summary Confirmation, answered "Looks correct").
> Commit `825a0f8` (`825a0f8d0a87df19d1b774367c77197b95840178`), 2026-10-05.

## Baseline

- `aidlc/spaces/default/memory/team.md`: the five sections affirmed on
  2026-10-04 (intent `261004-dashboard-deploy-pipelin`). This is the current
  baseline.
- `aidlc/spaces/default/memory/project.md`: the standing `## Mandated`,
  `## Forbidden`, `## Corrections`, `## Deployment`, `## Testing Posture` and
  `## Code Style` entries.
- `aidlc/spaces/default/memory/org.md`: the framework defaults that `team.md`
  specialises.

## Sources inspected

### Repository and CI

| Source | What it shows |
|---|---|
| `git log` (last 25 commits), `git branch -a`, `git ls-remote --heads origin` | Squash merge of PR #3 as `825a0f8` ("… (#3)"). Earlier commits on 2026-10-03/04 (`1586133`, `14f7b24`) went to `main` before the ruleset existed. Remote branches: `main`, `ci-pipeline` (merged, not deleted), two Dependabot branches (`dependabot/pip/mcp-2.2.0`, `dependabot/pip/python-minor-and-patch-…`). Local branch `backup/pre-rollback-2026-10-03`. |
| `.github/workflows/ci.yml` | 11 jobs: `lint`, `workflow-lint`, `secrets`, `audit`, `sast`, `lock-check`, `matrix`, `tests (3.10/3.14[/HOSTED_PYTHON])`, `coverage-gate`, `browser-tests`. Triggers: pull requests and pushes to `main`, nightly cron, manual. `permissions: {}` at the top and `contents: read` per job; actions pinned by SHA; actionlint and gitleaks downloads checksum-verified. Tests run plain `pytest tests/ -q --reruns 1`; coverage only on 3.14. `browser-tests` runs `-m browser`, no-ops on pull requests unless one of five watched paths changed, and accepts pytest exit 5 because no browser test exists yet. No deploy workflow. |
| Ruleset `main_branch_protection` (id 24043060) | Pull request required, squash only, 10 required checks with strict up-to-date, no bypass. Recorded in the session's project memory note on 2026-10-04; not re-queried through the GitHub API in this draft. |
| `.github/dependabot.yml` | Weekly updates for Actions pins and pip locks, minor and patch grouped. Majors arrive as single pull requests (the open `mcp` 2.2.0 branch is one). |
| `.test-floor`, `.coverage-floor` | 745 and 95.00. |
| `.coveragerc` | Source set `agents`, `dashboard`, `mock_hsm`, `mcp_server`, `.claude/hooks`; `patch = subprocess`; `parallel = true`; `tests/*` omitted. |
| `ruff.toml` | `py310`, line length 120, the rule list stated in `team.md` Code Style. |
| `security-exceptions.toml` | Register format only; no active exception. |
| `requirements.in`, `requirements-dev.in` | Runtime: `streamlit==1.64.0` only. Dev: `-r requirements.in`, `mcp[cli]==1.30.0` (pinned to 1.x on purpose), ruff, pytest and the gate tools. No Authlib, no playwright. |
| `.streamlit/config.toml` | `address = "127.0.0.1"`, `maxUploadSize = 2`. |
| `.gitignore` | `.env.local` is ignored only through `*.local` (line 30) inside the AI-DLC block; `.streamlit/secrets.toml` is not ignored. |
| `tests/conftest.py` | `perf` and `browser` markers; `perf` skipped when no `-m` is given; `browser` skipped unless `-m` names it. |
| `pytest --collect-only -q` (run by the lead, `.venv`, Python 3.14) | 837 tests collected at `825a0f8`. Pass and skip counts and run time were not measured in this draft. |
| `CLAUDE.md` | Commands, CI section, floors and exceptions, dependency rules, burned-secret note. Matches the CI file. |

### Reverse-engineering knowledge base

All under `aidlc/spaces/default/codekb/hsm-claude-code-cli/`:

| Artifact | Used for |
|---|---|
| `code-structure.md` | Module map; `dashboard/app.py` runs at import; `mock_hsm/server.py` `run()` blocks; `HSM_BASE_URL` frozen at import in `agents/hsm_client.py`. Supports the in-process backend and single-instance points in Deployment. |
| `technology-stack.md` | Tool versions, config files, the decided hosting target; Authlib and playwright not present yet. |
| `dependencies.md` | Internal graph, the shared trust root in `mock_hsm.auth`, environment propagation to subprocess tests, the missing dependencies, the affirmed lockfile rules. Supports the Code Style dependency points and the test-secret open point. |
| `code-quality-assessment.md` | Findings CQ-1 to CQ-12. CQ-1 (secret read at call time), CQ-2 (atomic burned-literal removal), CQ-3 (persona picker is the only sign-in), CQ-4 (in-process backend), CQ-5 (persistence conflict with `team.md`), CQ-6 (Authlib and Playwright), CQ-8 (browser-test path watch list), CQ-9 (`.gitignore` gaps), CQ-10 (two `noqa` without reason), CQ-12 (837 tests, floors). |
| `architecture.md` | Layered modular monolith; all three front ends reach the backend through `HsmClient`; state in memory, audit trail on disk. Supports Code Style layer boundaries and the CQ-5 point. |
| `business-overview.md` | The domain and the two gated writes; confirms the read-only smoke-check constraint still matters. |

### This intent's ideation

- `ideation/approval-handoff/decision-log.md`: D1 (sole decision-maker), D2
  (success metrics: CI-gated pull requests, burned-secret check clean, floors
  held, non-allowlisted visitor refused), D6 (Streamlit secrets and GitHub
  Actions; free tier), D7 (risks: sign-in parity, in-process backend, browser in
  CI), D8 (all eight changes required; banner in scope), D9 (burned-secret
  removal first), D10 (hosted apps created in this intent after the changes
  merge), D11 (full process).
- `ideation/scope-definition/scope-document.md`: items 1 to 9, the out-of-scope
  deploy work, and the boundary rules.
- `aidlc-state.md`: scope `feature`, brownfield, Construction Checkpoints
  enabled, unit-major, serial. `.claude/scopes/aidlc-feature.md` declares
  `skeleton: on`.

## Inferences and the evidence behind them

| # | Inference | Evidence | Confidence |
|---|---|---|---|
| I1 | Trunk-based with pull requests and squash merges is how the team works now, and it is enforced. | Ruleset; PR #3 squash commit; repository squash-only setting. | High |
| I2 | AI-DLC's local Bolt squash-merge into `main` cannot be pushed under the ruleset; Bolts must reach `main` through pull requests. | Ruleset (no bypass); `branching-strategies.md` trunk runbook merges into local `main`. The last intent used one branch (`ci-pipeline`) and one pull request. | High on the conflict; the way to resolve it is a human choice |
| I3 | `team.md` and `project.md` disagree on how the hosted apps are protected; `project.md` is the later decision. | `team.md` § Deployment "private … viewer allowlist"; `project.md` § Deployment (learned 2026-10-04 at requirements-analysis) "public … st.login plus an email allowlist"; CQ-3. | High |
| I4 | `team.md`'s "data and audit log survive a redeploy" is not met and this intent plans the opposite (reset banner). | CQ-5; scope item 7; in-memory `mock_hsm/db.py` and `writes._state`; audit file inside the checkout. | High on the conflict; resolution is a human choice |
| I5 | The coverage and test-count numbers in `team.md` are out of date. | `.coverage-floor` 95.00 and the 80% gate in `coverage-gate`; `.test-floor` 745; 837 collected now against 757 in the baseline. | High |
| I6 | `ruff format` has been introduced; the "we introduce it" wording is out of date. | Required `lint` job runs `ruff format --check` and passed on PR #3. | High |
| I7 | This intent adds two dependencies that change the gates: Authlib (runtime lock, `pip-audit`) and playwright (dev lock, `pip-audit`), plus a Chromium download that neither the lock nor `pip-audit` covers. | CQ-6; `ci.yml` `browser-tests` comment; `dependencies.md` § Missing. | High |
| I8 | The baseline Walking Skeleton (deploy to staging first) cannot be the first slice of this intent, because no hosted app may exist until the gate and secret changes merge. | Scope item 9 and D10; boundary rules; `skeleton: on` in the feature scope. | High on the conflict; the replacement slice is a human choice |
| I9 | The Trivy rule has nothing to apply to today. | No image build in `ci.yml`; Streamlit Cloud builds from the repository. | High |
| I10 | `mcp` 2.x would break the MCP server if Dependabot's pull request were merged; the floor and test gates would catch it, but the pull request will keep reappearing. | `requirements-dev.in` comment; remote branch `dependabot/pip/mcp-2.2.0`; `dependabot.yml` has no ignore rule. | Medium (the effect on tests was not run) |

## Drift between the baseline and current evidence

The right-hand column was the lead draft's proposal. The outcome of each row is
in "Interview decisions" below.

| Topic | Baseline says | Evidence says | Draft proposed |
|---|---|---|---|
| App protection | Private apps, viewer allowlist (`team.md`) | Public apps, `st.login`, email allowlist (`project.md`) | Align `team.md` with `project.md` (Deployment open point 2) |
| Data and audit after redeploy | Both survive; persistent store needed | In memory; reset banner in scope (CQ-5) | Accept the reset, amend the rule, or add a store (Deployment open point 1) |
| Coverage floor | 80% | 80% gate plus a 95.00 ratchet floor | State both |
| Test baseline | 757 collected / 745 passed at `1586133` | 837 collected at `825a0f8`; `.test-floor` 745 | Update; re-measure pass counts before Code Generation |
| Required checks | "CI checks are required" | 10 named checks, strict, no bypass | State them |
| Formatter | "We introduce it" | Introduced and enforced | Past tense |
| Smoke check | "Read-only health check" | Planned Playwright post-deploy check (scope item 8) | Name the mechanism and what it asserts |
| Walking skeleton | Deploy-to-staging slice first | Hosted apps come last in this intent | Choose a slice for this intent (Walking Skeleton open point 1) |

## Not inspected or not verified

- The ruleset was not re-read through the GitHub API; its content comes from the
  project memory note written when it was created.
- The full test suite was not run; only collection was. The pass, skip and
  timing figures at `825a0f8` are left for re-measurement.
- The parked intent's designs (`261004-dashboard-deploy-pipelin/construction/`)
  were not re-read; their outcomes are taken from `project.md` § Deployment and
  this intent's scope document.

## Measured figures (kept here, not in `team.md`, per Q8)

| Figure | Value | How measured |
|---|---|---|
| Tests collected | 837 | `pytest tests/ --collect-only -q` by the lead, `.venv`, Python 3.14, commit `825a0f8` |
| `.test-floor` | 745 | File content |
| `.coverage-floor` | 95.00 | File content; the 80% gate is on because the floor is at least 80 (`scripts/coverage_gate.py`) |
| Baseline in old `team.md` | 757 collected / 745 passed / 12 `perf` skipped, 86.7 s | Measured 2026-10-04 at `1586133`; now out of date |
| `ruff check .` / `ruff format --check .` | Clean; "365 files already formatted" | Run by the developer reviewer |

## Participants' positions

### aidlc-quality-agent (`contributions/aidlc-quality-agent.md`)

- Agreed: local walking-skeleton slice, with the pull-request CI run as the proof
  command; the burned-secret removal as its own first pull request; browser tests
  not counted toward `.test-floor`, run on pull requests only against a local app
  with an identity test double; the reset banner as a tested requirement;
  Chromium option (a) with a version-keyed cache; F1, M1, M2, F2; fixing CQ-10
  now.
- Objected: writing floor numbers into `team.md` (adopted, Q8); the
  `browser-tests` bullet without hardening (adopted: drop the exit-5 pass once a
  browser test exists, a watch-list meta-test, a single retry).
- Added: the test floor applies in every matrix leg; coverage is measured on 3.14
  only; the end-of-intent floor ratchet; free ports for new server tests; a
  single-backend test; the marker-hygiene test; the explicit deny in the publish
  hook when the secret is missing, tested first; a pure sign-in decision function
  with its minimum cases.
- Favoured Dependabot ignoring majors for `mcp` and `streamlit` (overruled, Q10).
- Could not run the suite (delegated-agent guard).

### aidlc-developer-agent (`contributions/aidlc-developer-agent.md`)

- Agreed: naming (all error classes and constants conform), formatter in past
  tense, the dependency and exception-register practices, the layer boundaries,
  F2, M1, fixing CQ-10 in the change that already touches the publish hook.
- Objected: the `noqa: BLE001` rule as worded (adopted: two shapes, boundary with
  reason or record-and-re-raise without `noqa`, and only review checks the
  reason); "`auth.py` stays standard-library only" (adopted: "the standard library
  and `mock_hsm` itself").
- Added: `agents/` holds framework-free helpers such as `build_info`; the file
  placement table for hosting code (adopted in Code Style).

### aidlc-devsecops-agent (`contributions/aidlc-devsecops-agent.md`)

- Agreed: aligning `team.md` with `project.md` on public apps with `st.login`;
  M1, M2, F1; F2 widened to `.env` and `.env.*`; dropping M3; Chromium option (a)
  only in jobs without secrets; keeping Trivy as a conditional rule; fixing CQ-10.
- Objected: the "Who can reach it" bullet as untestable (adopted: fail closed
  before any render, verified email required, trimmed lower-cased exact-match
  allowlist, per-environment cookie and signing secrets, and the accepted risk
  that any allowlisted user can pick any persona); the "outside local
  development" carve-out (adopted after Q15: no fallback anywhere); the
  `browser-tests` watch list (adopted: add `requirements-dev.txt` and
  `.github/workflows/ci.yml`).
- Added: a 32-byte minimum for the secret; the secret never in `.mcp.json` or
  other committed config; error messages name the variable, not the value.
- Favoured Dependabot ignoring `mcp` majors only (overruled, Q10: skip none).

## Interview decisions

| Q | Decision | Where it lands |
|---|---|---|
| Q1, refined by Q14 | The burned-secret removal ships first as its own pull request; everything else ships as one pull request at the end. Q1's "one pull request for everything" is superseded by Q14; both answers stay visible in the questions file. | Way of Working |
| Q2 | A local walking-skeleton slice: the secret-removal pull request merges with all 10 required checks green, and the dashboard starts locally behind the sign-in screen. The staging slice stays the team default when hosted apps exist. | Walking Skeleton |
| Q3 | Construction Verification Command: the CI run on the pull request with all 10 required checks green. | Walking Skeleton |
| Q4 | Data and audit trail reset on redeploy; the reset banner stays and is tested; the old "survive a redeploy" rule is replaced. | Deployment, Testing Posture |
| Q5 | Public apps with `st.login`, verified email and an email allowlist kept in each app's Streamlit secrets, maintained by the owner. | Deployment |
| Q6 | The owner alone approves production releases. | Deployment |
| Q7, superseded by Q15 | No committed fallback signing secret anywhere; local development uses the ignored `.env.local` from the dev-secret script; tests generate a throwaway secret per run. | Deployment, Testing Posture |
| Q8 | `team.md` points to `.test-floor` and `.coverage-floor`; measured figures stay in this file. | Testing Posture |
| Q9 | Chromium installed by Playwright, cached by Playwright version, only in jobs that hold no secrets. | Deployment (pipeline hygiene) |
| Q10 | Dependabot skips no major versions. | Way of Working |
| Q11 | M1, M2, F1 and F2 become project rules; M3 dropped as already covered. | `discovered-rules.md` |
| Q12 | `scripts/` stays out of coverage; the post-deploy check is held to its own tests. | Testing Posture |
| Q13 | GitHub auto-deletes merged branches; `ci-pipeline` is deleted; the backup branch is kept. | Way of Working |
| Without asking (all three reviewers agreed) | Trivy applies only if an image is ever built; the two `noqa` comments without a reason are fixed in this work. | Deployment, Code Style |

The Q7 → Q15 sequence follows the `project.md` correction on conflicting
answers: Q7's "keep a fallback" conflicted with the earlier no-fallback decision
and the burned-secret rule, the follow-up Q15 settled it, and both answers stay
visible.

## Remaining uncertainty

- **Suite pass, skip and run time at `825a0f8`** have not been measured; only
  collection was (837). Neither the lead nor the quality reviewer could run the
  full suite. Re-measure before Code Generation, matching CI:
  `coverage run -m pytest tests/ -q --reruns 1 --junitxml=junit.xml`, then
  `coverage combine -q` and `python scripts/test_floor.py junit.xml`.
- **Repository settings are unverified from code**: the ruleset content (taken
  from the project memory note), automatic deletion of merged branches,
  Dependabot alerts and security updates, secret scanning and push protection.
  Check them once in the GitHub settings or through the API.
- **Whether Streamlit Community Cloud enforces the hashes in
  `requirements.txt`** when it installs the runtime lock is unknown. Confirm it
  once from a real build log when the apps are created.
- **The end-of-intent floor ratchet** (raise both floor files, keeping headroom)
  was proposed by the quality reviewer and folded in without a separate question;
  the headroom size is decided at Build and Test.
