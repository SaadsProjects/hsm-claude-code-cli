## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-05T16:10:18Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/functional-design/entities.md > entity SecretRefusal, and rules.md BR1.3/BR1.4 | Contract C1 (contract-summary.md) pins the exception as `SecretMissingError`, a subclass of `RuntimeError`, raised for both a missing and a short secret. The design instead models `SecretRefusal(reason=missing/too_short)` and never names the Python class or its base. U2 and U3 import the C1 name, and the contract says a rename needs every consumer changed together. The base class also matters. `server._dispatch` catches only `TokenError` around `verify_token`, and `mcp_server/hsm_tools.py::_client` and the hook broad-catch rely on the exception type. | State that `SecretRefusal` is a design-level name for C1's `SecretMissingError` (RuntimeError subclass), or align the names. Say whether `reason` is an attribute on the exception. Keep the class a non-`TokenError` so the 401 branch cannot swallow it. | New |
| R-02 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/functional-design/functional-spec.md > W4 step 3 and rules.md BR3.3 | W4 and BR3.3 require the start script to "accept a port setting" so AC2.2.4 can start the backend on a free port. No mechanism is specified. C2 lists no port variable. `mock_hsm.server.run(host, port=8770)` takes a parameter, but `__main__` calls `run()` with none, so nothing can pass a port through `python3 -m mock_hsm.server`. A developer would have to invent the interface (variable name, flag, or `__main__` parsing, and the invalid-port behaviour). The tests in AC2.2.4 depend on it. | Define the port interface: the variable or flag name, how `__main__` reads it, the default 8770, and the error on a non-integer value. Add it to the C2 schema, or note it as a U1-local extension of C2. | New |
| R-03 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/functional-design/functional-spec.md > W2 | The `.env.local` loader is shared by the backend, the hook and the MCP server, but the design does not say which module owns it. If it lived in `mock_hsm/auth.py` it would need to respect BR1.1 (no read at import) and BR1.2 (standard library only). "Project root" is also ambiguous. The hook and the MCP server both run with a cwd that Claude Code sets, so the root should come from the file's own location, as the hook already does with `sys.path`. Quoted values (`KEY="v"`) are not covered either. | Name the owning module and function, state that the root is resolved from `__file__`, and state the quoting rule. Reject quotes, or strip them consistently with the dev-secret script's output. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/functional-design/rules.md > BR3.5 | BR3.5 covers only `verify_token` in `_dispatch`. Public routes such as `POST /sessions` mint a token inside the handler. Today `_dispatch` turns any handler exception into a 500 with `str(e)`, so a mid-run secret loss on login would return 500 rather than 503. | Add that `ApiError`-style mapping (503) also applies to a secret refusal raised by `mint_token` inside a handler, or state that 500 is accepted there. | New |
| R-05 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/functional-design/functional-spec.md > W4 step 2 | The shell start script must check "under 32 bytes". Bash `${#var}` counts characters, not UTF-8 bytes. | State that the script counts bytes (for example with `wc -c` or `LC_ALL=C`) or delegates to `require_secret()` from Python. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| traceability sensor (manual cross-check of traceability.json) | All 29 upstream ACs listed in the brief (US1.1-1.4, 2.1-2.4, 2.6, 8.4, 10.1) map to existing BR targets; BR1.6 and BR3.5 are reverse N/A with a reason. AC2.5.x belongs to U3 and is correctly absent. The `unit` value `u1-secret-fail-closed` matches unit-of-work.md. | PASS |
| Code cross-check | `mock_hsm/auth.py` holds the `_SECRET` literal at module scope, which is what BR1.1 and BR2.1 remove. `TEMPORARY_EXCLUSIONS = ("mock_hsm/auth.py",)` matches BR2.1. The hook's existing broad catch already denies on a crash, so BR4.1 adds an explicit early deny. | Design matches the current code, apart from R-01 and R-02. |

### Summary

The design is largely implementable. Rules, state machine and acceptance-criteria traceability are consistent with the code, and the ordering (hook deny test first, literal removed last) is sound. Two Major gaps need tightening before code generation: the exception name and base class differ from contract C1, and the port interface for the start script is unspecified. The Minor items are small clarifications. Zero Critical and two Major findings gives READY.
