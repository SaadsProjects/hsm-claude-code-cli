# HSM Agentic Automation — Claude Code CLI Edition

Two HSM (restaurant back-office) use cases — labor scheduling and
inventory/COGS + vendor ordering — automated as a real **Claude Code CLI**
project: MCP tools, subagents, slash commands, and a permission/hook-enforced
approval gate, rather than a bespoke script that calls the Anthropic API
directly.

See `CLAUDE_CODE_CLI_PLAN.md` for the full design writeup and rationale.
`CLAUDE.md` is the short brief Claude Code itself loads every session.

## Quick start

```bash
# Requires Python 3.10+ (the mcp SDK's minimum). Recommended: a venv.
python3 -m venv .venv && source .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt   # dev/test lock; requirements.txt is the hosted-app runtime lock

# Once per clone -- create the local token-signing secret (.env.local, git-ignored)
scripts/dev-secret.sh

# Terminal 1 -- start the mock HSM backend (refuses to start without the secret)
bash scripts/start_mock_server.sh

# Terminal 2 -- pick a persona, then start Claude Code in this directory
export HSM_ACTIVE_USER=user_rm_midtown      # Restaurant Manager, site_001
claude
> /schedule-labor site_001

# or, headless:
claude -p "/schedule-labor site_001" --output-format json

# Regional Manager use case:
export HSM_ACTIVE_USER=user_regional_atl
claude -p "/review-inventory" --output-format json
```

Tokens are signed with `HSM_SIGNING_SECRET`, which has no default anywhere.
`scripts/dev-secret.sh` writes a fresh one (at least 32 bytes) to `.env.local`
with mode 600, and refuses to replace an existing one unless you pass
`--force`. The backend, the start script, the publish hook and the MCP server
read `.env.local` when the variable isn't exported, so the `claude` shell gets
the same value without any extra step; an exported value always wins. Without
a secret, the backend won't start, the publish hook denies and every HSM tool
returns an error naming `HSM_SIGNING_SECRET`.

The first time you start `claude` in this directory it will ask to
approve the project's `.mcp.json` server (`hsm`) — approve it, since
that's what exposes the HSM tools.

### Dashboard

```bash
# the dashboard runs its own mock backend in-process (no separate backend or
# HSM_BASE_URL needed) and reads the signing secret from .env.local itself;
# the sign-in settings come from .streamlit/secrets.toml (git-ignored)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # once
streamlit run dashboard/app.py
```

A Streamlit view of forecasts, labor demand, rosters, published schedules
(with a Labor Rules Engine compliance check), on-hand stock, usage
anomalies, reorder needs and submitted POs. A sign-in gate comes first: only
a Google account whose verified email is on the `HSM_ALLOWED_EMAILS`
allowlist gets in, and nothing else renders before that (with the example's
placeholders you see the sign-in screen; a real sign-in needs your own Google
OAuth client). Inside, pick a demo persona in the sidebar; that starts a
backend session. The backend's site/region scope
decides what that persona can see and change. Once logged in, the "Manage
data" tab adds, edits, deletes and bulk-uploads records, and the "Audit" tab
lists the audit trail. These overview tabs stay read-only, and the dashboard
never publishes or submits. See `dashboard/README.md` for details.

### Audit trail

The mock backend records every schedule-publish and purchase-order attempt
that reaches its route, whether allowed or refused (400/403/404), plus every
dashboard data write, bulk row, login and logout, in an append-only audit
trail (`mock_hsm/audit.py`). Each entry is written and `fsync`-ed before the
request continues, so it survives a restart for as long as it is retained.

- **Location:** the file named by `HSM_AUDIT_PATH`. The default is
  `mock_hsm/audit/audit.jsonl`, which is gitignored. The file is created with
  mode 0600 in a 0700 directory, and a wider existing file or directory is
  narrowed back at startup. The test suite points `HSM_AUDIT_PATH` at a
  temporary file per test (`tests/conftest.py`), so tests never touch the
  default file.
