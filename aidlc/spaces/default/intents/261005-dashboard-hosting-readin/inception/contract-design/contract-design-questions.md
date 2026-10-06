# Contract Design Questions — Dashboard Hosting Readiness

## Sources

- `inception/units-generation/unit-of-work.md` and `unit-of-work-dependency.md` (edges U2→U1, U3→U1, U3→U2, U4→U3, U5→U3, U6→U4/U5)
- `inception/domain-design/components.md` and the accepted domain-design findings R-01 (where the backend address lives) and R-03 (hosted audit path)
- `inception/requirements-analysis/requirements.md`; `memory/team.md` Deployment

All units ship inside one app, built and merged together (apart from U1), so these contracts are in-process Python interfaces, a shared settings layout, and the post-deploy check's command-line interface. No network API is added.

## Q1. Where is the embedded backend's address held (domain-design finding R-01)?

`session.client_for(user_id)` is called from about ten places and takes no address today.

A. EmbeddedBackend holds it: `embedded.current()` returns the running instance's handle, and `client_for` uses that address when no `base_url` is given. The call sites stay unchanged.
B. The dashboard keeps it in `st.session_state` and every `client_for` call passes it explicitly (about ten call sites change)
X. Other (please specify)

[Answer]: A

## Q2. How are the hosted app's secrets laid out?

You enter these in the Streamlit Cloud console when creating staging (U6).

A. `HSM_SIGNING_SECRET` and `HSM_ALLOWED_EMAILS` (a list of strings) at the top level; Streamlit's own `[auth]` section (`redirect_uri`, `cookie_secret`, and `[auth.google]` with `client_id`, `client_secret`, `server_metadata_url`) as Streamlit documents it
B. The same, but the app's own keys grouped under an `[hsm]` table (`[hsm] signing_secret`, `[hsm] allowed_emails`)
X. Other (please specify)

[Answer]: A

## Q3. Where does the hosted audit trail go (domain-design finding R-03)?

Today it defaults to `mock_hsm/audit/audit.jsonl` inside the checkout.

A. The in-process start defaults it to a file in the system temp directory when `HSM_AUDIT_PATH` isn't set; local `run()` keeps today's default. An unwritable path is a start failure (Screen 4).
B. Keep today's default everywhere; set `HSM_AUDIT_PATH` in the hosted secrets
X. Other (please specify)

[Answer]: A

## Q4. What exit codes does the post-deploy check use?

A. 0 passed; 1 an assertion failed (gate missing, not the app); 2 bad usage or input; 3 the app didn't answer in time
B. Just 0 for pass and 1 for any failure
X. Other (please specify)

[Answer]: A

## Q5. How are these contracts versioned?

A. No version numbers: provider and consumer always change in the same pull request; marker names are never reused for a different element
B. Version each contract
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Backend address (Q1): EmbeddedBackend holds it. `embedded.current()` returns the running instance's handle, and `client_for` uses that address when no `base_url` is given; call sites stay unchanged.
- Hosted secrets layout (Q2): `HSM_SIGNING_SECRET` and `HSM_ALLOWED_EMAILS` (a list of strings) at the top level, plus Streamlit's own `[auth]` and `[auth.google]` sections as Streamlit documents them.
- Hosted audit trail (Q3): the in-process start defaults it to a file in the system temp directory when `HSM_AUDIT_PATH` isn't set; local `run()` keeps today's default. An unwritable path is a start failure (Screen 4).
- Post-deploy check exit codes (Q4): 0 passed; 1 an assertion failed; 2 bad usage or input; 3 the app didn't answer in time.
- Versioning (Q5): no version numbers. Provider and consumer change in the same pull request, and marker names are never reused for a different element.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
