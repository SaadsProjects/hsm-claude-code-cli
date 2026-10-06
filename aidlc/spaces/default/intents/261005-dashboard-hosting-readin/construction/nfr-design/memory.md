<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->

- 2026-10-06T00:30:00Z — U3 sign-in-gate is a ui-kind unit, so only performance, security, logical-components and traceability were produced; NFR3.11 (test seam, floors) and NFR5.11 (screen accessibility) were placed in logical-components and NFR4.11 (refusal logging) in security-design, since no reliability or observability design applies to the kind.
- 2026-10-06T00:30:00Z — the literal-email rule (NFR1.27) reuses the existing dashboard.safe_text.escape_md rather than a new helper, and the gate's boundary relies on Streamlit 1.64.0's StopException/RerunException deriving from BaseException (checked against the installed package).

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-05T16:35:00Z — the per-unit reviewer's exempt list held only the passed artifacts, so the reviewer-scope hook blocked it from reading the source files it was told to check; future per-unit reviewer dispatch records should also exempt the code-context paths.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-05T16:35:00Z — U1 NFR design review (READY) items for the code plan: pick one burned-value test mechanism that keeps the scan green (e.g. test asserts BURNED_SHA256 equals the sha256 recorded in .gitleaks.toml's allowlist, or similar excluded source); the start script must not `source` .env.local — let Python's load_local_secret be the only loader; hook's auth import inside the deny-guarded try with a test; local `streamlit run` .env.local loading belongs to U3's SecretsBridge; 503 warning logs path without query string.
- 2026-10-06T00:40:00Z — U3 NFR design review (READY, two Major) items for the code plan: R-01 end_visitor_session must clear state in a finally (or before the backend call) and also catch SecretMissingError/ValueError from mint_token, with a broken-secret sign-out test; R-02 one owner for the page header — gate() renders set_page_config + h1 and app.py drops its own (lines ~455-456); R-03 render the email with a non-Markdown element or pin the escaped value in the test; R-04 render each gate screen into one st.empty that Screen 5 replaces; R-05 account binding compares trimmed lower-cased emails and the first allow only binds; R-06 write the AppTest nested-secrets helper test first.