- **Layout:** one JSON line per append call,
  `{"hwm": <n>, "entries": [ ... ]}`. A single append writes one entry. A bulk
  upload writes all of its rows as one line, so a crash keeps either the
  whole file's entries or none of them. `hwm` is the high-water mark: the
  highest entry id assigned so far. Entry ids are 12-digit numbers that are
  never reused. Files written in the earlier one-entry-per-line layout, with
  an optional `{"_meta": {"next_id": N}}` first line, are still read, and the
  next purge rewrites them in the new layout.
- **Viewing:** `GET /audit` returns 50 entries per page, newest first. Pass
  `?before=<entry_id>`, taken from the previous page's `next_before`, to get
  older entries. Any well-formed 12-digit id is accepted, even one whose
  entry has been purged; anything else is a 400. The backend filters entries
  by the caller's token. A region-wide or `SYSTEM_ADMIN` token sees
  everything. Any other token sees the entries about its own sites plus its
  own actions. The same test applies to entries recorded as `unknown`, so a
  Restaurant Manager sees an `unknown` attempt on its own site's data but not
  one on shared data. Pages are served from memory and never read the file.
  Nothing can edit or delete an entry.
- **Retention:** entries older than 90 days are purged at startup. After
  that, the first append or `GET /audit` once 24 hours have passed since the
  last purge runs it again before doing its own work. There is no background
  thread. The purge writes a temporary file, `fsync`s it and swaps it in
  with an atomic rename. It keeps the high-water mark on a leading
  `{"hwm": <n>, "entries": []}` line, so ids are never reused even when every
  entry is purged.
- **Fail closed:** if an entry can't be written, or a purge fails after its
  swap, the trail becomes unavailable. Publish, PO submit, dashboard writes,
  login, logout and `GET /audit` then return
  `503 {"error": "audit unavailable"}` until the backend restarts. Other
  reads keep working. Each failure writes one `[mock-hsm] ERROR audit: ...`
  line to stderr. A purge that fails before its swap keeps the old file and
  the trail stays up; it is retried 24 hours later.

**Recovering from an unreadable trail.** At startup, a last line with no
terminating newline is from a write that never finished. The backend removes
it automatically; for a bulk upload, that drops the whole upload's entries.
Any other unreadable line, including a complete last line, makes the trail
unavailable, and stderr names the file and line:
`audit: trail unavailable, unreadable line <n> in <path>`. The backend never
repairs or discards such a line itself. To recover:

1. Stop the backend.
2. Move the file aside (`mv mock_hsm/audit/audit.jsonl{,.corrupt}`) to start
   a fresh trail, or repair or remove the named line by hand to keep the
   rest. Keep the moved file if you need its history. A fresh trail restarts
   entry ids at 1. To keep numbering, start the new file with the line
   `{"hwm": <n>, "entries": []}`, where `<n>` is the highest id in the old file.
3. Start the backend again. Check for the line
   `audit: loaded <n> entries, torn line <dropped|none>, purged <m>, high-water mark <id>`
   on stderr.

**Recovering from a failed rollback.** If a write fails, the backend cuts
the file back to where that write began. If that cut also fails, the error
line ends with
`rollback failed (...): remove every byte from offset <n> onward in <path> before restarting`.
Those bytes record an operation that returned 503 and never ran. Stop the
backend and remove them, for example with
`python3 -c "import os,sys; os.truncate(sys.argv[1], int(sys.argv[2]))" <path> <n>`,
then restart. If you skip this and the leftover is an incomplete last line,
startup drops it anyway. A complete leftover line, though, would be loaded
as if the operation had been recorded, so remove it.

If the cause was an unwritable file or a full disk, fix that first, then
restart. A restart is the only thing that clears the unavailable state.

### Dashboard data writes

