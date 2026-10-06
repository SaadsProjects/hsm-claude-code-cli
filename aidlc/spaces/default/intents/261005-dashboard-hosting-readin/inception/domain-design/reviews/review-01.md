## Review

**Verdict:** READY
**Reviewer:** aidlc-architecture-reviewer-agent
**Date:** 2026-10-05T12:35:01Z
**Iteration:** 1

### Findings

| ID | Severity | Location | Finding | Required action | Status |
|---|---|---|---|---|---|
| R-01 | Major | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/domain-design/components.md > DashboardShell, HsmClient behaviour; decisions.md > ADR-006 | The design says the embedded address reaches the client "through session.client_for with base_url", but dashboard/session.py client_for(user_id) takes no base_url and is called from about 10 sites (actions.py, manage_tab.py, app.py:49). The catalogue never says where the address is held (module global, session_state) or who owns that. dashboard/app.py:483 and :510 also print the import-time HSM_BASE_URL in the backend caption and error text, which would show the wrong address once the backend is embedded. | State which component holds the embedded address and how client_for obtains it. Add the app.py caption and error text to DashboardShell's behaviour so the displayed address is the real one. | New |
| R-02 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/domain-design/components.md > EmbeddedBackend behaviour | The singleton "returns the same running instance" with no liveness check. If the daemon server thread dies, every later rerun gets a stale address and Screen 4 never shows. BackendInstance has a status attribute but no rule that updates it. | Add a rule: reuse an instance only while its thread is alive and its socket answers. Otherwise report a failure, still with no retry loop. | New |
| R-03 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/domain-design/components.md > MockBackend / EmbeddedBackend | audit.configure() sets process-global state, and the default audit path is under the repo checkout (mock_hsm/audit/). Hosting the backend in the dashboard process makes the dashboard share that state. The catalogue lists only a start failure as an assumption. The hosted-disk writability assumption is not tied to a rule such as an explicit HSM_AUDIT_PATH under a writable temp directory. | Record the hosted audit path source (env or secrets) and who sets it. Confirm in NFR Design that an unwritable path surfaces as Screen 4. | New |
| R-04 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/domain-design/components.md > PostDeployCheck dependency on DashboardShell; decisions.md > ADR-007 | PostDeployCheck imports dashboard/markers.py, but nothing requires that module to stay free of Streamlit and other third-party imports. The check job is meant to hold no secrets and a minimal install, and an import of dashboard.app internals would break that. | Add to ADR-007 or the DashboardShell behaviour: markers.py is constants only, with no Streamlit import. | New |
| R-05 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/domain-design/components.md > SignInGate external_dependencies | SignInGate and its identity seam call st.login, st.user and st.logout, but the catalogue lists only Google and Streamlit secrets. The Streamlit runtime is listed only under DashboardShell. | Add Streamlit (streamlit[auth] and Authlib) to SignInGate's external_dependencies and to the External Dependencies table. | New |
| R-06 | Minor | aidlc/spaces/default/intents/261005-dashboard-hosting-readin/inception/domain-design/traceability.json > US8.2, US8.3, US9.1 | These stories are marked Deferred to infrastructure-design rather than mapped. That is defensible because they are CI and hosting concerns, not components. The status value is non-standard compared with OK, GAP and N/A, so the sensor may read it as a gap. | Confirm the traceability sensor accepts Deferred, or recode these as N/A with the infrastructure-design pointer kept in the target text. | New |

### Validation Tool Results

| Tool | Result | Interpretation |
|---|---|---|
| Manual YAML well-formedness check (no PyYAML available; checked by reading all 12 components) | PASS | Component names are unique. Every depends_on has a matching dependents entry and the reverse. The graph is acyclic: DashboardShell depends on 6 components and no edge points back. Every entity has one owner and an identifier. Both references resolve (VisitorIdentity under SignInGate). Infrastructure appears only as external_dependencies. |
| traceability.json against stories.md | PASS | All 35 USx.y IDs in stories.md appear in upstream_ids, with no extras. Every OK target is a declared component or entity name. |
| Code spot-check (mock_hsm/server.py, mock_hsm/auth.py, agents/hsm_client.py, dashboard/session.py) | Claims verified | run() blocks in serve_forever, so a separate embedded start is needed. HSM_BASE_URL is frozen as a default argument at import, which confirms ADR-006. The _SECRET literal at auth.py:24 confirms the TokenAuth change is needed. |

### Summary

The decomposition is sound: boundaries are clean, the dependency graph is acyclic and symmetric, entity ownership is unambiguous, and the ADRs carry Context, Decision, Consequences and Alternatives Rejected. The one gap worth weighing before approval is R-01: the path by which the embedded backend's address reaches the existing client call sites is not pinned down. The remaining findings are minor.
