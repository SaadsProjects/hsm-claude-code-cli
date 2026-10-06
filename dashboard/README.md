# HSM dashboard

A Streamlit dashboard over the HSM labor and inventory services. You sign in
with Google, and only allowlisted email addresses get in; inside, you act as a
demo persona. The Overview, Labor and Inventory tabs are read-only. **Manage data**
adds, edits, deletes and bulk-uploads reference data. **Audit** lists the audit
trail. The dashboard never publishes schedules or submits purchase orders.

## Start it

```bash
pip install --require-hashes -r requirements-dev.txt   # includes streamlit 1.64
scripts/dev-secret.sh                                 # once: HSM_SIGNING_SECRET into .env.local
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # once: sign-in settings (git-ignored)
streamlit run dashboard/app.py --server.address 127.0.0.1
```

Tokens are signed with `HSM_SIGNING_SECRET`, and there is no default. The
dashboard takes it from the first source that has it: an exported value, then
`HSM_SIGNING_SECRET` in the Streamlit secrets (how the hosted apps get it),
then `.env.local` (written by `scripts/dev-secret.sh`). Nothing needs
exporting locally. The secrets example sets no signing secret on purpose, so
a local copy never shadows `.env.local`. If you do put `HSM_SIGNING_SECRET` in
`.streamlit/secrets.toml`, it replaces an exported value: Streamlit copies
top-level secrets into the environment itself, and removing that line while
the app runs unsets the variable until the app restarts.

No separate backend is needed. The dashboard starts the mock backend inside
its own process (`mock_hsm/embedded.py`) at the top of every render: one per
process, bound to `127.0.0.1` on a free port. Every read and write goes through
`HsmClient`, addressed by `session.client_for` to that backend; `HSM_BASE_URL`
is not read (it is for the MCP server and the hooks, which use
`python3 -m mock_hsm.server`). The sidebar caption shows the backend's address.
The audit trail goes to `HSM_AUDIT_PATH` when it is set, otherwise to
`<system temp>/hsm-demo-<uid>/audit.jsonl`, in a directory the dashboard
creates with mode 0700.

The backend starts only after the sign-in gate lets the visitor in. If it
can't start (for example the audit trail is unusable), the page shows only
the Account section and "The demo backend didn't start. Reload the page or
try again later." The cause is logged as a warning by the `mock_hsm.embedded`
logger.

### Reach

`.streamlit/config.toml` makes the dashboard listen on this machine only
(`server.address = "127.0.0.1"`). It also makes Streamlit refuse uploads over
2 MB (`server.maxUploadSize = 2`). The persona picker is not a sign-in; the
sign-in gate below is, and anyone it lets in can pick any persona, including
the system administrator. To open the dashboard to your network on purpose,
start it with `--server.address 0.0.0.0`, and only on a network you trust.

## Sign in

Every rerun starts with the sign-in gate (`dashboard/auth_gate.py`). Nothing
else renders, and the backend isn't started, until it lets the visitor in:

