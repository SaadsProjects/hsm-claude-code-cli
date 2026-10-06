# Performance Design — U2 embedded-backend

## Sources

- `nfr-requirements/performance-requirements.md` NFR2.1–NFR2.3
- `functional-design/functional-spec.md` W1, W2

## Design Decisions

### P1 — Start path (NFR2.1)

A fresh start does only: the secret check, the audit directory check, `audit.configure()` (which loads the existing trail; empty on a fresh host), binding the socket, and starting one daemon thread. The start returns once the socket is bound and the thread has been started; it does not wait for a first request. A test times one fresh start and asserts under 2 seconds (ordinary test, runs in CI).

### P2 — Liveness check (NFR2.2)

```
is_live(handle):
    return handle.thread.is_alive() and probe(handle.port)
probe(port):
    try: socket.create_connection(("127.0.0.1", port), timeout=LIVENESS_TIMEOUT_S).close(); return True
    except OSError: return False      # refused, timed out or reset
LIVENESS_TIMEOUT_S = 0.5
```

The timeout is a module constant so a test can assert it. Tests cover a refused connect (closed port), a simulated timeout (the connect function replaced by one raising `socket.timeout`), and a wall-clock bound of under 1.5 seconds against a closed port.

### P3 — Reuse cost (NFR2.3)

A rerun with a live backend pays only the lock acquisition and one loopback connect (sub-millisecond in practice). No bind, no audit configuration and no thread start happen on reuse.

## Assumptions & Open Questions

None.
