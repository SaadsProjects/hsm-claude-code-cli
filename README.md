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
pip install -r requirements.txt

# Terminal 1 -- start the mock HSM backend
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

The first time you start `claude` in this directory it will ask to
approve the project's `.mcp.json` server (`hsm`) — approve it, since
that's what exposes the HSM tools.

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
mock_hsm/                       mock HSM REST backend
agents/hsm_client.py            REST client used by the MCP tools
agents/labor_scheduling_agent.py   pure demand-calculation function only
agents/inventory_agent.py          pure anomaly/reorder-calculation functions only
mcp_server/hsm_tools.py         MCP server: wraps the above as tools
.mcp.json                       registers the hsm MCP server for this project
.claude/agents/                 labor-scheduler.md, inventory-analyst.md, code-reviewer.md
.claude/commands/               /schedule-labor, /review-inventory, /commit
.claude/hooks/                  require_no_violations.py, lint_before_commit.py (both PreToolUse)
.claude/settings.json           permission rules + hook registration
tests/test_mcp_tools.py         protocol-level test, no LLM required
```

## Linting + code review before committing

Use `/commit <message>` rather than a bare `git commit` for changes to
this project's own code. It runs the `code-reviewer` subagent (read-only —
no `Edit`/`Write`, so it reports findings instead of silently altering
your code) against the staged diff, then commits only if you're satisfied
with the review — and even then, `lint_before_commit.py` independently
runs `ruff check` as a hard `PreToolUse` gate on the commit itself, so a
dirty lint result blocks the commit regardless of what the review
concluded or what a human approved. It lints what the commit will
actually contain (the staged index, plus the working tree for `commit -a`
or pathspecs). Install `ruff` (already in `requirements.txt`): if the hook
can't find it on PATH, in `.venv/bin`, or as `python -m ruff`, it blocks
the commit rather than letting it through unchecked.

## Persona reference

| `HSM_ACTIVE_USER` | Persona | Scope |
|---|---|---|
| `user_rm_midtown` | Restaurant Manager | `site_001` only |
| `user_regional_atl` | Regional Manager | `region_atl` (site_001, site_002, site_003) |

Set this before starting `claude` — the MCP server mints a token for
whichever user it names, and the mock backend enforces that user's scope
on every call, exactly as HSM's real Apigee-fronted services would.
