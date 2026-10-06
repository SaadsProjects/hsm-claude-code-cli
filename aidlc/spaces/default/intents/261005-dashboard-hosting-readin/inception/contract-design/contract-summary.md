# Contract Summary — Dashboard Hosting Readiness

## Sources

- `inception/units-generation/unit-of-work.md` and `unit-of-work-dependency.md` (edges and integration points)
- `inception/domain-design/components.md` and `decisions.md` (ADR-001 to ADR-007); accepted domain-design findings R-01 to R-05
- `inception/requirements-analysis/requirements.md`; `inception/user-stories/stories.md`; `inception/refined-mockups/mockups.md`
- Answers Q1–Q5 in `contract-design-questions.md`
- Current code at `825a0f8`: `mock_hsm/auth.py` (`mint_token`, `verify_token`, `TokenError`), `dashboard/session.py` (`client_for(user_id)`)

All units ship inside one app, and no network API is added. The contracts are in-process Python interfaces, two shared settings layouts, the markers module, the post-deploy check's command line, and the hosted app's public surface.

## Contracts

| # | Provider Unit | Consumer | Mechanism | Owner |
|---|---------------|----------|-----------|-------|
| C1 | U1 secret-fail-closed (TokenAuth) | U2, U3; also PublishHook, McpTools and MockBackend inside U1 | In-process Python API | U1 |
| C2 | U1 secret-fail-closed | Every process (dashboard, backend, hook, MCP server, start script) | Environment-variable schema | U1 |
| C3 | U2 embedded-backend (EmbeddedBackend) | U3 (DashboardShell startup, `session.client_for`) | In-process Python API | U2 |
| C4 | U3 sign-in-gate (SignInGate) | DashboardShell (U3), and U2's Screen 4 | In-process Python API | U3 |
| C5 | U3 sign-in-gate (DashboardShell frame) | U4 build-and-banner | In-process Python rendering slots | U3 |
| C6 | U3 sign-in-gate (`dashboard/markers.py`) | U5 post-deploy check; browser and `AppTest` tests | Shared constants module | U3 |
| C7 | U6 staging-app (hosted secrets) | U3 (SecretsBridge, SignInGate) | Shared settings schema (Streamlit secrets TOML) | U6, with the schema defined by U3 |
| C8 | U5 postdeploy-check | U6 (the owner by hand); External: GitHub `workflow_dispatch` | Command line and workflow inputs | U5 |
| C9 | The hosted app (U2–U4) | External: public web | HTTPS through Streamlit Community Cloud | U3 |

## C1 — TokenAuth API

```yaml
# Python interface, mock_hsm/auth.py (standard library + mock_hsm only)
module: mock_hsm.auth
constants:
  SECRET_ENV: "HSM_SIGNING_SECRET"
  MIN_SECRET_BYTES: 32        # counted in UTF-8 bytes
exceptions:
  SecretMissingError:          # subclass of RuntimeError
    raised_when: variable unset/empty, or shorter than MIN_SECRET_BYTES
    message: names HSM_SIGNING_SECRET and the rule broken; never contains the value
  TokenError:                  # unchanged
functions:
  require_secret() -> None:
    reads: environment at call time
    raises: SecretMissingError
  mint_token(user_id: str) -> str:
    behaviour: unchanged claims; reads the secret at call time via require_secret()
    raises: [SecretMissingError, KeyError for unknown user]
  verify_token(token: str) -> dict:
    behaviour: unchanged; reads the secret at call time
    raises: [SecretMissingError, TokenError]
  site_allowed / region_allowed: unchanged
import_rule: importing the module never reads the environment and never raises
```

**Failure behaviour by caller:**
- **MockBackend `run()`:** exits non-zero with the message.
- **PublishHook:** returns a deny decision with the message.
- **McpTools:** returns a tool error with the message.
- **SecretsBridge:** fails closed, and the app shows Screen 5.

## C2 — Process environment schema

