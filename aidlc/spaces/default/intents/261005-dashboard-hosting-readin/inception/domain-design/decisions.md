# Architecture Decisions — Dashboard Hosting Readiness (Domain Design)

## Sources

- `domain-design-questions.md` Q1–Q5; `components.md`
- `inception/user-stories/stories.md` and the developer's mob contribution
- Code knowledge base `code-quality-assessment.md` (CQ-1, CQ-4); `memory/team.md` Code Style

## ADR-001: In-process backend start in its own module

- **Status:** Accepted (Q1)
- **Context:** Streamlit Cloud runs one process, so the backend must start inside the dashboard. `server.run()` blocks, and `app.py` reruns on every interaction, so a guard there would run again on every rerun (CQ-4). Team rules require a standard-library-only start function in `mock_hsm/`.
- **Decision:** a new module, `mock_hsm/embedded.py` (component EmbeddedBackend), holds the start function and a module-level, lock-guarded singleton. It configures the audit trail, binds `127.0.0.1`, runs the server in a daemon thread and returns the address. `server.py` keeps its handler and `run()`.
- **Consequences:**
  - (+) The guard lives in an imported module, so `sys.modules` keeps it across reruns, and it is testable alone, including under concurrent calls.
  - (+) `server.py` stays focused.
  - (−) There is one more module, and `embedded.py` depends on the handler and audit configuration that `server.py` exposes.
- **Alternatives rejected:**
  - A second start function inside `server.py`: it mixes a process-lifecycle concern into a large routing module, and its tests overlap the server tests.

## ADR-002: The sign-in gate is one cohesive module

- **Status:** Accepted (Q2)
- **Context:** the gate has a pure decision function (unit-tested without Streamlit), an identity seam (needed because `AppTest` can't set a user), and three screens that must never leak dashboard content.
- **Decision:** `dashboard/auth_gate.py` (component SignInGate) holds the decision function, the identity seam (`current_identity`, `sign_in` → `st.login("google")`, `sign_out`) and the rendering of Screens 1, 2 and 5. `app.py` only calls it.
- **Consequences:**
  - (+) Every access rule and every screen a refused visitor can see sit in one file, which CI already watches.
  - (−) The module mixes pure logic with Streamlit calls. This is mitigated by keeping the decision function free of Streamlit and the rendering thin.
- **Alternatives rejected:**
  - Screens drawn in `app.py`: refusal content would spread into the file that also draws the dashboard, making leaks easier to introduce and harder to review.

## ADR-003: The secrets bridge is its own module, run first

- **Status:** Accepted (Q3)
- **Context:** the hosted secret lives in Streamlit secrets, but `mock_hsm/auth.py` must stay standard-library only. The app must also fail closed when the signing secret equals the cookie secret.
- **Decision:** `dashboard/secrets_bridge.py` (component SecretsBridge) runs once at app start, before the gate. It copies the secret into the environment, then calls `require_secret()`, and refuses on a missing secret or a signing secret equal to the cookie secret.
- **Consequences:**
  - (+) There is a single place where secrets enter the process, with a narrow surface to test.
  - (+) The gate stays about access, not configuration.
  - (−) A visitor-facing refusal can start in two places (the bridge and the gate). DashboardShell routes both to Screen 5.
- **Alternatives rejected:**
  - Inside `auth_gate.py`: mixes two security concerns.
  - Inline in `app.py`: untestable in isolation, and it reruns on every interaction.

## ADR-004: One shared secret check for every entry point

- **Status:** Accepted (Q4)
- **Context:** the backend, the start script, the hook, the tool server and the dashboard must all refuse to run without a valid secret, and the rule (at least 32 bytes, no fallback, never echo the value) must not drift between them.
- **Decision:** `mock_hsm/auth.py` (component TokenAuth) exposes `require_secret()`, which raises the standard error. Every Python entry point calls it at startup. The shell start script checks the variable before launching Python, and Python checks again.
- **Consequences:**
  - (+) One rule and one message, tested once.
  - (−) Every caller is coupled to `TokenAuth`. They already were, through `mint_token`.
- **Alternatives rejected:**
  - Each entry point implementing its own check: the rules would drift, and the hook's crash-fails-open risk would be harder to audit.

## ADR-005: The gate owns allowlist parsing

- **Status:** Accepted (Q5)
- **Context:** the parsing rules (a non-empty list of strings, trimmed, lower-cased, no wildcards) are as security-critical as the decision itself.
- **Decision:** SignInGate reads the allowlist from Streamlit secrets through its seam and parses it. A malformed or empty list refuses, and the visitor sees Screen 5.
- **Consequences:**
  - (+) All access rules sit beside the decision, and the unit tests cover them together.
  - (−) The gate reads one setting directly rather than receiving it.
- **Alternatives rejected:**
  - The bridge parses and passes a list: it splits the access rules across two modules, and the bridge would need access-control knowledge.

## ADR-006: The dashboard passes the backend address explicitly

- **Status:** Accepted (from the developer's mob position on US3.1, adopted in AC3.1.2)
- **Context:** `agents/hsm_client.py` reads `HSM_BASE_URL` once at import and uses it as a default argument, so setting the variable after import has no effect.
- **Decision:** DashboardShell passes the address that EmbeddedBackend returns into the client as `base_url` (through `session.client_for`). The client's API is unchanged.
- **Consequences:**
  - (+) No ordering trap between imports.
  - (+) Tests can point the client anywhere.
  - (−) Every dashboard client creation must thread the address through.
- **Alternatives rejected:**
  - Setting `HSM_BASE_URL` before the first import: fragile, because any earlier import silently freezes the old value.

## ADR-007: The dashboard owns the markers shared with tests and the check

- **Status:** Accepted (team Code Style file placement; US7.1)
- **Context:** the browser tests and the post-deploy check must find screens without depending on copy text, which may change.
- **Decision:** `dashboard/markers.py` (part of DashboardShell) defines stable marker names. The app renders them, and the tests and PostDeployCheck import them.
- **Consequences:**
  - (+) A copy change can't silently break the check.
  - (−) PostDeployCheck depends on dashboard code, so the two ship together.
- **Alternatives rejected:**
  - Matching on visible text: brittle, and copy is a design decision.

## Assumptions & Open Questions

None.
