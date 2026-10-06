<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-04T22:40:00Z — kept mock_hsm/auth.py stdlib-only and put the Streamlit-secrets-to-env bridge in the dashboard, because auth.py is shared with the MCP server and hooks that never import Streamlit.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-04T22:40:00Z — wrote five NFR documents with shell heredocs, which the write hook does not record, so the review request was refused until they were re-saved with the file-write tool; write stage artifacts with Write/Edit only.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-04T22:40:00Z — added a source-fingerprint fallback for the build identifier instead of relying on .git being present in the Streamlit Cloud checkout; it costs one shared helper but removes a single point of failure for every post-deploy check.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-04T22:40:00Z — reviewer R-10 (minor, after the final review): do the burned-secret source check by digest not by grepping the literal, and define the fingerprint file set by path globs excluding __pycache__; carry into NFR Design.
