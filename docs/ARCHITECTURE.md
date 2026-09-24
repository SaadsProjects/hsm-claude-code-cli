# Architecture: subagent call flows

How each subagent's work actually travels through Claude Code, the `hsm` MCP
server, and the mock HSM backend. The source of truth is the code; this
page is a map of it:

| Piece | Where |
|---|---|
| Slash commands | `.claude/commands/{schedule-labor,review-inventory,commit}.md` |
| Subagents + tool allowlists | `.claude/agents/{labor-scheduler,inventory-analyst,code-reviewer}.md` |
| Permission rules + hooks | `.claude/settings.json`, `.claude/hooks/*.py` |
| MCP tools | `mcp_server/hsm_tools.py` (registered in `.mcp.json`) |
| Deterministic math | `agents/labor_scheduling_agent.py`, `agents/inventory_agent.py` |
| HTTP client | `agents/hsm_client.py` (`HSM_BASE_URL`) |
| Mock backend | `mock_hsm/server.py`, `mock_hsm/db.py`, `mock_hsm/auth.py` |

Legend used in the sequence diagrams: **[det]** deterministic code,
**[LLM]** model judgment, **[gate]** a check that can block a write.

## Shared path for every HSM tool call

```mermaid
flowchart LR
    U([User]) -->|"/schedule-labor, /review-inventory"| MC[Main Claude session]
    MC -->|Agent tool| SA["Subagent<br/>(tools: allowlist)"]
    SA -->|"mcp__hsm__*"| T["MCP tool<br/>mcp_server/hsm_tools.py"]
    T --> C["_client()<br/>mint_token(HSM_ACTIVE_USER)<br/>mock_hsm/auth.py"]
    C --> H["HsmClient<br/>agents/hsm_client.py"]
    H -->|"HTTP + bearer token<br/>HSM_BASE_URL"| S["mock_hsm/server.py<br/>verify token, enforce site/region scope<br/>(403 outside scope)"]
    S --> DB[("mock_hsm/db.py<br/>in-memory")]
    T -.->|"local call [det]"| AG["agents/*.py<br/>compute_demand<br/>compute_usage_anomalies<br/>compute_reorder_needs"]
```

The deterministic functions run inside the MCP tool process, on data the
tool fetched through `HsmClient`. The tools never read data tables from
`mock_hsm.db`: the only local use is token minting, which looks the persona
up in its user table. Labor-rule validation is the exception to local
math: it runs server-side in `POST /labor/rules/validate`.

## labor-scheduler: `/schedule-labor <site_id> [--publish]`

Persona: Restaurant Manager scoped to the site (e.g. `user_rm_midtown`).

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant MC as Main Claude
    participant LS as labor-scheduler
    participant T as MCP tools
    participant HK as require_no_violations.py
    participant API as Mock HSM API

    U->>MC: /schedule-labor site_001 [--publish]
    MC->>LS: Agent(labor-scheduler), publish only if --publish
    LS->>T: compute_labor_demand(site_id)
    T->>API: GET /forecast/sites/{site}/sales
    API-->>T: forecast rows with site-local dates
    Note over T: [det] compute_demand, role-hours per day
    T-->>LS: demand
    LS->>T: get_employees(site_id)
    T->>API: GET /labor/sites/{site}/employees
    LS->>T: get_labor_rules(jurisdiction)
    T->>API: GET /labor/rules?jurisdiction=GA
    Note over LS: [LLM] draft a week of shifts
    loop validate, then revise and re-validate up to 3 more times while violations remain
        LS->>T: validate_schedule(jurisdiction, shifts)
        T->>API: POST /labor/rules/validate
        API-->>LS: violations
        Note over LS: [LLM] revise, prefer reassigning to same job_code
    end
    opt --publish and zero violations
        LS->>T: publish_schedule(site_id, shifts)
        Note over T,HK: [gate] PreToolUse hook runs first
        HK->>API: POST /labor/rules/validate (exact shifts, HSM_JURISDICTION)
        alt violations, or cannot validate
            HK-->>LS: deny
        else clean
            HK-->>U: fall through, [gate] permissions.ask prompt
            U-->>T: approve
            T->>API: POST /labor/sites/{site}/schedules/publish
            API-->>LS: published (403 if site out of scope or persona cannot publish)
        end
    end
    LS-->>MC: draft, coverage gaps, violations, projected cost
    MC-->>U: report
