<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-05T16:20:00Z — U1 Q1/Q4: the human chose to let the hook, MCP tool server and separate-process backend read HSM_SIGNING_SECRET from .env.local when unset, which changes the affirmed team.md Deployment rule ("the MCP server inherits it from the shell"); the rule change must be persisted through the learnings ritual, not a direct edit.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-05T16:25:00Z — U1 review (READY) left five items for the code plan: SecretRefusal is C1's SecretMissingError (RuntimeError subclass, not TokenError, reason attribute); the backend port interface (a flag or variable read by mock_hsm.server __main__, default 8770); the .env.local loader's home (auth.py, root from __file__, no read at import, quoting rule); 503 also for mint_token failures inside handlers; byte-length check in the shell script (or delegate to Python).
