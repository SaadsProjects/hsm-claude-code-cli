#!/usr/bin/env python3
"""
PreToolUse hook guarding `git commit`.

Deterministic gate, same shape as require_no_violations.py: linting is a
pass/fail check with no judgment involved, so it belongs in a hook that
can hard-block the commit, not in a subagent's discretion. Code review
(judgment: is this diff actually correct/safe/consistent) is handled
separately by the code-reviewer subagent via /commit -- this hook only
ever checks "does it lint clean."

Claude Code invokes this with a JSON payload on stdin for every Bash call:
    {"tool_name": "Bash", "tool_input": {"command": "..."}, "cwd": "...", ...}
and reads a JSON decision from stdout, per the PreToolUse hook schema:
    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                             "permissionDecision": "deny",
                             "permissionDecisionReason": "..."}}
Omitting permissionDecision falls through to Claude Code's normal
permission flow, so a command that isn't `git commit`, or a `git commit`
that lints clean, both pass through untouched -- this hook only ever
actively blocks, never grants a bypass a human/agent didn't already have.

If `ruff` isn't installed, this fails OPEN (allows the commit through)
rather than blocking every commit in an environment that never installed
it -- see the printed note in that case. Install ruff to make the gate
actually enforce: `pip install ruff`.
"""
import json
import re
import shutil
import subprocess
import sys

GIT_COMMIT_RE = re.compile(r"(^|[;&|]\s*)git\s+commit\b")


def pass_through():
    print(json.dumps({}))


def deny(reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return pass_through()

    command = payload.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT_RE.search(command):
        return pass_through()

    if not shutil.which("ruff"):
        print("[lint_before_commit] ruff not found on PATH -- allowing commit "
              "through unchecked. Run `pip install ruff` to enforce this gate.",
              file=sys.stderr)
        return pass_through()

    cwd = payload.get("cwd") or "."
    result = subprocess.run(["ruff", "check", "."], cwd=cwd, capture_output=True, text=True, timeout=60,
                            check=False)

    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        # Keep the reason readable in a permission prompt / transcript.
        truncated = output if len(output) < 2000 else output[:2000] + "\n... (truncated)"
        return deny(f"ruff check failed -- fix lint errors before committing:\n{truncated}")

    return pass_through()


if __name__ == "__main__":
    main()