The mock backend accepts writes to 11 kinds of demo data: menu items,
recipes, raw materials, units of measure, vendors, employees, job codes,
on-hand counts, par levels, reorder points and labor rules
(`mock_hsm/writes.py`, routes in `mock_hsm/server.py`). Added records go
into the same in-memory collections the read routes and the Claude Code
tools read, so an added raw material with stock and a vendor shows up in
reorder suggestions, and an added employee shows up in the site's roster.
Everything is in memory and is lost when the backend restarts. Only the
audit trail is durable.

- **Personas:** the Restaurant Manager (`user_rm_midtown`) writes only its
  own site's employees and on-hand counts. The Regional Manager
  (`user_regional_atl`) and the developer/tester (`user_dev_tester`) write
  every kind for site_001 to site_003. The developer/tester has the Regional
  Manager's persona value and scope, so the gated publish and PO routes
  treat it the same way. The audit trail tells it apart by its user id.
- **Sessions:** `POST /sessions` starts a login session for the token's
  persona. The bearer token, signed with `HSM_SIGNING_SECRET`, is the only
  credential. Every write carries the `session_id` and a
  `request_id` in its JSON body. A session ends on
  `POST /sessions/{id}/logout`, or after 15 minutes without a data write.
  Reads and status checks (`GET /sessions/{id}`) never refresh it. A session
  only works with its own persona's token.
- **What can be changed:** seeded records are read-only. A dashboard-added
  record can be updated by any persona with the rights for its kind, but
  only deleted by the persona that added it, in the same session, and only
  while no other record uses it. Updates and deletes carry the `version`
  they read; a stale one gets 409. References (units, raw materials, job
  codes, menu items) must name dashboard-added records.
- **Entry limit:** each session may add at most 100 records per kind.
  Deleting a record does not give its slot back. A new session starts again
  at zero.
- **Bulk files:** `POST <collection>/bulk` takes 1 to 500 rows parsed from
  one CSV file and saves all of them or none. `GET <collection>/template`
  returns the CSV columns. A recipe file has one line per row, grouped by
  menu item. While a bulk file is checked and saved, it holds the data lock,
  for up to its 2-second budget, and reads wait for it.
- **Retries:** a repeated `request_id` from the same user, within 15
  minutes, gets the original response. Nothing is saved or audited twice.
- **Metadata:** add `?with=meta` to a read to get each record's origin,
  creator, timestamps and version beside the unchanged payload. Metadata
  never includes a session id.
- **Audit:** every write attempt that reaches a data-write route gets
  exactly one audit entry, and so does every row of a bulk file. The
  exception is a bulk file whose rows are never examined: one with 0 or
  more than 500 rows, a `rows` value that isn't a list, or bad or repeated
  row numbers. Such a file gets a single entry. Logins and logouts are
  audited too. The entry is written before the change is applied. If it
  can't be written, nothing changes and the write returns
  `503 {"error": "audit unavailable"}`. Like the gated routes, writes,
  logins and logouts then keep returning 503 until the backend restarts,
  while reads keep working. A different 503, `audit could not record the
  attempt`, means the trail is healthy but refused this entry as invalid.
  It is not retried, and nothing is applied. A bulk file's entries are
  written with one durable write, all or none. **Crash limit:** if the
  backend crashes in the middle of that write, the reload discards only an
  incomplete last line, so some complete entries of that file can remain.
