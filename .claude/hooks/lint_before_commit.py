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

What gets linted is what the commit will contain: the staged index always
(exported to a temp dir), plus the working tree when the commit takes
content from it (`-a`, `-i`, `-o`, or pathspecs). Commit detection errs
toward over-matching -- a false positive only costs a lint run.

Fails CLOSED: a crashed or timed-out hook is non-blocking in Claude Code,
so every failure to lint a commit (ruff missing, git error, timeout) is an
explicit deny instead. Per-step timeouts stay well under the hook timeout
in .claude/settings.json.
"""
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STEP_TIMEOUT_SECONDS = 20  # up to 4 steps; hook timeout in settings.json is 120s

# Splits a shell command into simple commands, ignoring quotes. That
# over-splits quoted text (a message like "fix (x)"), so it's only trusted to
# *detect* commits -- including ones hidden in quoted $(...) or backticks.
# Commit arguments come from the quote-aware parse (_quoted_segments).
_SEGMENT_SPLIT_RE = re.compile(r"\|\||&&|[;|&\n()`]|\$\(")
_SHELL_PUNCTUATION = set("();<>|&$")
_SHELL_OPTS_WITH_VALUE = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}

_GIT_GLOBAL_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                               "--exec-path", "--config-env", "--super-prefix"}
_COMMIT_OPTS_WITH_VALUE = {"-m", "--message", "-F", "--file", "-C", "--reuse-message", "-c",
                           "--reedit-message", "--author", "--date", "-t", "--template",
                           "--fixup", "--squash", "--cleanup", "--trailer"}
_COMMIT_SHORT_WITH_VALUE = set("mFCct")
_COMMIT_WORKTREE_OPTS = {"-a", "--all", "-i", "--include", "-o", "--only", "--pathspec-from-file"}
_COMMIT_SHORT_WORKTREE = set("aio")


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


def _tokens(segment):
    try:
        return shlex.split(segment)
    except ValueError:  # unbalanced quotes from over-splitting
        return [t.strip("\"'") for t in segment.split()]


def _loose_segments(command):
    return [_tokens(segment) for segment in _SEGMENT_SPLIT_RE.split(command)]


def _quoted_segments(command):
    """Simple commands split on shell operators outside quotes, or None if
    the command can't be tokenized (e.g. an unclosed quote)."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    segments = [[]]
    for tok in tokens:
        if set(tok) <= _SHELL_PUNCTUATION:
            segments.append([])
        else:
            segments[-1].append(tok)
    return segments


def _shell_script(toks, i):
    """The script of `sh -c <script>` (also bundled flags like `-lc`)
    starting at toks[i], or None if it isn't a -c invocation."""
    j, has_c = i + 1, False
    while j < len(toks) and toks[j][:1] in ("-", "+"):
        opt = toks[j]
        if opt in _SHELL_OPTS_WITH_VALUE:
            j += 2
            continue
        has_c = has_c or (opt[0] == "-" and not opt.startswith("--") and "c" in opt[1:])
        j += 1
    return toks[j] if has_c and j < len(toks) else None


def _commits_in(command, split, depth=0):
    segments = split(command)
    if segments is None:
        return None
    commits = []
    for toks in segments:
        for i, tok in enumerate(toks):
            base = os.path.basename(tok)
            script = None
            if depth < 3 and base in _SHELLS:
                script = _shell_script(toks, i)
            elif depth < 3 and base == "eval":
                script = " ".join(toks[i + 1:])
            elif base == "git":
                j = i + 1
                while j < len(toks) and toks[j].startswith("-"):
                    j += 2 if toks[j] in _GIT_GLOBAL_OPTS_WITH_VALUE else 1
                if j < len(toks) and toks[j] == "commit":
                    commits.append(toks[j + 1:])
            if script is not None:
                nested = _commits_in(script, split, depth + 1)
                if nested is None:
                    return None
                commits += nested
    return commits


