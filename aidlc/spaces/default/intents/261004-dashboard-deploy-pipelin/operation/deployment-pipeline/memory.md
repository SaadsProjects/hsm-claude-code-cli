<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-06T17:00:00Z — Q2's "a fixed few minutes" was set to 180 seconds and confirmed in the summary; the check's own --timeout 600 then covers FR8.2's 10-minute wait.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-06T17:00:00Z — Production removed by the human mid-workflow: promote.yml, prod-check.yml, the production Environment, deploy key and ruleset are dropped from the design; the approved requirement and design records that mention them stay as written.
- 2026-10-06T17:00:00Z — staging-check.yml posts no commit status and passes no --commit/--checkout/--report flags: contract C8's shipped check takes only a URL and --timeout, and with no promotion nothing reads a status.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-06T17:00:00Z — A new push-only staging-check.yml instead of adding a push trigger to postdeploy.yml, so the manual workflow keeps its tested dispatch-only contract and the automatic run needs no input defaults.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
