# Scalability Design — U2 embedded-backend

## Sources

- `nfr-requirements/scalability-requirements.md` NFR2.4, NFR2.5
- `functional-design/rules.md` BR2.1

## Design Decisions

### SC1 — One backend per process (NFR2.4)

A module-level holder in `mock_hsm/embedded.py` keeps the current handle, server and thread, guarded by one `threading.Lock`. Python module state lives for the whole process, so it survives every Streamlit rerun and is shared by every visitor session. `start()` holds the lock for the whole check-and-maybe-start sequence, so two concurrent callers can never both start a backend; the second gets the first's handle.

Tests: two sequential calls return the same address; repeated `AppTest` reruns leave one backend; two threads released by a barrier at the same moment both get the same address and exactly one server exists.

### SC2 — Concurrent requests (NFR2.5)

The existing `ThreadingHTTPServer` serves each request on its own thread; no cap is added. The backend's in-memory data and the audit module already serialise their own writes. A test sends 10 concurrent authenticated GET requests from separate threads to one instance and asserts all return 200.

### SC3 — Out of scope

Multiple processes or hosts are not supported: each process would have its own backend and its own demo data. The hosted app runs one process.

## Assumptions & Open Questions

None.
