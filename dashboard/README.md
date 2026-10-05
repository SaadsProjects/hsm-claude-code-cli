# HSM dashboard

A Streamlit dashboard over the HSM labor and inventory services. You log in as
a persona. The Overview, Labor and Inventory tabs are read-only. **Manage data**
adds, edits, deletes and bulk-uploads reference data. **Audit** lists the audit
trail. The dashboard never publishes schedules or submits purchase orders.

## Start it

```bash
pip install --require-hashes -r requirements-dev.txt   # includes streamlit 1.64
scripts/dev-secret.sh                                 # once: HSM_SIGNING_SECRET into .env.local
export HSM_SIGNING_SECRET="$(sed -n 's/^HSM_SIGNING_SECRET=//p' .env.local)"
streamlit run dashboard/app.py --server.address 127.0.0.1
```

Tokens are signed with `HSM_SIGNING_SECRET`, and there is no default. The
dashboard mints its tokens in its own process and doesn't read `.env.local`
(written by `scripts/dev-secret.sh`) yet, so export the value in the
dashboard's shell, as above.

No separate backend is needed. The dashboard starts the mock backend inside
its own process (`mock_hsm/embedded.py`) at the top of every render: one per
process, bound to `127.0.0.1` on a free port. Every read and write goes through
`HsmClient`, addressed by `session.client_for` to that backend; `HSM_BASE_URL`
is not read (it is for the MCP server and the hooks, which use
`python3 -m mock_hsm.server`). The sidebar caption shows the backend's address.
The audit trail goes to `HSM_AUDIT_PATH` when it is set, otherwise to
`<system temp>/hsm-demo-<uid>/audit.jsonl`, in a directory the dashboard
creates with mode 0700.

If the backend can't start (for example `HSM_SIGNING_SECRET` is missing or
too short, or the audit trail is unusable), the page shows only "The demo
backend didn't start. Reload the page or try again later." The cause is
logged as a warning by the `mock_hsm.embedded` logger.

### Reach

`.streamlit/config.toml` makes the dashboard listen on this machine only
(`server.address = "127.0.0.1"`). It also makes Streamlit refuse uploads over
2 MB (`server.maxUploadSize = 2`). The persona picker is not a sign-in: anyone who
can open the page can log in as any persona. To open the dashboard to your network on
purpose, start it with `--server.address 0.0.0.0`, and only on a network you
trust.

## Log in

1. In the sidebar, pick a persona and click **Log in**. This starts a backend
   session. The tabs appear only while you are logged in.
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
```