def find_commits(command):
    """Argument lists (after `commit`) of every git commit in a shell command.
    An entry is None when that commit's arguments can't be read reliably, so
    callers must assume the worst about it."""
    detected = _commits_in(command, _loose_segments)
    parsed = _commits_in(command, _quoted_segments)
    if parsed is None or len(parsed) < len(detected):
        # Unparseable, or a commit the quote-aware parse can't see (inside a
        # quoted $(...) or backticks): its real arguments are unknown.
        return [None] * max(len(detected), len(parsed or []))
    return parsed


def commit_uses_worktree(args):
    """True if `git commit <args>` takes content from the working tree
    rather than only from the index. None (unknown arguments) counts as yes."""
    if args is None:
        return True
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            return len(args) > i + 1
        if arg.startswith("--"):
            name = arg.split("=", 1)[0]
            if name in _COMMIT_WORKTREE_OPTS:
                return True
            i += 2 if (name in _COMMIT_OPTS_WITH_VALUE and "=" not in arg) else 1
            continue
        if arg.startswith("-") and len(arg) > 1:
            takes_next = False
            for pos, letter in enumerate(arg[1:], start=1):
                if letter in _COMMIT_SHORT_WORKTREE:
                    return True
                if letter in _COMMIT_SHORT_WITH_VALUE:
                    takes_next = pos == len(arg) - 1  # "-m" + next token vs "-mmsg"
                    break
            i += 2 if takes_next else 1
            continue
        return True  # positional arg = pathspec
    return False


def _ruff_command(repo):
    if shutil.which("ruff"):
        return ["ruff"]
    venv_ruff = Path(repo) / ".venv" / "bin" / "ruff"
    if venv_ruff.exists():
        return [str(venv_ruff)]
    if importlib.util.find_spec("ruff"):
        return [sys.executable, "-m", "ruff"]
    return None


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=STEP_TIMEOUT_SECONDS, check=False)


def _lint(ruff, cwd, label):
    result = _run([*ruff, "check", "--no-cache", "."], cwd)
    if result.returncode == 0:
        return None
    output = (result.stdout + result.stderr).strip()
    # Keep the reason readable in a permission prompt / transcript.
    truncated = output if len(output) < 2000 else output[:2000] + "\n... (truncated)"
    return f"ruff check failed on the {label} -- fix lint errors before committing:\n{truncated}"


def lint_commit(repo, uses_worktree):
    ruff = _ruff_command(repo)
    if ruff is None:
        return ("ruff not found (checked PATH, .venv/bin, and `python -m ruff`) -- "
                "install it with `pip install -r requirements.txt` so commits can be linted.")

    toplevel = _run(["git", "rev-parse", "--show-toplevel"], repo)
    if toplevel.returncode != 0:
        return None  # not a git repo -- the commit itself will fail
    repo = toplevel.stdout.strip()

    with tempfile.TemporaryDirectory() as staged:
        export = _run(["git", "checkout-index", "-a", "-f", f"--prefix={staged}/"], repo)
        if export.returncode != 0:
            return f"could not export the staged index for linting: {export.stderr.strip()}"
        failure = _lint(ruff, staged, "staged changes")
    if failure is None and uses_worktree:
        failure = _lint(ruff, repo, "working tree (this commit includes unstaged changes)")
    return failure


def main(raw_payload):
    payload = json.loads(raw_payload)
    if payload.get("tool_name") != "Bash":
        return pass_through()

    commits = find_commits(payload.get("tool_input", {}).get("command", ""))
    if not commits:
        return pass_through()

    repo = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    failure = lint_commit(repo, any(commit_uses_worktree(args) for args in commits))
    return deny(failure) if failure else pass_through()


if __name__ == "__main__":
    raw = sys.stdin.read()
    try:
        main(raw)
    except Exception as e:  # noqa: BLE001
        # A crashed hook fails open. Deny anything that might be a commit, but
        # don't let a hook bug block every other Bash command.
        if "commit" in raw:
            deny(f"lint_before_commit could not check this command: {type(e).__name__}: {e}")
        else:
            pass_through()
