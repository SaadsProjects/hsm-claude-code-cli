<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-04T23:20:00Z — added a bandit report filter (filter_bandit.py) so security-exceptions.toml entries apply to bandit as the NFR design says, instead of relying on inline nosec comments.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-04T23:20:00Z — the infra scope has no code-generation or build-and-test stage, so the application changes the designs require were split into a follow-up piece of work at the human's choice; this stage built only CI workflow, gate scripts, lockfiles and config.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-04T23:20:00Z — set .coverage-floor to 95.00 against a measured 96% and kept .test-floor at the designed 745 although 811 tests now pass; both leave headroom for runner differences on the first CI run and can only be raised later.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-04T23:20:00Z — confirm Dependabot's uv ecosystem raises PRs for requirements*.in within two weeks of merge; if not, add a scheduled lock-refresh workflow.
