## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-06T13:03:57Z
**Iteration:** 2

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | scripts/postdeploy_check.py > `_settle` / `_confirm_pass` | Still holds in the current tree. `_settle` returns a pass only through `_confirm_pass`. That function needs no running script and an unchanged state for QUIET_SECONDS. Tabs end the wait at once. A deadline reached first returns `reliable=False`, which `classify` reports as UNSETTLED, never PASS. Unchanged since e436355. | None. | Resolved |
| R-02 | Minor | scripts/postdeploy_check.py > `_gather` / `classify` | Still holds. A failed frame read sets `reliable=False`. Tabs still win over unreliability, and an unreliable state is re-polled and never passes. | None. | Resolved |
| R-03 | Minor | tests/test_ci_browser_watch.py > `project_sources` | Still holds. The ci.yml browser-tests watch regex covers all of `agents/`, `dashboard/` and `mock_hsm/*.py`, plus `scripts/postdeploy_check.py`, `tests/.*browser.*`, `tests/conftest.py`, `requirements-dev.txt` and `ci.yml`. The meta-test passes. | None. | Resolved |
| R-04 | Minor | scripts/postdeploy_check.py > `_press_wake_button` | Unchanged. The wake click matches in every frame. It runs only after the page classifies as WAKING, which needs host-wake wording and no sign-in screen. It is the only click, and it signs nobody in. | Optionally limit it to the top-level frame. | Unresolved |
| R-05 | Minor | inception/contract-design/contract-summary.md > C8 exit_codes | Code, README and docs/staging-app.md agree with each other: exit 3 is widened and exit 4 is new. They still differ from C8, and C8 is unchanged. The human accepted this at the iteration-1 checkpoint. | Update C8 or record the deviation as accepted. | Unresolved |
| R-06 | Minor | aidlc/spaces/default/memory/team.md > browser-tests watch list | The ci.yml watch list is still wider than the list written in team.md. Accepted at the iteration-1 checkpoint. | Update the team rule through the learnings path. | Unresolved |
| R-07 | Minor | docs/staging-app.md > step 4 Timing (NFR2) and step 4(e) | The 8.5 s local pass and the green workflow run show the awake, gated path working against the real host. The sleep/wake path and the 30 s wake target have not been run against the real host. The runbook leaves both open and tells the owner to record them as not yet proven, which is honest. Until they are run, the wake-button logic is verified only against test doubles. | Run the timing step once the app has slept and record the result. No code change is needed. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| ruff check . | PASS | Clean. |
| ruff format --check . | PASS (552 files) | Clean. |
| scripts/check_workflows.py .github/workflows | PASS (2 files) | Clean. |
| pytest test_postdeploy_check, test_ci_browser_watch, test_postdeploy_workflow | PASS (63) | Exit codes, classification and workflow shape are covered. |
| pytest test_staging_runbook | PASS (21) | The runbook's claims about the check and the secrets keys are tested. |

### Summary

The guarantees still hold in the current tree. Commit e1ddc16 only added a runbook and a one-line link each in CLAUDE.md and README.md, and the script, workflow and watch list are unchanged since e436355. The check never signs in and its only click is the host's wake button. Exit codes 0/1/2/3/4 match the script, README and runbook. A pass needs a quiet page with no tabs. The workflow is `workflow_dispatch` only, with `permissions: {}` at the top, `contents: read` on the job, no secrets, and the inputs passed through env. `docs/staging-app.md` is accurate about the check (exit codes, never signs in, timing procedure). The remaining items are minor and carried over, apart from the new R-07.
