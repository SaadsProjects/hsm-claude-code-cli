# Practices Discovery — Evidence

This is a brownfield first run of practices discovery. The `infra` scope skips
reverse engineering, so the upstream artifacts `code-structure`,
`technology-stack`, `dependencies`, `code-quality-assessment`, `architecture`
and `business-overview` do not exist for this intent. The repository's own
`CLAUDE.md`, `README.md`, `dashboard/README.md` and `docs/ARCHITECTURE.md`
stood in for them. Before this run, `aidlc/spaces/default/memory/team.md` had
every section empty. `project.md` held two learnings from
`261004-dashboard-writes`, and neither one is about deployment.

## Sources

- Initial description: "set up a deployment pipeline for the dashboard" [desc]
- [scope] Workflow-selected scope: `infra`.
- Depth: Standard. The `infra` scope declares `skeleton: on`
  (`.claude/scopes/aidlc-infra.md`).
- Repository at commit `1586133` (`main` = `origin/main`).
- Lead draft: `aidlc-pipeline-deploy-agent`.
- Blind support reviews: `contributions/aidlc-quality-agent.md`,
  `contributions/aidlc-developer-agent.md`,
  `contributions/aidlc-devsecops-agent.md`.
- Completed interview: `practices-discovery-questions.md` (Q1 to Q15, plus the
  consolidated summary, which the human confirmed as "Looks correct").

## What each participant inspected

### Lead (aidlc-pipeline-deploy-agent)

