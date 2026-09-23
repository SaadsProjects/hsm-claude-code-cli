#!/usr/bin/env python3
"""
PreToolUse hook guarding mcp__hsm__publish_schedule.

This is the hard backstop for the labor-scheduling approval gate: even if
the labor-scheduler subagent (or a human clicking "yes" on the permission
prompt) is wrong about a schedule being compliant, this hook independently
re-validates the exact shift list against the (mock) Labor Rules Engine
before the write is allowed through. It deliberately does not trust
anything the subagent said about compliance -- it re-derives the answer
itself, the same way validate_schedule would.

Claude Code invokes this with a JSON payload on stdin:
    {"tool_name": "mcp__hsm__publish_schedule",
     "tool_input": {"site_id": "...", "shifts": [...]}, ...}
and reads a JSON decision from stdout:
    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                             "permissionDecision": "deny" | "allow",
                             "permissionDecisionReason": "..."}}
Omitting permissionDecision falls through to Claude Code's normal
permission flow (the "ask" rule in settings.json), so this hook only ever
actively BLOCKS -- it never grants a bypass. It falls through only after a
successful validation with zero violations; any failure to validate denies.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Well under the 30s hook timeout in settings.json, so a hung backend ends in
# an explicit deny rather than Claude Code killing the hook (which fails open).
BACKEND_TIMEOUT_SECONDS = 5


def deny(reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    from agents.hsm_client import HsmClient
    from mock_hsm.auth import mint_token

    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "mcp__hsm__publish_schedule":
        print(json.dumps({}))  # not our tool -- fall through
        return

    tool_input = payload.get("tool_input", {})
    shifts = tool_input.get("shifts", [])
    jurisdiction = os.environ.get("HSM_JURISDICTION", "GA")
    user_id = os.environ.get("HSM_ACTIVE_USER")

    if not user_id:
        deny("HSM_ACTIVE_USER is not set; cannot independently re-validate this schedule")

    client = HsmClient(mint_token(user_id), timeout=BACKEND_TIMEOUT_SECONDS)
    result = client.validate_schedule(jurisdiction, shifts)

    if result["violations"]:
        summary = "; ".join(f"{v['employee_id']}: {v['rule']}" for v in result["violations"][:5])
        deny(f"{len(result['violations'])} unresolved labor-rule violation(s): {summary}")

    print(json.dumps({}))  # no violations -- fall through to the normal "ask" permission prompt


if __name__ == "__main__":
    # A crashed hook is a non-blocking error in Claude Code, so any failure to
    # re-validate (bad payload, import error, unknown user, unreachable or
    # misbehaving backend) must become an explicit deny rather than a raise.
    # deny() exits via SystemExit, which this deliberately doesn't catch.
    try:
        main()
    except Exception as e:  # noqa: BLE001
        deny(f"could not re-validate schedule against the Labor Rules Engine: {type(e).__name__}: {e}")
