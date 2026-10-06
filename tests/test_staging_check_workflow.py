"""The automatic staging check, .github/workflows/staging-check.yml.

After every merge to main it waits for Streamlit Community Cloud to redeploy
staging, then runs scripts/postdeploy_check.py against the staging URL. Like
the manual postdeploy workflow it holds read-only permissions and no secrets,
pins every action by commit SHA, and passes values to the shell through `env`.
Read as text, like scripts/check_workflows.py, so no YAML parser is needed.
"""

import re
from pathlib import Path

from ci_scripts import load
from test_postdeploy_workflow import run_commands

cw = load("check_workflows")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "staging-check.yml"


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


def test_triggers_on_push_to_main_only():
    _, block = _top_level_block("on")
    triggers = [line.strip().rstrip(":") for line in block if re.match(r"^  \S", line)]
    assert triggers == ["push"]
    assert re.search(r"^    branches: \[main\]$", "\n".join(block), flags=re.MULTILINE)


def test_a_newer_merge_cancels_an_older_check():
    _, block = _top_level_block("concurrency")
    body = "\n".join(block)
    assert "group: staging-check" in body
    assert "cancel-in-progress: true" in body


def test_permissions_are_read_only():
    head, _ = _top_level_block("permissions")
    assert head == "permissions: {}"
    grants = re.findall(r"^\s+(\S+):\s*(read|write|none)\s*$", text(), flags=re.MULTILINE)
    assert grants == [("contents", "read")]
    # The regex above can't see a blanket grant such as `permissions: write-all`.
    assert not re.search(r"\b(read|write)-all\b", text())


def test_the_checkout_keeps_no_credentials():
    assert "persist-credentials: false" in text()


def test_the_job_limit_covers_the_wait_and_the_check():
    # Install (~4 min) + sleep 180 s + check timeout 600 s must fit.
    limit = re.search(r"^    timeout-minutes: (\d+)$", text(), flags=re.MULTILINE)
    assert limit, "the job has no timeout-minutes"
    assert int(limit.group(1)) * 60 >= 4 * 60 + 180 + 600


def test_holds_no_secrets():
    assert "secrets." not in text()
    assert "secrets:" not in text()


def test_every_action_is_pinned_and_the_policy_check_passes():
    uses = re.findall(r"uses:\s*(\S+)", text())
    assert uses, "the workflow uses no actions"
    assert all(re.search(r"@[0-9a-f]{40}$", ref) for ref in uses), uses
    assert cw.check_text(WORKFLOW.name, text()) == []


def test_the_url_comes_from_the_repository_variable_through_env():
    body = text()
    assert "URL: ${{ vars.STAGING_URL }}" in body
    assert [c for c in run_commands(body) if "${{" in c] == []


def test_refuses_to_run_without_a_staging_url():
    commands = run_commands(text())
    assert any('[ -n "$URL" ]' in c for c in commands), commands
    assert any("STAGING_URL" in c for c in commands if "echo" in c), commands


def test_waits_for_the_redeploy_before_checking():
    commands = run_commands(text())
    check = 'python scripts/postdeploy_check.py "$URL" --timeout 600'
    assert check in commands
    assert "sleep 180" in commands
    assert commands.index("sleep 180") < commands.index(check)
