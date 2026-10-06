## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-05T16:16:30Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/nfr-design/security-design.md > D1 (burned-value test) and Assumptions & Open Questions | The NFR review item R-03 asked how the NFR1.7 test gets the burned value without a literal in tracked files. D1 offers two alternatives and defers the choice to the code plan. One reads the value from "the git history allowlist fixture used by gitleaks", which is not a named artifact. The other is a "test-only hash injection", which would never exercise the real stored constant. check_burned_secret.py excludes only .gitleaks.toml and the record tree, so neither mechanism is guaranteed to keep NFR1.1 and gitleaks green. NFR1.7 is therefore not implementable as designed. | Pick one mechanism. For example: the test takes the value from the permanently excluded location, naming it, or it asserts the shipped constant against a value derived at test time without a tracked literal. State where the value lives and why scan checks pass. | New |
| R-02 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/nfr-design/security-design.md > D2 row `scripts/start_mock_server.sh` and D3 | The start script "loads .env.local if the variable is unset" in bash, while D3 defines the Python `load_local_secret()` (KEY=VALUE only, no expansion, quote stripping, root from `__file__`) and says Python runs the gate anyway. The design does not say how bash loads the file. `source`/`export $(cat ...)` would apply shell expansion and execute arbitrary content, which violates NFR1.10, and it would create a second parser that can diverge from the Python one. The step is also redundant. | Drop the bash load and let Python's `load_local_secret()` be the only loader. If bash must read the file, specify a literal-only parse (no `source`) and add a test of it. | New |
| R-03 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/nfr-design/security-design.md > D2 row Publish hook | The design says the existing broad catch keeps any other failure a deny. The project's own rule is that a crashed hook fails open. The design does not say that the `mock_hsm.auth` import, and `sys.path` setup if needed, happen inside the guarded region. An import failure at module top level would fail open and bypass NFR1.4. I could not read the hook code in this review scope, so this is unverified. | State that import and `load_local_secret`/`require_secret` all run inside the try that maps to deny, with a test where the import fails. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/nfr-design/security-design.md > D2 table and D3 (`load_local_secret` "never used by the hosted dashboard path") | The entry-point table has no row for a local `streamlit run dashboard/app.py`. That path mints tokens through `mint_token` and so fails closed per NFR1.3, but nothing says who loads `.env.local` for it. Whether that falls to this unit or to the sign-in or hosting units is not stated. | Add a one-line note: either the dashboard is out of scope and owned by another unit through contract C1/C2, or it is a surface here. | New |
| R-05 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/nfr-design/security-design.md > D2 row Running backend request (Q1 warning) | The 503 warning is logged once per request with no rate limit. The design does not say whether it logs the path with or without the query string. It should be the path only, to avoid logging query parameters, and a flood of requests produces a flood of log lines. | Specify path only and accept the per-request volume explicitly. | New |
| R-06 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/secret-fail-closed/nfr-design/traceability.json | `upstream_ids` lists only 14 NFR IDs. The nfr-requirements review noted NFR2, NFR5 and NFR6 as N/A. Their N/A rationale is not carried here. | Carry the N/A entries with their rationale so every inception NFR resolves. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| traceability.json manual check | All 14 listed NFR IDs map to a section in security-design.md or tech-stack-decisions.md. NFR2, NFR5 and NFR6 are not listed. | Substantially complete (see R-06). |
| Code context check | Blocked by the per-unit read-scope hook, so findings R-03 and R-04 rest on the artifacts only. | Unverified items are phrased as questions. |

### Summary

The defense-in-depth design (single `require_secret()` gate, per-entry-point failure surfaces, owner-only `.env.local`) is sound and resolves the prior functional-design and NFR review items. Two Major gaps remain: the burned-value test mechanism is still deferred, and the bash `.env.local` loading is unspecified in a way that can violate NFR1.10. That is within the READY limit of two Majors, but both should be fixed before code generation.
