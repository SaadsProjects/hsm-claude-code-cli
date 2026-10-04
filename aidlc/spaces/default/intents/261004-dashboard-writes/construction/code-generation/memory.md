<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-04T17:16:15Z The human's "build on a189674 instead of starting fresh" was read as a byte-for-byte restore of that commit plus hand merges of CLAUDE.md and .gitignore; the commit and its tests stand in for the skipped requirements and unit artifacts.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-04T17:16:15Z Step order only: tests/conftest.py imports mock_hsm.audit and mock_hsm.writes, so writes.py was restored with the conftest (Step 4) rather than at Step 7; test_dashboard_data.py only fully passes after dashboard/session.py arrives (Step 11); dashboard/README.md restored at Step 12 because a dashboard test reads it. No file content deviates from a189674 except the planned CLAUDE.md merge.
- 2026-10-04T17:16:15Z unit-test-instructions.md says the a189674 tests simulate audit failure via an unwritable HSM_AUDIT_PATH; in fact the route-level 503 tests monkeypatch audit._write_all, and only a PO test breaks the trail through HSM_AUDIT_PATH. A one-off scratch check confirmed both publish and PO return 503 with an unwritable path.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-04T17:16:15Z No extra env-path 503 test for publish was added, because the plan only allowed a new test when coverage was missing and route-level coverage exists for both publish and PO.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-04T17:16:15Z Whether to add a publish 503 test that goes through an unwritable HSM_AUDIT_PATH (tests/test_audit_routes.py) rather than the monkeypatch.
