# Code Summary — Restore dashboard writes (a189674)

Commit `a189674` ("Add dashboard data writes with sessions, audit trail and
client retry") was restored on top of `main` (`034684e`) in the working tree.
Nothing is staged or committed. Committing goes through `/commit`.

## Files created or modified

28 of the 29 files in a189674 are byte-identical to a189674 (checked with
`cmp` against `git show a189674:<path>`). `CLAUDE.md` is the only hand merge
that differs from a189674.

| Kind | Files |
|------|-------|
| Created | `.streamlit/config.toml`, `mock_hsm/audit.py`, `mock_hsm/writes.py`, `dashboard/actions.py`, `dashboard/session.py`, `dashboard/manage_tab.py`, `dashboard/audit_tab.py`, `dashboard/kind_forms.py`, `dashboard/csv_rows.py`, `dashboard/safe_text.py`, `dashboard/README.md`, `tests/conftest.py`, `tests/test_audit_log.py`, `tests/test_audit_routes.py`, `tests/test_dashboard_app.py`, `tests/test_dashboard_units.py`, `tests/test_hsm_client_writes.py`, `tests/test_writes_core.py`, `tests/test_writes_routes.py`, `tests/test_writes_service.py` |
| Modified (restored byte-for-byte) | `mock_hsm/db.py`, `mock_hsm/server.py`, `agents/hsm_client.py`, `dashboard/app.py`, `requirements.txt`, `README.md`, `tests/test_dashboard_data.py` |
| Modified (hand merge) | `.gitignore`, `CLAUDE.md` |

Not touched: `.claude/settings.json` (it already had uncommitted changes
before this stage), `.claude/settings.local.json`, hooks, `mcp_server/`,
subagent definitions and AI-DLC files.

## Key decisions

- **`.gitignore` (reconcile point 2).** Added only a189674's two lines
  (`# Audit trail data …` and `mock_hsm/audit/`) above the existing
  `# BEGIN AI-DLC:gitignore` block. The file has exactly one AI-DLC block. The
  result happens to match a189674 byte-for-byte, because the working tree's
  block matches the copy a189674 carried.
- **`CLAUDE.md` (reconcile point 1).** Applied a189674's three hunks: the
  `-m perf` command line, the dashboard command comment, and the dashboard
  paragraph rewritten into three paragraphs about read-only tabs, writes and
  the audit trail. Kept the working tree's paragraph saying the project hooks
  are registered in `.claude/settings.local.json`, and its sentence "A new
  project hook goes in `settings.local.json`." Diffing against a189674 shows
  only those two additions.
- **Dependency (reconcile point 3).** `.venv` already had streamlit 1.64.0,
  which satisfies `>=1.64`. `pip install -r requirements.txt` ran cleanly with
  no changes.
- **Safety invariants (reconcile point 4)** were checked without editing
  anything:
  - `.claude/settings.json` `permissions.ask` still lists
    `mcp__hsm__publish_schedule` and `mcp__hsm__submit_purchase_order`.
  - `.claude/settings.local.json` still registers `require_no_violations.py`
    for `mcp__hsm__publish_schedule` and `lint_before_commit.py` for `Bash`.
  - The dashboard has no publish, submit or draft action. Two tests enforce
    this: `test_no_publish_or_submit_button_for_any_persona` and
    `test_no_publish_or_submit_anywhere_in_the_dashboard`.
  - The audit trail fails closed. When it can't be written, publish and PO
    return 503 and nothing is stored.

## Test results

Runner: `.venv/bin/python -m pytest` (Python 3.14.7, streamlit 1.64.0). Lint:
`.venv/bin/ruff check .`.

| Command | Result |
|---------|--------|
| Baseline `pytest tests/ -q` (before any restore) | 121 passed |
| Baseline `ruff check .` | All checks passed |
| `pytest tests/test_dashboard_data.py -q` | 24 passed (after Step 11; see deviations) |
| `pytest tests/test_audit_log.py -q` | 77 passed, 3 skipped (perf) |
| `pytest tests/test_writes_core.py tests/test_writes_service.py -q` | 216 passed |
| `pytest tests/test_writes_routes.py tests/test_audit_routes.py tests/test_hsm_client_writes.py -q` | 185 passed, 5 skipped (perf) |
| `pytest tests/test_dashboard_units.py tests/test_dashboard_app.py -q` | 136 passed, 4 skipped (perf) |
| **Full suite** `pytest tests/ -q` | **735 passed, 12 skipped** in 86 s |
| Perf tests `pytest tests/ -q -m perf` (for information) | 12 passed, 735 deselected |
| Final `ruff check .` | All checks passed |

All 12 skips have the same reason, "timing test; run with -m perf". a189674's
`tests/conftest.py` skips perf-marked tests by default. They pass when run
explicitly.

Explicit coverage that the unit-test instructions require:

- **R4, 503 fail-closed.** `tests/test_audit_routes.py` covers both routes:
  - `test_unwritable_audit_store_refuses_and_applies_nothing` (publish, PO,
    and an out-of-scope publish)
  - `test_unwritable_audit_store_gives_503_over_http` (publish over HTTP)
  - `test_unreadable_trail_refuses_audited_operations_but_not_reads` (PO over
    HTTP, using a corrupt trail file)

  Coverage already existed, so no test was added (Step 10's condition).
- **R6, no publish/submit/draft action.** The two dashboard tests named under
  Key decisions cover it.

## Deviations from the plan

1. **Step order: the conftest and `writes.py` came earlier.**
   `tests/conftest.py` imports `mock_hsm.audit` and `mock_hsm.writes` at
   module level. No test can run under it until both modules exist. So
   `mock_hsm/writes.py` (Step 7) and the conftest (Step 4) were restored
   together, just before running the Step 6 audit tests. No file content
   changed.
2. **`tests/test_dashboard_data.py` passed in Step 12, not Step 4.** a189674's
   version of this file logs in through `dashboard.session` (Step 11). Its 11
   app-level tests could only pass after the dashboard layer was restored. In
   Step 4, its 13 loader-level tests passed and the 11 app tests failed with
   `ImportError` because `dashboard.session` didn't exist yet. After Step 11,
   all 24 passed.
3. **`dashboard/README.md` came forward from Step 14 to Step 12.**
   `test_dashboard_listens_on_this_machine_by_default` reads it, so the file
   was restored before rerunning the dashboard tests.

No test, threshold or lint rule was changed. No restored file needed a
compatibility fix: since a189674, `main` changed only subagent frontmatter.

## Open questions

- The unit-test instructions say the a189674 tests simulate audit failure by
  pointing `HSM_AUDIT_PATH` at an unwritable location. They don't. The
  route-level 503 tests stub `audit._write_all` with monkeypatch. One test
  uses a corrupt trail file through `HSM_AUDIT_PATH`, but it covers PO only.
  A one-off check in the scratchpad showed that an unwritable
  `HSM_AUDIT_PATH` also returns 503 "audit unavailable" for both publish and
  PO, and stores nothing. No test was added, because the plan allows a new
  test only when coverage is missing. If the team wants an env-path test for
  publish, it would go in `tests/test_audit_routes.py`.
