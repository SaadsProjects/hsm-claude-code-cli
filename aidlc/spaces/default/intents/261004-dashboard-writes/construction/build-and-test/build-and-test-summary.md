# Build and Test Summary — Restore dashboard writes

## Build status

The build is ready. Dependencies are consistent (`pip check`), every new module
imports, and ruff is clean. Commands are in `build-instructions.md`.

## Test types

| Type | File | Generated because |
|------|------|-------------------|
| Unit and per-layer | `construction/code-generation/unit-test-instructions.md` | Code Generation (Minimal strategy) |
| Integration | `integration-test-instructions.md` | Records the live-backend tests a189674 ships |
| Performance | `performance-test-instructions.md` | Records the opt-in `-m perf` timing tests; no performance NFRs |
| Security | `security-test-instructions.md` | New login and write paths next to the safety-critical writes |

Coverage expectation: one zero-unit stage; every command passes and the
existing suite stays green. There is no coverage floor in this scope. Inputs
were `code-generation-plan` (Testing Contract), `unit-test-instructions` and
`code-summary`.

## Target inventory

There are no `nfr-requirements/` or `nfr-design/` artifacts in this workflow.
The targets come from the `## Testing Contract` in `code-generation-plan.md`
(test-after, Minimal strategy, scope floor "keep the existing test suite
green") and from the coverage requirements in `unit-test-instructions.md`.

## Target Verification Matrix

| Target ID | Source | Expected | Actual | Evidence | Owning Stage | Verdict |
|-----------|--------|----------|--------|----------|--------------|---------|
| TC-SCOPE-1 | code-generation-plan.md > Testing Contract > scope_floor | Existing suite green | 735 passed, 0 failed (12 perf skipped by design) | test-results.md > Tests, row 1 | build-and-test | Met |
| TC-STRAT-1 | code-generation-plan.md > Testing Contract > strategy_volume | At least one test per requirement R1–R8 | All eight R-IDs map to existing tests or tested modules | cross-unit-traceability.md | build-and-test | Met |
| TC-STRAT-2 | code-generation-plan.md > Testing Contract > strategy_volume | Happy-path test per component (backend, audit, writes, client, dashboard) | Each component's test file passes | test-results.md > per-layer rows | build-and-test | Met |
| UTI-R4 | unit-test-instructions.md > Coverage targets | 503 fail-closed on publish and PO when audit unavailable | Covered by `test_unwritable_audit_store_gives_503_over_http` (publish) and `test_unreadable_trail_refuses_audited_operations_but_not_reads` (PO) | test-results.md > routes row | build-and-test | Met |
| UTI-R6 | unit-test-instructions.md > Coverage targets | No publish/submit/draft action for any persona | Covered by `test_no_publish_or_submit_button_for_any_persona` | test-results.md > dashboard row | build-and-test | Met |
| BUILD-LINT | code-generation-plan.md > Step 13 | `ruff check .` clean | All checks passed | test-results.md > Build | build-and-test | Met |

## Readiness

- **Build-ready:** yes.
- **Test-ready:** yes. Every executed command passed and every target is Met.
- **Deployment-ready:** not applicable. The work runs locally and is ready to
  commit through `/commit`.

## Known limitations

- The publish 503 test simulates audit failure with a monkeypatch, not an
  unwritable `HSM_AUDIT_PATH` (finding R-01 at Code Generation, accepted).
- The safety settings are checked by reading them, not by a test (R-02). The
  project hooks live in gitignored `settings.local.json`, so fresh clones have
  no hooks (R-03).
- The suite now takes about 86 s, up from about 24 s.