```

## inventory-analyst: `/review-inventory [--submit]`

Persona: Regional Manager for `region_atl` (`user_regional_atl`), sites
site_001 to site_003.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant MC as Main Claude
    participant IA as inventory-analyst
    participant T as MCP tools
    participant API as Mock HSM API

    U->>MC: /review-inventory [--submit]
    MC->>IA: Agent(inventory-analyst), sites 001-003, submit only if --submit
    loop each site
        IA->>T: compute_usage_anomalies(site_id)
        T->>API: GET /inventory/sites/{site}/usage (past 7 days)
        T->>API: GET /inventory/vendors
        Note over T: [det] variance vs expected, 15% threshold
        T-->>IA: anomalies
        IA->>T: compute_reorder_needs(site_id)
        T->>API: GET /forecast/sites/{site}/sales (next 7 days)
        T->>API: GET /inventory/sites/{site}/on-hand
        T->>API: GET /inventory/recipes/{item} (per forecast item)
        T->>API: GET /inventory/vendors
        Note over T: [det] projected use vs reorder point and par
        T-->>IA: reorder needs
    end
    Note over IA: [LLM] cause and severity per anomaly
    IA->>T: get_vendors()
    T->>API: GET /inventory/vendors
    Note over IA: [LLM] draft POs per vendor, consolidate vs min_order_value
    Note over IA: [LLM] prompt rule, not enforced by code: cap qty at suggested_order_qty for medium/high anomalies
    opt --submit
        IA->>T: submit_purchase_order(vendor_id, line_items, site or region)
        Note over U,T: [gate] permissions.ask prompt (no hook on this tool)
        U-->>T: approve
        T->>API: POST /inventory/purchase-orders
        API-->>IA: PO (403 if site or region out of scope, or region PO without a regional persona)
    end
    IA-->>MC: anomalies, draft POs, capped items
    MC-->>U: report
```

## code-reviewer: `/commit <message>`

No MCP tools. The reviewer has `Read, Grep, Glob, Bash` and no
`Edit`/`Write` tools. Its prompt says to only report, but with Bash that
is not enforced. The lint gate is the `PreToolUse` Bash hook, which sees
every Bash call and only acts on ones that look like a commit.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant MC as Main Claude
    participant CR as code-reviewer
    participant LH as lint_before_commit.py
    participant G as git and ruff

    U->>MC: /commit message
    MC->>G: git status, git diff, git add only if nothing staged (Bash)
    Note over LH: every Bash call passes the hook, not a commit so fall through
    MC->>CR: Agent(code-reviewer)
    CR->>G: git diff --staged
    Note over CR: [LLM] read surrounding code, run pytest if tested code changed
    CR-->>MC: findings, most severe first
    MC-->>U: show findings
    alt real problems found
        U-->>MC: decide, fix first or commit anyway
    else clean, or user accepts
        MC->>LH: Bash git commit -m message ([gate] PreToolUse)
        Note over LH: [det] find_commits, quote-aware args plus regex detector
        LH->>G: checkout-index staged index to temp dir, ruff check
        opt -a, -i, -o, pathspec, or unreadable args
            LH->>G: ruff check on working tree
        end
        alt lint errors, ruff missing, or hook error
            LH-->>MC: deny, fix lint and retry
        else clean
            LH-->>MC: fall through
            MC->>G: git commit
        end
    end
    MC-->>U: commit hash
```

## Where writes are gated

| Write | `permissions.ask` | PreToolUse hook | Prompt rule |
|---|---|---|---|
| `publish_schedule` | yes | `require_no_violations.py` re-validates exact shifts | only with `--publish`, only at zero violations |
| `submit_purchase_order` | yes | none | only with `--submit`, cap anomalous materials |
| `git commit` | no | `lint_before_commit.py` | via `/commit` after review |

Hooks run before the permission prompt and only ever deny or fall through.
They never grant `allow`.
