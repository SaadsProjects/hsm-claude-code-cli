# Build Instructions — Dashboard Hosting Readiness

## Sources

- Per-unit `construction/*/code-generation/code-summary.md` and `unit-test-instructions.md` (U1 secret-fail-closed to U6 staging-app)
- `CLAUDE.md` § Commands; `README.md`; `.github/workflows/ci.yml` (the authoritative gate)
- `memory/team.md` Testing Posture and Code Style

## Prerequisites

- Python 3.10 or newer (CI tests 3.10 and 3.14; the staging app runs 3.14).
- `uv` 0.12.15, only to check or recompile the lockfiles.
- Chromium for the browser tests, installed once with `python -m playwright install chromium` after the dev lock.
- No other services. Tests start their own backends; the dashboard runs its backend in-process.

## Dependency Installation

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt   # dev/test lock; requirements.txt is the hosted runtime lock
python -m playwright install chromium                    # only for -m browser and the post-deploy check
```

Both locks are hash-pinned. Edit only `requirements.in` and `requirements-dev.in`, and recompile with the `uv pip compile` command at the top of each file.

## Environment Setup

- **Signing secret:** run `scripts/dev-secret.sh` once per clone. It writes `HSM_SIGNING_SECRET` to the git-ignored `.env.local` with mode 600. There is no fallback secret: without one, every entry point refuses to run.
- **Tests need nothing extra.** `tests/conftest.py` generates a throwaway secret and a temp `HSM_AUDIT_PATH` per run.
- **Dashboard sign-in, locally:** copy `.streamlit/secrets.toml.example` to the git-ignored `.streamlit/secrets.toml`. With its placeholders, the gate shows the sign-in screen. A real local sign-in needs your own Google OAuth client and your email in `HSM_ALLOWED_EMAILS`.
- **Hosted (staging):** the app's Streamlit secrets carry all seven keys. See `docs/staging-app.md`.

## Build Commands

This is a Python project with nothing to compile or bundle. "Building" means installing the hash-pinned locks and passing the static gates CI runs:

```bash
ruff check .                     # lint, rules pinned in ruff.toml
ruff format --check .            # formatting
python3 scripts/check_workflows.py .github/workflows
python3 scripts/check_burned_secret.py
# Lock check, the way CI runs it: start from the committed locks
cp requirements.txt /tmp/requirements.txt; cp requirements-dev.txt /tmp/requirements-dev.txt
uv pip compile requirements.in --universal --generate-hashes --python-version 3.10 --no-header -o /tmp/requirements.txt
uv pip compile requirements-dev.in --universal --generate-hashes --python-version 3.10 --no-header -o /tmp/requirements-dev.txt
diff -u requirements.txt /tmp/requirements.txt && diff -u requirements-dev.txt /tmp/requirements-dev.txt
```

## Build Verification

```bash
python3 -m pytest tests/ -q                                         # full suite (perf and browser skipped by default)
coverage run -m pytest tests/ -q && coverage combine -q && coverage json -q
python scripts/test_floor.py junit.xml                              # with --junitxml=junit.xml on the run above
python3 scripts/coverage_gate.py --coverage-json coverage.json --floor-file .coverage-floor
streamlit run dashboard/app.py                                      # starts the gated dashboard with its own backend
```

The authoritative verification is the pull request's CI run with all 10 required checks green (`gh pr checks --required`).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "HSM_SIGNING_SECRET is not set" from the backend, hook or MCP tools | No `.env.local` and nothing exported | `scripts/dev-secret.sh` |
| The dashboard shows only "Sign-in isn't available right now." | Missing or placeholder sign-in keys, a bad allowlist, or a signing secret equal to `cookie_secret` | Check `.streamlit/secrets.toml` against the example; the cause is in the app log |
| The lock check differs only by newer upstream versions | It was compiled from scratch instead of from the committed locks | Copy the committed locks first, as above |
| Port 8772 or 8773 already in use | Two test runs at once; `test_mcp_tools.py` and `test_hooks.py` use fixed ports | Run the suite serially; never with `-n` |
| `-m browser` errors with "Executable doesn't exist" | Chromium isn't installed | `python -m playwright install chromium` |
| The commit hook blocks every commit | `ruff` missing or lint dirty | Install from the dev lock; fix and re-stage |
