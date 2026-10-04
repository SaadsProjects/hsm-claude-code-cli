# Unit Test Instructions — Restore dashboard writes (a189674)

## Framework and setup

- Runner: pytest, using the project virtualenv (`.venv/bin/python`). Tests start
  their own mock servers (ports 8772, 8773 and one ephemeral), so no backend
  needs to be running.
- `tests/conftest.py` (restored from a189674) points `HSM_AUDIT_PATH` at a
  per-test temp file, so tests never write to `mock_hsm/audit/`.
- Dashboard tests use Streamlit's `AppTest`; they need `streamlit>=1.64`
  installed in `.venv` (`.venv/bin/python -m pip install -r requirements.txt`).
- Lint: `.venv/bin/ruff check .` (rules pinned in `ruff.toml`).

## Commands for this unit

Each command is scoped to the files this restore adds or changes:

```bash
# Baseline before restoring anything (existing suite, expected green)
.venv/bin/python -m pytest tests/ -q

# Data model
.venv/bin/python -m pytest tests/test_dashboard_data.py -q
# Audit trail (repository layer)
.venv/bin/python -m pytest tests/test_audit_log.py -q
# Write service (business logic)
.venv/bin/python -m pytest tests/test_writes_core.py tests/test_writes_service.py -q
# API routes and client
.venv/bin/python -m pytest tests/test_writes_routes.py tests/test_audit_routes.py tests/test_hsm_client_writes.py -q
# Dashboard
.venv/bin/python -m pytest tests/test_dashboard_units.py tests/test_dashboard_app.py -q
```

## Coverage targets

- Test strategy is Minimal and this scope adds no coverage floor. The restored
  a189674 tests (about 380 test functions) already exceed one test per
  requirement (R1-R8 in the plan) and a happy path per component.
- Required: every command above passes, and the full existing suite stays
  green (R8).
- Must be covered explicitly: the 503 fail-closed path on publish and PO
  submit when the audit trail is unavailable (R4), and the dashboard having no
  publish/submit/draft action for any persona (R6).

## Mocking and stubbing

- Use the real in-process mock backend started by the tests; do not mock
  `HsmClient` in route or client tests.
- Simulate audit-trail failure through `HSM_AUDIT_PATH` pointing at an
  unwritable location, as the a189674 tests do; do not patch the audit module.

## Test data

- Seeded RNG data from `mock_hsm/db.py`; dates are site-local and shift daily,
  so assertions must not hard-code dates or forecast numbers.
- Personas: `user_rm_midtown`, `user_regional_atl`, and a189674's
  `user_dev_tester`.
