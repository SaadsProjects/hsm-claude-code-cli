# Domain Design Questions — Dashboard Hosting Readiness

## Sources

- `inception/requirements-analysis/requirements.md`; `inception/user-stories/stories.md`; `inception/refined-mockups/mockups.md`
- Code knowledge base: `architecture.md`, `component-inventory.md` (components `agents`, `mock_hsm`, `dashboard`, `mcp_server`, `claude-hooks`, `scripts`)
- `memory/team.md` Code Style: file placement (`dashboard/auth_gate.py`, `dashboard/markers.py`, `agents/build_info.py`, `scripts/postdeploy_check.py`); `mock_hsm/auth.py` standard library only; in-process start as an imported standard-library function in `mock_hsm/`

Already fixed by team rules, so not asked: which package each new piece lives in. These questions settle the remaining boundaries inside those packages.

## Q1. Where does the in-process backend start live?

A. A new module, `mock_hsm/embedded.py`, holding the start function and the one-per-process guard; `server.py` keeps only the route handler and `run()`
B. Inside `server.py`, as a second start function beside `run()`
X. Other (please specify)

[Answer]: A

## Q2. How is the sign-in gate split?

A. `dashboard/auth_gate.py` holds the decision function, the identity seam (`current_identity`, `sign_in`, `sign_out`) and the refusal and sign-in screens; `app.py` only calls it
B. `auth_gate.py` holds the decision and the seam; the screens are drawn in `app.py`
X. Other (please specify)

[Answer]: A

## Q3. Where does the Streamlit-secrets bridge live?

It copies `HSM_SIGNING_SECRET` from Streamlit secrets into the environment, and refuses to start when the signing secret equals the cookie secret.

A. Its own module, `dashboard/secrets_bridge.py`, called once at app start before the gate
B. Inside `auth_gate.py`
C. Inline in `app.py`
X. Other (please specify)

[Answer]: A

## Q4. How do the entry points check for the secret?

The backend, start script, hook and tool server must all refuse to run without a valid secret.

A. `mock_hsm/auth.py` exposes one shared check (for example `require_secret()`, which raises the standard error); every Python entry point calls it at startup, and the shell start script checks before launching Python
B. Each entry point implements its own check
X. Other (please specify)

[Answer]: A

## Q5. Who reads and parses the allowlist?

A. The gate: it reads the allowlist from Streamlit secrets through the seam and parses it, so every parsing rule (list of strings, trimmed, lower-cased) sits next to the decision
B. The secrets bridge parses it and passes a ready list to the gate
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- In-process backend (Q1): a new module, `mock_hsm/embedded.py`, holds the start function and the one-per-process guard. `server.py` keeps the route handler and `run()`.
- Sign-in gate (Q2): `dashboard/auth_gate.py` holds the decision function, the identity seam and the sign-in, refusal and unavailable screens; `app.py` only calls it.
- Secrets bridge (Q3): its own module, `dashboard/secrets_bridge.py`, called once at app start before the gate.
- Secret check at entry points (Q4): one shared check in `mock_hsm/auth.py` (`require_secret()`), called by every Python entry point at startup. The shell start script checks before launching Python.
- Allowlist (Q5): the gate reads it from Streamlit secrets through the seam and parses it.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
