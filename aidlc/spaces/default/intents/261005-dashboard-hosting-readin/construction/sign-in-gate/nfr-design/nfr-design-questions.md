# NFR Design Questions — U3 sign-in-gate

The approved requirements already fix most of the design:
- a pure decision function plus a thin identity seam;
- fail closed to Screen 5 on any error;
- one refusal log line per reason per session, at INFO or WARNING;
- no I/O beyond reading secrets and logging, and a 50 ms advisory budget;
- `streamlit[auth]` through the lock.

These questions cover the two design choices still open.

## Q1 — Where does the gate catch unexpected errors?

The team allows a broad `except Exception` only at a boundary that turns the failure into visible state, with a `# noqa: BLE001 -- <reason>` comment.

A. One boundary: the gate's entry function wraps all of its steps (settings, allowlist, identity, decision, screen rendering) in a single catch that turns any error into Screen 5 and a `gate_error` log line. Screen 5's own guarded identity read is the only other catch (Recommended)
B. A catch around each step, each mapping to its own reason
X. Other (please specify)

[Answer]: A

## Q2 — How do the existing dashboard tests get through the gate?

There are 66 tests in `test_dashboard_app.py`, `test_dashboard_data.py` and `test_dashboard_embedded.py`. They build the app with `AppTest.from_file` in three places. After this unit, every one of them must pass through the gate as an allowed visitor (AC4.8.1), with dummy sign-in settings and an allowlist supplied as AppTest secrets.

A. One shared test helper that builds an `AppTest` with dummy sign-in settings and an allowlist in its secrets, and patches the identity seam to a fake allowed identity. The three existing construction points switch to it, and the gate's own tests use the same helper with other identities (Recommended)
B. An autouse fixture in `tests/conftest.py` that patches the seam to an allowed identity for every test, which the gate tests override
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- **Error boundary (Q1 A):** the gate's entry function wraps all of its steps in one broad catch, with a `# noqa: BLE001 -- <reason>` comment. Any error becomes Screen 5 and one `gate_error` WARNING line naming only the exception type. Screen 5's guarded identity read is the only other catch. Expected failures are signalled by specific checks: a missing or short secret, a missing key, an invalid allowlist.
- **Existing tests (Q2 A):** one shared test helper builds an `AppTest` with:
  - dummy sign-in settings and an allowlist in its secrets;
  - a test signing secret;
  - the identity seam patched to a fake allowed identity.

  `test_dashboard_app.py`, `test_dashboard_data.py` and `test_dashboard_embedded.py` switch their three `AppTest.from_file` points to it. The gate's own tests use the same helper with other identities and settings. No autouse fixture patches the gate.
- **From the approved requirements (unchanged):**
  - a pure decision function and a thin seam;
  - fail closed to Screen 5;
  - refusals logged once per reason per session (INFO for visitors, WARNING for settings and errors);
  - no I/O beyond reading secrets and logging;
  - an advisory 50 ms budget, with a no-I/O test as the CI proxy;
  - no sleep or retry;
  - `streamlit[auth]==1.64.0` through both locks.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
