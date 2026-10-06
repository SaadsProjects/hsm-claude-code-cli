<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-04T22:10:00Z — treated the Q11 answer (dashboard only) as superseding the Q9 answer (hosted backend), because Q9 conflicted with the just-approved backend-isolation hard rule; both answers stay visible in the questions file.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-04T22:10:00Z — reworded Q10 option A before it was answered so it no longer kept the burned secret as a local test default, which would have contradicted the Q6 answer (secret always required locally, tests generate their own).

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-04T22:10:00Z — chose in-app st.login plus an email allowlist over Streamlit Cloud private apps, because the free tier limits private-app slots and two environments are needed; this departs from the team practice wording that the apps are private.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
