# Code Summary — U3 sign-in-gate

## Files

| File | Change | What it holds |
|------|--------|---------------|
| `dashboard/auth_gate.py` | Created | `Identity`, `Decision`, `parse_allowlist`, `decide` (pure); `_evaluate` (fixed check order); `_log_refusal_once`; `end_visitor_session`, `_bind_account`; Screens 1, 2 and 5 drawn into one placeholder; `render_account_section`; `gate()` with its one error boundary; the identity seam `current_identity`, `sign_in`, `sign_out` |
| `dashboard/secrets_bridge.py` | Created | `read_hosted_secrets` (guarded; `{}` on error), `bridge_signing_secret` (export, then hosted, then `.env.local`), `cookie_secret_conflict` (`hmac.compare_digest`) |
| `dashboard/markers.py` | Created | The 10 C6 marker constants (`hsm-…` strings), with `__future__` as the only import |
| `dashboard/app.py` | Modified | `run()`: `_page_header()` once, `auth_gate.gate()`, `st.stop()` unless allowed, then the embedded start, Screen 4 (now with the Account section) and `main()`. `main()` draws the Account section, a divider and "Demo persona" first in the sidebar, with the caption "Acting as …" |
| `.streamlit/secrets.toml.example` | Created | The C7 shape with placeholders. `HSM_SIGNING_SECRET` appears only as a comment |
| `requirements.in`, `requirements.txt`, `requirements-dev.txt` | Modified | `streamlit[auth]==1.64.0`. Authlib 1.8.0 and its dependencies (cryptography, cffi, pycparser, joserfc, httpx, httpcore) are hash-pinned |
| `tests/gate_app.py` | Created | The shared `AppTest` builder: dummy sign-in settings, an allowlist, and the seam patched to a fake identity |
| `tests/test_gate_app.py`, `tests/test_auth_gate.py`, `tests/test_secrets_bridge.py`, `tests/test_dashboard_gate.py` | Created | This unit's tests |
| `tests/test_dashboard_app.py`, `tests/test_dashboard_data.py`, `tests/test_dashboard_embedded.py` | Modified | Built through `gate_app`; caption and Screen 4 assertions updated; one start-failure test reworked to use an unusable audit path; one test added for a missing signing secret stopping at the gate |
| `CLAUDE.md`, `README.md`, `dashboard/README.md` | Modified | The sign-in gate, the secrets example, and the dashboard reading `.env.local` itself (the export step is gone) |

## Key Implementation Decisions

- The plan's D1–D12 are implemented as written. The deviations are listed below.
- The secrets bridge runs inside `gate()`'s boundary (S3, infrastructure spec), so an unreadable `.env.local` or secrets mapping becomes Screen 5 instead of a crash.
- `Decision` carries `identity` and `settings` as non-comparing fields. The screens need the email, and the log needs the setting names. Equality and `repr` stay as in C4, and the email is excluded from `Identity`'s `repr`.
- A failed provider sign-out is logged directly as `gate_error`, not through the refusal marks, so the just-cleared state stays empty.

## Test Coverage Summary

| Measure | Result |
|---------|--------|
| Unit command (7 files) | 217 passed, 5 skipped (re-run by the conductor after generation: same result) |
| `-m perf` timing test, by hand | passed (p95 at most 50 ms) |
| Full suite `python -m pytest tests/ -q` | 1063 passed, 13 skipped (baseline 922 passed, 12 skipped; `.test-floor` 745) |
| Coverage | 97% total (`.coverage-floor` 95.00). `auth_gate.py` 98%: only the three seam bodies are uncovered, and they are reached by real Streamlit sign-in only. `secrets_bridge.py` and `markers.py` 100% |
| `ruff check .` / `ruff format --check .` | All checks passed / 508 files already formatted (re-run by the conductor) |
| `pip-audit -r requirements.txt --require-hashes` (local) | No known vulnerabilities found |
| Local start (Step 15) | `streamlit run dashboard/app.py` on 127.0.0.1 answered `/_stcore/health` "ok" and `GET /` 200. The unpatched app under `AppTest`, with the copied example secrets, showed Screen 1 ("Access to this demo is by invitation.", Sign in with Google, no tabs or selectbox), with the signing secret taken from `.env.local`. The temporary `.streamlit/secrets.toml` was deleted |

### Red evidence (TDD)

