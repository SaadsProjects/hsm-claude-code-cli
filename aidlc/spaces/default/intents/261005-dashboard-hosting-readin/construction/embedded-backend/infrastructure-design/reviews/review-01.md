## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-05T22:18:21Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/embedded-backend/infrastructure-design/cicd-pipeline.md > How U2 Is Built and Gated, item 4 | The claim "browser-tests watch list is unchanged" holds today, since the regex in .github/workflows/ci.yml (line 249) lists only postdeploy_check.py, markers.py, auth_gate.py, build_info.py and tests/*browser*. team.md also says a meta-test fails when a source file a browser test imports is off the list. Once U3/U5 browser tests start the embedded backend, the new mock_hsm module becomes such an import. Nothing in the artifact hands that watch-list addition to the unit that adds the browser tests. | Add a one-line note that the new mock_hsm embedded-start module must be added to the browser-tests watch list by the unit whose browser test imports it (U3/U5). | New |
| R-02 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/embedded-backend/infrastructure-design/monitoring-design.md > SLIs / SLOs, Cold start row | The 30-second cold-start SLO is measured by the U5 post-deploy check, but the pipeline note (cicd-pipeline.md) never records this as a cross-unit dependency. The post-deploy check never signs in (team.md), so whether it can observe "usable page" is not established. | State what the post-deploy check observes for this SLO (for example the sign-in screen appearing) or mark the SLO as unmeasured until U5 confirms. | New |
| R-03 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/construction/embedded-backend/infrastructure-design/cicd-pipeline.md > How U2 Is Built and Gated, item 3 | NFR2.1 (start under 2 s) and NFR2.2 (closed-port check under 1.5 s) are wall-clock assertions in the required test jobs. They are not perf-marked and run on shared runners. The artifact relies on the margin and the single CI retry (--reruns 1, ci.yml line 183) but does not say so. | Record that these are deliberately wide-margin ordinary tests relying on the existing one retry, with the bound as the only tuning knob. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Source cross-check against .github/workflows/ci.yml and tests/conftest.py | Consistent | Existing jobs and the plain pytest invocation match the artifact. CI sets no HSM_SIGNING_SECRET, and the tests job fails if one is set (ci.yml lines 173-174). The tests' temp HSM_AUDIT_PATH is consistent with the NFR1.13 test approach. |

### Summary

U2 adds no infrastructure beyond the in-process loopback backend and a private temp audit directory. Every component maps to the Streamlit Cloud single process, and the human's two decisions (HSM_AUDIT_PATH unset, no CI change) are applied consistently across the artifacts. Only minor documentation gaps around the future browser-test watch list, the cold-start SLO measurement, and timing-test flakiness remain.
