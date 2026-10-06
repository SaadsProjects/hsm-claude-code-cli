# Quality Gates — Dashboard Deployment Pipeline (CI)

## Sources

- `construction/nfr-requirements/*.md` NFR1.9 to NFR1.14, NFR2.1, NFR2.2, NFR3.1, NFR4.1, NFR5.1 to NFR5.3 [requirements]
- `construction/infrastructure-design/cicd-pipeline.md` stage → gate summary [cicd-pipeline]
- `ci-pipeline-questions.md` CQ1 to CQ3

## Merge gates (all required on `main` once the ruleset is applied)

| Gate | Job | Pass criterion | Fails on | NFR |
|---|---|---|---|---|
| Lint | `lint` | ruff 0.16.8 reports nothing | any `ruff check` finding | NFR5.2 |
| Format | `lint` | `ruff format --check .` is clean | any unformatted file | Code Style practice |
| Workflow policy | `workflow-lint` | actionlint and `check_workflows.py` are clean | unpinned action, missing version comment, missing top-level `permissions`, secret on a `run:` line, `promote.yml` without the main guard | NFR1.9 |
| Secret scan | `secrets` | gitleaks finds no leak in full history | any finding outside the value allowlist | NFR1.10, NFR1.11 |
| Burned secret | `secrets` | the digest scan is clean | the burned value in any tracked file outside the exclusions; **a temporary exclusion whose file no longer holds the value** | NFR1.3, NFR1.11 |
| Dependency audit | `audit` | no high or critical vulnerability | OSV label HIGH/CRITICAL, CVSS ≥ 7.0, no severity found, a failed lookup, or a pip-audit tool error (exit ≥ 2) | NFR1.12 |
| Exceptions register | `audit` | every entry valid | an expired entry, one longer than 90 days, or one missing its id, tool, reason or dates | NFR1.14 |
| SAST | `sast` | no high-severity bandit finding | a HIGH finding not in the register, or a file bandit could not scan | NFR1.13 |
| Lock freshness | `lock-check` | the recompiled locks match | any diff | NFR5.1, NFR5.3 |
| Tests | `tests (3.10)`, `tests (3.14)` (+ hosted Python) | 0 failures after one retry | any failure after retry; step longer than 5 min | NFR2.2, NFR4.1 |
| Test floor | `tests (*)` | passed ≥ `.test-floor` (745) | below the floor; `.test-floor` lowered compared with the base branch | NFR4.1 |
| Coverage | `coverage-gate` | total ≥ `.coverage-floor` (95.00), and ≥ 80 since the floor is ≥ 80 | below either; `.coverage-floor` lowered compared with the base branch | NFR3.1 |
| Browser tests | `browser-tests` | passes, or no browser test affected or present | any failure in `pytest -m browser` | NFR6.2 (enabled by the follow-up) |
| Whole run | all | finishes within 15 min | job timeouts (10 or 15 min) | NFR2.1 |

## Gate behaviour rules

- **No bypass.** The ruleset bypass list is empty. Gates are changed only by a reviewed PR that itself passes them.
- **Floors only rise.** A PR may raise `.test-floor` or `.coverage-floor`, never lower them. The measured coverage set in `.coveragerc` is fixed.
- **Retries are visible.** A test that passed only on its retry is listed by name in that leg's job summary.
- **Fail closed.** The audit filter blocks when severity can't be determined, and the burned-secret check blocks on a stale exclusion.
- **Perf and browser tests stay out of plain runs.** `tests/conftest.py::skip_reason` skips `perf` unless some `-m` is given and `browser` unless `-m browser` is given. Plain `pytest tests/` is the CI invocation.

## Not gates (yet)

| Item | Status |
|---|---|
| Staging check, promotion, production check | Deployment Pipeline stage (next) |
| Playwright browser tests | Follow-up application work. The job no-ops until then |
| Lock refresh if Dependabot `uv` doesn't raise PRs | Watch for two weeks after merge. If no Python PR appears, add a scheduled lock-refresh workflow (infrastructure finding R-01) |

## Assumptions & Open Questions

- None beyond those in `ci-config.md`.
