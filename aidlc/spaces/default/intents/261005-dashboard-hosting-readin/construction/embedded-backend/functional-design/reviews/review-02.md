## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-05T21:54:25Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Critical | construction/embedded-backend/functional-design/rules.md > BR3.2; entities.md > AuditTrail.path | Resolved. BR3.2 and the AuditTrail path now use a private app-owned directory, `<temp>/hsm-demo-<user id>/audit.jsonl`, created owner-only, and forbid a file directly in a shared directory. This matches `_ensure_storage` narrowing the parent in `mock_hsm/audit.py`. | None. | Resolved |
| R-02 | Major | rules.md > BR3.3; functional-spec.md > W1 step 6, Error Handling | Resolved. BR3.3 reads back the unavailable reason after `configure()` (a new public query on the audit module). It covers an OS error and a corrupt trail, and the Error Handling table has both rows. This matches `state.unavailable` in `audit.py`. | None. | Resolved |
| R-03 | Major | functional-spec.md > W1 step 4, W2 step 1; rules.md > BR2.4, BR2.5 | Resolved. A dead instance is closed before replacement, the replacement is logged as a demo-data reset, the address is read at each use, and cached reads are cleared. | None. | Resolved |
| R-04 | Major | functional-spec.md > Scope "Dashboard call sites that change", Render order; rules.md > BR4.1, BR5.4 | Resolved. The call sites are enumerated: `session.client_for`, and in `app.py` the `HSM_BASE_URL` import, the caption (line 483) and the URLError text (line 510). I checked these against the code, and `HsmClient(` is built only in `session.py`. A guard test is specified, and BR5.4 fixes the order after the U3 gate. | None. | Resolved |
| R-05 | Minor | rules.md > BR2.1; entities.md > StartAttempt.requested_port | Resolved. The port argument applies only to a new attempt and is ignored on reuse. | None. | Resolved |
| R-06 | Minor | functional-spec.md > Scope; rules.md > BR5.1 note | Resolved. The Sign out half of AC3.3.2 is stated as verified by U3. | None. | Resolved |
| R-07 | Minor | rules.md > BR3.2 | Suggestion only. A predictable `hsm-demo-<uid>` directory in a shared temp dir could be pre-created by another local user. Say that an existing directory not owned by the current user, or not mode 0700, makes the attempt fail. This is low risk on a single-tenant host. | Optionally add one line to BR3.2. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Code spot-check (`mock_hsm/audit.py`, `dashboard/session.py`, `dashboard/app.py`) | The design's claims match the code | The audit parent chmod, the unavailable state and the `HSM_BASE_URL` call sites are all as described. |

### Summary

All six prior findings are resolved, and I found no new blocking issue. The design is implementable without architectural guidance. R-07 is an optional hardening suggestion.