```yaml
# Shared schema: environment variables read by the processes
HSM_SIGNING_SECRET:
  required: true (every entry point)
  rule: ">= 32 UTF-8 bytes; no default anywhere"
  local_source: .env.local written by the dev-secret script (git-ignored)
  hosted_source: Streamlit secrets key HSM_SIGNING_SECRET, copied by SecretsBridge (C7)
  tests: generated per run in tests/conftest.py
  never_in: [.mcp.json, .streamlit/config.toml, committed examples, logs, error messages]
HSM_AUDIT_PATH:
  required: false
  default_local_run: mock_hsm/audit/audit.jsonl   # unchanged for python3 -m mock_hsm.server
  default_embedded: "<system temp dir>/hsm-audit.jsonl"   # Q3
  rule: an unwritable path is a start failure (EmbeddedBackend status=failed)
HSM_BASE_URL:
  required: false
  used_by: MCP server, hooks, the separate-process backend's clients (unchanged)
  not_used_by: the dashboard when embedded (it uses C3)
```

## C3 — EmbeddedBackend API

```yaml
# Python interface, mock_hsm/embedded.py (standard library only)
module: mock_hsm.embedded
types:
  BackendHandle:               # frozen dataclass
    address: str               # "http://127.0.0.1:<port>"
    host: "127.0.0.1"
    port: int
    started_at: datetime (UTC)
    status: "running" | "failed"
    failure_cause: str | None  # technical text for logs only, never shown on screen
functions:
  start(port: int = 0) -> BackendHandle:
    behaviour: >
      Lock-guarded. If a live instance exists (its thread is alive and its socket answers), return it.
      Otherwise call require_secret(), configure the audit trail (C2 HSM_AUDIT_PATH rules), bind 127.0.0.1,
      serve in a daemon thread, and return a running handle. Concurrent callers get the same handle.
      On any failure, return status="failed" with failure_cause; never raise to the caller, never loop retrying.
  current() -> BackendHandle | None:
    behaviour: the last handle if its instance is still live, else None (a dead instance is reported as failed by the next start())
consumer_rules:
  - dashboard.session.client_for(user_id) uses current().address as base_url when no base_url is given (Q1); its signature is unchanged
  - the backend caption shows the handle's address, not the import-time HSM_BASE_URL (domain-design R-01)
```

## C4 — SignInGate API

```yaml
# Python interface, dashboard/auth_gate.py
module: dashboard.auth_gate
types:
  Identity:                    # what the seam reports
    signed_in: bool
    email: str | None
    email_verified: bool | str | None   # raw provider value; only boolean True counts
  Decision:
    outcome: "allow" | "refuse_visitor" | "refuse_unavailable"
    reason: "ok" | "not_signed_in" | "not_verified" | "not_listed" | "settings_missing" | "allowlist_invalid" | "gate_error"
pure_functions:
  parse_allowlist(raw) -> tuple[str, ...]:
    rule: a non-empty list of strings, each trimmed and lower-cased; anything else raises AllowlistInvalidError
  decide(identity: Identity, allowlist: tuple[str, ...]) -> Decision:
    rule: allow only signed_in, email_verified is True, and trimmed lower-cased email in allowlist (exact match)
seam:                          # the only Streamlit auth calls; patched in tests
  current_identity() -> Identity     # wraps st.user
  sign_in() -> None                  # st.login("google")
  sign_out() -> None                 # clears the persona session, then st.logout()
rendering:
  gate() -> Decision:
    behaviour: >
      Reads settings and the allowlist through the seam, decides, logs any refusal with its reason only (never the email),
      renders Screen 1, 2 or 5 for a refusal, and returns the decision. Any exception becomes refuse_unavailable.
  render_account_section(identity: Identity) -> None:
    behaviour: sidebar "Account" heading, email, Sign out (used on Screens 3 and 4)
caller_rule: DashboardShell renders nothing else unless gate().outcome == "allow"
```

## C5 — Dashboard frame slots for U4

```yaml
# Rendering contract inside dashboard/app.py (DashboardShell)
slots:
  banner_slot:
    position: main area, after the title, before the site caption and tabs; rendered once per run
    filled_by: U4 render_reset_banner()
  build_caption_slot:
    position: sidebar bottom, after the backend caption
    filled_by: U4 render_build_caption(BuildInfo)
visibility: both slots render only on Screen 3; the build caption also renders on Screen 4
order_with_existing_notices: the existing unsaved-write notice renders below the reset banner (refined-mockups finding R-06)
```

## C6 — Markers module

