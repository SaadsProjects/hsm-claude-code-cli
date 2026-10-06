# Tech Stack Decisions — U2 embedded-backend

## Sources

- `memory/team.md` Code Style (standard library first; `mock_hsm/` never depends on Streamlit; the single in-process backend start is an imported standard-library-only function in `mock_hsm/`)
- `codekb/hsm-claude-code-cli/technology-stack.md`
- `construction/embedded-backend/functional-design/rules.md` BR1.2

## Decisions

| Area | Choice | Rationale | Alternatives rejected |
|------|--------|-----------|-----------------------|
| Server | The existing `http.server.ThreadingHTTPServer` and request handler from `mock_hsm/server.py`, hosted in a daemon thread | Reuses the backend unchanged; one code path for embedded and separate-process use | A second server implementation (duplicated behaviour); a subprocess (Streamlit Cloud runs one process) |
| Singleton | A module-level instance guarded by `threading.Lock` in `mock_hsm/embedded.py` | Survives Streamlit reruns (module state persists for the process) and serialises concurrent sessions | `st.cache_resource` (would make `mock_hsm` depend on Streamlit); a file lock (unneeded within one process) |
| Liveness probe | `threading.Thread.is_alive()` plus `socket.create_connection` with a 0.5-second timeout | Standard library only; no route change | An HTTP health route (changes the API surface) |
| Audit path | `tempfile.gettempdir()` plus a per-user subdirectory created with mode 0700 | Standard library; avoids narrowing a shared directory's permissions | A file directly in the temp directory (breaks or damages the shared directory) |
| Audit readiness | A small public query on `mock_hsm.audit` returning the unavailable reason | `configure()` never raises; the start needs a definite answer | A probe append (writes a fake audit entry) |
| Dependencies | None added | NFR7 | — |

## Assumptions & Open Questions

None.