- **Signed out:** "Access to this demo is by invitation." and **Sign in with
  Google** (Streamlit's `st.login("google")`).
- **Signed in, not allowed:** the email isn't on the allowlist, or Google
  doesn't report it as verified. The page says "This account doesn't have
  access.", shows the address, and offers **Sign out**.
- **Sign-in unavailable:** the signing secret is missing or too short, it
  equals `auth.cookie_secret`, a sign-in setting is missing or blank, the
  allowlist is empty or malformed, or the gate itself failed. The page says
  "Sign-in isn't available right now." with no detail; **Sign out** is offered
  only if someone is signed in. The `dashboard.auth_gate` logger records the
  reason (and the setting names or error type), never an email or a value.
- **Allowed:** the sidebar starts with **Account** (the email and **Sign
  out**), then **Demo persona**.

The sign-in settings and the allowlist come from Streamlit secrets; the keys
are in `.streamlit/secrets.toml.example`. `HSM_ALLOWED_EMAILS` lists exact
addresses (trimmed and lower-cased; no domains or wildcards). With the
example's placeholders the gate shows its sign-in screen. A real local sign-in
needs your own Google OAuth client with the redirect
`http://localhost:8501/oauth2callback`, and your address in the allowlist.
Without a `.streamlit/secrets.toml` the page shows "Sign-in isn't available
right now.", the fail-closed result.

**Sign out** ends the persona's backend session, clears this browser session's
dashboard state, then signs out of Google. A different account signing in on
the same tab starts with no persona selected.

## Build caption and demo-data notice

Once the gate lets you in, the last line of the sidebar names the running
build, under the backend caption: "Build abc1234" (the first 7 characters of
the git commit) or, when the checkout has no usable `.git`, "Build src-1a2b3c4d"
(the first 8 characters of a SHA-256 fingerprint of the source the app runs).
`agents/build_info.py` reads `.git` with file reads only, so no git binary is
needed. To see the same label from a shell:

```bash
python3 -m agents.build_info
```

The build is worked out once per process. If that fails, the caption reads
"Build unknown" and the `dashboard.app` logger records only the error type. The
caption also shows when the backend didn't start, under the Account section.

Above the tabs, on every tab and before a persona logs in, an info notice says
"Demo data: changes you make are reset periodically." The hosted demo keeps its
data in memory, so a restart or redeploy resets it. Neither the caption nor the
notice shows on the sign-in screens.

## Log in as a persona

1. In the sidebar, under **Demo persona**, pick a persona and click **Log
   in**. This starts a backend session. The tabs appear only while you are
   logged in, and the caption reads "Acting as {name} ({persona})".
2. Each time the page refreshes, the dashboard checks the session. A session
   ends after 15 minutes without a save, and the dashboard then logs you out
   and says why.
3. **Log out** ends the session at once. If a write was still unconfirmed, it
   is dropped, and the logged-out page says so: reload after logging in to
   check whether it was saved.

The Restaurant Manager can change site data (employees and on-hand counts) at
its own site. Data shared by all sites is read-only for that persona. The
Regional Manager and the developer/tester persona can change all data.

## Change data (Manage data tab)

- Pick a data set, then a kind of record. The table shows every record with
  who added and changed it, its origin and its version.
- **Add**: fill in the form. Reference fields offer only dashboard-added
  records. Seeded records cannot be referenced, edited or deleted.
- **Edit**: pick a dashboard-added record, change it and click **Save**. If
  someone changed the record after you opened it, click **Reload** and try
  again.
- **Delete**: offered only for records you added in this login session, after
  a confirmation.
- **Bulk upload**: click **Download template**, fill in the CSV file (UTF-8,
  header line first), pick it and click **Upload**. The backend saves either
  the whole file or nothing, and lists any problem rows. The file must stay
  under about 960 KiB.

The backend decides every rule and reports problems by field. If a write gets
no answer, a banner offers **Try again**, which can never save twice, or
**Discard**.

Each button's action runs when you click it, and the page then redraws once to
show the outcome, so the page may flicker once after a click.

The Manage data tables are read once per browser session and reused for 60
seconds. Your own writes, **Refresh data** in the sidebar and logging out
reload them at once. A change made in another browser session shows up here
after at most 60 seconds, or on **Refresh data**. If you edit a record that
changed meanwhile, the backend refuses it and offers **Reload**. The Overview,
Labor and Inventory tabs keep their shared 60-second cache, which every write
clears.

## Audit tab

Shows the newest 50 entries the persona may see. **Load older** loads more, and
**Refresh** reloads the newest. The filters narrow only the entries already
loaded. Pick an entry to see its changes.

## Tests

```bash
.venv/bin/python -m pytest tests/test_dashboard_units.py tests/test_dashboard_app.py -q           # timing tests skipped
.venv/bin/python -m pytest tests/test_dashboard_units.py tests/test_dashboard_app.py -q -m perf   # timing tests only
.venv/bin/python -m pytest tests/test_auth_gate.py tests/test_secrets_bridge.py tests/test_dashboard_gate.py -q   # the sign-in gate
.venv/bin/python -m pytest tests/test_build_info.py tests/test_dashboard_build_banner.py -q   # build caption and reset notice
```

Every dashboard `AppTest` is built with `tests/gate_app.py`. It gives the app
placeholder sign-in settings and an allowlist as `AppTest` secrets and
replaces only the identity seam (`auth_gate.current_identity`, `sign_in` and
`sign_out`) with a fake identity, allowed by default. Everything else of the
gate runs for real, so a test that builds its app another way meets the real
gate and gets "Sign-in isn't available right now."