- **What an entry's `changes` holds:**

  | Attempt | `changes` |
  |---------|-----------|
  | Allowed add, or allowed bulk row | `{"record": ...}`: the submitted fields |
  | Allowed update | `{"before": ..., "after": ...}`, holding only the fields that changed |
  | Allowed delete | `{"record": ...}`: the deleted record |
  | Refused add, update or bulk row | `{"record": ...}` as submitted, or `{"parse_error": ...}` for an unreadable CSV line |
  | Refused delete | `{"version": ...}` as submitted |
  | Whole bulk file (wrong row count, malformed rows) | `{"file_name": ..., "row_count": ...}` |
  | Body that isn't an object, or nests deeper than 32 levels | `{"truncated": true, "unserializable": true}` |

  A refused write to a site kind also records `site_id` in `changes`
  when the path site is unknown or outside the persona's sites. The
  entry's own `site_id` field only ever names an existing site. A failed
  apply after the audit adds a compensating violation that repeats the
  allowed entry, with reason `failed after audit: <error>`.

  Before an entry is sent, `record_id`, `site_id`, `kind`, `reason` and
  every text value and key inside `changes` are cut to at most 1,024
  characters, ending in `...(truncated)`. Non-finite numbers are kept as
  text (`"nan"`), and a value that still can't be stored as JSON becomes
  the marker above. `user_id`, `persona` and `session_id` are never cut. A
  `session_id` is recorded only when it names an existing session.
- **A hung audit disk** (one that stops answering rather than failing)
  blocks every read and write until it answers, because reads and writes
  share the data lock that is held while an entry is written. This is
  accepted for the demo.

### Shared client: data writes

`agents/hsm_client.HsmClient` has methods for the routes above:
`start_session`, `end_session`, `session_status`, `list_records` (every
kind as `{records, meta}`), `add_record`, `update_record`, `delete_record`,
`bulk_add`, `csv_template`, `audit_page(before=None)` and `retry_write`.
They are transport only; the backend makes every decision. The existing
methods, which the MCP tools, the publish hook and the dashboard's current
screens use, are unchanged.

- **Errors:** every error is an `HsmApiError` (`status`, `message`,
  `problems`). Two subclasses tell the new flows apart, so catch them
  first: `SessionExpired` (401) means a data write's login session has
  ended, so log in again; `HsmUnavailable` (status 0) means no answer came
  back. The client logs nothing.
- **Retries:** a data write that gets no answer is sent once more at once,
  with the same `request_id`. If that also gets none, the outcome is
  unknown: `HsmUnavailable` has `outcome_unknown=True`, the `request_id`
  and a `retry_deadline`. "Try again" calls `client.retry_write(error)`,
  which re-sends the identical request. The backend answers a repeated
  request id with its stored response, so nothing is saved twice. That
  holds even after a logout: if the first attempt never arrived, the retry
  gets `SessionExpired` instead.
- **Deadline:** `retry_write` is refused (`ValueError`, nothing sent) more
  than 14 minutes after the first attempt, a minute inside the backend's
  15-minute replay window. After that, reload and check before saving
  again.
- **Replay cap:** the backend keeps at most 1,000 stored responses per user.
  A pending retry could only be pushed out by more than 1,000 writes from
  the same user within 15 minutes, which the 100-per-kind entry limit makes
  unrealistic for the demo.

## What's real vs. what's a sketch

Everything in this project was built and verified in this environment:

