# Unit Test Instructions — U6 staging-app

## Framework and Setup

- `pytest` from `requirements-dev.txt`. No new dependency or configuration.
- The test reads repository files only (`docs/staging-app.md`, `.streamlit/secrets.toml.example`). It starts no server and no browser and needs no secret, so it runs the same locally and in CI.
- Python 3.10 has no `tomllib`, so key names come from a line pattern over the example file, `^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=`. A self-test pins what that reader returns.

## Running This Unit's Tests

The runner check before the first Red step (Step 1):

```bash
python3 -m pytest tests/test_postdeploy_check.py -q
```

This unit's tests:

```bash
python3 -m pytest tests/test_staging_runbook.py -q
```

A single behaviour, for example the secret keys:

```bash
python3 -m pytest tests/test_staging_runbook.py -k keys -q
```

## Test Files and Volume (Standard strategy)

| File | Component | Tests (at least) |
|------|-----------|------------------|
| `tests/test_staging_runbook.py` | Staging runbook (`docs/staging-app.md`) | 6: the runbook exists; it names every key from the secrets example; it says the signing and cookie secrets differ; it names `dashboard/app.py` and `main`; it gives the post-deploy check command and the `/oauth2callback` path; the key reader returns exactly the seven expected names from the example file |

The staging app itself is proven by the owner's steps (plan Step 7), not by tests in this repository. The browser tests from U5 stay loopback-only, and only the post-deploy check reaches staging.

## Coverage Targets

- No measured file changes (`docs/` and `tests/` are not measured), so repository coverage is unchanged and stays at or above `.coverage-floor` (95.00) and the 80% gate.
- The passing count rises by the new tests and stays at or above `.test-floor` (745). No floor file, `.coveragerc` omit or `# pragma: no cover` is touched.

## Mocking and Stubbing

- None. The tests read the real files. The self-test for the key reader also runs it on a small string written to `tmp_path`, so a change to the example file's layout is caught separately from a missing key.

## Test Data

- The seven expected keys: `HSM_SIGNING_SECRET`, `HSM_ALLOWED_EMAILS`, `redirect_uri`, `cookie_secret`, `client_id`, `client_secret`, `server_metadata_url`.
- No real URL, email, client id or secret appears in the runbook or the tests; the runbook uses placeholders such as `<staging-app>`.
