# Logical Components — U3 sign-in-gate

## Sources

- `nfr-requirements/security-requirements.md` NFR1.21–NFR1.28, NFR4.11, NFR5.11; `performance-requirements.md` NFR2.11–NFR2.13, NFR3.11; `tech-stack-decisions.md`
- `functional-design/functional-spec.md` W1–W5; `functional-design/frontend-components.md`
- `inception/contract-design/contract-summary.md` C1, C3, C4, C5, C6, C7
- `nfr-design-questions.md` Q1 A, Q2 A (summary confirmed)
- `security-design.md` and `performance-design.md` in this directory

## Components

| Component | Module | Responsibility | NFR patterns applied |
|-----------|--------|----------------|----------------------|
| SecretsBridge | `dashboard/secrets_bridge.py` | Copy the hosted signing secret into the environment when it is unset there. Treat unreadable secrets as absent | Copy only when unset; guarded read (security-design S4) |
| Decision core | `dashboard/auth_gate.py`: `parse_allowlist`, `decide` | Pure allowlist parsing and the access decision | Pure functions, an `is True` check, exact match (S2) |
| Identity seam | `dashboard/auth_gate.py`: `current_identity`, `sign_in`, `sign_out` | The only calls to `st.user`, `st.login` and `st.logout` | Thin seam patched in tests (S2) |
| Gate | `dashboard/auth_gate.py`: `gate`, `_render_screen`, `_render_unavailable`, `_log_refusal_once` | Run W1, render Screens 1, 2 or 5, and log each refusal once | One error boundary (S3); once-per-session logging (S7); no I/O and no waiting (P2, P3) |
| Visitor session | `dashboard/auth_gate.py`: `end_visitor_session`, `render_account_section` | Sign-out state clearing, the account binding and the sidebar Account section | Best-effort backend end; key list from `session.py` (S6) |
| Markers | `dashboard/markers.py` | String constants for screen containers and buttons | Constants only, no Streamlit import (C6) |
| DashboardShell (changed) | `dashboard/app.py` | Call `gate()` straight after the page header and stop unless allowed. Move the persona login under "Demo persona" | Caller rule (S1) |
| Test helper | `tests/` shared helper module (Q2 A) | Build an `AppTest` with dummy sign-in settings, an allowlist, a test signing secret and the seam patched to a chosen identity | One construction point for every dashboard `AppTest` |

## Failure Domains and Blast Radius

| Failure | Contained by | Visitor sees | Blast radius |
|---------|--------------|--------------|--------------|
| Missing or short signing secret, secret equal to cookie secret | Gate secret check | Screen 5 | Every visitor of that app until fixed; no data reachable |
| Missing sign-in key or section | Gate settings check | Screen 5 | Same as above |
| Invalid allowlist | `parse_allowlist` | Screen 5 | Same as above |
| Unexpected exception anywhere in the gate | The one boundary in `gate()` (S3) | Screen 5, Sign out only if an identity can be read | One rerun of one browser session; the next rerun tries again |
| Identity provider outage | Streamlit's sign-in flow | Screen 1 again after a failed sign-in | Sign-in only; nobody is let in |
| Backend failure at sign-out | `end_visitor_session` named catches | Sign-out completes; Screen 1 next | None: the backend session times out on its own |
| Embedded backend fails to start | U2, after the gate allows | Screen 4 with the Account section | Allowed visitors only; the gate is unaffected |

The gate has no dependency that can make it fail open. Every failure path above ends on Screen 1, 2, 4 or 5, and only `allow` reaches the backend or the persona picker.

## Shared Resources

| Resource | Shared with | Isolation |
|----------|-------------|-----------|
| `HSM_SIGNING_SECRET` in `os.environ` | `mock_hsm.auth` (C1), the embedded backend (U2) | The bridge writes it only when unset. It is read at call time and never logged |
| Streamlit secrets | Streamlit's own `st.login` (`[auth]` keys) | The gate reads the keys and never writes them |
| Browser session state | Existing dashboard modules (`session.py`) | The gate owns two keys: the refusal log marks and the account binding. It clears the others only through `end_visitor_session` |
| Logger namespace | None | `dashboard.auth_gate` is used only by this unit |

## Screens and Accessibility (NFR5.11)

- `gate()` renders the page header first, on every path. That is the one h1, "HSM labor & inventory" (BR4.4). No gate screen calls `st.title` or a Markdown heading of level 1, so each of Screens 1, 2 and 5 has exactly one h1.
- Each screen states its message as text elements with the fixed mockup copy and offers one standard `st.button`. Streamlit buttons are native `<button>` elements, reachable with Tab and activated with Enter.
- Each screen container and button carries its constant from `dashboard/markers.py` as its key (C6), so `AppTest`, the browser tests and the post-deploy check find them the same way.
- **Tests:** an `AppTest` per screen asserts one h1 and the exact copy. The keyboard check runs in U5's browser tests, against the same markers.

## Test Seam and Floors (NFR3.11, Q2 A)

- One shared helper builds every dashboard `AppTest`. It sets dummy values for the five sign-in keys and `HSM_ALLOWED_EMAILS` in the `AppTest` secrets, sets the test signing secret from `tests/conftest.py`, and patches `current_identity` (and `sign_in` and `sign_out`) to a fake identity. The default identity is signed in, verified and listed.
- The three existing `AppTest.from_file` points in `test_dashboard_app.py`, `test_dashboard_data.py` and `test_dashboard_embedded.py` switch to the helper, so all 66 existing tests pass through the gate as an allowed visitor (AC4.8.1). The gate's own tests call the helper with other identities and settings. No autouse fixture patches the gate, so a test that forgets the helper meets the real gate and fails closed rather than passing silently.
- `auth_gate.py`, `secrets_bridge.py` and `markers.py` are under `dashboard/`, which `.coveragerc` measures. The tests for S1–S8 and P1–P3 cover their paths, so line coverage over `dashboard/` doesn't fall. The passing count stays at or above `.test-floor` on both Python legs, and `coverage-gate` stays green.

## Assumptions & Open Questions

- [assumption] `AppTest` in Streamlit 1.64.0 accepts secrets set on the test object (`at.secrets[...]`) and exposes them to `st.secrets` inside the script. The helper depends on this. If nested `[auth.google]` keys can't be set this way, the helper patches the secrets read in `secrets_bridge` and the settings check instead, and nothing else changes.
