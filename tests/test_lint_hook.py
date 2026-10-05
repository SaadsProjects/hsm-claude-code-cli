"""
Tests for .claude/hooks/lint_before_commit.py: commit detection, deciding
what the commit will contain, and end-to-end deny/allow against a real
throwaway git repo.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOOK = PROJECT_ROOT / ".claude" / "hooks" / "lint_before_commit.py"

_spec = importlib.util.spec_from_file_location("lint_before_commit", HOOK)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m x",
        "git add . && git commit -m x",
        "git -C . commit -m x",
        "git -c user.name=x commit -m x",
        "/usr/bin/git commit -m x",
        "(git commit -m x)",
        "echo hi\ngit commit -m x",
        "FOO=1 git commit -m x",
        'bash -c "git add x; git commit -m y"',
        "eval git commit -m x",
        "cd repo; git --no-pager commit -m x",
        'bash -lc "git commit -m x"',
        'sh -ec "git commit -m x"',
        'bash -o pipefail -c "git commit -m x"',
        'bash --rcfile /dev/null -c "git commit -m x"',
    ],
)
def test_detects_commit(command):
    assert hook.find_commits(command)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ('git commit -m "fix (x)"', False),
        ('git commit -m "fix (x)" -a', True),
        ('git commit -m "a && b" -a', True),
        ('git commit -m"a;b" -a', True),
        ('git commit -m "x|y" file.py', True),
        ('bash -lc "git commit -m \\"a;b\\" -a"', True),
        ('git commit -m "$(git commit -am y)"', True),  # hidden commit: args unknown
        ('git commit -m "unclosed', True),  # unparseable: args unknown
    ],
)
def test_worktree_mode_from_command(command, expected):
    assert any(hook.commit_uses_worktree(a) for a in hook.find_commits(command)) is expected


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git log --oneline",
        "ls commit",
        "python3 -m pytest",
    ],
)
def test_ignores_non_commit(command):
    assert not hook.find_commits(command)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["-m", "msg"], False),
        (["-mmsg"], False),
        (["--message=msg", "--no-verify"], False),
        (["-m", "-a looks like a flag but is the message"], False),
        (["-a", "-m", "msg"], True),
        (["-am", "msg"], True),
        (["--all", "-m", "msg"], True),
        (["-m", "msg", "file.py"], True),
        (["-m", "msg", "--", "file.py"], True),
        (["-o", "-m", "msg", "file.py"], True),
    ],
)
def test_commit_uses_worktree(args, expected):
    assert hook.commit_uses_worktree(args) is expected


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    shutil.copy(PROJECT_ROOT / "ruff.toml", tmp_path / "ruff.toml")
    (tmp_path / "ok.py").write_text("X = 1\n")
    git("add", ".")
    return tmp_path, git


def _decision(repo_dir, command):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo_dir)})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo_dir)}
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env, timeout=60, check=False
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout).get("hookSpecificOutput", {}).get("permissionDecision")


LINT_ERROR = "import os\n"  # F401 unused import


def test_clean_commit_allowed(repo):
    repo_dir, _ = repo
    assert _decision(repo_dir, "git commit -m x") is None


def test_staged_lint_error_denied(repo):
    repo_dir, git = repo
    (repo_dir / "bad.py").write_text(LINT_ERROR)
    git("add", "bad.py")
    assert _decision(repo_dir, "git commit -m x") == "deny"


def test_staged_error_denied_even_if_worktree_fixed(repo):
    repo_dir, git = repo
    (repo_dir / "bad.py").write_text(LINT_ERROR)
    git("add", "bad.py")
    (repo_dir / "bad.py").write_text("X = 2\n")  # fixed but not re-staged
    assert _decision(repo_dir, "git commit -m x") == "deny"


def test_unstaged_error_ignored_for_index_only_commit(repo):
    repo_dir, _ = repo
    (repo_dir / "ok.py").write_text(LINT_ERROR)  # tracked, modified, not staged
    assert _decision(repo_dir, "git commit -m x") is None


def test_unstaged_error_denied_for_commit_all(repo):
    repo_dir, _ = repo
    (repo_dir / "ok.py").write_text(LINT_ERROR)
    assert _decision(repo_dir, "git commit -am x") == "deny"


def test_untracked_error_ignored_for_commit_all(repo):
    repo_dir, _ = repo
    (repo_dir / "scratch.py").write_text(LINT_ERROR)  # untracked: -a won't commit it
    assert _decision(repo_dir, "git commit -am x") is None


@pytest.mark.parametrize(
    "command",
    ["git add . && git commit -am x", "git add scratch.py && git commit -m x", "git stage -A; git commit -m x"],
)
def test_untracked_error_denied_when_same_command_stages(repo, command):
    repo_dir, _ = repo
    (repo_dir / "scratch.py").write_text(LINT_ERROR)
    assert _decision(repo_dir, command) == "deny"


def test_large_untracked_venv_does_not_block_staging_commit(repo):
    repo_dir, _ = repo
    venv = repo_dir / "venv" / "lib"  # not gitignored, but in ruff's default excludes
    venv.mkdir(parents=True)
    for i in range(3000):
        (venv / f"m{i}.py").write_text(LINT_ERROR)
    assert _decision(repo_dir, "git add ok.py && git commit -m x") is None


def test_ignored_untracked_file_skipped_when_same_command_stages(repo):
    repo_dir, _ = repo
    (repo_dir / ".gitignore").write_text("scratch.py\n")
    (repo_dir / "scratch.py").write_text(LINT_ERROR)
    assert _decision(repo_dir, "git add . && git commit -m x") is None


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git add . && git commit -m x", True),
        ("git status && git diff && git commit -m x", False),
        ("git commit -am x", False),
    ],
)
def test_stages_in_same_command(command, expected):
    assert hook.stages_in_same_command(command) is expected


def test_invalid_worktree_pyproject_denied_for_commit_all(repo):
    repo_dir, git = repo
    (repo_dir / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1"\n')
    git("add", "pyproject.toml")
    (repo_dir / "pyproject.toml").write_text("[project]\nname = 1\n")  # RUF200
    assert _decision(repo_dir, "git commit -am x") == "deny"


def test_deleted_tracked_file_ignored_for_commit_all(repo):
    repo_dir, git = repo
    (repo_dir / "gone.py").write_text("Y = 1\n")
    git("add", "gone.py")
    (repo_dir / "gone.py").unlink()
    assert _decision(repo_dir, "git commit -am x") is None


def test_non_commit_passes_through(repo):
    repo_dir, git = repo
    (repo_dir / "bad.py").write_text(LINT_ERROR)
    git("add", "bad.py")
    assert _decision(repo_dir, "git status") is None


def test_missing_ruff_denies(repo, monkeypatch):
    repo_dir, _ = repo
    monkeypatch.setattr(hook.shutil, "which", lambda _name: None)
    monkeypatch.setattr(hook.importlib.util, "find_spec", lambda _name: None)
    message = hook.lint_commit(str(repo_dir), uses_worktree=False)
    assert "ruff not found" in message
    # ruff lives in the dev lock; requirements.txt is the hosted-app runtime lock.
    assert "pip install --require-hashes -r requirements-dev.txt" in message
