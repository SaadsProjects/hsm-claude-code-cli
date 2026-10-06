# CI/CD Pipeline — U2 embedded-backend

## Sources

- `.github/workflows/ci.yml` (current jobs and required checks)
- `memory/team.md` Way of Working, Testing Posture, Deployment
- `infrastructure-design-questions.md` Q2 (A)

## Pipeline Changes

None. U2 changes no workflow file, job, step, permission or required check (Q2 A).

## How U2 Is Built and Gated

1. U2's code and tests land on the intent branch cut from the updated `main` (after pull request 1 merges), test-first, through `/commit`.
2. The intent's pull request runs the existing required checks. U2's tests run in `tests (3.10)` and `tests (3.14)` with plain `python -m pytest tests/`; the new module under `mock_hsm/` counts toward `coverage-gate`.
3. U2's timing tests (NFR2.1–NFR2.3) are ordinary tests and run in those jobs; none is `perf`- or `browser`-marked.
4. The `browser-tests` watch list is unchanged. U2 touches `dashboard/app.py` and `dashboard/session.py`, which are not on it; browser tests arrive with U3 and U5.

## Stage → Gate Mapping

| Stage | Gate (existing required check) |
|-------|-------------------------------|
| Lint and format | `lint` |
| Tests on both Python legs | `tests (3.10)`, `tests (3.14)` |
| Coverage floor and 80% gate | `coverage-gate` |
| Secrets, dependencies, SAST, locks | `secrets`, `audit`, `sast`, `lock-check` (no new dependency, so no lock change) |
| Workflow lint | `workflow-lint` (no workflow change) |
| Browser tests | `browser-tests` (reports success without running, since no watched file changes) |

## Deployment and Rollback

Deployment is unchanged: staging redeploys on merge to `main`; production moves only by the gated promotion. No hosted app exists until U1–U3 have merged (team.md Deployment order). Rollback is a revert on `main` or moving the production pointer back, then re-running the post-deploy check.

## Secrets in CI

None added. CI exports no `HSM_SIGNING_SECRET` (the U1 CI step fails the tests job if one is set); tests generate their own (`tests/conftest.py`) and set `HSM_AUDIT_PATH` to a temp file, so the NFR1.13 tests unset it and redirect the temp directory explicitly.

## Assumptions & Open Questions

None.
