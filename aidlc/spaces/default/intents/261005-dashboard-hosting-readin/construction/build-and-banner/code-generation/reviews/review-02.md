## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T05:34:08Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | agents/build_info.py > `_git_dirs` | A `.git` file's `gitdir:` and a `commondir` file are joined without confinement to the repo. Only SHA-shaped values are returned and everything else falls back to the fingerprint, so exposure is limited. This is unchanged in 2bf012d. | Optionally confine, or record that the SHA-only return makes this acceptable. | Unresolved |
| R-02 | Minor | dashboard/app.py > `run()` | Originally the caption was drawn only on normal return or on the three caught errors. It is now drawn in a `finally`, so every signed-in path draws it. The no-sites path returns instead of calling `st.stop()`. | None required. | Resolved |

### Fix verification

- **Stale label.** `build_info()` reads `.git` on every call, and only the fingerprint is cached, keyed on (path, size, mtime_ns). I mutated it to cache the SHA. `test_a_moved_branch_ref_is_seen_without_a_restart` then failed, so the test guards the fix.
- **Caption in `finally`.** I changed `finally` to `else`. `test_a_backend_lost_mid_render_shows_screen_4_text_without_the_banner` failed, so it guards the fix. The no-sites test still passed under that mutation because a `return` runs `else`. Its guard against the old `st.stop()` is therefore indirect.
- **Banner slot.** The banner is drawn into `st.empty()` and emptied when the backend is lost mid-render. The Screen 4 tests assert it is absent on a failed start and on a mid-render loss.
- **Widened `_REF`.** I reverted it to a narrow character class. Four branch-name tests then failed, among them `issue#12` and `café`. The `..` rejection is still in `_commit_sha`.
- **No regression.**
  - The gate-screen tests pass with neither banner nor caption.
  - `agents/build_info.py` has no Streamlit import.
  - The only broad catches are in `dashboard/app.py`, and both keep their `# noqa: BLE001 -- <reason>`.
  - I restored the working tree after the mutations.

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| ruff check | PASS | Clean. |
| ruff format --check | PASS | 524 files already formatted. |
| pytest (build_info, banner, gate, app, embedded) | 139 passed, 5 skipped | Skips are the browser or perf marks. |
| python -m agents.build_info | `Build 2bf012d` | Matches HEAD (AC5.1.3). |

### Summary

All three commit-review fixes are present, and each has a test that fails without it. I found no regressions or new architectural issues. Only the carried minor R-01 remains, and it is acceptable.
