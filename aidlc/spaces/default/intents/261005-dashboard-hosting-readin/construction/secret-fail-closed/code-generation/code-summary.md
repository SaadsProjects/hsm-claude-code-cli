# Code Summary — U1 secret-fail-closed

## Files Changed

All changes are uncommitted on branch `secret-fail-closed`, which was cut from `main` at `825a0f8`.

| File | Change |
|------|--------|
| `mock_hsm/auth.py` | Adds `SECRET_ENV`, `MIN_SECRET_BYTES`, `BURNED_SECRET_SHA256`, `SecretMissingError` (reasons `missing`, `too_short`, `burned`), `require_secret()`, `_secret_bytes()`, `load_local_secret()` and `default_local_secret_path()`. `mint_token` and `verify_token` read the secret on every call. The burned `_SECRET` literal is removed (step 13). |
| `mock_hsm/server.py` | Adds `main(argv)` with `--port` (argparse). It exits 1 and names the variable when there is no usable secret. `_dispatch` turns `SecretMissingError` into a 503 and logs one stderr line that holds the path without its query string. |
| `mcp_server/hsm_tools.py` | `main()` calls `load_local_secret()` before `mcp.run()`. A missing secret reaches the caller as a tool error. |
| `.claude/hooks/require_no_violations.py` | After the tool-name check and before validation, it loads `.env.local` and denies when no usable secret exists, naming the variable. The broad catch gets a `noqa` reason. |
| `scripts/start_mock_server.sh` | Now runs `exec python3 -m mock_hsm.server "$@"`. |
| `scripts/dev-secret.sh` (new, executable) | Writes a mode-600 `.env.local` with a fresh secret. It refuses to overwrite without `--force`, and `--file PATH` points it at another file. |
| `scripts/check_burned_secret.py` | `TEMPORARY_EXCLUSIONS = ()`. |
| `tests/conftest.py` | Sets a fresh `secrets.token_urlsafe(32)` secret at import, always overwriting. |
| `.gitignore` | Explicit `.env`, `.env.local`, `.env.*` and `.streamlit/secrets.toml` lines, placed above the AI-DLC block. |
| `.github/workflows/ci.yml` | Adds the step "No signing secret in the job environment" to the `tests` job: a plain `run` step with no new action or permission. |
| `CLAUDE.md`, `README.md`, `dashboard/README.md` | The dev-secret then start sequence, how the hook and MCP server read `.env.local`, how to export the secret for the local dashboard, and the "Burned secret" paragraph updated. The "no password" wording is gone. |
| `tests/test_signing_secret.py`, `tests/test_secret_entry_points.py` (new) | 56 tests covering the auth module, the loader, the server process, the scripts, the hook, the MCP tools, `.gitignore`, the docs and the burned-literal removal. |

## Key Implementation Decisions

- Plan decisions P1–P9 are applied as written. `require_secret() -> None` wraps `_secret_bytes()`, and `mint_token` still raises `ValueError` for an unknown user.
- The burned value is compared only by its SHA-256. The tests read the value from `.gitleaks.toml`, so no tracked test file holds the literal.
- The server's "listening" line is printed with `flush=True`, so the subprocess tests can detect it through a pipe.
- The local dashboard reads the secret with a `sed` extraction from `.env.local`, without sourcing the file, until U3's secrets bridge lands.

## Test Coverage

- **Unit command:** `python3 -m pytest tests/test_signing_secret.py tests/test_secret_entry_points.py -q` passes 56 tests.
- **Full suite:**
  - 881 passed, 0 failed, 12 skipped (baseline: 825 passed).
  - 881 against a `.test-floor` of 745.
  - Coverage 96.58% against a `.coverage-floor` of 95.00, with the 80% gate on.
- **Static checks:** `ruff check` and `ruff format --check` are clean, `check_burned_secret.py` reports ok, and `check_workflows.py` reports ok.
- **Floor files:** `.coveragerc`, `ruff.toml` and both floor files are unchanged. No `pragma: no cover` and no `nosec` was added.
- **Not run locally:**
  - Python 3.10, actionlint and shellcheck are not installed here.
  - CI on the pull request is their first check.

## Deviations from the Plan

- **Step 7 is only partly done.** The `noqa` reason in `.claude/hooks/lint_before_commit.py` was not added. The workflow's write guard refuses edits to installed hook files, and on 2026-10-05 the human decided to leave this part unfinished. As a result, AC8.4.1 and BR5.2 are only half met: `require_no_violations.py` has its reason, and `lint_before_commit.py` still has a bare `# noqa: BLE001` at line 372.
- **The edit to `.claude/hooks/require_no_violations.py`** was made with a shell write before the same guard began refusing hook-file edits. The human was told and asked to review that diff.
- **Tests added beyond the plan:**
  - `server.main` reads `.env.local`;
  - `.env.production` is ignored;
  - a mint-path 503;
  - a mid-run short-secret leak check;
  - a docs content check.
- **The two-commit split (A: steps 2–12, B: step 13)** is not yet applied. Both sets of changes are mixed in the working tree, so the split needs partial staging (`git add -p`) by the human.
