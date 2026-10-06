# Unit Test Instructions — U2 embedded-backend

## Framework and Setup

- pytest, from the hash-pinned dev lockfile (`pip install --require-hashes -r requirements-dev.txt`), using the project's `.venv`.
- No new configuration. `tests/conftest.py` already sets a fresh `HSM_SIGNING_SECRET` and a temp `HSM_AUDIT_PATH` per run.
- Python 3.10 and 3.14 must both pass.

## How to Run This Unit's Tests

The tests run with this exact command from the repository root:

```bash
python3 -m pytest tests/test_embedded_backend.py tests/test_dashboard_embedded.py -q
```

Before Step 2 creates these files, the runner check (Step 1) uses existing files with the same runner:

```bash
python3 -m pytest tests/test_mcp_tools.py tests/test_hooks.py -q
```

## Scope and Volume (Standard Strategy)

| Component | Test file | Tests |
|-----------|-----------|-------|
| Audit readiness query | `test_embedded_backend.py` | 3 |
| Start on loopback and imports | `test_embedded_backend.py` | 3 |
| Secret refusal | `test_embedded_backend.py` | 2 |
| Audit directory and readiness | `test_embedded_backend.py` | 6 |
| One backend per process | `test_embedded_backend.py` | 3 |
| Liveness and replacement | `test_embedded_backend.py` | 7 |
| Logging | `test_embedded_backend.py` | 2 |
| Concurrency and start time | `test_embedded_backend.py` | 2 |
| Client address and guard | `test_dashboard_embedded.py` | 3 |
| Dashboard wiring, Screen 4, caption | `test_dashboard_embedded.py` | 5 |

That is about 36 tests. The embedded server is exercised for real on loopback; the dashboard is exercised with `AppTest`.

## Coverage Targets

- Every branch of `mock_hsm/embedded.py` (refusal, audit directory failures, audit unavailable, bind failure, reuse, replacement) is covered, as are the new lines in `mock_hsm/audit.py`, `dashboard/session.py` and `dashboard/app.py`.
- The whole suite stays at or above `.coverage-floor` and the 80% gate. The test count stays at or above `.test-floor`.
- Neither floor file, nor `.coveragerc`, is edited to make a run pass.

## Mocking and Stubbing

- Each test that starts a backend resets the module's holder in a fixture and retires any server it started, so tests never share an instance.
- The audit-directory tests unset `HSM_AUDIT_PATH` with `monkeypatch.delenv` and redirect `tempfile.gettempdir` to `tmp_path`.
- A bind failure is forced by occupying the port first; a connect timeout is simulated by replacing the module's connect function with one that raises `socket.timeout`.
- `AppTest` runs patch the dashboard's start seam (plan P7) to return a failed handle for Screen 4, and let it start a real backend otherwise.
- Servers bind port 0. No new fixed port. No network outside loopback.

## Test Data

- Secrets come from `tests/conftest.py`; refusal tests set `HSM_SIGNING_SECRET=""` or a short value built in code.
- A corrupt audit trail is a temp file holding one unreadable newline-terminated line.
- Every assertion on a log or screen checks that the secret value is absent.
