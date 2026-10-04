# Performance Test Instructions — Restore dashboard writes

There are no performance NFRs in this workflow: `code-generation-plan` and
`unit-test-instructions` set none, and `code-summary` reports none. a189674 does
ship a set of timing tests, recorded here so they are not forgotten.

## Timing tests

- Marked `perf` and skipped by default by `tests/conftest.py` (these are the 12
  skips in the full-suite run).
- They are spread across the audit-log, route and dashboard test files.

## How to run

```bash
.venv/bin/python -m pytest tests/ -q -m perf
```

## Expectations

All 12 pass on a developer machine. They are local sanity bounds, not SLO
measurements; no load testing applies to an in-memory mock backend.
