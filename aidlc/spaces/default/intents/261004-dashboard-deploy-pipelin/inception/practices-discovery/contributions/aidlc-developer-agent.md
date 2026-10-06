**Collaborator:** aidlc-developer-agent

## Contribution

Developer view: naming, layer boundaries, error handling, file organization,
code style, and what the dashboard needs at runtime to be packaged and
deployed. Every claim cites a file in the repo at commit `1586133`.

### 1. Code style and naming (confirms the lead, adds detail)

- Python modules, functions and variables use snake_case. Module-level
  constants use UPPER_SNAKE (`HSM_BASE_URL`, `RETRY_WINDOW`, `CACHE_TTL_SECONDS`,
  `PERSONA_KEY`). Private helpers use a leading underscore (`_client`,
  `_dispatch`, `_now`). Errors are named classes that end in `Error` or name the
  condition (`HsmApiError`, `SessionExpired`, `HsmUnavailable`, `TokenError`,
  `ApiError`). Docstrings cite the design IDs they implement (`NFR2.3`, `BR2.2`,
  `review R-04`). Comments and docstrings say *why*, not what.
- `ruff.toml` pins the rule set but not the ruff version. `requirements.txt`
  lists `ruff` with no version, and `.venv` has 0.16.8. A CI lint gate on an
  unpinned ruff can turn red when ruff ships new checks inside a selected
  group. The pipeline should pin ruff, either in `requirements.txt` or in a
  separate dev requirements file.
- `BLE` (blind except) is selected, so every `except Exception` carries a
  `# noqa: BLE001 -- <reason>` comment (`dashboard/actions.py:129,214`,
  `dashboard/app.py:361`, `mock_hsm/server.py:694`, `mock_hsm/writes.py:1204,1284,1448,1483`).
  Candidate practice: a broad catch is allowed only at a boundary that turns
  the failure into visible state or an HTTP status, and it must carry a
  justified `noqa`. A broad catch with no reason is not allowed.
- No formatter is configured. Adding `ruff format` to an existing codebase
  rewrites many files in one commit. If the team adopts it (Q11), do it as its
  own commit, not inside a pipeline Bolt.

### 2. Layer boundaries: one correction and one coupling the pipeline inherits

- `CLAUDE.md` forbids importing `mock_hsm.db` from the **MCP tool layer** only.
  The dashboard imports the backend package directly:
  `dashboard/app.py:33` (`from mock_hsm.db import USERS`, the persona list) and
  `dashboard/session.py:25` (`from mock_hsm.auth import mint_token`). The
  MCP server does the same with `mint_token` (`mcp_server/hsm_tools.py:29`).
- What this means for deployment:
  1. The dashboard artifact must ship the `mock_hsm` package (and `agents`),
     even if the backend runs as a separate process or container. A
     "dashboard-only" image is not possible without a code change.
  2. The dashboard mints its own HMAC tokens with the same hardcoded secret
     the backend verifies (`mock_hsm/auth.py:23`). If Q9 moves the secret into
     the environment, **both** processes must read the same variable. No such
     variable exists today, so this is a code change in `mock_hsm/auth.py`,
     not just pipeline configuration.
  3. The persona list comes from the dashboard's own copy of `db.USERS`, not
     from the backend. If `HSM_BASE_URL` points at a different backend build,
     the two copies can drift.

### 3. Error handling at integration boundaries (already consistent)

- `agents/hsm_client.py` separates "no answer" (transport errors, mapped to
  `HsmUnavailable` and retried within `RETRY_WINDOW`, which is 14 minutes, inside
  the backend's 15-minute replay window) from "an answer" (`HsmApiError` with
  status and field problems). `SessionExpired` covers exactly the 401
  "no active session" case.
- The backend turns any handler exception into a JSON 500 instead of a
  dropped connection, and refuses gated writes with 503 when the audit trail
  is unavailable.
- In deployment terms, a missing, read-only or unmounted audit path makes
  every data write, publish and PO return 503 while reads still work. A smoke
  check that only reads data will not notice this. It needs an audit
  writability check, or at least a check that the backend starts cleanly,
  since `audit.configure()` runs at boot (`mock_hsm/server.py:720-728`).

