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

What gets linted is what the commit will contain. The hook runs before
the whole Bash command, so it sees the index as it is *before* anything
else in that command runs:
- always: the staged index (exported to a temp dir);
- when the commit takes content from the working tree (`-a`, `-i`, `-o`,
  or pathspecs): the working tree's tracked files;
- when the same command also runs a git subcommand that can stage files
  (`git add . && git commit ...`, or anything not known to be read-only):
  the working tree's tracked *and* untracked, non-ignored files.
For tracked files, only ones ruff would lint are passed (Python sources and
pyproject.toml); with untracked files in play, ruff walks the tree itself.
Detection errs toward over-matching -- a false positive only costs a lint run.

Scope limits: non-git commands earlier in the same Bash call (`sed -i`,
scripts, `make`, `pre-commit run`) run after this hook, so files they edit
or stage aren't seen. This checks the project repo (CLAUDE_PROJECT_DIR) and its
default index; a commit aimed elsewhere -- `git -C <dir>`, `cd <dir> &&`,
`GIT_DIR`/`GIT_INDEX_FILE` -- is linted against this repo, not the one
actually committed to.

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

STEP_TIMEOUT_SECONDS = 20  # up to 5 steps; hook timeout in settings.json is 120s

# Git subcommands that never change the index. Any other git call in the same
# command as a commit is assumed to possibly stage files.
_READ_ONLY_GIT = {
    "status",
    "diff",
    "log",
    "show",
    "rev-parse",
    "ls-files",
    "blame",
    "grep",
    "describe",
    "shortlog",
    "help",
    "version",
    "remote",
    "fetch",
    "push",
    "config",
    "branch",
    "tag",
    "reflog",
    "cat-file",
    "rev-list",
}

# Splits a shell command into simple commands, ignoring quotes. That
# over-splits quoted text (a message like "fix (x)"), so it's only trusted to
# *detect* commits -- including ones hidden in quoted $(...) or backticks.
# Commit arguments come from the quote-aware parse (_quoted_segments).
_SEGMENT_SPLIT_RE = re.compile(r"\|\||&&|[;|&\n()`]|\$\(")
_SHELL_PUNCTUATION = set("();<>|&$")
_SHELL_OPTS_WITH_VALUE = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}

_GIT_GLOBAL_OPTS_WITH_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--config-env",
    "--super-prefix",
}
_COMMIT_OPTS_WITH_VALUE = {
    "-m",
    "--message",
    "-F",
    "--file",
    "-C",
    "--reuse-message",
    "-c",
    "--reedit-message",
    "--author",
    "--date",
    "-t",
    "--template",
    "--fixup",
    "--squash",
    "--cleanup",
    "--trailer",
}
_COMMIT_SHORT_WITH_VALUE = set("mFCct")
_COMMIT_WORKTREE_OPTS = {"-a", "--all", "-i", "--include", "-o", "--only", "--pathspec-from-file"}
_COMMIT_SHORT_WORKTREE = set("aio")


def pass_through():
    print(json.dumps({}))


def deny(reason: str):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


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


def _git_calls(command, split, depth=0):
    """(subcommand, args) for every git invocation in a shell command, or
    None if the command can't be tokenized."""
    segments = split(command)
    if segments is None:
        return None
    calls = []
    for toks in segments:
        for i, tok in enumerate(toks):
            base = os.path.basename(tok)
            script = None
            if depth < 3 and base in _SHELLS:
                script = _shell_script(toks, i)
            elif depth < 3 and base == "eval":
                script = " ".join(toks[i + 1 :])
            elif base == "git":
                j = i + 1
                while j < len(toks) and toks[j].startswith("-"):
                    j += 2 if toks[j] in _GIT_GLOBAL_OPTS_WITH_VALUE else 1
                if j < len(toks):
                    calls.append((toks[j], toks[j + 1 :]))
            if script is not None:
                nested = _git_calls(script, split, depth + 1)
                if nested is None:
                    return None
                calls += nested
    return calls


