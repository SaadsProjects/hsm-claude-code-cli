"""
Which build is running (FR5.1): the git commit, read from ``.git`` with file
reads only, or a fingerprint of the source when there is no usable ``.git``
(a hosted checkout may lack one).

No ``git`` subprocess is run, so the hosted app needs no git binary and there
is nothing for bandit to flag. Standard library only; never Streamlit.
"""

from __future__ import annotations

import functools
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# SHA-1 (40) or SHA-256 (64) object names, lower-case as git writes them.
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
# A symbolic ref git would write in HEAD: any name under refs/ without the
# characters git forbids in ref names (control characters, space, ~ ^ : ? * [ \).
# A ".." is rejected separately; anything else is malformed, never followed.
_REF = re.compile(r"refs/[^\x00-\x20\x7f~^:?*\[\\]+")

# What the app runs (B2). Files it writes while running (__pycache__, *.pyc,
# the audit trail under mock_hsm/audit/) are left out, so they never change it.
_SOURCE_PACKAGES = ("agents", "dashboard", "mock_hsm", "mcp_server")
_SOURCE_FILES = ("requirements.txt", ".streamlit/config.toml")
_AUDIT_DIR = ("mock_hsm", "audit")


@dataclass(frozen=True)
class BuildInfo:
    kind: str  # "commit" or "fingerprint"
    value: str  # the full SHA or hex digest

    @property
    def label(self) -> str:
        """What the sidebar shows (mockups Screen 3): "Build abc1234" or "Build src-1a2b3c4d"."""
        if self.kind == "commit":
            return f"Build {self.value[:7]}"
        return f"Build src-{self.value[:8]}"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _git_dirs(root: Path) -> tuple[Path, Path]:
    """The gitdir (where HEAD lives) and the common dir (shared refs). A
    ``.git`` file, as in a linked worktree, points at the gitdir."""
    dot_git = root / ".git"
    if dot_git.is_file():
        line = _read(dot_git)
        if not line.startswith("gitdir:"):
            raise ValueError(".git file has no gitdir line")
        gitdir = (root / line[len("gitdir:") :].strip()).resolve()
    else:
        gitdir = dot_git
    commondir = gitdir / "commondir"
    common = (gitdir / _read(commondir)).resolve() if commondir.is_file() else gitdir
    return gitdir, common


def _resolve_ref(ref: str, gitdir: Path, common: Path) -> str | None:
    for base in dict.fromkeys((gitdir, common)):  # loose refs first; a loose ref is newer than a packed one
        loose = base / ref
        if loose.is_file():
            return _read(loose)
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line.startswith(("#", "^")):
                continue
            sha, _, name = line.partition(" ")
            if name.strip() == ref:
                return sha
    return None


def _commit_sha(root: Path) -> str | None:
    """The checked-out commit, or None when ``.git`` is absent or can't be read."""
    try:
        gitdir, common = _git_dirs(root)
        head = _read(gitdir / "HEAD")
        if head.startswith("ref:"):
            ref = head[len("ref:") :].strip()
            if not _REF.fullmatch(ref) or ".." in ref:
                return None
            head = _resolve_ref(ref, gitdir, common) or ""
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return head if _SHA.fullmatch(head) else None


def _is_runtime_output(rel: Path) -> bool:
    return "__pycache__" in rel.parts or rel.parts[: len(_AUDIT_DIR)] == _AUDIT_DIR


def _source_files(root: Path) -> list[Path]:
    files = [root / name for name in _SOURCE_FILES]
    for package in _SOURCE_PACKAGES:
        files += (root / package).rglob("*.py")
    return sorted(
        (f.relative_to(root) for f in files if f.is_file() and not _is_runtime_output(f.relative_to(root))),
        key=Path.as_posix,
    )


def _fingerprint(root: Path) -> str:
    """SHA-256 over the sorted relative paths and bytes of the source files.
    Each path and body is length-prefixed, so moving bytes between files or
    renaming one always changes the digest."""
    digest = hashlib.sha256()
    for rel in _source_files(root):
        body = (root / rel).read_bytes()
        name = rel.as_posix().encode()
        digest.update(len(name).to_bytes(8, "big") + name + len(body).to_bytes(8, "big") + body)
    return digest.hexdigest()


def _source_signature(root: Path) -> tuple:
    """Path, size and modification time of every source file: cheap to read,
    and it changes whenever the source does."""
    signature = []
    for rel in _source_files(root):
        stat = (root / rel).stat()
        signature.append((rel.as_posix(), stat.st_size, stat.st_mtime_ns))
    return tuple(signature)


@functools.lru_cache(maxsize=8)
def _cached_fingerprint(root: Path, signature: tuple) -> str:
    # Keyed on the signature, so a changed file is hashed again; only an
    # unchanged tree reuses the digest.
    return _fingerprint(root)


def build_info(root: Path | str | None = None) -> BuildInfo:
    """The running build, read afresh on every call. A hosted app can pull a
    new commit into a running process, so a cached answer would go stale
    (commit review 1). The commit is a few small file reads; only the
    fingerprint's hashing is reused while the source is unchanged."""
    resolved = Path(REPO_ROOT if root is None else root).resolve()
    sha = _commit_sha(resolved)
    if sha is not None:
        return BuildInfo(kind="commit", value=sha)
    return BuildInfo(kind="fingerprint", value=_cached_fingerprint(resolved, _source_signature(resolved)))


# Lets tests start from an empty fingerprint cache, as a new process would.
build_info.cache_clear = _cached_fingerprint.cache_clear


if __name__ == "__main__":
    # AC5.1.3: the same label the app shows, so a deploy can be matched to a commit.
    print(build_info().label)
