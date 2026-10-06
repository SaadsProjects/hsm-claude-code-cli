## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T06:02:34Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | scripts/postdeploy_check.py > `_settle` / `classify` | `_settle` returns the moment `classify` leaves NOT_APP, so a page that shows the sign-in marker first passes at once. Streamlit renders a script incrementally. A gate that forgets to stop would show the sign-in screen and add the tabs afterwards, and the check would pass before the tabs appear. No test covers sign-in plus tabs arriving over time. `test_check_fails_when_tabs_render_without_the_gate` has no sign-in screen. The classify unit test covers only the instantaneous case. I could not run a live repro because the sandbox blocked the launch. This is read from the code. | After the sign-in marker is seen, wait for the script run to finish (the Streamlit running indicator gone, or a short quiet period), then re-read tabs before returning PASS. Add a browser test with a sign-in container followed by a delayed tab block that expects exit 1. | New |
| R-02 | Minor | scripts/postdeploy_check.py > `_gather` | The `sign_in` assignment precedes the tabs reads inside one `try`. If a frame raises on the tabs read (detach or navigate), the state keeps sign_in True and tabs False, so a transient error can produce a PASS. | Mark the state unreliable when any frame read raises, and re-poll instead of classifying it. | New |
| R-03 | Minor | tests/test_ci_browser_watch.py > `project_sources` | The meta-test follows only the first-level imports of the browser test files and the scripts they name. Files `dashboard/app.py` imports (session, tabs, `mock_hsm/embedded.py`) are not watched, so a change to them skips `browser-tests`. This matches the team.md watch list as written, but the blind spot is not stated. | Record this limit in the test docstring or in team.md, or follow imports transitively. | New |
| R-04 | Minor | scripts/postdeploy_check.py > `_press_wake_button` | The wake click matches a button named "get this app back up" in every frame, including the app's own frame. It runs only when the page classifies as WAKING, so the exposure is small. The AST test confirms it is the only click. | Optionally limit the click to the host's top-level frame. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| `ruff check .` | PASS | Clean. |
| `ruff format --check .` | PASS | 535 files already formatted. |
| `python3 scripts/check_workflows.py .github/workflows` | PASS | 2 files OK. |
| unit and meta tests (54) | PASS | Includes the AST test that the only click is the wake button. |
| `pytest tests/ -m browser` | PASS | 8 passed. Server processes are terminated and killed in `finally`. Ports are bound on 127.0.0.1 and chosen by binding port 0. The test-double secrets.toml sits in a temp dir. |
| `git status` (paths outside `aidlc/`) | PASS | Every changed path outside `aidlc/` is a claimed path. |

Workflow checks done by reading:
- postdeploy.yml: inputs reach the shell through `env`, not spliced into the command. Actions are pinned by full SHA. `permissions` is `{}` at workflow level and `contents: read` on the job. It holds no secrets.
- ci.yml: the `browser-tests` job name is unchanged (M2). Exit 5 now fails the job. `--reruns 1` gives the single retry. The Chromium cache key includes the Playwright version. The watch list was widened as the plan requires.
- Lock diff: adds only playwright, greenlet and pyee.
- Floors are untouched.

### Summary

The unit meets its rules: nothing signs in, the workflow has no injection path, CI cannot pass with zero tests, the lock changes stay narrow, and lint and tests are green. The one real weakness is R-01: the check can pass a gate that leaks tabs a moment after the sign-in screen renders. That is one Major finding, so the verdict stays READY, but R-01 should be fixed before the check is relied on for deploys.
