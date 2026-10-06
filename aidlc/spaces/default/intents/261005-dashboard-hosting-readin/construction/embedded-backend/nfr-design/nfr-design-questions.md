# NFR Design Questions — U2 embedded-backend

The approved requirements fix the targets (2-second start, 0.5-second liveness timeout, 10 concurrent requests, a private audit directory, causes in the log and never on screen). Two design choices are still open.

## Q1 — Where is the pre-existing audit directory checked?

NFR1.13 says a pre-existing audit directory must be a real directory owned by the current user with no group or other access, and that the app never changes the mode of a directory it did not create. Today `mock_hsm/audit.py` narrows whatever parent directory it finds.

A. The embedded start validates (or creates) the private directory itself before configuring the audit trail; `audit.py` is unchanged for the separate-process backend (Recommended)
B. Change `audit.py` so it never narrows a pre-existing directory and refuses a loose one, for both the embedded and the separate-process backend
C. Both: validate in the embedded start, and also harden `audit.py`
X. Other (please specify)

[Answer]: A

## Q2 — How are the start-failure cause and the replacement warning logged?

A. Through Python's standard `logging` module under a `mock_hsm.embedded` logger, at WARNING; Streamlit shows it in the app log (Recommended)
B. Printed to standard error, like the separate-process server's messages
C. Both
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- **Audit directory (Q1 A):** the embedded start validates or creates its private audit directory before configuring the audit trail. A pre-existing directory must be a real directory (not a symlink) owned by the current user with no group or other access, or the start fails. `mock_hsm/audit.py` is unchanged, so the separate-process backend behaves as before.
- **Logging (Q2 A):** the start-failure cause and the "backend replaced, demo data reset" warning go through Python's `logging` module under a `mock_hsm.embedded` logger at WARNING, and appear in the Streamlit app log. The secret value is never logged.
- **Design detail (no choice needed):** a dead backend is stopped without waiting on a thread that has already died (only the socket is closed), and a live-but-unresponsive one is shut down with a bounded wait before its socket is closed; liveness uses the thread check plus a 0.5-second TCP connect; the singleton is a module-level instance behind a lock; the dashboard clears its cached reads after a replacement.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
