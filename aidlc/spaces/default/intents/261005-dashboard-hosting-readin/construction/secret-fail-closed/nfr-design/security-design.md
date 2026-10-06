# Security Design — U1 secret-fail-closed

## Sources

- `construction/secret-fail-closed/nfr-requirements/security-requirements.md` (NFR1.1–NFR7.1) and `tech-stack-decisions.md`
- `construction/secret-fail-closed/functional-design/functional-spec.md` (W1–W9), `rules.md`; functional-design review items R-01 to R-05; NFR review items R-01 to R-04
- `inception/contract-design/contract-summary.md` C1, C2
- `nfr-design-questions.md` Q1

## Design Overview

Defense in depth for one asset, the signing secret:

1. **No secret in code:** the literal and its scan exclusion go (NFR1.1).
2. **One gate:** every path into the secret goes through `require_secret()` (NFR1.2, NFR1.3, NFR1.7).
3. **Every entry point fails closed, in its own native way:** an exit, a deny, a tool error, or a 503 (NFR1.4, NFR1.5).
4. **No disclosure:** messages carry the variable name and the rule only (NFR1.6, NFR4.1).
5. **Safe local storage:** an owner-only, git-ignored `.env.local`, with a loader that never overrides (NFR1.8–NFR1.10).

## D1 — The single gate: `require_secret()` (contract C1)

- It lives in `mock_hsm/auth.py`, uses the standard library only, and runs only when called.
- Its order of checks:
  1. unset or empty: refuse with reason `missing`;
  2. under 32 UTF-8 bytes: refuse with reason `too_short`;
  3. SHA-256 equal to the stored hash of the burned value: refuse with reason `burned`.
- The burned-value comparison is exact only. A longer secret that merely contains the old value is caught by the CI window scan of tracked files instead; `.env.local` is never tracked (NFR review item R-02).
- Only the hash constant is in the code, never the literal. The test checks the comparison by hashing a candidate it builds without a literal in tracked files: it asserts the stored constant equals the hash of the value read from the git history allowlist fixture used by gitleaks, or else checks the refusal through a test-only hash injection (NFR review item R-03; the exact mechanism is settled in the code plan).
- The error is `SecretMissingError(RuntimeError)`, with a `reason` attribute (`missing`, `too_short` or `burned`) and a message naming `HSM_SIGNING_SECRET`. "SecretRefusal" in the functional design is the business name for this class (functional-design review item R-01; NFR review item R-01).
- `mint_token` and `verify_token` call `require_secret()` and use its returned value. Nothing is cached.

```text
require_secret() -> bytes
  value = environ.get("HSM_SIGNING_SECRET", "")
  if not value:                        raise SecretMissingError("missing")
  if len(value.encode()) < 32:         raise SecretMissingError("too_short")
  if sha256(value) == BURNED_SHA256:   raise SecretMissingError("burned")
  return value.encode()
```

## D2 — Entry-point surfaces

| Entry point | When checked | Surface on refusal |
|-------------|--------------|--------------------|
| `python3 -m mock_hsm.server` | `__main__`: parse `--port` (default 8770; a non-integer is a usage error, exit 2), call `load_local_secret()`, then `require_secret()` before binding | Message on stderr, exit 1, no listener (functional-design review item R-02) |
| Running backend request | `_dispatch` catches `SecretMissingError` ahead of the generic handler, around both `verify_token` and handler code that mints (for example `POST /sessions`) | HTTP 503, JSON `{"error": "<message naming HSM_SIGNING_SECRET>"}`, plus one stderr warning with the request path (Q1; functional-design review item R-04) |
| `scripts/start_mock_server.sh` | Loads `.env.local` if the variable is unset, then launches Python, which runs `require_secret()`; bash counts no bytes (functional-design review item R-05) | Python's message and a non-zero exit pass through; `--port` is forwarded |
| Publish hook | `load_local_secret()` then `require_secret()` at the top of `main()`, before validation | Explicit deny with the message; the existing broad catch keeps any other failure a deny, and its `noqa` now has a reason |
| MCP tools | `load_local_secret()` at server start; `_client()` calls `mint_token`, which runs the gate | Tool error carrying the message |
| Tests | `tests/conftest.py` sets a fresh `secrets.token_urlsafe(32)` before anything starts | Not applicable |

## D3 — Local secret storage and loading

- **`scripts/dev-secret.sh`:**
  - runs `umask 077` and writes `HSM_SIGNING_SECRET=<token_urlsafe(32)>`, keeping any other lines;
  - after any write, including a `--force` overwrite, runs `chmod 600` on the file (NFR review item R-04);
  - refuses to replace an existing value without `--force`.
- **`load_local_secret()`** in `mock_hsm/auth.py`:
  - resolves the project root from `auth.py`'s own location (`Path(__file__).resolve().parents[1]`), not the working directory (functional-design review item R-03);
  - if `HSM_SIGNING_SECRET` is already set, does nothing;
  - otherwise reads `.env.local` line by line and accepts only `HSM_SIGNING_SECRET=<value>`, stripping one pair of matching surrounding quotes and doing no shell expansion;
  - a missing file or line is a no-op;
  - never logs the value;
  - is called only by local entry points, never by the hosted dashboard path.
- **`.gitignore`:** explicit lines for `.env`, `.env.local`, `.env.*` and `.streamlit/secrets.toml`, placed above the AI-DLC-managed block.

## D4 — Disclosure controls

- Every message is built from fixed text plus the variable name and the reason. No message is ever formatted from the secret value.
- Tests trigger each surface with a known value and assert the value is absent from stdout, stderr, the HTTP body and the deny reason.
- `.mcp.json` is checked by a test for the absence of `HSM_SIGNING_SECRET`.

## D5 — Removal order (M1)

The literal goes last, in one commit with an empty `TEMPORARY_EXCLUSIONS` and the regression tests, after D1–D4 are green. The `.gitleaks.toml` allowlist entries stay.

## Assumptions & Open Questions

- The exact way the burned-value test obtains its comparison value without a literal in tracked files is settled in the code plan. Both candidate mechanisms in D1 keep the literal out of tracked files.
