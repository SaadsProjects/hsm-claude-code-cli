"""CI gate: policy checks on GitHub Actions workflow files.

    python scripts/check_workflows.py [.github/workflows]

Complements actionlint (syntax and expressions) with this project's rules:
  - every third-party action is pinned to a full 40-character commit SHA, with
    a `# vX.Y.Z` comment saying which release it is;
  - every workflow declares top-level `permissions`, so jobs start from none;
  - no `${{ secrets.* }}` expression appears on a `run:` line or inside a
    `run:` block (secrets reach steps through `env:` only, never a command line).
"""

import re
import sys
from pathlib import Path

_USES = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>[^\s#]+)\s*(?P<comment>#.*)?$")
_PINNED = re.compile(r"@[0-9a-f]{40}$")
_RUN = re.compile(r"^(?P<indent>\s*)-?\s*run:\s*(?P<rest>.*)$")
_SECRET = re.compile(r"\$\{\{\s*secrets\.")


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def check_text(name, text):
    problems = []
    lines = text.splitlines()

    if not any(line.startswith("permissions:") for line in lines):
        problems.append(f"{name}: missing top-level permissions (use `permissions: {{}}` and grant per job)")

    run_block_indent = None
    for number, line in enumerate(lines, start=1):
        if run_block_indent is not None:
            if line.strip() and _indent(line) <= run_block_indent:
                run_block_indent = None
            elif _SECRET.search(line):
                problems.append(f"{name}:{number}: secret used on a run: line; pass it through env: instead")
                continue

        uses = _USES.match(line)
        if uses:
            ref = uses.group("ref")
            if not ref.startswith(("./", "docker://")):
                if not _PINNED.search(ref):
                    problems.append(f"{name}:{number}: {ref} is not pinned to a full commit SHA")
                elif not uses.group("comment"):
                    problems.append(f"{name}:{number}: {ref} needs a version comment (# vX.Y.Z)")

        run = _RUN.match(line)
        if run:
            rest = run.group("rest").strip()
            if _SECRET.search(rest):
                problems.append(f"{name}:{number}: secret used on a run: line; pass it through env: instead")
            if rest in ("|", ">", "|-", ">-", "|+", ">+"):
                run_block_indent = _indent(line) + (len(line.lstrip(" ")) - len(line.lstrip(" -")))

    return problems


def main(argv=None):
    directory = Path((argv or sys.argv[1:] or [".github/workflows"])[0])
    files = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    if not files:
        print(f"workflow check: no workflow files in {directory}")
        return 1
    problems = []
    for path in files:
        problems += check_text(path.name, path.read_text())
    for problem in problems:
        print(f"workflow check: {problem}")
    if not problems:
        print(f"workflow check: ok ({len(files)} files)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