| Step | Failing command (all with `.venv/bin/python -m pytest`) | Failure |
|------|--------------------------------------------------------|---------|
| 3 | `tests/test_gate_app.py` | `ModuleNotFoundError: No module named 'gate_app'` |
| 4 | `tests/test_auth_gate.py` | `ImportError: cannot import name 'auth_gate' from 'dashboard'` |
| 5 | `tests/test_auth_gate.py -k markers` | `ImportError: cannot import name 'markers' from 'dashboard'` |
| 6 | `tests/test_secrets_bridge.py` | `ImportError: cannot import name 'secrets_bridge'` |
| 7 | `tests/test_auth_gate.py` | 33 failed: `module 'dashboard.auth_gate' has no attribute '_evaluate'` |
| 8 | `tests/test_auth_gate.py` | 12 failed, e.g. `assert 0 == 20` (logger level) |
| 9 | `tests/test_dashboard_gate.py` | 20 failed, 6 passed, e.g. `assert set() == {'hsm-sign-in-button'}` |
| 10 | `tests/test_dashboard_gate.py` | 3 failed, e.g. `assert ('Selectbox' == 'Block')` (sidebar's first block) |
| 11 | `tests/test_auth_gate.py tests/test_dashboard_gate.py` | 14 failed, e.g. `no attribute 'ACCOUNT_BOUND'` |
| 12 | the three existing dashboard files | 59 failed (no sign-in settings gave Screen 5), then 77 passed, 4 skipped after the switch to `gate_app` |
| 13 | the no-I/O, no-wait and timing tests | Passed on their first run, because the code already met them. There was no honest Red, and this is recorded as such |
| 14 | the secrets-example tests, with the file moved aside | 3 failed: `FileNotFoundError: .streamlit/secrets.toml.example` |

## Deviations from the Plan

- **D2 error list:** `mint_token` raises `ValueError` for an unknown user, not `KeyError`. `end_visitor_session` catches both, along with `BackendNotRunning`, `HsmApiError` and `SecretMissingError`.
- **Bridge placement:** the plan's Step 9 sketch has `run()` call the bridge and then the gate. The bridge actually runs inside `gate()`'s boundary, as above.
- **TOML on Python 3.10:** the secrets-example tests use `tomllib` with the `tomli` fallback already used in `test_dashboard_units.py`, instead of skipping on 3.10. A line-scan test also covers the signing-secret rule.
- **Red output:** the plan put it here, and the conductor recorded it from the developer's report.

## Fixes from the Commit Review

The `/commit` code reviewer found three low-severity issues in the staged diff. The human chose to fix all three before committing. The fixes are in commit `fa3264b`.

- **Duplicate Sign out key.** An error after Screen 2 had already drawn its Sign out button made Screen 5 register the same widget key again, so Streamlit raised instead of showing Screen 5. `gate()` now keeps a per-run `drawn` set, and `_sign_out_button(state, drawn)` registers the key at most once per run. In that rare case Screen 5 shows no Sign out, and the reload line is the way out (BR4.3). New test: `test_an_error_after_screen_2_drew_sign_out_still_lands_on_screen_5`.
- **Google sign-out skipped.** An unexpected error while ending the backend session skipped the Google sign-out. `_sign_out_clicked` now calls `sign_out()` in a `finally`. New test: `test_sign_out_still_signs_out_of_google_when_ending_the_session_fails_unexpectedly`.
- **Docs on the secret order.** The docstring in `dashboard/secrets_bridge.py`, `dashboard/README.md` and `CLAUDE.md` now say that a `HSM_SIGNING_SECRET` line in `.streamlit/secrets.toml` replaces an exported value, because Streamlit copies top-level secrets into the environment itself.

After the fixes, the full suite gives 1065 passed and 13 skipped, ruff is clean, and all 10 required checks are green on draft PR #7.

## Open Items for the Human

- **Real Google sign-in.** Confirming that `email_verified` arrives as a boolean needs a local Google OAuth client with redirect `http://localhost:8501/oauth2callback` and your email in `HSM_ALLOWED_EMAILS`. Until then, anything but boolean `True` is refused, which fails closed.
- **INFO lines and handlers.** The gate's logger is set to INFO, and the tests capture the INFO lines. With no root handler configured, Python's last-resort handler prints only WARNING and above, so `not_verified` and `not_listed` lines may not appear in real logs. The failure signals (WARNING) are unaffected. Making them visible means configuring a handler, which belongs to Build and Test or a follow-up.
- **Streamlit copies top-level secrets into the environment.** When Streamlit reads a real `secrets.toml`, it puts top-level string secrets into `os.environ` and overwrites an exported value. This is harmless with the committed example, which sets no `HSM_SIGNING_SECRET`, and with the hosted apps, which export nothing. It does mean "an exported value always wins" holds only while `secrets.toml` lacks that key.
