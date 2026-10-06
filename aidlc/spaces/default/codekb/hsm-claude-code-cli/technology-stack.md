# Technology Stack: hsm-claude-code-cli

Commit `825a0f8`. Versions from `requirements.txt` / `requirements-dev.txt`.

## Language and Runtime

| Item | Version | Notes |
|---|---|---|
| Python | 3.10 floor | `ruff.toml` `target-version = "py310"`; locks compiled with `--python-version 3.10` |
| Python (dev, CI gate) | 3.14.7 | CI matrix runs 3.10 and 3.14 (plus optional `vars.HOSTED_PYTHON`) |

## Application Frameworks and Libraries

| Library | Version | Where | Purpose |
|---|---|---|---|
| Python stdlib (`http.server`, `urllib`, `hmac`, `hashlib`, `threading`, `zoneinfo`, `json`) | n/a | `mock_hsm`, `agents` | Backend, REST client, tokens, site-local dates |
| `streamlit` | 1.64.0 | runtime | Dashboard UI; brings `pandas` (2.3.3 on 3.10, 3.0.6 on 3.11+), `altair` 6.x, `pyarrow` 25.0.1, `starlette` 1.7.0, `uvicorn` 0.54.0 |
| `mcp[cli]` | 1.30.0 | dev only | FastMCP stdio server (pinned to 1.x; 2.x renamed the API) |

Not present yet, needed by the hosting intent: `Authlib` (via
`streamlit[auth]`, for `st.login`) and `playwright` (browser tests). See
`dependencies.md` and `code-quality-assessment.md` CQ-6.

## Tooling

| Tool | Version | Purpose |
|---|---|---|
| `ruff` | 0.16.8 | Lint (`ruff.toml`) and format |
| `pytest` | 9.1.1 | Test runner; custom `perf` and `browser` markers |
| `pytest-rerunfailures` | 16.7 | One CI retry |
| `coverage` | 7.16.2 | Line coverage with subprocess measurement |
| `bandit` | 1.9.4 | SAST, `--ignore-nosec` |
| `pip-audit` | 2.10.1 | Dependency audit |
| `cvss` | 3.6 | Scores OSV vectors in `filter_audit.py` |
| `tomli` | (Python < 3.11) | Reads `security-exceptions.toml` |
| `uv pip compile` | n/a | Compiles hash-pinned lockfiles |
| gitleaks, actionlint | CI actions | Secret scan, workflow lint |

## Configuration Files

`requirements.in`, `requirements-dev.in` and their `.txt` locks; `ruff.toml`;
`.coveragerc`; `.streamlit/config.toml` (`address = "127.0.0.1"`,
`maxUploadSize = 2`); `.gitleaks.toml`; `security-exceptions.toml`;
`.mcp.json` (passes `HSM_BASE_URL` to the MCP server); `.test-floor` (745);
`.coverage-floor` (95.00); `.claude/settings.json`;
`.claude/settings.local.json.example`.

## Hosting Target (decided upstream, not yet implemented)

Streamlit Community Cloud, two apps (staging tracks `main`, production tracks a
promote-only branch), in-app `st.login` with an email allowlist, backend in the
same process on loopback. See `team.md` / `project.md` § Deployment.
