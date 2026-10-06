<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-04T23:05:00Z — made browser-tests always run and no-op when not needed, because a GitHub required check that never reports blocks every PR.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-04T23:05:00Z — chose a hand-applied settings checklist over IaC for GitHub rulesets, Environment and Streamlit Cloud apps; two managed platforms with no IaC provider in scope, and the checklist makes drift visible at the cost of manual re-verification.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-04T23:05:00Z — reviewer findings after READY to carry into CI Pipeline: R-01 Dependabot uv support for hashed requirements lockfiles is unverified (needs a supported mechanism or a scheduled lock-refresh job); R-02 deploy job needs a checkout/fetch of the target; R-03 cancelled staging checks must not post failure; R-04 detect disabled prod-check schedule; R-07 confirm Cloud ignores server.address=127.0.0.1; R-08 bootstrap order (create production branch before the ruleset); R-09 single source for required-check names.