### 4. Runtime inventory: what a package or deploy must provide

| Item | Today | Source | Packaging gap |
|---|---|---|---|
| Dashboard entrypoint | `streamlit run dashboard/app.py` | `CLAUDE.md`, `dashboard/README.md` | `app.py:20` adds the repo root to `sys.path`, so the code must keep the repo layout (`agents/`, `dashboard/`, `mock_hsm/` as siblings). |
| Dashboard bind/port | `127.0.0.1`, Streamlit default port 8501 | `.streamlit/config.toml` | That file is read from the **working directory**, so the process must start from the repo root, or the settings must be passed as `STREAMLIT_SERVER_ADDRESS` / `STREAMLIT_SERVER_PORT` / `--server.*`. In a container, `127.0.0.1` cannot be reached from outside, so the address has to be overridden. That override is exactly the "open on purpose" step in `dashboard/README.md`, and Q8 must approve it. |
| Dashboard health | none in app code | — | Streamlit serves `/_stcore/health`. It shows the process is up, not that the backend is reachable. |
| Backend entrypoint | `python3 -m mock_hsm.server` | `scripts/start_mock_server.sh`, `server.py:731` | `run()` hardcodes `host="127.0.0.1", port=8770`. Nothing reads an env var or CLI argument for these. A backend in a **separate** container cannot be reached without a small code change (for example `HSM_BIND_HOST` / `HSM_PORT`). In the **same** container or pod, the loopback default works. |
| Backend health | `GET /healthz` returns 200 `{"status":"ok"}`, public | `server.py:613-618` | Usable as a liveness and smoke target with no token. |
| `HSM_BASE_URL` | default `http://127.0.0.1:8770` | `agents/hsm_client.py:21` | Read once at import time, so it must be set before the process starts. |
| `HSM_AUDIT_PATH` | default `mock_hsm/audit/audit.jsonl` inside the package dir (gitignored) | `mock_hsm/audit.py:64-65,138` | Needs a writable path, preferably on a volume. Inside an image layer it is lost on every redeploy, and a read-only filesystem gives 503s (see §3). |
| `HSM_ACTIVE_USER` | optional; only preselects the persona on the login form | `dashboard/app.py:303` | Not required for the dashboard. The MCP server requires it (`mcp_server/hsm_tools.py:42`), but the MCP server is not part of a dashboard deploy. |
| HMAC secret | hardcoded literal | `mock_hsm/auth.py:23` | See §2.2. There is no env var yet. |
| State | in-memory backend, sessions included (`POST /sessions`, `server.py:559`); Streamlit `session_state` is per browser connection | `CLAUDE.md`, `server.py` | Exactly **one backend instance** is possible: replicas would each hold different data and sessions. Every backend restart or deploy logs every dashboard user out and drops all dashboard-added records. Several dashboard replicas would also need sticky sessions. The simple, correct shape is one dashboard plus one backend. |
| Python | `ruff.toml` targets py310; local `.venv` runs **3.14.7** | `ruff.toml`, `.venv` | The base image or CI Python version is undecided. Tests have only been run on 3.14, and the 3.10 floor is untested. |
| Dependencies | lower bounds only, no lockfile; `.venv` has streamlit 1.64.0, pandas 3.0.6, altair 6.3.0, mcp 1.30.0 | `requirements.txt` | The runtime image needs only streamlit (which brings pandas and altair). `mcp[cli]`, `ruff` and `pytest` are dev or MCP-only. A runtime/dev split plus a lock or constraints file would make builds reproducible (Q11). |
| Upload limit | `maxUploadSize = 2` MB, plus the app's own 960 KiB check and the backend's 1 MiB body cap | `.streamlit/config.toml`, `dashboard/README.md`, `server.py` `_read_body` | If a reverse proxy goes in front, its body limit must allow at least 2 MB. Streamlit also needs WebSocket upgrade on `/_stcore/stream`. |

### 5. File organization conventions for new pipeline files

