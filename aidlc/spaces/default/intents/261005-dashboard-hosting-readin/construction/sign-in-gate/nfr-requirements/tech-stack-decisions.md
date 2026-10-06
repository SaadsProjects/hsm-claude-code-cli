# Tech Stack Decisions — U3 sign-in-gate

## Sources

- `aidlc/spaces/default/codekb/hsm-claude-code-cli/technology-stack.md` (Streamlit 1.64.0; Authlib not yet present)
- `inception/requirements-analysis/requirements.md` FR4.2, FR8.1, NFR7
- `inception/domain-design/decisions.md` (the gate, the bridge and their placement)
- `nfr-requirements-questions.md` Q2, Q3; `memory/team.md` Code Style

## Decisions

| Area | Decision | Rationale | Alternatives rejected |
|------|----------|-----------|-----------------------|
| Sign-in | Streamlit's built-in `st.login("google")`, `st.user` and `st.logout` behind a thin identity seam | Already decided (FR4.2). It is the free, built-in OpenID Connect flow on Streamlit Community Cloud, and needs no extra service | A hand-written OAuth flow (more security-critical code to own); a reverse-proxy sign-in (not available on Streamlit Community Cloud) |
| Sign-in library | `streamlit[auth]==1.64.0` in `requirements.in`; the hash-pinned runtime lock pins the Authlib that the extra resolves to (Q2 A). Both locks are recompiled and committed together, and must resolve on Python 3.10 and 3.14 | Keeps one pin (Streamlit) as the source of truth, and the extra pulls a compatible Authlib. `lock-check` and `audit` gate the result | An explicit Authlib lower bound (a second pin to keep in step with Streamlit's own constraint) |
| Gate module | `dashboard/auth_gate.py`: pure decision and allowlist parsing, the identity seam, the gate screens, `end_visitor_session` | Fixed by the CI watch list (CQ-8) and the team's file placement rule | Drawing the screens in `app.py` (domain-design ADR-002) |
| Secrets bridge | `dashboard/secrets_bridge.py` | Streamlit-specific code stays out of `mock_hsm/` (team.md Code Style; project.md correction) | Putting it in `mock_hsm/auth.py` or in the gate (ADR-003) |
| Markers | `dashboard/markers.py`, string constants only, no Streamlit import | Shared by `AppTest`, the browser tests and the post-deploy check (C6) | Selectors inlined in tests (they drift from the app) |
| Logging | Standard-library `logging`, logger `dashboard.auth_gate`, at INFO for visitor refusals and WARNING for settings or gate errors (Q3 A) | Consistent with the existing `mock_hsm.embedded` logger. Streamlit Community Cloud shows the app's log to the owner | `print` (no levels); Streamlit's own logger (not the app's namespace) |
| Tests | `pytest` with `streamlit.testing.v1.AppTest` and a shared fake allowed identity fixture patched at the seam; `perf`-marked timing test | Matches the existing dashboard suite. The seam keeps tests free of a real identity provider | A fake OpenID provider in unit tests (that belongs to U5's browser tests) |

## Constraints Carried

- Python 3.10 floor; ruff rules from `ruff.toml`; a broad `except` only at a boundary that becomes visible state, with a `# noqa: BLE001 -- <reason>` comment (the gate's catch-all that turns an error into Screen 5 is such a boundary).
- No new dev dependency in this unit (Playwright arrives with U5).

## Assumptions & Open Questions

- [assumption] `streamlit[auth]==1.64.0` resolves to an Authlib release with no high or critical advisory at lock time. If `pip-audit` reports one, the fix is a lock refresh, not a `security-exceptions.toml` entry, unless no fixed version exists.