def _commits_in(command, split):
    calls = _git_calls(command, split)
    return None if calls is None else [args for sub, args in calls if sub == "commit"]


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


def stages_in_same_command(command):
    """True if the command runs a git subcommand, besides the commit, that
    might change the index before the commit runs. Uses the quote-blind
    split, so it over-matches (e.g. `git add` inside a commit message)."""
    calls = _git_calls(command, _loose_segments)
    return any(sub not in _READ_ONLY_GIT and sub != "commit" for sub, _ in calls)


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
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=STEP_TIMEOUT_SECONDS, check=False)


_PYTHON_SUFFIXES = (".py", ".pyi", ".ipynb")
_MAX_PATH_ARGS = 2000  # beyond this, lint the whole tree instead of an argv list


def _lintable(path):
    return path.endswith(_PYTHON_SUFFIXES) or os.path.basename(path) == "pyproject.toml"


def _lint(ruff, cwd, label, paths=(".",)):
    result = _run([*ruff, "check", "--no-cache", "--force-exclude", "--", *paths], cwd)
    if result.returncode == 0:
        return None
    output = (result.stdout + result.stderr).strip()
    # Keep the reason readable in a permission prompt / transcript.
    truncated = output if len(output) < 2000 else output[:2000] + "\n... (truncated)"
    return f"ruff check failed on the {label} -- fix lint errors before committing:\n{truncated}"


def lint_commit(repo, uses_worktree, include_untracked=False):
    ruff = _ruff_command(repo)
    if ruff is None:
        return (
            "ruff not found (checked PATH, .venv/bin, and `python -m ruff`) -- "
            "install it with `pip install --require-hashes -r requirements-dev.txt` so commits can be linted."
        )

    toplevel = _run(["git", "rev-parse", "--show-toplevel"], repo)
    if toplevel.returncode != 0:
        return None  # not a git repo -- the commit itself will fail
    repo = toplevel.stdout.strip()

    with tempfile.TemporaryDirectory() as staged:
        export = _run(["git", "checkout-index", "-a", "-f", f"--prefix={staged}/"], repo)
        if export.returncode != 0:
            return f"could not export the staged index for linting: {export.stderr.strip()}"
        failure = _lint(ruff, staged, "staged changes")
    if failure is None and (uses_worktree or include_untracked):
        failure = _lint_worktree(ruff, repo, include_untracked)
    return failure


def _lint_worktree(ruff, repo, include_untracked):
    if include_untracked:
        # Anything non-ignored may get staged: let ruff walk the tree itself
        # (it honours .gitignore and its default excludes like venv/).
        return _lint(ruff, repo, "working tree (this command also stages files)")
    listed = _run(["git", "ls-files", "-z", "--cached"], repo)
    if listed.returncode != 0:
        return f"could not list tracked files for linting: {listed.stderr.strip()}"
    paths = sorted({p for p in listed.stdout.split("\0") if _lintable(p) and os.path.isfile(os.path.join(repo, p))})
    if not paths:
        return None
    label = "working tree (this commit includes unstaged changes)"
    if len(paths) > _MAX_PATH_ARGS:
        # Too many to pass as arguments; linting everything over-blocks
        # (untracked files too) but never lets a dirty file through.
        return _lint(ruff, repo, label)
    return _lint(ruff, repo, label, paths)


def main(raw_payload):
    payload = json.loads(raw_payload)
    if payload.get("tool_name") != "Bash":
        return pass_through()

    commits = find_commits(payload.get("tool_input", {}).get("command", ""))
    if not commits:
        return pass_through()

    command = payload.get("tool_input", {}).get("command", "")
    repo = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    failure = lint_commit(
        repo, any(commit_uses_worktree(args) for args in commits), include_untracked=stages_in_same_command(command)
    )
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