- **The MCP server (`mcp_server/hsm_tools.py`) is real** and was tested
  with the official `mcp` Python SDK doing an actual stdio JSON-RPC
  handshake against the mock HSM backend — `initialize`, `list_tools`,
  and `call_tool` for every registered tool, including a negative test
  proving persona scope enforcement holds through the MCP layer (a
  Restaurant Manager's token gets a 403 reading another site). Run it
  yourself: `python3 -m pytest tests/test_mcp_tools.py -v` (or
  `python3 tests/test_mcp_tools.py` directly — it starts the mock server
  itself and needs no API key).
- **Both hooks are real.** `require_no_violations.py` and
  `lint_before_commit.py` were each tested by piping the exact JSON
  payload Claude Code sends on `stdin` (`tool_name` / `tool_input` /
  `cwd`) and checking `stdout` against Claude Code's actual `PreToolUse`
  hook output schema (`hookSpecificOutput.permissionDecision`).
  `require_no_violations.py` correctly denies a schedule with a
  manufactured violation and passes a clean one through.
  `lint_before_commit.py` was tested against this actual codebase: it
  passes a clean `git commit` through, ignores non-commit Bash commands,
  and denies a `git commit` after a lint error (an unused, multi-target
  import) was deliberately introduced into `agents/hsm_client.py` and
  removed again afterward.
- **The subagents, slash commands, and `.claude/settings.json` permission
  rule were not run through an actual `claude` agent turn in this
  environment** — doing so would mean this session (itself a Claude
  agent) spawning a *nested* live Claude Code session against the real
  Anthropic API, which didn't seem like the right thing to do
  unprompted. Their content is written to the real, current frontmatter
  formats (`tools:`, `argument-hint:`, `$ARGUMENTS`, the `mcp__hsm__*`
  tool-naming convention) — verified against this environment's actual
  installed Claude Code CLI (`claude`, v2.1.272) rather than guessed —
  but you should run the two slash commands yourself as the actual
  end-to-end check.

## Layout

```
mock_hsm/                       mock HSM REST backend (audit.py: append-only audit trail;
                                writes.py: dashboard data writes and sessions;
                                embedded.py: the backend the dashboard runs in its own process)
agents/hsm_client.py            REST client used by the MCP tools
agents/labor_scheduling_agent.py   pure demand-calculation function only
agents/inventory_agent.py          pure anomaly/reorder-calculation functions only
mcp_server/hsm_tools.py         MCP server: wraps the above as tools
dashboard/                      Streamlit dashboard: read-only overview tabs, plus login, Manage data and Audit tabs
.mcp.json                       registers the hsm MCP server for this project
.claude/agents/                 labor-scheduler.md, inventory-analyst.md, code-reviewer.md
.claude/commands/               /schedule-labor, /review-inventory, /commit
.claude/hooks/                  require_no_violations.py, lint_before_commit.py (both PreToolUse)
.claude/settings.json           permission rules + hook registration
tests/test_mcp_tools.py         protocol-level test, no LLM required
tests/conftest.py               per-test temporary audit trail (HSM_AUDIT_PATH); resets U1 writes after each test;
                                skips the `perf` timing tests unless run with `-m perf`
tests/test_writes_*.py          dashboard data writes: building blocks, write service, HTTP routes and perf
docs/ARCHITECTURE.md            call-flow diagrams for each subagent
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for per-subagent call-flow diagrams.

## Linting + code review before committing

Use `/commit <message>` rather than a bare `git commit` for changes to
this project's own code. It runs the `code-reviewer` subagent (read-only —
no `Edit`/`Write`, so it reports findings instead of silently altering
your code) against the staged diff, then commits only if you're satisfied
with the review — and even then, `lint_before_commit.py` independently
runs `ruff check` as a hard `PreToolUse` gate on the commit itself, so a
dirty lint result blocks the commit regardless of what the review
concluded or what a human approved. It lints what the commit will
actually contain in this project's repo: the staged index, plus tracked
working-tree files for `commit -a` or pathspecs, plus untracked files when
the same command also stages (`git add . && git commit`). Install `ruff` (already in `requirements-dev.txt`): if the hook
can't find it on PATH, in `.venv/bin`, or as `python -m ruff`, it blocks
the commit rather than letting it through unchecked.

## Persona reference

| `HSM_ACTIVE_USER` | Persona | Scope |
|---|---|---|
| `user_rm_midtown` | Restaurant Manager | `site_001` only |
| `user_regional_atl` | Regional Manager | `region_atl` (site_001, site_002, site_003) |
| `user_dev_tester` | Developer/tester (Regional Manager persona value) | `region_atl` (site_001, site_002, site_003) |

Set this before starting `claude` — the MCP server mints a token for
whichever user it names, and the mock backend enforces that user's scope
on every call, exactly as HSM's real Apigee-fronted services would.
