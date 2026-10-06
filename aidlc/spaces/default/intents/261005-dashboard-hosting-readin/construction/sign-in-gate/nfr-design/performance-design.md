# Performance Design — U3 sign-in-gate

## Sources

- `nfr-requirements/performance-requirements.md` NFR2.11, NFR2.12, NFR2.13
- `functional-design/functional-spec.md` W1 (the gate runs first on every rerun) and the VisitorAccess state machine (recomputed each rerun)
- `inception/contract-design/contract-summary.md` C4 (SignInGate API), C7 (hosted secrets schema)
- `nfr-design-questions.md` Q1 A, Q2 A (summary confirmed)

## Design Decisions

### P1 — Gate cost on one rerun (NFR2.11)

The gate is a fixed, short sequence of in-memory steps with no loop that grows with anything but the allowlist:

| Step (W1) | Work | Cost driver |
|-----------|------|-------------|
| 0 Page header | page setup and one h1 | constant |
| 1 Bridge | one read of the hosted secrets mapping, at most one environment write | constant |
| 2 Secret check | `require_secret()` from `mock_hsm.auth`: one environment read and a length check | constant |
| 3 Settings check | five key lookups | constant |
| 4 Allowlist | `parse_allowlist`: one pass, trim and lower-case each entry, return a tuple | linear in entries (tens) |
| 5 Identity | one read of Streamlit's user object through the seam | constant |
| 6 Decision | `decide`: trim and lower-case one email, membership test on the tuple | linear in entries |
| 7 Log | at most one log line, and only the first time a reason is seen in the session | constant |
| 8 Render | one gate screen (two or three elements) or hand-off to DashboardShell | constant |

- **No caching of access.** The decision is recomputed on every rerun by design (functional spec: "Nothing about access is cached between reruns"), so an allowlist edit or a broken setting takes effect on the next interaction. The work is too small to need a cache, and a cache would add a staleness path to a security decision.
- **The allowlist stays a tuple.** At tens of entries, a linear membership test costs microseconds. Converting it to a set would change C4's return type for no measurable gain.
- **The 50 ms budget is advisory.** A `perf`-marked test runs the whole gate 50 times in-process through the shared test helper (Q2 A) with a fake allowed identity and a 50-entry allowlist, and asserts the 95th percentile is at most 50 ms. It runs by hand with `-m perf` and never in CI (team.md Testing Posture; project.md Forbidden). P2's no-I/O test is the CI proxy that keeps the gate cheap.

### P2 — No I/O of the gate's own (NFR2.12)

- The only external reads are the hosted secrets mapping and the environment. Streamlit loads the secrets file itself; the gate only reads the mapping it exposes.
- The only external write is a log line, through the standard `logging` module to the app's log.
- The gate opens no file, socket or subprocess. Ending the backend session at sign-out is a backend call, but it belongs to W4, which the visitor starts. It is not part of the gate's rerun path.
- **CI test:** with the identity seam patched, the test replaces `socket.socket.connect` and `socket.create_connection` with a function that records the call and raises. It runs one allowed gate and one refused gate (signed out, not listed and settings missing), and asserts nothing was recorded. The embedded backend's start is stubbed in the allowed run, because the start (U2) is outside the gate.

### P3 — No waiting (NFR2.13)

- The gate has no `time.sleep`, no retry loop and no polling. Every failure is decided once and becomes Screen 5 on the same rerun (security-design S3), so the gate never adds to NFR2's 30-second cold-start figure.
- **CI test:** an AST scan of `dashboard/auth_gate.py` and `dashboard/secrets_bridge.py` fails on any call to `time.sleep` or `sleep` and on any `while` loop. It also fails on a `for` loop whose body contains a `try` statement, which is the usual shape of a retry loop.

## Assumptions & Open Questions

- [assumption] Streamlit's own sign-in redirect and callback time stays outside this unit's budget (performance-requirements). The post-deploy check (U5) times only the signed-out path.
- [assumption] Reading `st.secrets` after Streamlit has loaded the file doesn't touch the disk again on each rerun. If it does in 1.64.0, the read is Streamlit's work, not the gate's, and P2's socket test still holds because it covers network I/O only. The disk side of NFR2.12 is held by code review of the two modules.
