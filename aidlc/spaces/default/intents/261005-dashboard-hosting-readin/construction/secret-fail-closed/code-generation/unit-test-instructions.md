# Unit Test Instructions — U1 secret-fail-closed

## Framework and Setup

- pytest, from the hash-pinned dev lockfile (`pip install --require-hashes -r requirements-dev.txt`), using the project's `.venv`.
- No new configuration. `tests/conftest.py` sets a fresh `HSM_SIGNING_SECRET` per run (Step 2), and the existing audit-trail fixtures stay unchanged.
- Python 3.10 and 3.14 must both pass.

## How to Run This Unit's Tests

The tests run with this exact command from the repository root:

```bash
python3 -m pytest tests/test_signing_secret.py tests/test_secret_entry_points.py -q
```

Before Step 2 creates these files, the runner check (Step 1) uses an existing file with the same runner:

```bash
python3 -m pytest tests/test_hooks.py -q
```

## Scope and Volume (Standard Strategy)

| Component | Test file | Tests |
|-----------|-----------|-------|
| Secret gate (`require_secret`, `SecretMissingError`, mint/verify) | `test_signing_secret.py` | 8 |
| Local loader | `test_signing_secret.py` | 7 |
| Burned-literal removal (Step 13) | `test_signing_secret.py` | 3 |
| Test-session secret | `test_signing_secret.py` | 2 |
| Backend start and 503 | `test_secret_entry_points.py` | 6 |
| Start script | `test_secret_entry_points.py` | 2 |
| Publish hook | `test_secret_entry_points.py` | 3 |
| MCP tools and `.mcp.json` | `test_secret_entry_points.py` | 2 |
| Dev-secret script | `test_secret_entry_points.py` | 5 |
| `.gitignore` | `test_secret_entry_points.py` | 2 |

That is about 40 tests. Process boundaries (the server, both scripts, the hook) are tested as real subprocesses: these are the integration tests for the unit's key boundaries.

## Coverage Targets

- New and changed lines in `mock_hsm/auth.py`, `mock_hsm/server.py`, `mcp_server/hsm_tools.py` and `.claude/hooks/` are covered, including subprocess runs (`.coveragerc` subprocess support).
- The whole suite stays at or above `.coverage-floor` (95.00) and the 80% gate. The test count stays at or above `.test-floor`.
- Neither floor file, nor `.coveragerc`, is edited to make a run pass.

## Mocking and Stubbing

- Use `monkeypatch.setenv` and `monkeypatch.delenv` for the secret inside one process.
- For subprocesses, pass an explicit `env`. Set `HSM_SIGNING_SECRET=""` to simulate a missing secret, so a developer's real `.env.local` is never read (plan P4).
- The loader and the dev-secret script get paths in `tmp_path` (`load_local_secret(path=...)`, `dev-secret.sh --file ...`). No test writes the real `.env.local`.
- Servers bind port 0, or a free port found by binding port 0 first. No new fixed port.
- No network access outside loopback.

## Test Data

- Secrets are generated with `secrets.token_urlsafe(32)`. Length-edge values are built in code (`"a" * 31`, `"a" * 32`, and a multi-byte string).
- The burned value is read at test time from `.gitleaks.toml` (plan P3). No tracked test file contains it.
- Every assertion on a message checks that the secret value is absent.
