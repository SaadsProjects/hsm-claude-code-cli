# Functional Design Questions — U1 secret-fail-closed

## Sources

- `inception/units-generation/unit-of-work.md` (U1) and `unit-of-work-story-map.md` (US1.1–US1.4, US2.1–US2.4, US2.6, US8.4, US10.1 secret setup)
- `inception/contract-design/contract-summary.md` C1 (TokenAuth API) and C2 (process environment); accepted contract-design finding R-06
- Current code: `mock_hsm/auth.py` (module-level `_SECRET`, `mint_token` raises `ValueError` for an unknown user), `scripts/start_mock_server.sh`, `.claude/hooks/require_no_violations.py` (its `__main__` already turns any exception into a deny), `mcp_server/hsm_tools.py` (`_client()` mints a token per call)

Already settled, so not asked: the 32-byte minimum, no fallback, the error naming the variable but not the value, the hook denying, the tool server erroring, tests generating their own secret, the `.gitignore` lines, and removing the literal and its exclusion in one commit.

## Q1. How do the hook and the MCP tool server get the secret on your machine?

They run as child processes of `claude`, so they see only what your shell exported (contract-design finding R-06).

A. They inherit it from the shell: the docs say to run `set -a; . ./.env.local; set +a` before starting `claude`, and the hook and tool server read only the environment
B. They also read `.env.local` from the project root themselves when the variable isn't set in the environment
X. Other (please specify)

[Answer]: B

## Q2. What does the running backend do if the secret disappears or becomes invalid after it started (contract-design finding R-06)?

Because tokens are now verified against the secret at call time, a request can hit this.

A. Answer that request with HTTP 503 and a JSON error naming `HSM_SIGNING_SECRET` (never its value); keep serving
B. Answer with HTTP 500 and the same message
X. Other (please specify)

[Answer]: A

## Q3. What form does the dev-secret script take?

A. `scripts/dev-secret.sh` (bash), generating the value with `python3 -c 'import secrets; …'`, with a `--force` option to overwrite
B. `scripts/dev_secret.py` (Python), with the same behaviour and its own tests importing it directly
X. Other (please specify)

[Answer]: A

## Q4. Follow-up to Q1: change the team rule, and where does `.env.local` loading live?

The team rule you affirmed this morning (`team.md` Deployment) says "the MCP server inherits it from the shell". Q1 B also lets the hook and the tool server read `.env.local` themselves. That needs the rule changed and one shared loader.

A. Yes: change the rule to "inherits it from the shell, or reads it from `.env.local` in the project root when unset". One small standard-library loader in `mock_hsm/auth.py`, `load_local_secret()`, used by the hook, the tool server and the start script's Python launch. It never overrides a variable already set and never runs on the hosted app.
B. Keep the team rule as it is and use Q1 option A instead (export before `claude`)
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Local secret for the hook and tool server (Q1, Q4): they use the environment first, and otherwise read `HSM_SIGNING_SECRET` from `.env.local` in the project root. One shared standard-library loader, `load_local_secret()` in `mock_hsm/auth.py`, serves the hook, the tool server and the backend's local launch. It never overrides a variable that is already set, and it isn't used by the hosted app. The team rule "the MCP server inherits it from the shell" is to be updated to match, through the learnings step, not by editing the file directly.
- Secret lost mid-run (Q2): the backend answers that request with HTTP 503 and a JSON error naming `HSM_SIGNING_SECRET`, never its value, and keeps serving.
- Dev-secret script (Q3): `scripts/dev-secret.sh` (bash), generating the value with Python's `secrets` module, with `--force` to overwrite.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
