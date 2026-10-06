## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-04T22:29:20Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261004-dashboard-deploy-pipelin/construction/nfr-requirements/security-requirements.md > NFR1.3, NFR1.18 | Resolved. NFR1.18 defines one local contract: the single env var HSM_SIGNING_SECRET reaches the mock server, MCP server, publish-gate hook, dashboard and start script. Each fails closed with a message naming the variable. conftest generates a per-session secret and exports it to subprocesses. The suite must pass with the variable unset in the shell. Code check: auth.py currently has a literal and the hook and MCP read only HSM_ACTIVE_USER, so this is a code-generation task now specified. | None. | Resolved |
| R-02 | Major | reliability-requirements.md > NFR6.2 step 0, NFR6.3; performance NFR2.4 | Resolved. NFR6.3 now permits exactly one click, on the platform wake button, and a static test asserts it. NFR6.2, NFR2.4 and NFR7.1 agree. | None. | Resolved |
| R-03 | Major | reliability-requirements.md > NFR6.1, NFR6.2(a) | Resolved. A fingerprint fallback (fp:) is specified, along with "unknown is a mismatch", a single Playwright session, and the open item recorded honestly. | None. See R-10 for a residual detail. | Resolved |
| R-04 | Major | security-requirements.md > NFR1.19, T5 | Resolved. The Environment deployment-branch policy allows main only, promote.yml has a ref guard, a manual negative check is recorded, and TS14 lints the guard. | None. | Resolved |
| R-05 | Minor | performance-requirements.md > NFR2.2 | Resolved. A step-level timeout of 5 min is specified. | None. | Resolved |
| R-06 | Minor | performance-requirements.md > NFR2.3 | Resolved. The target is now "at most 1 of 20 loads exceeds 5 s". | None. | Resolved |
| R-07 | Minor | security-requirements.md > NFR1.3, NFR1.4, NFR1.11 | Resolved for the digest test and the stdlib-only auth.py, which is bridged from the dashboard. One residual: the NFR1.3 CI grep for "the old literal" needs the literal itself in the CI script. See R-10. | None for this ID. | Resolved |
| R-08 | Minor | security-requirements.md > NFR1.2 | Resolved. email_verified is checked and malformed allowlist entries fail closed. | None. | Resolved |
| R-09 | Minor | reliability-requirements.md > NFR6.7, NFR3.1, ID note | Resolved. NFR6.7 decides on skip-when-404, `.coverage-floor` is named as the ratchet storage, and the 6.8/6.9 gap is noted. | None. | Resolved |
| R-10 | Minor | security-requirements.md > NFR1.3 (CI grep) vs NFR1.4; reliability NFR6.1 (fingerprint) | (1) The NFR1.3 verify step greps tracked files for the burned literal, which puts the literal in the CI script and contradicts NFR1.4's "never appears in source or tests". (2) The fingerprint covers "tracked" files, but without .git the app can only walk the directory, so __pycache__ or untracked files could make the app and check script disagree. | (1) Do the check by SHA-256 digest comparison over file contents, or limit the grep to the allowlisted gitleaks entry. (2) Define the file set by path globs and extensions, excluding __pycache__ and *.pyc, and use it in both places. Both can be settled in NFR Design. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| python3 -m json.tool traceability.json | PASS | Valid JSON. NFR1 to NFR7 are covered, including NFR1.18 and NFR1.19. |

### Summary

All iteration-1 Major and Minor findings are resolved by concrete, testable requirements: the local secret contract, the wake click, the build fingerprint fallback and the Environment branch policy. One new Minor remains (the burned-literal grep and the fingerprint file set). It does not block, so the verdict is READY.
