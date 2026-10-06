# Architecture: hsm-claude-code-cli

Commit `825a0f8`. Component names match `component-inventory.md`.

## System Overview

Three front ends share one backend contract:

- **Claude Code** (subagents → MCP tools in `mcp_server`) for the two agentic
  workflows.
- **The Streamlit dashboard** (`dashboard`) for people.
- **Claude Code hooks** (`claude-hooks`) that independently re-validate before
  a publish and lint before a commit.

All three reach the mock HSM backend (`mock_hsm`) only through the stdlib REST
client `HsmClient` (`agents`), carrying an HMAC bearer token minted per call
from a persona id. The backend verifies the token and enforces site/region
scope on every route except `GET /healthz`.

## Architectural Style

**Layered modular monolith, run as several local processes.** Evidence:

- One repository, no packaging (`sys.path.insert` of the repo root in four
  entry points), shared Python packages.
- Clear layers: front ends (`dashboard`, `mcp_server`, `claude-hooks`) →
  client and pure calculations (`agents`) → HTTP backend (`mock_hsm`).
- Processes today: the backend (`python3 -m mock_hsm.server`, 127.0.0.1:8770),
  the Streamlit app (127.0.0.1), the MCP server (stdio child of Claude Code),
  and short-lived hook subprocesses.
- The backend keeps all state in memory (`mock_hsm.db` collections and
  `mock_hsm.writes._state`); only the audit trail is on disk.

## Component Relationships

```mermaid
flowchart LR
    subgraph ClaudeCode["Claude Code session"]
        CMD["slash commands<br/>schedule-labor, review-inventory, commit"]
        SUB["claude-subagents-and-commands<br/>labor-scheduler, inventory-analyst, code-reviewer"]
        HOOKS["claude-hooks<br/>require_no_violations, lint_before_commit"]
    end
    MCP["mcp_server<br/>hsm_tools.py, 11 tools"]
    DASH["dashboard<br/>Streamlit app"]
    AG["agents<br/>HsmClient + pure calculations"]
    AUTH["mock_hsm auth<br/>mint_token / verify_token"]
    BE["mock_hsm server<br/>ThreadingHTTPServer :8770"]
    DB[("mock_hsm db + writes state<br/>in memory")]
    AUD[("audit.jsonl<br/>HSM_AUDIT_PATH")]

    CMD --> SUB
    SUB -->|"mcp__hsm__* tools"| MCP
    HOOKS -->|"validate before publish"| AG
    MCP --> AG
    DASH --> AG
    MCP -->|"mint per call"| AUTH
    DASH -->|"mint per persona"| AUTH
    HOOKS -->|"mint"| AUTH
    AG -->|"HTTP + Bearer token"| BE
    BE -->|"verify"| AUTH
    BE --> DB
    BE --> AUD
    DASH -.->|"imports USERS"| DB
```

Text fallback: commands start subagents; subagents call MCP tools; MCP tools,
the dashboard and the publish hook all use `agents.HsmClient`, which calls the
backend over HTTP with a token minted by `mock_hsm.auth`; the backend verifies
the token, reads/writes in-memory state and appends to the audit file. The
dashboard also imports `mock_hsm.db.USERS` directly for its persona list.

## Data Flow

1. A front end chooses a persona id (`HSM_ACTIVE_USER` for MCP and hooks, the
   in-app picker for the dashboard).
2. `mock_hsm.auth.mint_token` signs a claims payload (persona, org, sites,
   region, one-hour TTL) with the module-level secret.
3. `HsmClient` (base URL from `HSM_BASE_URL`, frozen at import) sends the
   request with `Authorization: Bearer <token>`.
4. `mock_hsm.server.Handler` caps body size, verifies the token (401 on
   failure), matches the regex route table and runs the handler, which checks
   scope (403 outside it).
5. Read routes return seeded or in-memory data. Write routes go through
   `mock_hsm.writes` (sessions, versioned records) or the publish/PO handlers,
   and each one appends to the audit trail first; if the trail is unavailable
   publish/PO return 503.
6. Front ends feed fetched rows into `agents` pure functions
   (`compute_demand`, `compute_usage_anomalies`, `compute_reorder_needs`).

## Write Gating

Layered, for `publish_schedule` and `submit_purchase_order`:

1. `permissions.ask` rules in `.claude/settings.json` prompt the human.
2. `PreToolUse` hook `require_no_violations.py` re-runs validation on the exact
   `shifts` and denies on any violation or any exception (fails closed by
   design; a timed-out hook fails open, so the hook keeps a short budget).
   It uses `HSM_JURISDICTION` (default `GA`).
