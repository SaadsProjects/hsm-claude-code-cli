# Build Instructions — Restore dashboard writes (a189674)

Inputs: `code-generation-plan` (Steps 1 and 13), `unit-test-instructions`
(framework and setup), and `code-summary` (files changed) under
`construction/code-generation/`.

## Prerequisites

- Python 3.10+ with the project virtualenv at `.venv/`.
- No compile or bundle step: the project is plain Python, a Streamlit app and an
  in-memory mock backend.

## Dependency installation

```bash
.venv/bin/python -m pip install -r requirements.txt   # streamlit>=1.64, mcp<2, pytest, ...
.venv/bin/python -m pip check                         # expect: No broken requirements found.
```

`ruff` is only installed in `.venv` on this machine; use `.venv/bin/ruff`.

## Environment

| Variable | Purpose | Default |
|----------|---------|---------|
| `HSM_BASE_URL` | Backend URL used by `HsmClient` | `http://127.0.0.1:8770` |
| `HSM_ACTIVE_USER` | Persona for the MCP server (export before starting `claude`) | none |
| `HSM_AUDIT_PATH` | Audit-trail JSONL file | `mock_hsm/audit/audit.jsonl` (gitignored) |
| `HSM_JURISDICTION` | Jurisdiction used by the publish re-validation hook | `GA` |

`.streamlit/config.toml` binds the dashboard to this machine and caps uploads
at 2 MB. Tests point `HSM_AUDIT_PATH` at a temp file through `tests/conftest.py`.

## Build verification

```bash
.venv/bin/python -c "import mock_hsm.server, mock_hsm.writes, mock_hsm.audit, agents.hsm_client, dashboard.app"
.venv/bin/ruff check .
```

Run the services locally:

```bash
python3 -m mock_hsm.server &            # backend on 127.0.0.1:8770
streamlit run dashboard/app.py          # dashboard with login and data writes
```

## Troubleshooting

- `ModuleNotFoundError: mock_hsm.writes` when collecting tests: the conftest
  imports the audit and write modules, so the restore must include both.
- Dashboard `AppTest` errors on older Streamlit: reinstall from
  `requirements.txt` (needs 1.64+).
- Publish or PO returns 503 "audit unavailable": `HSM_AUDIT_PATH` points at an
  unwritable or corrupt file. This is the intended fail-closed behaviour.
