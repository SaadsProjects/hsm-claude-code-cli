# Reliability Design — U2 embedded-backend

## Sources

- `nfr-requirements/reliability-requirements.md` NFR3.3–NFR3.8
- `functional-design/rules.md` BR2.2–BR2.5, BR3.3, BR4.2, BR6.1
- `functional-design/functional-spec.md` W1–W3 and the state machine

## Design Decisions

### R1 — One attempt, no loop (NFR3.3)

`start()` makes at most one new attempt per call and returns a handle with `status="failed"` instead of raising. It never sleeps or retries. The dashboard calls it once per rerun, so a visitor's reload is the retry.

### R2 — Replacing a dead backend (NFR3.4)

```
retire(old):
    if old.thread.is_alive():                       # alive but not answering
        t = Thread(target=old.server.shutdown, daemon=True); t.start(); t.join(SHUTDOWN_WAIT_S)
    old.server.server_close()                       # always release the socket
    log WARNING "embedded backend replaced on a new port; the demo data is kept (it lives in mock_hsm.db)"
SHUTDOWN_WAIT_S = 1.0
```

Correction to BR2.4 and NFR4.3: the demo data lives in `mock_hsm.db` module state, not in the server object, so a replacement within the same process keeps it. The warning still records the replacement, but says the data is kept rather than reset; only a process restart resets the data.

`server.shutdown()` waits for the serve loop to exit and would block forever if that loop is gone, so it is never called on a dead thread and is bounded when called on a live one. After `retire`, `start()` continues with one new attempt.

### R3 — Audit readiness (NFR3.5)

After `audit.configure(path)`, the start calls a new small public function in `mock_hsm/audit.py`, `unavailable_reason()`, which returns the current trail's unavailable reason or `None`. This is the one change to `audit.py`, and it is read-only. A reason means a failed start with that reason as the cause, before anything binds.

### R4 — No lazy start in the client path (NFR3.6)

`dashboard.session.client_for(user_id)` calls `embedded.current()`. If it returns `None`, `client_for` raises `BackendNotRunning` (a `RuntimeError` subclass defined in `mock_hsm/embedded.py`) with a message naming the cause; it never calls `start()`.

### R5 — Separate backend unchanged (NFR3.7)

`mock_hsm/server.py` `run()` and `main()` are not changed. The embedded start reuses the server's request handler class and does not modify it. The existing MCP and hook tests run unchanged.

### R6 — Test-first and floors (NFR3.8)

Every behaviour above gets a failing test first. The new module counts toward coverage (it lives under `mock_hsm/`), so its branches (refusal, audit failure, bind failure, replacement) are each covered.

## Assumptions & Open Questions

None.
