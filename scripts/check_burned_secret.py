"""CI gate: no tracked file may contain the burned token-signing secret.

    python scripts/check_burned_secret.py

The old signing secret was committed to this public repository, so it is
burned: no environment may use it again. This check reads every tracked
non-binary file, takes every window of the burned value's length inside each
run of token characters, and compares each window's SHA-256 with the burned
value's digest. The value itself never has to appear here, and it is found even
when embedded in a longer token (`MOCK_<value>`, `<value>_v2`).
"""

import fnmatch
import hashlib
import re
import subprocess
import sys

BURNED_SECRET_SHA256 = "2afa3c5c080b9584be9548e7d8ac9ac6bc2868c33bf3bf058307f09022a76907"
BURNED_SECRET_LENGTH = 37

# Permanent: the gitleaks allowlist must name the value, and AI-DLC records are
# audit evidence that quote the (already public) value and must not be rewritten.
PERMANENT_EXCLUSIONS = (".gitleaks.toml", "aidlc/spaces/*/intents/**")

# Temporary: removed by the follow-up change that takes the literal out of the
# file. Each entry fails the check once its file no longer holds the value, so
# an exclusion can't outlive the literal.
TEMPORARY_EXCLUSIONS = ("mock_hsm/auth.py",)

_TOKEN_CHARS = re.compile(r"[A-Za-z0-9_-]+")
_BINARY_SNIFF_BYTES = 8192


def candidates(text, length=BURNED_SECRET_LENGTH):
    windows = []
    for run in _TOKEN_CHARS.findall(text):
        windows += [run[i : i + length] for i in range(len(run) - length + 1)]
    return windows


def _contains(text, digest, length):
    return any(hashlib.sha256(window.encode()).hexdigest() == digest for window in candidates(text, length))


def _excluded(path, patterns):
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def is_binary(data):
    return b"\0" in data[:_BINARY_SNIFF_BYTES]


def scan(files, digest=BURNED_SECRET_SHA256, length=BURNED_SECRET_LENGTH, temporary_exclusions=TEMPORARY_EXCLUSIONS):
    """``files`` maps repo-relative paths to their text; returns problem lines."""
    problems = [
        f"{path}: temporary exclusion names a file that is no longer tracked; remove it from TEMPORARY_EXCLUSIONS"
        for path in temporary_exclusions
        if path not in files
    ]
    for path in sorted(files):
        found = _contains(files[path], digest, length)
        if path in temporary_exclusions:
            if not found:
                problems.append(
                    f"{path}: temporary exclusion no longer needed (the burned value is gone); "
                    "remove it from TEMPORARY_EXCLUSIONS"
                )
            continue
        if _excluded(path, PERMANENT_EXCLUSIONS):
            continue
        if found:
            problems.append(f"{path}: contains the burned signing secret")
    return problems


def tracked_text_files():
    listing = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    files = {}
    for raw in filter(None, listing.split(b"\0")):
        path = raw.decode()
        try:
            with open(path, "rb") as f:
                data = f.read()
        except (FileNotFoundError, IsADirectoryError):
            continue  # deleted in the working tree but not yet from the index, or a submodule
        if not is_binary(data):
            files[path] = data.decode("utf-8", errors="replace")
    return files


def main():
    problems = scan(tracked_text_files())
    for problem in problems:
        print(f"burned secret: {problem}")
    if not problems:
        print("burned secret: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
