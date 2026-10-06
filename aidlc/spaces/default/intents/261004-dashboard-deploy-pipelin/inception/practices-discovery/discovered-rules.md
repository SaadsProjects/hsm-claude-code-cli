# Discovered Rules

Hard rules the human confirmed at the practices-discovery interview (Q15:
groups A, B and C). Group A restates existing rules from the repository's
`CLAUDE.md`, group B comes from the quality review, and group C comes from the
security review.

## Mandated

- ALWAYS commit through `/commit`, so the `code-reviewer` subagent reviews the staged diff before `git commit` runs. *(group A; source: `CLAUDE.md` § "Committing changes to this project", `.claude/commands/commit.md`)*
- ALWAYS fix ruff lint errors and re-stage when the lint gate blocks a commit, and install `ruff` rather than working around a missing one. *(group A; source: `CLAUDE.md` § Commands, `.claude/hooks/lint_before_commit.py`)*
- ALWAYS point the test audit trail at a temporary file (`HSM_AUDIT_PATH` via `tests/conftest.py`), including in CI, so no test or pipeline run writes the real `mock_hsm/audit/audit.jsonl`. *(group A; source: `CLAUDE.md` audit-trail paragraph, `tests/conftest.py`)*
- ALWAYS keep the two write tools, `publish_schedule` and `submit_purchase_order`, behind `ask` rules in `.claude/settings.json`, and re-add those rules after any `aidlc config --force`. *(group A; source: `CLAUDE.md` § Architecture, "Gating of writes")*
- ALWAYS run the CI test suite with plain `python -m pytest tests/` (or an explicit `-m "not perf"`), never with an unrelated `-m` expression. *(group B; source: `tests/conftest.py::pytest_collection_modifyitems`, which only skips `perf` when no `-m` is given)*
- ALWAYS pin third-party GitHub Actions by full commit SHA and give every workflow least-privilege `permissions`. *(group C, R-SEC-4; source: devsecops review)*
- ALWAYS authenticate pipeline deploys and any cloud access from CI with short-lived OIDC credentials. *(group C, R-SEC-5; source: devsecops review)*
- ALWAYS run lint, the test suite, the secret scan and the dependency audit in CI as required status checks before any deploy; the local commit hook stays, but CI is the authoritative gate. *(group C, R-SEC-6; source: devsecops review, `.claude/settings.local.json.example` shows the local hook is opt-in)*

## Forbidden

- NEVER bypass the `lint_before_commit.py` gate, for example by committing outside `/commit`, using `--no-verify`-style workarounds, or using `git -C`/`GIT_INDEX_FILE` to dodge the check. *(group A; source: `CLAUDE.md` § "Committing changes to this project", `.claude/commands/commit.md`)*
- NEVER call `publish_schedule` or `submit_purchase_order` from a pipeline, smoke check, or deploy step unless the human explicitly asks for it. *(group A; source: `CLAUDE.md` § "Non-negotiable rules")*
- NEVER give the dashboard a publish-schedule or submit-PO path; outside "Manage data", the dashboard's only POST is the side-effect-free `/labor/rules/validate`. *(group A; source: `CLAUDE.md` dashboard paragraph, enforced by a test)*
- NEVER run the `perf`-marked timing tests in CI or let them block a merge or deploy; they are machine-dependent by design. *(group B; source: `tests/conftest.py`, interview Q11)*
- NEVER lower the coverage floor, or narrow the measured package set, to make a pipeline run pass. *(group B; source: `org.md` § Testing Posture, "may not be weakened to make a step pass")*
- NEVER expose the dashboard beyond loopback or a private network without a sign-in layer in front of it. *(group C, R-SEC-1; source: devsecops review, interview Q1)*
- NEVER make the mock backend reachable from outside the dashboard's own host, container or process. *(group C, R-SEC-2; source: devsecops review)*
- NEVER deploy beyond localhost with the hard-coded signing secret in `mock_hsm/auth.py`; hosted deploys read it from the environment and fail closed when it is missing. *(group C, R-SEC-3; source: devsecops review, interview Q4)*
- NEVER store long-lived cloud access keys as repository secrets. *(group C, R-SEC-5; source: devsecops review)*
