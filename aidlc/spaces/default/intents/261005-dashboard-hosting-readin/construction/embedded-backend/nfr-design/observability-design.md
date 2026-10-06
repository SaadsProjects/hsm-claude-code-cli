# Observability Design — U2 embedded-backend

## Sources

- `nfr-requirements/observability-requirements.md` NFR4.2–NFR4.4, NFR5.1
- `nfr-design-questions.md` Q2 (A)
- `inception/refined-mockups/mockups.md` Screen 4

## Design Decisions

### O1 — Logger (NFR4.2, NFR4.3, Q2 A)

`mock_hsm/embedded.py` uses `logging.getLogger("mock_hsm.embedded")`. It logs at WARNING:

- `embedded backend failed to start: <failure_cause>` on every failed attempt;
- `embedded backend replaced on a new port; the demo data is kept` before a replacement attempt (corrects BR2.4 and NFR4.3, which said the data resets; see reliability-design R2).

It logs at INFO `embedded backend listening on http://127.0.0.1:<port>` on a successful start. The module adds no handler; Streamlit's logging configuration shows WARNING and above in the app log. Tests use pytest's `caplog` on that logger name.

### O2 — Backend caption (NFR4.4)

`dashboard/app.py`'s sidebar caption is built at render time from `embedded.current().address` (with the existing cache-TTL text), replacing the import-time `HSM_BASE_URL`. An `AppTest` asserts the caption contains the running handle's address.

### O3 — Screen 4 (NFR5.1)

When the start returns a failed handle, `run()` logs nothing further (O1 already logged), renders the page title as an h1 and then the fixed text "The demo backend didn't start. Reload the page or try again later.", and returns before the persona login, site picker, banner or tabs. The text is plain markdown, not colour-coded. The Account section with "Sign out" is added by U3.

### O4 — No metrics or alerts

There is no monitoring stack for the demo; the post-deploy check (U5) is the deployment health signal.

## Assumptions & Open Questions

None.
