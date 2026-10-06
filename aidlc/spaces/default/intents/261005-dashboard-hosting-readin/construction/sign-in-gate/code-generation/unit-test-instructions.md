# Unit Test Instructions — U3 sign-in-gate

## Framework and Setup

- `pytest` with Streamlit's `streamlit.testing.v1.AppTest`, both from `requirements-dev.txt` (`pip install --require-hashes -r requirements-dev.txt` after Step 2's lock refresh, which adds Authlib through `streamlit[auth]`).
- `tests/conftest.py` already provides a throwaway `HSM_SIGNING_SECRET` per run, a temp `HSM_AUDIT_PATH`, and the default skip of `perf`-marked tests. No new configuration file is needed.
- `tests/gate_app.py` (new, not collected) is the one way to build a dashboard `AppTest`. It sets dummy sign-in settings and an allowlist as `AppTest` secrets and patches the identity seam (`auth_gate.current_identity`, `sign_in`, `sign_out`) to a fake identity, allowed by default.

## Running This Unit's Tests

The runner check before the first Red step (Step 1) uses the existing dashboard files:

```bash
python3 -m pytest tests/test_dashboard_app.py tests/test_dashboard_data.py tests/test_dashboard_embedded.py -q
```

This unit's tests, new and moved:

```bash
python3 -m pytest tests/test_gate_app.py tests/test_auth_gate.py tests/test_secrets_bridge.py tests/test_dashboard_gate.py tests/test_dashboard_app.py tests/test_dashboard_data.py tests/test_dashboard_embedded.py -q
```

A single behaviour, for example the decision tests:

```bash
python3 -m pytest tests/test_auth_gate.py -k decide -q
```

The advisory timing test (NFR2.11), by hand only and never in CI:

```bash
python3 -m pytest tests/test_dashboard_gate.py -m perf -q
```

## Test Files and Volume (Standard strategy, 5–8 or more per component)

| File | Component | Tests (at least) |
|------|-----------|------------------|
| `tests/test_gate_app.py` | Shared helper | 2: secrets reach the script, including the nested `auth.google` keys; the seam patch is in place |
| `tests/test_auth_gate.py` | Decision core, markers, refusal logging, sign-out, binding | 8 or more for `decide` and `parse_allowlist` (parametrised over the NFR1.22 cases); 2 AST and seam-scope scans; 1 markers test; 6 or more logging tests; 6 or more sign-out and binding tests |
| `tests/test_secrets_bridge.py` | Secrets bridge | 7: export wins; hosted copied when unset; hosted copied when empty; `.env.local` fallback; unreadable secrets count as absent; cookie clash; `mock_hsm` has no Streamlit import |
| `tests/test_dashboard_gate.py` | Gate screens and wiring (`AppTest`) | 12 or more: Screens 1, 2 and 5 per path; render-tree and start-spy checks; literal email; mid-render error; signed-in frame; Screen 4 Account section; sign-out end to end; no-I/O; no-wait scan; control exceptions; secrets example; `.gitignore`; 1 `perf` test |
| Existing `test_dashboard_app.py`, `test_dashboard_data.py`, `test_dashboard_embedded.py` | Whole dashboard through the gate | Unchanged in number; construction switched to `gate_app`; caption assertions updated |

## Coverage Targets

- Every line of `dashboard/auth_gate.py`, `dashboard/secrets_bridge.py` and `dashboard/markers.py` is covered, apart from lines that only Streamlit's real sign-in reaches inside the three seam functions. Those are exercised by U5's browser tests and the human's local sign-in.
- Repository line coverage stays at or above `.coverage-floor` (95.00) and the 80% gate. The passing count stays at or above `.test-floor` (745). Neither file is edited, and no `# pragma: no cover` or `.coveragerc` omit is added.

## Mocking and Stubbing

- **Identity:** patch only the seam (`auth_gate.current_identity`, `sign_in`, `sign_out`) through `gate_app`. Never patch `decide`, `end_visitor_session` or the screen functions, except where a test injects an error on purpose (a raising `decide`, a raising screen draw).
- **Backend:** the existing fixtures run the real mock backend in process on an ephemeral port and patch `session.client_for`. To force a backend failure, patch `embedded.start` as `test_dashboard_embedded.py` already does. A refusal-path test replaces `embedded.start` with a spy that records calls.
- **Secrets:** pass them as `AppTest` secrets through `gate_app(secrets=...)`. For the bridge unit tests, call `bridge_signing_secret(hosted_dict)` directly, with `monkeypatch.setenv` and `monkeypatch.delenv` for the environment. `.env.local` tests patch `mock_hsm.auth.default_local_secret_path` to a `tmp_path` file. No real secret is committed.
- **Sockets:** monkeypatch `socket.socket.connect` and `socket.create_connection` with a recorder that raises.
- **Logs:** use `caplog.at_level(logging.INFO, logger="dashboard.auth_gate")`, plus one test with no `caplog` level set, to prove the module sets INFO itself.

## Test Data

- Allowed identity: `allowed@example.com`, verified `True`. Others: `stranger@example.com` (not listed), `allowed@example.com` with `email_verified` values `False`, `None`, `"true"`, `"false"` and `1`, markup emails `<b>x</b>@example.com` and `*a*@example.com`, and a mixed-case `  Allowed@Example.COM `.
- Allowlist: `["allowed@example.com", "example.com"]` (the second entry proves no domain matching); 50 entries for the timing test.
- Sign-in settings: the five C7 keys with placeholder strings. The cookie secret is a fixed dummy that differs from the per-run signing secret. One test sets it equal to that secret to prove the clash.
