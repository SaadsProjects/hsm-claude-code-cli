# Component Inventory: hsm-claude-code-cli

Commit `825a0f8`. Headings are the component names used in
`reverse-engineering-timestamp.md` § Scope of Analysis. Health ratings:
healthy / at-risk / degraded.

## agents

- **Type:** library (Python package).
- **Responsibility:** the only path to the backend (`HsmClient`, stdlib
  `urllib`) and the deterministic calculations (`compute_demand`,
  `compute_usage_anomalies`, `compute_reorder_needs`).
- **Depends on:** nothing in the repo at import; reaches `mock_hsm` over HTTP.
- **Used by:** `dashboard`, `mcp_server`, `claude-hooks`, `tests`.
- **Health:** at-risk for hosting. `HSM_BASE_URL` is frozen at import (CQ-4).

## mock_hsm

- **Type:** service (Python package).
- **Responsibility:** mock HSM backend: route table and handler (`server`),
  token mint/verify (`auth`), seed data and in-memory collections (`db`),
  sessions and per-kind writes (`writes`), durable JSONL audit (`audit`).
- **Depends on:** stdlib only. Internal: `server` → `audit`, `db`, `writes`,
  `auth`; `writes` → `audit`, `db`, `auth.site_allowed`; `auth` → `db`.
- **Used by:** `dashboard` (imports `auth.mint_token`, `db.USERS`),
  `mcp_server` and `claude-hooks` (import `auth`), every front end over HTTP.
- **Health:** at-risk for hosting. Burned secret literal (CQ-1, CQ-2),
  blocking-only start (CQ-4), in-memory state (CQ-5). Large but cohesive
  modules (`writes.py` 1,870 lines, `audit.py` 740).

## dashboard

- **Type:** UI (Streamlit package).
- **Responsibility:** the people-facing app: login panel (persona picker),
  read-only Overview/Labor/Inventory tabs, Manage data tab (writes after a
  backend session), Audit tab.
- **Depends on:** `agents`, `mock_hsm.auth`, `mock_hsm.db.USERS`, `streamlit`.
- **Used by:** people, via `streamlit run dashboard/app.py`.
- **Health:** at-risk for hosting. No identity gate in front of the persona
  picker (CQ-3); `app.py` reruns on every interaction, so process-level setup
  cannot live there (CQ-4).

## mcp_server

- **Type:** service (FastMCP stdio server, `hsm_tools.py`).
- **Responsibility:** expose 11 `mcp__hsm__*` tools to Claude Code subagents;
  thin adapter over `agents`.
- **Depends on:** `agents`, `mock_hsm.auth`, `mcp` 1.30.0 (dev lockfile only).
- **Used by:** `claude-subagents-and-commands`.
- **Health:** healthy. Not part of the hosted app.

## claude-hooks

- **Type:** tooling (`.claude/hooks/require_no_violations.py`,
  `.claude/hooks/lint_before_commit.py`).
- **Responsibility:** independent publish re-validation; lint gate on commit.
- **Depends on:** `agents.hsm_client`, `mock_hsm.auth` (publish hook); `ruff`
  and git (lint hook).
- **Used by:** Claude Code, only when registered in the gitignored
  `.claude/settings.local.json`.
- **Health:** healthy, with two `noqa: BLE001` lacking a reason (CQ-10).

## claude-subagents-and-commands

- **Type:** config (`.claude/agents/labor-scheduler.md`,
  `inventory-analyst.md`, `code-reviewer.md`; `.claude/commands/*.md`;
  `.claude/settings.json` `ask` rules).
- **Responsibility:** the judgment layer and its tool allowlists; the
  `/schedule-labor`, `/review-inventory` and `/commit` entry points.
- **Depends on:** `mcp_server` tools; `claude-hooks`.
- **Health:** healthy.

## scripts

- **Type:** tooling (Python and shell).
- **Responsibility:** CI gates (burned secret, exceptions register, workflow
  lint, audit/bandit filters, floors, coverage gate, job summary) and
  `start_mock_server.sh`.
- **Used by:** `ci-workflow`, developers, tests via `tests/ci_scripts.py`.
- **Health:** healthy; `check_burned_secret.py` carries a temporary exclusion
  that must leave with the literal (CQ-2). `start_mock_server.sh` has no
  secret step (CQ-7).

## tests

- **Type:** tests (pytest, 24 files, 837 collected at `825a0f8`).
- **Responsibility:** unit, route, subprocess (hooks on port 8773, MCP on
  8772) and Streamlit `AppTest` coverage; CI script tests.
- **Health:** healthy. No fixture sets a signing secret yet (CQ-1); fixed
  ports keep the suite serial.

## ci-workflow

- **Type:** CI (`.github/workflows/ci.yml`, `.github/dependabot.yml`).
- **Responsibility:** required checks `lint`, `workflow-lint`, `secrets`,
  `audit`, `sast`, `lock-check`, `tests (3.10)`, `tests (3.14)`,
  `coverage-gate`, `browser-tests`; plus the non-required `matrix` job.
- **Health:** healthy; `browser-tests` is wired but nothing installs Playwright
  yet (CQ-6), and it keys on fixed future file paths (CQ-8). No deploy
  workflow exists.
