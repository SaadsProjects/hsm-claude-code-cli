# Performance Design — Dashboard Deployment Pipeline

## Sources

- `construction/nfr-requirements/performance-requirements.md` NFR2.1 to NFR2.5 [performance-requirements]
- `construction/nfr-requirements/tech-stack-decisions.md` TS3, TS4, TS6, TS7, TS11 [tech-stack-decisions]

## PD1 — CI job graph (NFR2.1, NFR2.2)

```
lint (ruff check + format --check, workflow-lint)   ┐
secrets (gitleaks full history)                      │ parallel, timeout 10 min each
audit (pip-audit + filter), sast (bandit)            │
lock-check (uv pip compile --check)                  ┘
tests [matrix: 3.10, 3.14 (+ hosted version if different)]  timeout 15; pytest step timeout 5
coverage-gate (needs: tests on 3.14 leg's coverage.json)     timeout 5
```

Text fallback: five independent check jobs run in parallel with the test matrix. The coverage gate depends only on the 3.14 test leg.

- **Dependency caching:** `actions/setup-python` pip cache, keyed on the hash of `requirements-dev.txt`. uv is installed from a pinned release with a checksum check, and the binary is cached.
- **Superseded runs:** `concurrency: ci-${{ github.ref }}` with `cancel-in-progress: true` for PR refs. It is not set for `main`, so every `main` commit gets a full result.
- **Coverage:** coverage is collected only on the 3.14 leg. The 3.10 leg runs plain pytest. This keeps the 3.10 leg fast and avoids double-counting.
- **Budget:** about 90 s for the suite, about 60 s for install from cache, and under 30 s for setup. The expected per-leg total is about 3 min, against the 5 min step timeout and the 15 min job timeout.

## PD2 — Browser-based checks (NFR2.4, NFR2.5)

- Playwright's Chromium is installed only in the check workflows (`playwright install --with-deps chromium`) and cached by Playwright version. It is never installed in the PR test jobs.
- The post-deploy check has a hard 10-minute wait budget, then at most 2 minutes for steps b and c. Job `timeout-minutes` is 15.

## PD3 — Signed-in page speed (NFR2.3)

- Backend reads already go through the dashboard's `CACHE_TTL_SECONDS = 60` data cache (`dashboard/app.py`). There is no change.
- The in-process backend removes a network hop. Each call goes over loopback inside one process.
- The gate (SD1) adds one secrets read per run, which is negligible.
- Measurement: 20 manual loads at the skeleton checkpoint, recorded in the runbook. At most 1 may exceed 5 s.

## Assumptions & Open Questions

- [assumption] Coverage overhead with subprocess measurement adds no more than 50% to suite time. That keeps it within the 5 min step timeout. It is verified on the first PR.
- None.