3. Hooks only deny or fall through; they never grant `allow`.
4. The dashboard has no publish or PO path at all, enforced by a test.

Note: hooks are registered in the gitignored `.claude/settings.local.json`, so
a fresh clone has no hook gate until the example is copied.

## Interaction Diagrams

### Labor scheduling with publish

```mermaid
sequenceDiagram
    actor H as Human
    participant C as Claude Code
    participant LS as labor-scheduler subagent
    participant T as mcp_server tools
    participant K as require_no_violations hook
    participant CL as HsmClient
    participant B as mock_hsm server

    H->>C: /schedule-labor site_001 --publish
    C->>LS: delegate
    LS->>T: compute_labor_demand(site_001)
    T->>CL: get_forecast
    CL->>B: GET /forecast/sites/site_001/sales
    B-->>CL: dated forecast rows
    T-->>LS: demand by day (compute_demand)
    LS->>T: get_employees, get_labor_rules
    LS->>T: validate_schedule(jurisdiction, shifts)
    T->>CL: validate_schedule
    CL->>B: POST /labor/rules/validate
    B-->>LS: violations list
    Note over LS: revise shifts until no violations
    LS->>T: publish_schedule(site_001, shifts)
    C->>H: permissions ask prompt
    H-->>C: allow
    C->>K: PreToolUse with exact shifts
    K->>B: POST /labor/rules/validate
    alt any violation or error
        K-->>C: deny
    else clean
        K-->>C: fall through
        T->>CL: publish_schedule
        CL->>B: POST /labor/sites/site_001/schedules/publish
        B->>B: append audit entry, store schedule
        B-->>LS: published
    end
```

### Inventory review with PO submit

```mermaid
sequenceDiagram
    actor H as Human
    participant IA as inventory-analyst subagent
    participant T as mcp_server tools
    participant B as mock_hsm server

    H->>IA: /review-inventory --submit
    loop each site in region_atl
        IA->>T: compute_usage_anomalies(site)
        T->>B: GET usage, recipes, sales
        T-->>IA: anomalies above 15 percent variance
        IA->>T: compute_reorder_needs(site)
        T->>B: GET on-hand, par levels, reorder points
        T-->>IA: suggested_order_qty per material
    end
    Note over IA: judge cause and severity, cap anomalous items at suggested qty, consolidate by vendor
    IA->>T: submit_purchase_order(vendor, lines)
    Note over T: permissions ask prompt to human first
    T->>B: POST /inventory/purchase-orders
    B->>B: audit append (503 if trail unavailable)
    B-->>IA: PO id
```

### Dashboard data write

```mermaid
sequenceDiagram
    actor U as Visitor
    participant D as dashboard app
    participant S as dashboard session
    participant A as dashboard actions
    participant B as mock_hsm server

    U->>D: pick persona in login panel
    D->>S: client_for(user_id)
    S->>B: POST /sessions
    B-->>S: session_id
    U->>D: Manage data, edit record
    D->>A: update_record(kind, id, version)
    A->>B: PUT item path with session_id and request_id
    alt version conflict or session ended
        B-->>A: 409 or session error
        A-->>D: visible error state
    else ok
        B->>B: apply write, audit append
        B-->>A: new version
    end
```

Text fallback: the labor flow loops validate until clean, then a publish passes
the human `ask` prompt and the independent hook re-validation before reaching
the backend. The inventory flow computes anomalies and reorder needs per site,
caps anomalous items and consolidates POs, then submits behind the `ask`
prompt. The dashboard write flow starts a backend session at login and sends
versioned writes with a session id; conflicts and ended sessions become
visible error states.

## Key Design Decisions (observed)

| Decision | Implication |
|---|---|
| Deterministic maths in `agents/`, judgment in subagents | Numbers are testable and repeatable; the LLM never invents them |
| Compliance decided server-side only | Hook and agent both defer to `/labor/rules/validate` |
| Stdlib-only backend and client | No runtime deps beyond Streamlit for hosting |
| Per-call token minting from a persona id | No login secret per user; the signing secret is the single trust root |
| Tool allowlists in subagent frontmatter | A new tool must be added there before a subagent can use it |
| In-memory backend state | Every restart resets demo data (conflicts with team.md; see `code-quality-assessment.md` CQ-5) |

## Improvement Opportunities (hosting intent)

Recorded once in `code-quality-assessment.md`: secret loading (CQ-1, CQ-2),
in-process backend start (CQ-4), identity gate (CQ-3), persistence (CQ-5).