| Area | Source | Finding |
|---|---|---|
| History | `git log` (17 commits, 2026-09-23 to 2026-10-04) | One human author under two identities (`Saadullah Ahmed` locally, `saad` for GitHub PR merges). Commits come in short bursts. |
| Branching | `git log --merges`, `git branch -a` | Two non-squash PR merges on 2026-09-26 (#1, #2), then direct pushes to `main`. The only other branch is the local safety snapshot `backup/pre-rollback-2026-10-03`. |
| Commit style | `git log` subjects | One imperative summary line. No conventional-commit prefixes, tags or releases. |
| Rollback precedent | `2eb1a8d` (revert), `1586133` (restore) | Rollback has so far been done with git reverts and restores on `main`. |
| CI/CD config | repo root | None: no `.github/`, Dockerfile, Procfile, Makefile or IaC. |
| Dashboard runtime | `.streamlit/config.toml`, `dashboard/README.md` | Binds `127.0.0.1`, 2 MB upload cap, no password. |
| Backend | `agents/hsm_client.py:21`, `mock_hsm/auth.py:23` | In-memory backend at `HSM_BASE_URL`. Tokens are signed with the literal `demo-shared-secret-not-for-production`. Gated writes return 503 when the audit file is unavailable. |
| Commit gates | `.claude/commands/commit.md`, `.claude/hooks/lint_before_commit.py` | `code-reviewer` subagent, then a ruff hook that fails closed. The hooks are registered only in the gitignored `settings.local.json`. |
| Write gating | `.claude/settings.json` | `ask` rules on `publish_schedule` and `submit_purchase_order`. |
| Dependencies | `requirements.txt` | Lower bounds only, no lockfile. |
| Repo visibility | `gh repo view` | `SaadsProjects/hsm-claude-code-cli` is **public**. |

### Quality (aidlc-quality-agent)

- Re-ran the suite: 757 collected, 745 passed, 12 `perf` skipped, 86.7 s on
  Python 3.14.7 (pytest 9.1.1). `ruff check .` passes with ruff 0.16.8. This
  replaced the remembered figure of about 735 tests.
- Found that any `-m` expression switches off the default `perf` skip
  (`tests/conftest.py`), and that the fixed ports 8772 and 8773 make
  `pytest-xdist` unsafe.
- Flagged `tests/test_hsm_client_writes.py:854` (a timing assertion that is not
  marked `perf`) as the most likely CI flake.
- Confirmed there is no coverage tool, and that `mcp_server/` and
  `.claude/hooks/` run mostly in subprocesses, so plain `pytest --cov` would
  under-report them.
- Proposed the ordered CI gates and the three testing rules (group B).

### Developer (aidlc-developer-agent)

- Confirmed the naming and style conventions and the `noqa: BLE001 -- <reason>`
  convention for broad catches.
- Corrected the layer-boundary wording: the ban on importing `mock_hsm.db`
  applies to the MCP tool layer. The dashboard imports `mock_hsm.db.USERS`
  (`dashboard/app.py:33`) and `mock_hsm.auth.mint_token`
  (`dashboard/session.py:25`), so it must ship with `mock_hsm`.
- Built the runtime inventory: the backend's bind address is hard-coded
  (`mock_hsm/server.py`), state is in memory so only one backend instance can
  exist, `HSM_BASE_URL` is read at import time, and `/healthz` and
  `/_stcore/health` are usable health targets.
- Noted that adopting a formatter should be its own commit.

### Security (aidlc-devsecops-agent)

- Verified that the dashboard holds the signing secret in-process (F1), that
  login is a persona picker with no credential (F2), and that the secret is a
  literal in tracked source (F3).
- Wrote a brief STRIDE summary: the risk depends almost entirely on who can
  reach the app.
- Proposed CI security gates (pinned ruff, bandit, gitleaks, `pip-audit`
  against a hash-pinned lock, Trivy, SHA-pinned Actions, OIDC) and rules
  R-SEC-1 to R-SEC-6 (group C).

## Interview decisions

| Q | Topic | Answer |
|---|---|---|
| Q1 | Who can reach it | C: the internet, but only behind a sign-in layer |
| Q2 | Host | D: Streamlit Community Cloud |
| Q3 | Environments | B: staging deploys on merge, production needs manual approval |
| Q4 | Signing secret | A: environment variable (Streamlit secrets when hosted), fail closed outside local dev |
| Q5 | Data and audit log on redeploy | C: both persist |
| Q6 | Path to `main` | A: PR with required CI checks, protected `main`, squash-merge |
| Q7 | Walking skeleton | B: yes, and it proves the security checks run and that strangers are kept out |
| Q8 | Test methodology | B: TDD |
| Q9 | Coverage scope | A: all app code, subprocess-run code measured |
| Q10 | Python | B: CI matrix 3.10 and 3.14 |
| Q11 | Perf and flaky tests | B: perf tests never run in CI, a flaky test may be retried once |
| Q12 | Dependencies | A: hash-pinned lockfile with a runtime/dev split |
| Q13 | Security checks | A, B, C, D, E: all five |
| Q14 | Formatter | B: adopt `ruff format`, checked in CI |
| Q15 | Hard rules | A, B, C: all three groups |

The human confirmed the consolidated summary ("Looks correct"). In that
summary, Q7's second security property is stated as "the sign-in layer blocks
strangers" rather than the option's original wording ("the backend port is not
reachable from outside"). With Streamlit Cloud the backend runs in-process on
loopback, so the confirmed summary wording is the one recorded in
`team-practices.md`. The rule that the backend is never reachable from outside
(R-SEC-2) still stands.

## How objections were resolved

- **Developer: layer-boundary wording.** Accepted. `team-practices.md` now says
  the ban covers the MCP tool layer and that the dashboard ships with
  `mock_hsm`.
- **Quality: stale suite figure.** Accepted. The measured baseline (757 / 745 /
  12 / 86.7 s) replaces the remembered one.
- **Quality: the coverage floor framed as optional.** Accepted. Q9 asked only
  how the floor is measured, not whether it applies.
- **Quality: PR versus direct push framed as a preference.** Accepted. Q6 named
  the "CI before merge" constraint, and the human chose required PR checks.
- **Quality: xdist note.** Accepted. The fixed-port warning is in Testing
  Posture.
- **Quality: no automatic retries (G3).** The human decided otherwise (Q11 B):
  a flaky test may be retried once. A test that fails its retry still blocks.
- **Security: deploy-on-merge must not put an unauthenticated app on a
  reachable host.** Resolved by Q1 C and Q2 D. Both apps are private, behind
  the viewer allowlist.
- **Security: the skeleton should prove security gates.** Accepted (Q7 B).
- **Security: dependency pinning is supply chain, not style.** Accepted. It was
  asked as its own question (Q12). The human promoted the security rules
  (group C) but not a separate pinning rule, so pinning is recorded as a
  practice, not a hard rule.
- **Security: add security candidates to the rules.** Accepted (Q15 C).
- **Org fit: a production branch.** `org.md` says to gate releases with tags
  or environment-specific deployment config rather than long-lived release
  branches. Streamlit Cloud deploys by tracking a branch, so production tracks
  its own branch. To stay within the org rule, that branch is a deployment
  pointer: nobody commits to it, and it only moves to a commit that already
  passed CI on `main`.

## Assumptions & Open Questions

- [assumption] Both git identities (`Saadullah Ahmed` and `saad`) are the same
  person, so this is a solo project.
- [assumption] The `backup/pre-rollback-2026-10-03` branch is a one-off safety
  snapshot and not part of the branching model.
- **Open (a): persistence is bigger than a pipeline.** Q5 C requires a
  persistent datastore for the backend's data and audit trail, which are in
  memory and on the local filesystem today. That is a backend change, not
  pipeline configuration. Requirements Analysis should size it and decide
  whether to split it into its own unit or intent.
- **Open (b): Streamlit Cloud private-app limits.** The free tier's limits on
  private apps and viewer allowlists must be confirmed for two private apps
  (staging and production) before the environment design is final.
- **Open (c): the signing secret is already public.** The repo is public
  (`gh repo view`), so the literal secret in `mock_hsm/auth.py:23` has already
  been disclosed. Moving it to the environment, with a new value that has
  never been in source, is a prerequisite before any hosted deploy. The old
  value also needs an explicit gitleaks allowlist entry with a reason, or the
  history scan will flag it on every run.
- **Open (d): single process.** Streamlit Cloud runs one process, so the mock
  backend must start inside the dashboard process, bound to loopback. The
  backend's host and port are hard-coded today (`mock_hsm/server.py`). The
  in-process start is a code change for Construction.
- **Open (e): platform fit of other choices.** Streamlit Cloud builds from a
  requirements file it finds itself and offers a fixed set of Python versions.
  Requirements Analysis should confirm that the hash-pinned runtime lockfile is
  in a form Cloud installs, which Python version the hosted apps run, and that
  it is one of the CI matrix versions. Cloud builds no image, so the Trivy
  check (Q13 E) applies only if CI builds one. Deploys on Cloud pull from git
  and need no CI cloud credentials, so the OIDC rule binds any cloud access CI
  adds later (for example, for the datastore).
- **Open (f): not asked at the interview.** Security gate thresholds (block on
  Critical/High or Critical only) and waiver policy (devsecops SQ3), whether
  all data is synthetic (SQ4), whether `user_dev_tester` is hidden in hosted
  environments (SQ2), and how the post-deploy check can confirm the audit path
  is writable without writing a business record (quality G7). These go to
  Requirements Analysis.
