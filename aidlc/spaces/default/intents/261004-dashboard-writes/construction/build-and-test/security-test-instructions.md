# Security Test Instructions — Restore dashboard writes

Minimal strategy normally adds no security file, but this change adds a login
and write paths next to the project's safety-critical writes, so the security
checks are named explicitly. Sources: `code-generation-plan` reconcile point 4
(safety invariants), `unit-test-instructions` (R4 and R6 must be covered), and
`code-summary` (safety settings check).

## Threats checked (STRIDE)

| Threat | Control | Check |
|--------|---------|-------|
| Spoofing / elevation: write outside persona scope | Server enforces site/region scope per route; 403 otherwise | `tests/test_writes_routes.py` (403 cases) |
| Elevation: dashboard reaching publish or PO submit | No such action exists in the dashboard | `tests/test_dashboard_app.py::test_no_publish_or_submit_button_for_any_persona` |
| Repudiation: unaudited writes | Every write and every publish/PO attempt is appended to the audit trail | `tests/test_audit_log.py`, `tests/test_audit_routes.py` |
| Fail-open when the audit trail breaks | Publish/PO return 503 "audit unavailable" and store nothing | `tests/test_audit_routes.py::test_unwritable_audit_store_gives_503_over_http`, `::test_unreadable_trail_refuses_audited_operations_but_not_reads` |
| Information disclosure via audit view | Restricted manager's audit view cannot be widened by query parameters | `tests/test_audit_routes.py::test_restaurant_manager_view_cannot_be_widened` |
| Bypass of existing gates | `ask` rules for `publish_schedule` / `submit_purchase_order` in `.claude/settings.json`; `require_no_violations.py` hook | `tests/test_hooks.py` (hook behaviour); manual read of the settings files (no automated test) |

## How to run

```bash
.venv/bin/python -m pytest tests/test_writes_routes.py tests/test_audit_routes.py tests/test_dashboard_app.py tests/test_hooks.py -q
.venv/bin/ruff check .
```

Manual check of the safety settings (read-only):

```bash
python3 -c "import json;print(json.load(open('.claude/settings.json'))['permissions']['ask'])"
python3 -c "import json;print([h['hooks'][0]['command'] for h in json.load(open('.claude/settings.local.json'))['hooks']['PreToolUse']])"
```

## Known gaps

- The 503 publish test breaks the trail with a monkeypatch, not an unwritable
  `HSM_AUDIT_PATH`. The PO path is also covered with a corrupt trail file.
- The `ask` rules and hook registration are checked by reading the files, not by
  a test. `settings.local.json` is gitignored, so a fresh clone has no hooks.
- No SAST or dependency CVE scan is configured in this repo.
