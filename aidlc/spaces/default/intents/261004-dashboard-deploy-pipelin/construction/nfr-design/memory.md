<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-04T22:55:00Z — excluded the AI-DLC record tree from the burned-secret scan rather than editing approved record files, because those files are audit evidence quoting an already-public value.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-04T22:55:00Z — split promote.yml into keyless preflight, approval-gated deploy and keyless verify jobs; GitHub holds an environment-bound job before any step runs, and the split also keeps the deploy key away from the resolver and the browser check.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-04T22:55:00Z — reviewer minors left after the final pass: R-05 how CI tolerates pip-audit's non-zero exit before filter_audit.py runs; R-10 register a browser pytest marker skipped unless -m browser so plain CI never collects the Playwright tests. Carry into Infrastructure Design / code generation.
