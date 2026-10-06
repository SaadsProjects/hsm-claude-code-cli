"""
Unit U4: ``agents/build_info.py`` names the running build (FR5.1, US5.1, US5.2).

Git trees are written by hand in ``tmp_path`` (``HEAD``, loose refs,
``packed-refs``), so no git binary is needed except for the one test that
compares against ``git rev-parse HEAD`` on this repository.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import build_info as bi

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "fedcba9876543210fedcba9876543210fedcba98"


@pytest.fixture(autouse=True)
def fresh_cache():
    # build_info() is computed once per root per process (B3); every test
    # starts and ends with an empty cache so trees in tmp_path don't leak.
    bi.build_info.cache_clear()
    yield
    bi.build_info.cache_clear()


def _git_dir(root, head):
    git = root / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text(head)
    return git


# ------------------------------------------------------- commit SHA (B1, AC5.1.1)


def test_a_branch_head_with_a_loose_ref_gives_that_commit(tmp_path):
    git = _git_dir(tmp_path, "ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text(SHA + "\n")
    info = bi.build_info(tmp_path)
    assert (info.kind, info.value) == ("commit", SHA)


def test_a_ref_only_in_packed_refs_gives_that_commit(tmp_path):
    git = _git_dir(tmp_path, "ref: refs/heads/feature/x\n")
    (git / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{OTHER_SHA} refs/heads/main\n"
        f"{SHA} refs/heads/feature/x\n"
        f"^{OTHER_SHA}\n"
    )
    info = bi.build_info(tmp_path)
    assert (info.kind, info.value) == ("commit", SHA)


def test_a_loose_ref_wins_over_a_stale_packed_one(tmp_path):
    git = _git_dir(tmp_path, "ref: refs/heads/main\n")
    (git / "packed-refs").write_text(f"{OTHER_SHA} refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text(SHA + "\n")
    assert bi.build_info(tmp_path).value == SHA


def test_a_moved_branch_ref_is_seen_without_a_restart(tmp_path):
    # A hosted app can pull a new commit into the running process; the
    # caption must follow it rather than keep the first answer (commit review 1).
    git = _git_dir(tmp_path, "ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text(SHA + "\n")
    assert bi.build_info(tmp_path).value == SHA
    (git / "refs" / "heads" / "main").write_text(OTHER_SHA + "\n")
    assert bi.build_info(tmp_path).value == OTHER_SHA


@pytest.mark.parametrize("branch", ["feat+x", "user@host", "issue#12", "café", "a/b-c_d.e"])
def test_any_valid_branch_name_gives_its_commit(tmp_path, branch):
    # Git allows these characters in ref names; only ".." and control or
    # reserved characters make a ref malformed (commit review 3).
    git = _git_dir(tmp_path, f"ref: refs/heads/{branch}\n")
    ref = git / "refs" / "heads" / branch
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(SHA + "\n", encoding="utf-8")
    info = bi.build_info(tmp_path)
    assert (info.kind, info.value) == ("commit", SHA)


def test_a_detached_head_holds_the_commit_itself(tmp_path):
    _git_dir(tmp_path, SHA + "\n")
    info = bi.build_info(tmp_path)
    assert (info.kind, info.value) == ("commit", SHA)


def test_a_git_file_is_followed_to_a_worktree_gitdir_and_its_common_dir(tmp_path):
    # A linked worktree: .git is a file, HEAD lives in the worktree's gitdir,
    # and the branch ref lives in the main repository's common dir.
    common = tmp_path / "main-repo" / ".git"
    (common / "refs" / "heads").mkdir(parents=True)
    (common / "refs" / "heads" / "wt-branch").write_text(SHA + "\n")
    gitdir = common / "worktrees" / "wt"
    gitdir.mkdir(parents=True)
    (gitdir / "HEAD").write_text("ref: refs/heads/wt-branch\n")
    (gitdir / "commondir").write_text("../..\n")
    checkout = tmp_path / "wt"
    checkout.mkdir()
    (checkout / ".git").write_text(f"gitdir: {gitdir}\n")
    info = bi.build_info(checkout)
    assert (info.kind, info.value) == ("commit", SHA)


def test_a_relative_gitdir_is_resolved_from_the_checkout(tmp_path):
    other = tmp_path / "elsewhere"
    (other / "refs" / "heads").mkdir(parents=True)
    (other / "HEAD").write_text(SHA + "\n")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: ../elsewhere\n")
    assert bi.build_info(checkout).value == SHA


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")
def test_this_repository_matches_git_rev_parse_head():
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    info = bi.build_info()
    assert (info.kind, info.value) == ("commit", head)


# --------------------------------------------- fingerprint fallback (B2, US5.2)


def _source_copy(tmp_path):
    """A small copy of the app's source without .git, as a checkout that has
    no .git directory would look."""
    root = tmp_path / "src"
    for package in ("agents", "dashboard"):
        (root / package).mkdir(parents=True)
        for name in ("__init__.py", "markers.py" if package == "dashboard" else "build_info.py"):
            shutil.copy(PROJECT_ROOT / package / name, root / package / name)
    (root / "requirements.txt").write_text("streamlit==1.64.0\n")
    return root


def _fresh(root):
    bi.build_info.cache_clear()
    return bi.build_info(root)


def test_fingerprint_is_stable_and_marked_as_a_fingerprint(tmp_path):
    root = _source_copy(tmp_path)
    first, second = _fresh(root), _fresh(root)
    assert first == second
    assert first.kind == "fingerprint"
    assert len(first.value) == 64 and int(first.value, 16) >= 0


def test_fingerprint_changes_when_a_source_file_changes(tmp_path):
    root = _source_copy(tmp_path)
    before = _fresh(root)
    with (root / "dashboard" / "markers.py").open("a") as f:
        f.write("\n# edited\n")
    assert _fresh(root).value != before.value


def test_a_changed_source_changes_the_fingerprint_without_a_restart(tmp_path):
    # As for the commit: a source change pulled into a running process must
    # reach the caption, so no cache may hide it (commit review 1).
    root = _source_copy(tmp_path)
    before = bi.build_info(root)
    (root / "dashboard" / "markers.py").write_text("X = 'edited, and a different size'\n")
    assert bi.build_info(root).value != before.value


def test_fingerprint_changes_when_requirements_change(tmp_path):
    root = _source_copy(tmp_path)
    before = _fresh(root)
    (root / "requirements.txt").write_text("streamlit==1.65.0\n")
    assert _fresh(root).value != before.value


def test_fingerprint_ignores_files_the_app_writes_while_running(tmp_path):
    root = _source_copy(tmp_path)
    before = _fresh(root)
    (root / "dashboard" / "__pycache__").mkdir()
    (root / "dashboard" / "__pycache__" / "markers.cpython-314.pyc").write_bytes(b"\x00compiled")
    (root / "agents" / "stray.pyc").write_bytes(b"\x00stray")
    (root / "mock_hsm" / "audit").mkdir(parents=True)
    (root / "mock_hsm" / "audit" / "audit.jsonl").write_text('{"event": "write"}\n')
    (root / "mock_hsm" / "audit" / "scratch.py").write_text("x = 1\n")
    assert _fresh(root).value == before.value


def test_a_malformed_git_dir_falls_back_to_the_fingerprint(tmp_path):
    root = _source_copy(tmp_path)
    expected = _fresh(root)
    _git_dir(root, "ref: refs/heads/missing\n")  # names a ref that exists nowhere
    info = _fresh(root)
    assert info.kind == "fingerprint"
    # .git itself isn't part of the source, so the fingerprint is unchanged.
    assert info.value == expected.value


@pytest.mark.parametrize(
    "head",
    [
        "ref: ../../etc/passwd\n",  # not under refs/
        "ref: refs/heads/../../HEAD\n",  # climbs out of refs/
        "not-a-sha\n",
        "",
    ],
)
def test_an_unusable_head_falls_back_to_the_fingerprint(tmp_path, head):
    root = _source_copy(tmp_path)
    _git_dir(root, head)
    assert _fresh(root).kind == "fingerprint"


def test_a_git_file_without_a_gitdir_line_falls_back_to_the_fingerprint(tmp_path):
    root = _source_copy(tmp_path)
    (root / ".git").write_text("something else\n")
    assert _fresh(root).kind == "fingerprint"


def test_an_unreadable_ref_falls_back_to_the_fingerprint(tmp_path):
    root = _source_copy(tmp_path)
    git = _git_dir(root, "ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_bytes(b"\xff\xfe not utf-8")
    assert _fresh(root).kind == "fingerprint"


# ------------------------------------------- label and command line (B3, B4)


def test_a_commit_label_is_build_and_the_first_seven_characters():
    assert bi.BuildInfo(kind="commit", value=SHA).label == "Build 0123456"


def test_a_fingerprint_label_is_build_src_and_the_first_eight_characters(tmp_path):
    info = _fresh(_source_copy(tmp_path))
    assert info.label == f"Build src-{info.value[:8]}"
    assert len(info.label) == len("Build src-") + 8


def test_python_m_agents_build_info_prints_the_label_the_app_shows():
    result = subprocess.run(
        [sys.executable, "-m", "agents.build_info"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == bi.build_info().label + "\n"


def test_build_info_imports_only_the_standard_library_and_never_streamlit():
    import ast

    tree = ast.parse((PROJECT_ROOT / "agents" / "build_info.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert "streamlit" not in imported
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported - set(sys.stdlib_module_names)
