# Code Generation Plan — Restore dashboard writes (a189674)

## Overview

Bring back commit `a189674` ("Add dashboard data writes with sessions, audit
trail and client retry", reverted by `2eb1a8d`) on top of the current `main`
(`034684e`) and reconcile it with what changed since. The intent is the human's
instruction "build on a189674 instead of starting fresh"; there is no separate
requirements or design artifact in this workflow, so the commit itself and its
tests are the specification. Nothing in a189674 is redesigned; deviations are
limited to the reconcile points below.

Source of every restored file: `git show a189674:<path>` (byte-for-byte), except
the three reconcile files, which are merged by hand.

What a189674 adds (29 files, +11,405 / -102):

| Layer | Files |
|-------|-------|
| Data model | `mock_hsm/db.py` (dev-tester login, fixed GL code list) |
| Audit trail | `mock_hsm/audit.py` (append-only JSONL, path from `HSM_AUDIT_PATH`) |
| Write service | `mock_hsm/writes.py` (add/edit/delete/CSV routes for 11 record kinds) |
| API | `mock_hsm/server.py` (sessions, `/audit`, write routes, 503 on publish/PO when audit unavailable) |
| Client | `agents/hsm_client.py` (write methods, retry) |
| Dashboard | `dashboard/app.py`, `actions.py`, `session.py`, `manage_tab.py`, `audit_tab.py`, `kind_forms.py`, `csv_rows.py`, `safe_text.py` |
| Config | `.streamlit/config.toml`, `requirements.txt` (`streamlit>=1.64`), `.gitignore` (`mock_hsm/audit/`) |
| Docs | `CLAUDE.md`, `README.md`, `dashboard/README.md` |
| Tests | `tests/conftest.py`, 8 new test files, `tests/test_dashboard_data.py` update |

## Reconcile points

1. **CLAUDE.md** — the working tree has an uncommitted paragraph saying the
   project hooks are registered in `.claude/settings.local.json`, plus the
   "A new project hook goes in `settings.local.json`" sentence. a189674 rewrites
   the adjacent "dashboard is read-only" paragraph. Merge by hand so both
   survive; do not drop either.
2. **.gitignore** — a189674 carries an older copy of the
   `# BEGIN AI-DLC:gitignore` block, which is already present (newer) in the
   working tree. Take only a189674's non-AI-DLC additions (the
   `mock_hsm/audit/` line); never duplicate the block.
3. **Dependency** — `requirements.txt` moves to `streamlit>=1.64`; install it
   into `.venv` before running dashboard tests.
4. **Safety invariants that must hold after the restore** (checked, not
   changed): `publish_schedule` / `submit_purchase_order` stay `ask`-gated in
   `.claude/settings.json`; `require_no_violations.py` still re-validates
   publishes; the dashboard exposes no publish/submit/draft action for any
   persona; the 503-when-audit-unavailable path fails closed.

## Testing Contract

```json
{
  "version": 1,
  "methodology": "test-after",
  "source": "org",
  "ordering": "implement each applicable testable layer, then write and run that layer's tests.",
  "scope": "dashboard-writes-restore",
  "test_strategy": "minimal",
  "project_type": "brownfield",
  "applicable_notes": [
    {
      "layer": "org",
      "text": "We treat tests as a first-class deliverable in every Bolt. The specific\nmethodology (TDD, BDD, ATDD, or classic test-after) is affirmed at\npractices-discovery and recorded in `team.md` under this heading with explicit\n`Methodology` and `Ordering` fields; Code Generation resolves those fields\nindependently from coverage, tooling, and scope notes.\n\nWhen no posture has been affirmed, our default per scope is:\n- **Methodology**: test-after\n- **Ordering**: implement each applicable testable layer, then write and run\n  that layer's tests.\n- `mvp`, `enterprise`, `feature`, `infra`, `classic` add an 80% line-coverage\n  floor and CI execution before merge.\n- `bugfix`, `security-patch` add a targeted regression for the specific\n  bug/vulnerability and require the existing suite to remain green.\n- `express` uses the Minimal strategy: requirement-driven unit tests (one per\n  requirement, with a happy-path floor per component); existing tests remain\n  green.\n- `poc`, `refactor`, `workshop` add no extra new-test floor and require the\n  existing suite to remain green.\n\nThe active `Test Strategy` still applies in every scope and determines test\nvolume/types. Scope floors are additive; they never reduce or replace the\nselected strategy.\n\nBuild and Test verifies defined coverage floors and affirmed quality targets;\nthey may not be weakened to make a step pass.\n\nAffirm a stricter posture in `team.md` if the team commits to one."
    }
  ],
  "obligations": {
    "strategy": "minimal",
    "strategy_volume": [
      "One verifiable test per requirement at the narrowest effective level.",
      "At least one happy-path unit test per component.",
      "Unit tests are the default; a bugfix/security scope floor may require an integration or E2E regression when that is the narrowest level that reproduces the defect."
    ],
    "scope_floor": [
      "Keep the existing test suite green.",
      "This scope adds no extra new-test floor beyond the selected test strategy."
    ],
    "combination_rule": "Apply every selected-strategy obligation and every scope-floor obligation; neither replaces the other, and a targeted scope regression may add the narrowest necessary test type beyond the strategy default."
  },
  "plan_profile": {
    "methodology": "test-after",
    "runner_step": "Verify the existing test runner/configuration and record the exact unit-scoped command.",
    "runner_ready_before_first_test": true,
    "testable_layers": [
      "Data model / database behavior",
      "Repository / data access",
      "Business logic",
      "API / endpoint",
      "Frontend behavior"
    ],
    "steps": [
      "Project structure and production configuration skeleton.",
      "Verify the existing test runner/configuration and record the exact unit-scoped command.",
      "Data model / database behavior - implement.",
      "Data model / database behavior - write and run its tests after implementation.",
      "Repository / data access - implement.",
      "Repository / data access - write and run its tests after implementation.",
      "Business logic - implement.",
      "Business logic - write and run its tests after implementation.",
      "API / endpoint - implement.",
      "API / endpoint - write and run its tests after implementation.",
      "Frontend behavior - implement.",
      "Frontend behavior - write and run its tests after implementation.",
      "Environment/build configuration.",
      "Documentation and traceability."
    ]
  },
  "input_sha256": "sha256:53d420d12b635983e2922f0853ef08179095000693275e3726c05048b475920a",
  "contract_sha256": "sha256:755a459ce28e6b43f4da199e3c39cdd3180a2de61d88e124640ef8063fb6b459"
}
```

