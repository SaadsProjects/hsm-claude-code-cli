"""Tests for scripts/check_workflows.py (workflow policy lint)."""

from ci_scripts import load

cw = load("check_workflows")

SHA = "a" * 40

GOOD = f"""\
name: ci
on: [push]
permissions: {{}}
jobs:
  lint:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
    env:
      TOKEN: ${{{{ secrets.SOME_TOKEN }}}}
    steps:
      - uses: actions/checkout@{SHA} # v4.2.2
      - uses: ./.github/actions/local
      - run: echo "$TOKEN" | wc -c
      - name: multi
        run: |
          ruff check .
          ruff format --check .
"""


def test_good_workflow_passes():
    assert cw.check_text("ci.yml", GOOD) == []


def test_unpinned_action_fails():
    text = GOOD.replace(f"actions/checkout@{SHA}", "actions/checkout@v4")
    problems = cw.check_text("ci.yml", text)
    assert any("not pinned to a full commit SHA" in p and "actions/checkout@v4" in p for p in problems)


def test_pinned_action_without_version_comment_fails():
    text = GOOD.replace(" # v4.2.2", "")
    assert any("version comment" in p for p in cw.check_text("ci.yml", text))


def test_missing_top_level_permissions_fails():
    text = GOOD.replace("permissions: {}\n", "")
    assert any("top-level permissions" in p for p in cw.check_text("ci.yml", text))


def test_secret_on_inline_run_line_fails():
    text = GOOD.replace('echo "$TOKEN" | wc -c', "curl -H 'x: ${{ secrets.SOME_TOKEN }}' https://x")
    assert any("secret used on a run: line" in p for p in cw.check_text("ci.yml", text))


def test_secret_inside_run_block_fails():
    text = GOOD.replace("ruff format --check .", "echo ${{ secrets.SOME_TOKEN }}")
    assert any("secret used on a run: line" in p for p in cw.check_text("ci.yml", text))


def test_secret_after_run_block_ends_is_allowed():
    text = GOOD + "      - uses: some/action@" + SHA + " # v1\n        with:\n          token: ${{ secrets.T }}\n"
    assert cw.check_text("ci.yml", text) == []


def test_promote_workflow_needs_main_ref_guard():
    problems = cw.check_text("promote.yml", GOOD)
    assert any("refs/heads/main" in p for p in problems)
    guarded = GOOD + '      - run: test "$GITHUB_REF" = refs/heads/main\n'
    assert cw.check_text("promote.yml", guarded) == []
