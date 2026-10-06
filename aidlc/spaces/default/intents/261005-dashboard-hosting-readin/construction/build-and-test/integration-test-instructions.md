# Integration Test Instructions — Dashboard Hosting Readiness

## Sources

- Per-unit code summaries and unit-test instructions (U1–U6)
- `inception/contract-design/contract-summary.md` (C1–C9: in-process interfaces, secrets schema, markers, check CLI)
- `memory/team.md` Testing Posture (browser tests, watch list, fixed ports)

## Key Boundaries Under Test

The units share one process, so these are in-process and subprocess boundaries, not network APIs between services.

| Boundary | Units | Integration evidence | Command |
|----------|-------|----------------------|---------|
| Secret reaches every entry point: backend, start script, publish hook, MCP server | U1 | Subprocess tests start each entry point with and without a secret | `python3 -m pytest tests/test_secret_entry_points.py tests/test_hooks.py tests/test_mcp_tools.py -q` |
| Streamlit secrets → environment → token minting | U1, U3 | The bridge copies the hosted secret before any token is minted; an export wins | `python3 -m pytest tests/test_secrets_bridge.py -q` |
| Gate → embedded backend → dashboard tabs: order and fail-closed | U2, U3, U4 | `AppTest` through `tests/gate_app.py` for every refusal path, the allow path and Screen 4 | `python3 -m pytest tests/test_dashboard_gate.py tests/test_dashboard_embedded.py tests/test_dashboard_build_banner.py tests/test_dashboard_app.py -q` |
| Dashboard client → embedded backend over loopback | U2 | One backend per process, liveness, replacement, 10 concurrent requests | `python3 -m pytest tests/test_embedded_backend.py -q` |
| Real browser → real `streamlit run` app → gate screens | U3, U5 | Playwright against `tests/browser_app.py`, with only the identity seam replaced | `python3 -m pytest tests/ -m browser -q` |
| Post-deploy check → any URL (read-only) | U5, U6 | The browser tests run the check against the app, an ungated double, a plain page and a closed port | as above, plus `python3 scripts/postdeploy_check.py <url>` |
| CI watch list ↔ files browser tests reach | U5 | Transitive import meta-test | `python3 -m pytest tests/test_ci_browser_watch.py -q` |
| Runbook ↔ secrets schema (C7) | U6 | The runbook's TOML block holds exactly the example's keys in the C7 layout | `python3 -m pytest tests/test_staging_runbook.py -q` |

## Setup

- `pip install --require-hashes -r requirements-dev.txt`, then `python -m playwright install chromium` for the browser rows.
- No secret to set: `tests/conftest.py` supplies a throwaway one and a temp audit path.
- Run serially. `test_mcp_tools.py` and `test_hooks.py` bind fixed ports 8772 and 8773; every new server binds port 0.

## Expected Results

- All rows pass. Browser tests don't count toward `.test-floor` and run in CI's `browser-tests` job, with one retry.
- Integration tests contribute to line coverage over `agents/`, `dashboard/`, `mock_hsm/`, `mcp_server/` and `.claude/hooks/`, gated at `.coverage-floor` and 80%.

## Test Data

- Identities are JSON passed to the identity seam: verified and allowlisted; verified but not listed; unverified.
- Allowlists and sign-in settings come from temp `secrets.toml` files written per test.
- No real Google account, OAuth client or staging URL is used in any automated test. Staging is reached only by the post-deploy check (`docs/staging-app.md`).
