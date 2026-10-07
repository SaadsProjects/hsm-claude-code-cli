"""CI gate: policy checks on GitHub Actions workflow files.

    python scripts/check_workflows.py [.github/workflows]

Complements actionlint (syntax and expressions) with this project's rules:
  - every third-party action is pinned to a full 40-character commit SHA, with
    a `# vX.Y.Z` comment saying which release it is;
  - every workflow declares top-level `permissions`, so jobs start from none;
  - no `${{ secrets.* }}` expression appears on a `run:` line or inside a
    `run:` block (secrets reach steps through `env:` only, never a command line);
  - every `actions/checkout` step sets `persist-credentials: false`, so later
    steps never find the job's token in .git/config;
  - no workflow or job grants `permissions: write-all`.
"""

import re
import sys
from pathlib import Path

_USES = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>[^\s#]+)\s*(?P<comment>#.*)?$")
_PINNED = re.compile(r"@[0-9a-f]{40}$")
_RUN = re.compile(r"^(?P<indent>\s*)-?\s*run:\s*(?P<rest>.*)$")
_SECRET = re.compile(r"\$\{\{\s*secrets\.")
_WRITE_ALL = re.compile(r"""^\s*permissions:\s*["']?write-all["']?\s*(#.*)?$""")
_WITH = re.compile(r"^\s*with:\s*(#.*)?$")
_PERSIST_OFF = re.compile(r"""^\s*persist-credentials:\s*["']?false["']?\s*(#.*)?$""")


def _checkout_keeps_credentials(lines, index):
    """True when the checkout step whose `uses:` is lines[index] lacks
    `persist-credentials: false` under its `with:`. The step runs until a line
    indented no deeper than its `- ` marker; the key counts only inside `with:`,
    since anywhere else (`env:`, say) checkout never reads it."""
    line = lines[index]
    step_indent = _indent(line) if line.lstrip().startswith("-") else _indent(line) - 2
    with_indent = None
    for following in lines[index + 1 :]:
        if not following.strip():
            continue
        if _indent(following) <= step_indent:
            break
        if with_indent is not None and _indent(following) <= with_indent:
            with_indent = None
        if _WITH.match(following):
            with_indent = _indent(following)
        elif with_indent is not None and _PERSIST_OFF.match(following):
            return False
    return True


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

        if _WRITE_ALL.match(line):
            problems.append(f"{name}:{number}: permissions: write-all; grant only the permissions the job needs")

        uses = _USES.match(line)
        if uses:
            ref = uses.group("ref")
            if ref.lower().startswith("actions/checkout@") and _checkout_keeps_credentials(lines, number - 1):
                problems.append(f"{name}:{number}: actions/checkout needs `with: persist-credentials: false`")
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
