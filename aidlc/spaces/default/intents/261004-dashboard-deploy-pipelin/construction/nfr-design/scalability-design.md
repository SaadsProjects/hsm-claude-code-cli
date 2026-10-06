# Scalability Design — Dashboard Deployment Pipeline

## Sources

- `construction/nfr-requirements/scalability-requirements.md` NFR6.4 to NFR6.6 [scalability-requirements]
- `construction/nfr-design/reliability-design.md` RD5 (backend runtime)

## SC1 — One backend per process (NFR6.5)

`ensure_backend()` is wrapped in `@st.cache_resource` (RD5). Streamlit shares that resource across every session and rerun in the process, so all tabs and users of one app share exactly one `ThreadingHTTPServer`. A unit test calls `ensure_backend()` twice and asserts that one server thread exists and that both calls return the same object.

## SC2 — Concurrent sessions (NFR6.4)

`ThreadingHTTPServer` handles each request on its own thread. The mock's in-memory data is read and mutated only while `db._lock` is held (`mock_hsm/server.py`: reads copy under the lock, and writes plus their audit appends run in one step under it, in lock order db then audit). This design adds no new shared mutable state. Three signed-in tabs are checked manually at the skeleton checkpoint.

## SC3 — No scale-out

There is no load balancing, replication or partitioning. One Streamlit Cloud app equals one process equals one backend. Data is bounded by the seed (NFR6.6). This decision is reversible: the persistence follow-up would replace the in-memory store and is the point at which to revisit it.

## Assumptions & Open Questions

- None. The locking was verified in `mock_hsm/server.py` (`with db._lock:` around reads and writes).
