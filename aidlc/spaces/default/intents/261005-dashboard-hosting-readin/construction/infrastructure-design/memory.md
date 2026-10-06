<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-06T00:30:00Z — U3 infrastructure review (READY, minors only) items for the code plan: set the dashboard.auth_gate logger level to INFO (an unconfigured logger drops INFO) and test that the INFO refusal line is captured; the post-U6 rollback follows team.md Rollback (move the production pointer, redeploy, rerun the post-deploy check); the "66 existing dashboard tests" figure came from the NFR design questions and should be recounted when the helper lands.
- 2026-10-06T00:30:00Z — Q1 A adds .env.local as a third signing-secret source for the bridge, which extends NFR design S4 (exported value, then Streamlit secrets); .streamlit/secrets.toml.example therefore carries HSM_SIGNING_SECRET only as a comment, so a local copy never shadows .env.local with a placeholder. Code Generation also updates CLAUDE.md to drop the export step for the local dashboard.
