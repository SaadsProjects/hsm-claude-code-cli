# Unit Test Instructions — U5 postdeploy-check

## Framework and Setup

- `pytest` from `requirements-dev.txt`, plus `playwright`, which this unit adds to the dev lock (Step 2). After installing the dev lock, run `python -m playwright install chromium` once to fetch the browser. CI does this in the `browser-tests` job and caches the browser.
- `tests/conftest.py` already skips `browser`-marked tests unless the `-m` expression names `browser`. It also supplies the signing secret and a temp `HSM_AUDIT_PATH`, which the launched app inherits.
- `tests/browser_app.py` (new) is the test-only entry script. It patches the identity seam from an environment variable and runs `dashboard/app.py`.

## Running This Unit's Tests

The runner check before the first Red step (Step 1):

```bash
python3 -m pytest tests/test_ci_check_workflows.py tests/test_conftest_markers.py -q
```

This unit's ordinary tests, which count toward `.test-floor`:

```bash
python3 -m pytest tests/test_postdeploy_check.py tests/test_ci_browser_watch.py tests/test_postdeploy_workflow.py -q
```

This unit's browser tests, which need Chromium and don't count toward `.test-floor`:

```bash
python3 -m pytest tests/test_postdeploy_browser.py -m browser -q
```

The check by hand, against a running app:

```bash
python3 scripts/postdeploy_check.py http://127.0.0.1:8501 --timeout 30
```

## Test Files and Volume (Standard strategy)

| File | Component | Tests (at least) |
|------|-----------|------------------|
| `tests/test_postdeploy_check.py` | Check script, no browser | 10: three usage errors (exit 2); `classify` for pass, not-gated (tabs), not-gated (marker and tabs), waking (each wording), not-app; selectors from markers; AST read-only scan |
| `tests/test_postdeploy_browser.py` (`browser`) | Check and gate in Chromium | 7: harness health; exit 0 on Screen 1 with only Screen 1 visible; exit 1 against a tabs-without-gate double; exit 1 against a plain page; exit 3 on a closed port within about 10 s; Screen 2 for a verified but unlisted email; Screen 2 for an unverified email |
| `tests/test_ci_browser_watch.py` | Watch list and marks | 4: required paths on the list; every browser test file on the list; every project source a browser test imports or launches on the list; no test both `perf` and `browser` (or reuse of an existing check) |
| `tests/test_postdeploy_workflow.py` | Manual workflow | 5: `workflow_dispatch` only; `contents: read` only; no `secrets.`; every `uses:` pinned by a 40-hex SHA; inputs passed through `env` |

## Coverage Targets

- `scripts/` and `tests/` aren't measured (`.coveragerc`), so this unit adds no measured code and repository coverage stays where it is. The script is held to its own tests instead, as the team's rule for pipeline helpers says.
- The passing count stays at or above `.test-floor` (745), and coverage at or above `.coverage-floor` (95.00). Neither floor file nor `.coveragerc` is touched.

## Mocking and Stubbing

- **Identity:** `tests/browser_app.py` reads an identity JSON from an environment variable and patches `auth_gate.current_identity` before running the app. Nothing else is patched, and Google is never contacted.
- **Test doubles for failing checks:**
  - a tiny Streamlit script that renders `st.tabs` in a block keyed `markers.APP_TABS` and no gate;
  - a plain `http.server` page;
  - a closed port, found by binding port 0, reading the port back and releasing it.
- **Servers:** every server binds `127.0.0.1` on a port found through port 0, and is stopped in fixture teardown.
- **Secrets:** each launched app gets a temp `.streamlit/secrets.toml`, written under `tmp_path` and pointed to by Streamlit's `--secrets.files` option, with placeholder auth keys and an allowlist of `allowed@example.com`. No real credential exists anywhere.

## Test Data

- Identities:
  - signed out;
  - `stranger@example.com`, verified (not on the allowlist);
  - `allowed@example.com` with `email_verified: false` (unverified).
- Timeouts: 3 s for the closed-port case; 60 s for the harness health wait; 30 s for a check against the harness.
