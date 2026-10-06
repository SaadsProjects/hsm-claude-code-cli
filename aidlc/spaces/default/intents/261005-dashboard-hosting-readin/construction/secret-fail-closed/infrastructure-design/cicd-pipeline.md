# CI/CD Pipeline — U1 secret-fail-closed

## Sources

- `.github/workflows/ci.yml` (required jobs `lint`, `workflow-lint`, `secrets`, `audit`, `sast`, `lock-check`, `tests (3.10)`, `tests (3.14)`, `coverage-gate`, `browser-tests`)
- `construction/secret-fail-closed/nfr-design/security-design.md` (D1–D5), `logical-components.md`
- `infrastructure-design-questions.md` Q1
- `memory/team.md` Way of Working, Testing Posture; `memory/project.md` M1, M2

U1 adds no hosting, no service and no new CI job. Its delivery is pull request 1. The only workflow change is one step inside the existing `tests` job, so no required check is renamed and no ruleset change is needed (M2).

## Delivery Steps

1. Branch `secret-fail-closed` from `main`.
2. Commit the changes test-first through `/commit`. Removing the burned literal, emptying `TEMPORARY_EXCLUSIONS` and adding the regression tests are one commit, and it comes last (M1, D5).
3. Open pull request 1 into `main`. CI runs every required job.
4. Merge by squash once all 10 required checks are green. GitHub deletes the branch.
5. The U1 checkpoint is verified on that pull request (the verification command still needs your approval at that checkpoint).

## Stage → Gate Mapping for Pull Request 1

| Job | What it proves for U1 | Change in U1 |
|-----|------------------------|--------------|
| `secrets` | gitleaks passes over full history (the allowlist stays); `check_burned_secret.py` passes with an empty `TEMPORARY_EXCLUSIONS` | None to the job; the script's exclusion entry is removed |
| `tests (3.10)`, `tests (3.14)` | The suite passes with a secret the tests generate themselves; the test floor holds | New first step in the job: fail if `HSM_SIGNING_SECRET` is set in the job environment, before pytest (Q1) |
| `coverage-gate` | New code in `mock_hsm/auth.py`, `mock_hsm/server.py` and the hooks keeps coverage at or above `.coverage-floor` | None |
| `lint` | `ruff check` and `ruff format --check` pass, including the `noqa` reasons | None |
| `sast` | Bandit shows no high-severity finding in the new loader or file handling | None |
| `audit`, `lock-check` | No dependency change | None |
| `workflow-lint` | The edited `ci.yml` passes actionlint and `scripts/check_workflows.py` | None |
| `browser-tests` | No watched file changes in U1, so it passes without running browser tests | None |

## The New CI Step (Q1)

- **Where:** in the `tests` job, before "Test suite" and "Test suite with coverage", on every matrix leg.
- **Behaviour:** if `HSM_SIGNING_SECRET` is set and non-empty in the job environment, print a message naming the variable (never the value) and fail the job.
- **Hygiene:** it uses a plain `run` step, so it adds no third-party action. Job `permissions` stay `contents: read`.

## Secrets Management in CI

- CI holds no signing secret and exports none (team.md Testing Posture). Tests generate a fresh one per run in `tests/conftest.py`.
- No repository secret is added for U1.

## Rollback

- Before merge: close the pull request; `main` is unchanged.
- After merge: revert the squash commit on `main` through a pull request. This brings back the burned literal and its exclusion together. That is safe because the burned-secret check expects that pair.
- No hosted environment exists yet, so nothing else needs redeploying.

## Assumptions & Open Questions

None.
