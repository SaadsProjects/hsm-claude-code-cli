<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-06T13:40:00Z — The 30 s whole-app cold start (inception NFR2) was kept out of this stage's target inventory. The inventory comes from the per-unit NFR records, and none of them owns the 30 s figure. It goes to the scheduled performance-validation stage and is surfaced as an open item in cross-unit traceability.
- 2026-10-06T13:40:00Z — The team rule "raise both floors in the intent's final pull request" was applied to a follow-up PR (#9). PR #7 had to merge before the staging app could exist, so it could no longer be the final PR.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-06T13:40:00Z — Standard strategy asks only for integration instructions. Performance and security instructions were generated as well, because the NFR stages set performance and security targets.
- 2026-10-06T13:40:00Z — The U5 command `postdeploy_check.py http://127.0.0.1:8501` wasn't run as written. No app runs on 8501 here; the same check ran against the browser-test apps and against staging.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-06T13:40:00Z — Cross-unit traceability fails the strict rule, because the unit files cite story ACs and NFRx.y, not parent FR/NFR IDs. The unit files were left alone: patching them would invalidate six Code Generation reviews with no passes left. The gap and its indirect coverage are surfaced at the gate instead.
- 2026-10-06T13:40:00Z — The floors went to 1100 and 96.00, about 8% and 1 point below the measurements, matching the headroom used when CI's floors were first set.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-06T13:40:00Z — The bare `noqa` at `.claude/hooks/lint_before_commit.py:372` (FR8.7/AC8.4.1) still waits for the human. Harness files are protected from agent edits.
- 2026-10-06T13:40:00Z — A local lock check compiled from scratch picks up newer upstream releases (filelock 4.0.10 → 4.0.12). Only CI's method, starting from the committed locks, is meaningful.
