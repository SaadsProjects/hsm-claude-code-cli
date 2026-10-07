"""The staging monitor workflow, .github/workflows/staging-monitor.yml (unit U1).

Every 30 minutes, and by hand for a practice alert, it runs
scripts/staging_monitor.py against staging and opens or closes the outage
issue. It is the only workflow that may write issues, so these tests pin its
triggers (never a pull request or a privileged trigger), its own
non-cancelling concurrency group, its permissions, the cache steps that carry
state between runs, and that every value reaches the shell through `env:`.
Read as text, like scripts/check_workflows.py, so no YAML parser is needed.
"""

import re
from itertools import pairwise
from pathlib import Path

from ci_scripts import load
from test_postdeploy_workflow import run_commands

cw = load("check_workflows")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "staging-monitor.yml"
CACHE_SHA = "55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
STATE_KEY = "staging-monitor-state-${{ github.run_id }}-${{ github.run_attempt }}"


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


def _steps():
    """Each step's lines, split on the `- ` that starts a step."""
    lines = text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "steps:")
    steps = []
    for line in lines[start + 1 :]:
        if re.match(r"^      - ", line):
            steps.append([line])
        elif steps:
            steps[-1].append(line)
    return ["\n".join(step) for step in steps]


def _step_index(fragment):
    return next(i for i, step in enumerate(_steps()) if fragment in step)


def test_triggers_are_the_schedule_and_manual_dispatch_only():
    _, block = _top_level_block("on")
    triggers = [line.strip().rstrip(":") for line in block if re.match(r"^  \S", line)]
    assert triggers == ["schedule", "workflow_dispatch"]
    body = "\n".join(block)
    assert re.search(r'^    - cron: "7,37 \* \* \* \*"$', body, flags=re.MULTILINE)
    assert len(re.findall(r"cron:", body)) == 1


def test_the_schedule_runs_no_more_often_than_every_5_minutes():
    minutes = re.search(r'cron: "([0-9,]+) ', text()).group(1).split(",")
    values = sorted(int(m) for m in minutes)
    gaps = [b - a for a, b in pairwise(values)] + [60 - values[-1] + values[0]]
    assert min(gaps) >= 5


def test_the_practice_address_is_an_optional_dispatch_input_defaulting_to_empty():
    _, block = _top_level_block("on")
    body = "\n".join(block) + "\n"
    assert re.search(r"\n      practice_address:\n(        .*\n)*?        required: false", body)
    assert re.search(r'\n      practice_address:\n(        .*\n)*?        default: ""', body)
    assert re.findall(r"^      (\w+):$", body, flags=re.MULTILINE) == ["practice_address"]


def test_no_pull_request_push_or_privileged_trigger():
    _, block = _top_level_block("on")
    body = "\n".join(block)
    for trigger in ("push", "pull_request", "pull_request_target", "issues", "issue_comment", "workflow_run"):
        assert not re.search(rf"^  {trigger}:", body, flags=re.MULTILINE), trigger


def test_its_own_concurrency_group_never_cancels_a_running_check():
    _, block = _top_level_block("concurrency")
    body = "\n".join(block)
    assert "group: staging-monitor" in body
    assert "cancel-in-progress: false" in body


def test_permissions_start_from_none_and_only_the_job_may_write_issues():
    head, _ = _top_level_block("permissions")
    assert head == "permissions: {}"
    grants = re.findall(r"^\s+(\S+):\s*(read|write|none)\s*$", text(), flags=re.MULTILINE)
    assert grants == [("contents", "read"), ("issues", "write")]
    assert not re.search(r"\b(read|write)-all\b", text())


def test_one_job_with_a_5_minute_limit():
    _, block = _top_level_block("jobs")
    jobs = [line.strip().rstrip(":") for line in block if re.match(r"^  \S", line)]
    assert jobs == ["monitor"]
    assert re.search(r"^    timeout-minutes: 5$", text(), flags=re.MULTILINE)
    assert re.search(r"^    runs-on: ubuntu-24.04$", text(), flags=re.MULTILINE)


def test_every_checkout_keeps_no_credentials():
    checkouts = [step for step in _steps() if "actions/checkout@" in step]
    assert checkouts
    assert all("persist-credentials: false" in step for step in checkouts)


def test_every_action_is_pinned_and_the_policy_check_passes():
    uses = re.findall(r"uses:\s*(\S+)", text())
    assert uses, "the workflow uses no actions"
    assert all(re.search(r"@[0-9a-f]{40}$", ref) for ref in uses), uses
    assert cw.check_text(WORKFLOW.name, text()) == []


def test_state_is_restored_before_the_monitor_and_saved_after_it_even_on_failure():
    restore = _step_index(f"actions/cache/restore@{CACHE_SHA}")
    monitor = _step_index("scripts/staging_monitor.py")
    save = _step_index(f"actions/cache/save@{CACHE_SHA}")
    assert restore < monitor < save
    steps = _steps()
    for index in (restore, save):
        assert "path: .staging-monitor" in steps[index]
        assert f"key: {STATE_KEY}" in steps[index]
    assert "restore-keys: staging-monitor-state-" in steps[restore]
    assert "if: always()" in steps[save]
    assert "continue-on-error" not in text()


def test_the_monitor_runs_with_its_state_file_and_values_from_env_only():
    commands = run_commands(text())
    assert commands == ["python scripts/staging_monitor.py --state .staging-monitor/state.json"]
    assert [c for c in commands if "${{" in c] == []
    step = _steps()[_step_index("scripts/staging_monitor.py")]
    assert "STAGING_URL: ${{ vars.STAGING_URL }}" in step
    assert "PRACTICE_ADDRESS: ${{ inputs.practice_address }}" in step
    assert "GITHUB_TOKEN: ${{ github.token }}" in step


def test_the_url_input_and_token_appear_only_under_env():
    for expression in ("vars.STAGING_URL", "inputs.practice_address", "github.token"):
        lines = [line.strip() for line in text().splitlines() if expression in line]
        assert len(lines) == 1, (expression, lines)
        assert re.match(r"^[A-Z_]+: \$\{\{ " + re.escape(expression) + r" \}\}$", lines[0]), lines


def test_holds_no_secrets():
    assert "secrets." not in text()
    assert "secrets:" not in text()


def test_installs_nothing_and_starts_no_browser():
    body = text().lower()
    assert "pip install" not in body
    assert "playwright" not in body
    assert "chromium" not in body
