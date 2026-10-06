"""The manual post-deploy workflow, .github/workflows/postdeploy.yml (plan K10).

It runs scripts/postdeploy_check.py against a URL someone types in, so it
must start only by hand, hold read-only permissions and no secrets, pin every
action by commit SHA, and pass its inputs to the shell through `env` rather
than splicing them into the command. Read as text, like
scripts/check_workflows.py, so no YAML parser is needed.
"""

import re
from pathlib import Path

from ci_scripts import load

cw = load("check_workflows")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "postdeploy.yml"


def text():
    return WORKFLOW.read_text()


def _top_level_block(name):
    """The lines of a top-level key's block, without the key line."""
    lines = text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{name}:"))
    block = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith(" "):
            break
        block.append(line)
    return lines[start], block


def test_triggers_on_workflow_dispatch_only():
    _, block = _top_level_block("on")
    triggers = [line.strip().rstrip(":") for line in block if re.match(r"^  \S", line)]
    assert triggers == ["workflow_dispatch"]
    body = "\n".join(block)
    assert re.search(r"\n      url:\n(        .*\n)*?        required: true", body + "\n")
    assert re.search(r"\n      timeout:\n(        .*\n)*?        default: \"120\"", body + "\n")


def test_permissions_are_read_only():
    head, _ = _top_level_block("permissions")
    assert head == "permissions: {}"
    # Every grant anywhere in the file: only the job's contents: read.
    grants = re.findall(r"^\s+(\S+):\s*(read|write|none)\s*$", text(), flags=re.MULTILINE)
    assert grants == [("contents", "read")]


def test_holds_no_secrets():
    assert "secrets." not in text()
    assert "secrets:" not in text()


def test_every_action_is_pinned_and_the_policy_check_passes():
    uses = re.findall(r"uses:\s*(\S+)", text())
    assert uses, "the workflow uses no actions"
    assert all(re.search(r"@[0-9a-f]{40}$", ref) for ref in uses), uses
    assert cw.check_text(WORKFLOW.name, text()) == []


def run_commands(workflow_text):
    """Every shell line: inline `run:` values and the lines of `run: |` blocks."""
    commands, block_indent = [], None
    for line in workflow_text.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        if block_indent is not None and (not line.strip() or indent > block_indent):
            commands.append(line.strip())
            continue
        block_indent = None
        match = re.match(r"^\s*-?\s*run:\s*(.*)$", line)
        if match:
            if match.group(1).strip() in ("|", ">", "|-", ">-"):
                block_indent = indent
            else:
                commands.append(match.group(1))
    return commands


def spliced_inputs(workflow_text):
    return [c for c in run_commands(workflow_text) if re.search(r"\$\{\{[^}]*inputs\.", c)]


def test_the_splice_check_catches_an_input_in_a_command():
    assert spliced_inputs("    steps:\n      - run: echo ${{ inputs.url }}\n")
    assert spliced_inputs("      - run: |\n          a\n          b ${{ github.event.inputs.url }}\n")


def test_inputs_reach_the_check_through_env_only():
    body = text()
    assert spliced_inputs(body) == []
    assert "URL: ${{ inputs.url }}" in body
    assert "TIMEOUT: ${{ inputs.timeout }}" in body
    assert 'python scripts/postdeploy_check.py "$URL" --timeout "$TIMEOUT"' in run_commands(body)
