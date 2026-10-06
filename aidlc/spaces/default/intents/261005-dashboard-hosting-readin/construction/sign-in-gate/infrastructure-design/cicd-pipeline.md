# CI/CD Pipeline — U3 sign-in-gate

## Sources

- `.github/workflows/ci.yml` (the 10 required jobs plus `matrix`), `requirements.in` and `requirements-dev.in` (compile commands)
- `nfr-design/security-design.md` S8 (dependency); `nfr-design/performance-design.md` P1–P3; `nfr-design/logical-components.md` Test Seam and Floors
- `nfr-requirements/security-requirements.md` NFR7.11; `performance-requirements.md` NFR2.11, NFR3.11
- `infrastructure-design-questions.md` Q1 A, Q2 A (summary confirmed)
- `memory/team.md` Way of Working (one pull request for the intent; ruleset `main_branch_protection`), Testing Posture (floors, `perf` never in CI, browser-test watch list) and Code Style (lockfiles); `memory/project.md` Mandated (required-check names change with the ruleset) and Forbidden (never commit `.streamlit/secrets.toml` or `.env.*`)

## Decision: no pipeline change in U3 (Q2 A)

U3 changes no job, step, trigger, permission, action pin or required check in `.github/workflows/ci.yml`. The ruleset's 10 required checks therefore stay as they are, and project.md's rule that a job rename travels with a ruleset change doesn't come into play. The watch-list extension, the first browser test, the meta-test and the browser-test retry stay with U5.

## How the existing gates exercise U3

| Required check | What it proves for U3 | U3 input that drives it |
|----------------|-----------------------|-------------------------|
| `lint` | `ruff check` and `ruff format --check` pass on the new modules. The gate's single broad catch carries `# noqa: BLE001 -- <reason>` (S3) | `dashboard/auth_gate.py`, `secrets_bridge.py`, `markers.py`, the test helper |
| `workflow-lint` | Unchanged workflows still pass | None |
| `secrets` | gitleaks finds no secret in history, and the burned-secret check passes. `.streamlit/secrets.toml.example` holds only placeholders and sets no `HSM_SIGNING_SECRET` (infrastructure-specification) | The example file |
| `audit` | `pip-audit` over the hash-pinned locks finds no high or critical advisory in Authlib or its dependencies, with no new `security-exceptions.toml` entry (NFR7.11) | Both lockfiles |
| `sast` | bandit finds no high-severity issue in `dashboard/`. The gate opens no subprocess, file or socket of its own (P2) | New modules |
| `lock-check` | `requirements.txt` and `requirements-dev.txt` match their `.in` files (NFR7.11) | `streamlit[auth]==1.64.0` in `requirements.in` |
| `tests (3.10)`, `tests (3.14)` | The whole suite, including the 66 existing dashboard tests moved onto the shared helper, passes with a count at or above `.test-floor`, and Authlib installs on both Pythons (NFR3.11, NFR7.11). The "no signing secret in the job environment" step still holds: tests get their secret from `tests/conftest.py` | All U3 tests |
| `coverage-gate` | Line coverage over `dashboard/` and the other measured packages stays at or above `.coverage-floor` and 80% (NFR3.11). The margin is about one point (unit-of-work), so the seam-based tests cover the sign-in wiring | New modules and tests |
| `browser-tests` | Runs, because `dashboard/auth_gate.py` and `dashboard/markers.py` are watched. With no `browser`-marked test yet, pytest exits 5, which the job accepts as a pass | Watched files |

`perf`-marked timing tests (P1) never run in CI. The `tests` jobs call plain `python -m pytest tests/` with no `-m`, so `tests/conftest.py` keeps skipping them (team.md Testing Posture; project.md Forbidden).

## Build and change procedure

1. Edit `requirements.in`: `streamlit==1.64.0` becomes `streamlit[auth]==1.64.0`.
2. Recompile both locks with the commands at the top of each file, then commit them in the same change:
   - `uv pip compile requirements.in --universal --generate-hashes --python-version 3.10 --no-header -o requirements.txt`
   - `uv pip compile requirements-dev.in --universal --generate-hashes --python-version 3.10 --no-header -o requirements-dev.txt`
3. Write failing tests first, then the code, following team.md's TDD ordering. Order: the shared helper's own test (review item R-06 from the NFR design), the gate behaviour and fail-closed tests, then the dashboard wiring.
4. Commit through `/commit`, so the `code-reviewer` subagent and the ruff hook run (project.md Mandated).
5. Push to the intent's working branch. The draft pull request's CI is the unit's verification (`gh pr checks --required`, the recorded Construction Verification Command). It is green when all 10 required checks pass.

## Deployment and promotion

- U3 deploys nothing. No hosted app exists until the intent's pull request merges and the owner creates both apps in U6 (team.md Order). Merging U3 alone therefore exposes nothing.
- After U6, staging redeploys on every merge to `main`, and production moves only through the gated promotion. Both are unchanged by U3.

## Secrets in CI/CD

- CI holds no signing secret, cookie secret, OAuth client or allowlist, and U3 adds none. Every value the tests need comes from `tests/conftest.py` (the signing secret) and the shared helper (dummy sign-in settings and allowlist in `AppTest` secrets).
- The real hosted values live only in each app's Streamlit secrets (C7, U6). `.streamlit/secrets.toml`, `.env` and `.env.*` stay git-ignored by the explicit `.gitignore` lines (project.md Forbidden).

## Rollback

- **Before merge:** revert the U3 commits on the intent's working branch. The other units' commits are unaffected, because U3's files are new apart from `app.py`, the lockfiles, `requirements.in`, CLAUDE.md and the three dashboard test files.
- **After merge, before U6:** revert the squash commit on `main` through a pull request. No hosted app exists, so nothing redeploys.
- **After U6:** never roll back only the gate. Reverting it would expose the persona picker on a public app, which project.md forbids. Roll back to an earlier commit that already had the gate (team.md Rollback), or take the app offline in the Streamlit Cloud console while fixing forward.

## Assumptions & Open Questions

- [assumption] Authlib, pulled in by `streamlit[auth]==1.64.0`, publishes wheels or a pure-Python sdist that installs on Python 3.10 and 3.14. The `tests` legs prove it. If 3.14 fails, the fix is a lock refresh to a compatible Authlib release, not a skipped leg.
- [assumption] gitleaks' default rules don't flag the angle-bracket placeholders in `.streamlit/secrets.toml.example` (for example `<per-app OAuth client secret>`). If they do, the placeholders change wording. No allowlist entry is added for them.
