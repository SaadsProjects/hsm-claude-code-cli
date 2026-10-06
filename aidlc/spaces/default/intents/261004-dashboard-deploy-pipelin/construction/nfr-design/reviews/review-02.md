## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-04T22:43:37Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261004-dashboard-deploy-pipelin/construction/nfr-design/reliability-design.md > RD3; security-design.md > SD5 `promote.yml` row | RD3 now has three jobs. `preflight` has no Environment and no key, and it resolves the target, runs the coverage gate and writes the target, mode and previous SHA to the job summary. `deploy` (`needs: preflight`, `environment: production`) only pushes with `--force-with-lease=production:<prev>` and tags. `verify` runs the check without the key. This matches how GitHub pauses an Environment-bound job, and SD5 agrees. | None. | Resolved |
| R-02 | Major | reliability-design.md > RD3 `preflight` permissions; security-design.md > SD5 | `preflight` now lists `contents: read`, `statuses: read`, `checks: read`. This covers the check-runs and status APIs RD3 step 2 calls. The `check_workflows.py` rule list in SD5 still does not assert per-job grants (only the presence of `permissions`). That is worth adding during implementation but does not block. | None required. Optionally add a per-job permission assertion for `promote.yml` to `check_workflows.py`. | Resolved |
| R-03 | Major | reliability-design.md > RD1 "Frame awareness" and tests; security-design.md > SD1 step 1 | The build ID is now `st.caption("Build: ...")`, located by text pattern rather than a `data-testid`. The app frame is found by that pattern. The step c marker scan runs over every `page.frames`. Positive controls use an iframe fixture, one passing and one exiting 3. The design is now implementable and not vacuous. The real Cloud wrapper is still confirmed only at the skeleton checkpoint, which RD1 already records. | None. | Resolved |
| R-04 | Major | reliability-design.md > RD6; traceability.json > NFR4.1 | `scripts/test_floor.py` reads each leg's JUnit XML. It fails on failures or errors above 0, or on passed tests below the checked-in `.test-floor` (745). A "may only rise" diff check applies, and the unit-test cases are listed. Traceability and C9/C14 now point at it. | None. | Resolved |
| R-05 | Minor | security-design.md > SD7 pip-audit filter | The severity source order is now defined: advisory label, then a CVSS vector scored with a pinned `cvss` library, then fail closed. Still unstated: pip-audit exits non-zero when it finds vulnerabilities, so the CI step needs `\|\| true` or a captured exit code before the JSON feeds `filter_audit.py`. A developer could build the step so it fails before the filter runs. | State that the audit step captures pip-audit's JSON and ignores its exit code, and that `filter_audit.py`'s exit code is the job result. | Unresolved |
| R-06 | Minor | security-design.md > SD1 step 0; observability-design.md > OD3 | Step 0 now detects a missing secrets file or a missing `[auth]` key, logs an ERROR naming the key, and stops. The local `secrets.toml` requirement is recorded. | None. | Resolved |
| R-07 | Minor | security-design.md > SD2 bridge; reliability-design.md > RD5 | The bridge now has a fixed key tuple that includes `HSM_INPROCESS_BACKEND`, `HSM_BACKEND_HOST` and `HSM_BACKEND_PORT`. RD5 says `serve_in_thread` calls `audit.configure()`. | None. | Resolved |
| R-08 | Minor | security-design.md > SD2 burned-value check | The scan now covers all tracked text types. The two documented exclusions are `.gitleaks.toml` and the record tree `aidlc/spaces/*/intents/**`. A `git grep` shows the literal only in `mock_hsm/auth.py` (removed by this change) and the two practices-discovery record files, so the exclusions fit. | None. | Resolved |
| R-09 | Minor | reliability-design.md > RD1 inputs | The script takes `--commit` and `--checkout` and computes both `sha:` and `fp:` expected values. It compares in the kind the app reports, and `unknown` never matches. | None. | Resolved |
| R-10 | Minor | reliability-design.md > RD1 tests "marked `browser`"; performance-design.md > PD2 | The browser integration tests are said to stay out of the default PR suite. The team rule requires plain `pytest tests/` with no `-m`. No mechanism keeps them out of that run. PD2 does not install Chromium in the PR test jobs, so the collected tests would error there. `tests/conftest.py` only skips `perf`, and only when no `-m` is given. These tests would also count toward the `.test-floor` run if collected. | Specify the mechanism, for example a `browser` marker registered in `conftest.py` and skipped unless `-m browser` is given, mirroring `perf`. Run them in the check workflows with `-m browser`. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| `python3 -m json.tool traceability.json` | PASS | Valid JSON. |
| NFR ID coverage (`upstream_ids` vs IDs declared in the nfr-requirements docs) | PASS | Unchanged from iteration 1: all 44 IDs are covered, with no gaps or extras. |
| Traceability truthfulness (NFR4.1 to RD6 `test_floor.py`) | PASS | A real design element now backs the 745 floor. |
| Repo fact checks | PASS | `git grep` finds the burned literal only in `mock_hsm/auth.py` and two record files. `tests/conftest.py` skips only `perf`, which is the basis for R-10. |

### Summary

All four Major findings from iteration 1 are resolved: the promotion workflow is now three jobs, with a keyless preflight, an approval-gated push, and a post-check. The frame-aware check, the 745-test floor and the permission grants are in place. One Minor remains (R-05, pip-audit exit handling) and one new Minor (R-10, keeping browser tests out of the default suite). A developer can build the system from these documents. READY.