## Steps

Test-after ordering: restore each layer, then restore and run that layer's
tests. Requirement IDs below (`R1`-`R8`) are this plan's own labels for what
a189674 delivers, used in `traceability.json`.

- R1 Writes to mock records (add/edit/delete/CSV) for in-scope personas only
- R2 Login/session per persona; 403 outside scope
- R3 Append-only audit trail of every write, readable via `/audit`
- R4 Publish/PO routes fail closed (503) when the audit trail is unavailable
- R5 Client write methods with bounded retry
- R6 Dashboard "Manage data" and "Audit" tabs; no publish/submit/draft action
- R7 Existing safety gates unchanged (ask rules, publish re-validation hook)
- R8 Existing suite stays green

- [x] Step 1: Project structure and configuration skeleton — restore
  `.streamlit/config.toml`; apply `requirements.txt` (`streamlit>=1.64`) and
  install it into `.venv`; add a189674's `mock_hsm/audit/` line to `.gitignore`
  outside the AI-DLC block (reconcile point 2). (R8)
- [x] Step 2: Verify the test runner — run the existing suite
  (`.venv/bin/python -m pytest tests/ -q`) to record the green baseline before
  any restore, and confirm `ruff check .` is clean. (R8)
- [x] Step 3: Data model — restore `mock_hsm/db.py` from a189674. (R2)
- [x] Step 4: Data model tests — restore `tests/conftest.py` (audit path to a
  temp file); run `tests/test_dashboard_data.py` after restoring its a189674
  version. (R2, R8)
- [x] Step 5: Repository / data access — restore `mock_hsm/audit.py`. (R3)
- [x] Step 6: Repository tests — restore and run `tests/test_audit_log.py`. (R3)
- [x] Step 7: Business logic — restore `mock_hsm/writes.py`. (R1)
- [x] Step 8: Business logic tests — restore and run
  `tests/test_writes_core.py` and `tests/test_writes_service.py`. (R1)
- [x] Step 9: API / endpoint — restore `mock_hsm/server.py` and
  `agents/hsm_client.py`. (R1-R5)
- [x] Step 10: API tests — restore and run `tests/test_writes_routes.py`,
  `tests/test_audit_routes.py`, `tests/test_hsm_client_writes.py`. Confirm a
  route test covers the 503 fail-closed path on publish and PO submit; if none
  does, add one to `tests/test_audit_routes.py`. (R1-R5)
- [x] Step 11: Frontend behavior — restore `dashboard/app.py`, `actions.py`,
  `session.py`, `manage_tab.py`, `audit_tab.py`, `kind_forms.py`,
  `csv_rows.py`, `safe_text.py`. (R6)
- [x] Step 12: Frontend tests — restore and run `tests/test_dashboard_units.py`
  and `tests/test_dashboard_app.py` (includes the no-publish/submit/draft-button
  test). (R6)
- [x] Step 13: Environment/build configuration — run the full suite and
  `ruff check .`; confirm `.claude/settings.json` still has both `ask` rules
  and `.claude/settings.local.json` still registers both project hooks
  (read-only check, no edits). (R7, R8)
- [x] Step 14: Documentation and traceability — restore `README.md` and
  `dashboard/README.md`; merge `CLAUDE.md` by hand (reconcile point 1); write
  `code-summary.md`, `source-manifest.json`, `traceability.json`. (R1-R8)

## Out of scope

- No redesign or new features beyond a189674.
- No changes to `.claude/settings.json`, `.claude/settings.local.json`, hooks,
  MCP tools, or subagent definitions.
- No commit; committing goes through `/commit` afterwards.
