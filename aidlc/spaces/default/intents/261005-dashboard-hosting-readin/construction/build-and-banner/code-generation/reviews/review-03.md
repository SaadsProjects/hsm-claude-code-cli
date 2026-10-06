## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T11:01:53Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | agents/build_info.py > `_git_dirs` | A `.git` file's `gitdir:` value and a `commondir` file are joined and resolved without confinement to the repo. `_commit_sha` returns only a value that fully matches `_SHA`, and the ref name is checked against `_REF` with `..` rejected. Everything else falls back to the fingerprint, so a crafted checkout cannot leak file contents. Unchanged at HEAD. | Optionally confine the resolved paths to the repo, or record that the SHA-only return makes this acceptable. | Unresolved |
| R-02 | Minor | dashboard/app.py > `run()` | The caption is drawn in a `finally`. `main()` returns instead of calling `st.stop()` when a persona has no sites. Gate refusals call `st.stop()` before the `try`, so no caption appears there. Verified in the code and by the passing banner tests. | None. | Resolved |
| R-03 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/build-and-banner/code-generation/code-summary.md > Files, Key Implementation Decisions, Deviations | The summary still describes the pre-fix design in three places. Files says `build_info` is "cached per resolved root", while the code reads `.git` on every call and caches only the fingerprint, keyed on a path/size/mtime signature. Key Implementation Decisions says the caption "doesn't appear" when a persona has no sites ("st.stop()"), while the later fix reverses this. Deviations says `functools.cache`, while the code uses `lru_cache(maxsize=8)`. The "Fixes from the Commit Review" section is correct, so the document contradicts itself. | Correct those three statements so the summary matches the final tree. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| `ruff check .` | PASS (All checks passed) | Clean. |
| `ruff format --check .` | PASS (539 files already formatted) | Clean. |
| `pytest tests/test_build_info.py tests/test_dashboard_build_banner.py tests/test_dashboard_app.py -q` | 90 passed, 4 skipped | Green. The skips are the expected optional-`git` and similar cases. |

### Summary

The implementation is sound. `agents/build_info.py` is standard-library only and uses no subprocess. It reads `.git` fresh on each call, validates the SHA and ref shape, and falls back to a length-prefixed source fingerprint. The caption and banner wiring in `dashboard/app.py` sits behind the sign-in gate and draws on every signed-in path. The remaining findings are Minor: the unconfined gitdir join, which is mitigated by the SHA-only return, and a stale code-summary narrative.