```yaml
# Shared constants, dashboard/markers.py
rules:
  - constants only (str values); no imports beyond __future__/typing; never imports Streamlit (domain-design R-04)
  - names are never reused for a different element (Q5)
constants:
  SIGN_IN_SCREEN: sign-in screen container (Screen 1)
  SIGN_IN_BUTTON: "Sign in with Google" button
  REFUSAL_SCREEN: refused-visitor screen (Screen 2)
  UNAVAILABLE_SCREEN: sign-in-unavailable screen (Screen 5)
  BACKEND_FAILED_SCREEN: backend-failure screen (Screen 4)
  ACCOUNT_SECTION: sidebar Account section
  SIGN_OUT_BUTTON: Sign out button
  RESET_BANNER: reset banner
  BUILD_CAPTION: build caption
  APP_TABS: the tabs container
```

## C7 — Hosted secrets schema

```toml
# Streamlit secrets for one hosted app (entered by the owner in U6; never committed).
# A committed .streamlit/secrets.toml.example carries this shape with placeholders only.
HSM_SIGNING_SECRET = "<at least 32 bytes, unique to this app>"
HSM_ALLOWED_EMAILS = ["owner@example.com"]

[auth]
redirect_uri = "https://<app>.streamlit.app/oauth2callback"
cookie_secret = "<random, different from HSM_SIGNING_SECRET>"

[auth.google]
client_id = "<per-app OAuth client id>"
client_secret = "<per-app OAuth client secret>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

**Rules:**
- SecretsBridge copies `HSM_SIGNING_SECRET` into the environment only if it is unset there.
- SecretsBridge refuses to start if `HSM_SIGNING_SECRET` equals `cookie_secret`.
- SignInGate parses `HSM_ALLOWED_EMAILS` with `parse_allowlist`.
- A missing `[auth]` or `[auth.google]` section is `settings_missing`.

## C8 — Post-deploy check command line

```yaml
# scripts/postdeploy_check.py
usage: "python scripts/postdeploy_check.py <url> [--timeout SECONDS]"
arguments:
  url: https URL of the app (http://127.0.0.1:<port> allowed for local tests)
  --timeout: total seconds to wait for the app, including a sleeping host waking up (default 120)
behaviour: >
  Opens the URL in Chromium (Playwright). While the host shows its sleep or waking page, retries until the timeout; such a page is never a pass.
  Passes when the SIGN_IN_SCREEN marker is visible and APP_TABS is absent. Never signs in, never writes, holds no credentials.
exit_codes:
  0: passed
  1: assertion failed (gate missing, tabs visible, or the page is not the app)
  2: bad usage or input (missing or invalid URL)
  3: the app didn't answer, or didn't finish waking, within the timeout
output: one line per assertion and a final PASS/FAIL line naming the failure; no secrets
github_workflow:
  trigger: workflow_dispatch
  inputs:
    url: { required: true, type: string }
    timeout: { required: false, type: string, default: "120" }
  permissions: { contents: read }
  secrets: none
```

## C9 — Hosted app public surface

```yaml
# The only externally reachable surface, served by Streamlit Community Cloud
paths:
  "/": the Streamlit app; unauthenticated requests get Screen 1 only
  "/oauth2callback": Streamlit's own sign-in callback (managed by st.login)
not_exposed:
  - the mock backend (127.0.0.1 only, inside the app process)
  - any custom API route
```

## Contract Ownership Rules

- **Who owns what:**
  - the provider unit owns each spec (table above);
  - U3 defines C7's schema, and U6 fills in the values for staging;
  - the parked deploy intent fills them in for production.
- **Changing a contract:** no version numbers (Q5). A change to any contract changes its provider and every consumer in the same pull request. U2–U5 already ship as one pull request, and U1's contracts are only extended (new exceptions and functions), never broken.
- **Additive changes stay safe:** new optional fields on `BackendHandle`, `Identity` or `Decision`, and new marker constants. Consumers ignore fields they don't use.
- **Never allowed without changing every consumer:** removing or renaming a marker, a C1 function or exception, or a C7 key; or changing a C8 exit code's meaning.

## Open Questions

| Contract | Question | Blocks |
|----------|----------|--------|
| C8 | The exact text and structure of Streamlit Community Cloud's sleep and waking page, which the check must recognise | U5 (settled during its functional design) |
| C4 | Whether `st.user` reports `email_verified` as a boolean for Google (feasibility risk R1); `decide` already refuses anything else | U3 |
| C7 | The exact `redirect_uri` for staging, known only once the app URL is created | U6 |

## Assumptions & Open Questions

- [assumption] The 120-second default timeout for the check (C8) is a starting value. NFR Requirements settles it together with the cold-start target (NFR2).
- The open contract points are listed in the table above.