The repo has no `.github/`, Dockerfile, Makefile or IaC (the lead's evidence
says the same). Proposed defaults for the interview to confirm:

- CI workflows go in `.github/workflows/` if Q11 picks GitHub Actions.
- Container and run files go at the repo root (`Dockerfile`, `.dockerignore`)
  or under a new `deploy/` directory. Shell entrypoints follow
  `scripts/start_mock_server.sh`: bash, `cd "$(dirname "$0")/.."`, and a header
  comment that says what the script starts and on which address. Ruff's `EXE`
  rule set already checks shebang and executable-bit consistency for Python
  files.
- `.dockerignore` must exclude `.venv/`, `aidlc/`, `.claude/settings.local.json`,
  `mock_hsm/audit/` and caches, so audit data and local settings never end up
  in an image.
- Any new Python helper, such as a smoke-check script, goes under `scripts/`
  or `tests/`, follows `ruff.toml`, and uses only the stdlib (`urllib`), the
  same as `HsmClient`.

### 6. Gaps the interview must resolve (beyond lead Q1 to Q12)

- **D1 (adds to Q6/Q9): deployment topology.** Should the dashboard and the
  backend run in one container or pod (no code change; loopback works), or
  separately (needs configurable host and port in `mock_hsm/server.py`)?
- **D2 (adds to Q9): secret externalization.** Is a code change to read the
  HMAC secret from an env var in scope for this intent? It touches the
  dashboard, the backend and the MCP server.
- **D3: Python version** for the image and CI: 3.10 (the declared floor), the
  locally used 3.14, or a matrix of both?
- **D4: audit trail persistence.** Should it live on a volume that outlives
  deploys, or is losing it on each deploy acceptable for a demo? The answer
  changes whether a deploy counts as an "audit-preserving" operation.
- **D5: smoke check depth.** Is `/healthz` plus `/_stcore/health` enough? Or
  must the check also log in through `POST /sessions` and do one read? Any
  smoke check must not call publish or submit (lead Forbidden rule), and it
  should log out afterwards so it does not leave a 15-minute session open.

## Positions

- AGREE: The Code Style section (py310, ruff rules pinned in `ruff.toml`, line length 120, no formatter, lint in CI before merge pending Q11). It matches `ruff.toml` exactly. I only add that the ruff *version* is unpinned (§1).
- OBJECT: The Code Style bullet "The MCP tools and the dashboard call the backend only through `HsmClient` and never import `mock_hsm.db`" — the rule in `CLAUDE.md` covers the MCP tool layer only. The dashboard imports `mock_hsm.db.USERS` (`dashboard/app.py:33`) and `mock_hsm.auth.mint_token` (`dashboard/session.py:25`). The MCP server also imports `mint_token`. Restate it as: "Backend *data* goes through `HsmClient`. The MCP tools never import `mock_hsm.db`. The dashboard imports the persona table and the token minter from `mock_hsm`, so it ships with that package." As drafted, a reader would think the dashboard can be packaged without the backend's code.
- AGREE: Deployment must not be affirmed until Q6 to Q10 are answered. The runtime facts in §4 (hardcoded backend bind, a secret used by two processes, in-memory sessions, a single-instance limit) make those answers determine the design, not just the configuration.
- AGREE: Inference 4, that the security posture of the target is the dominant risk. I add that the dashboard holds the signing secret in-process (§2.2), so exposing the dashboard also exposes everything needed to mint any persona's token.
- AGREE: Walking Skeleton stance (commit, lint and tests, one environment, smoke check). I propose that the smoke check covers both health endpoints and the audit-writability concern in §3 (D5).
- AGREE: Testing Posture stays test-after and provisional, as drafted. I add D3: the Python version CI runs is undecided, because only 3.14 has been exercised.
- AGREE: Discovered rules, Mandated and Forbidden, as candidates. In particular, the "never call publish/submit from a pipeline or smoke step" rule should bind every smoke script the pipeline adds.
- AGREE: The evidence row on dependencies (lower bounds only, no lockfile). I add that the runtime image needs only streamlit, so splitting runtime and dev requirements is a natural practice to ask about under Q11.
