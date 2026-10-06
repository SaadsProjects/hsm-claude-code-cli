# Infrastructure Design Questions — U1 secret-fail-closed

## Sources

- `construction/secret-fail-closed/nfr-design/security-design.md` (D1–D5) and `logical-components.md`
- `.github/workflows/ci.yml` (10 required jobs; `secrets` runs gitleaks and `scripts/check_burned_secret.py`; tests run with plain `python -m pytest tests/`)
- `memory/team.md` Testing Posture (CI exports no signing secret of its own; tests generate one) and Way of Working (pull request 1 is the secret removal)

U1 needs no hosting, no new services and no new CI job. One CI point is open.

## Q1. Should CI prove that the tests don't depend on a secret from the environment?

A. Yes: the `tests` job asserts that `HSM_SIGNING_SECRET` is unset before running pytest, so a passing run proves the suite brings its own secret
B. No: CI simply doesn't set it, and that is enough
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- CI secret check (Q1): the `tests` job asserts that `HSM_SIGNING_SECRET` is unset before running pytest, so a passing run proves the suite brings its own secret.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
