"""Tests for scripts/check_workflows.py (workflow policy lint)."""

import pytest
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
        with:
          fetch-depth: 0
          persist-credentials: false
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


CHECKOUT_WITH = """          fetch-depth: 0
          persist-credentials: false
"""


def test_checkout_without_persist_credentials_fails():
    text = GOOD.replace("        with:\n" + CHECKOUT_WITH, "")
    problems = cw.check_text("ci.yml", text)
    assert any("persist-credentials: false" in p and ":12:" in p for p in problems), problems


def test_checkout_whose_with_block_lacks_persist_credentials_fails():
    text = GOOD.replace("          persist-credentials: false\n", "")
    assert any("persist-credentials: false" in p for p in cw.check_text("ci.yml", text))


def test_checkout_that_keeps_credentials_fails():
    text = GOOD.replace("persist-credentials: false", "persist-credentials: true")
    assert any("persist-credentials: false" in p for p in cw.check_text("ci.yml", text))


def test_a_named_checkout_step_is_checked_too():
    named = GOOD.replace(
        f"      - uses: actions/checkout@{SHA} # v4.2.2\n        with:\n" + CHECKOUT_WITH,
        f"      - name: Check out\n        uses: actions/checkout@{SHA} # v4.2.2\n",
    )
    assert any("persist-credentials: false" in p for p in cw.check_text("ci.yml", named))
    fixed = named.replace("# v4.2.2\n", "# v4.2.2\n        with:\n          persist-credentials: false\n")
    assert cw.check_text("ci.yml", fixed) == []


def test_persist_credentials_on_a_later_step_does_not_count():
    text = GOOD.replace("          persist-credentials: false\n", "") + (
        f"      - uses: some/action@{SHA} # v1\n        with:\n          persist-credentials: false\n"
    )
    assert any("persist-credentials: false" in p for p in cw.check_text("ci.yml", text))


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("permissions: write-all", id="top-level"),
        pytest.param("permissions: 'write-all'", id="quoted"),
        pytest.param('    permissions: "write-all"', id="job-level"),
    ],
)
def test_write_all_permissions_fail(line):
    if line.startswith(" "):
        text = GOOD.replace("    permissions:\n      contents: read\n", line + "\n")
    else:
        text = GOOD.replace("permissions: {}", line)
    assert any("write-all" in p for p in cw.check_text("ci.yml", text))


def test_persist_credentials_outside_the_with_block_does_not_count():
    text = GOOD.replace("        with:\n          fetch-depth: 0\n", "        env:\n          fetch-depth: 0\n")
    assert any("persist-credentials: false" in p for p in cw.check_text("ci.yml", text))


def test_an_expression_is_not_a_literal_false():
    text = GOOD.replace("persist-credentials: false", "persist-credentials: ${{ false }}")
    assert any("persist-credentials: false" in p for p in cw.check_text("ci.yml", text))


def test_the_checkout_rule_ignores_the_case_of_the_action_name():
    text = GOOD.replace("actions/checkout@", "Actions/Checkout@").replace("          persist-credentials: false\n", "")
    assert any("persist-credentials: false" in p for p in cw.check_text("ci.yml", text))


def test_write_all_with_a_trailing_comment_still_fails():
    text = GOOD.replace("permissions: {}", "permissions: write-all  # temporary")
    assert any("write-all" in p for p in cw.check_text("ci.yml", text))


def test_persist_credentials_under_a_key_after_with_does_not_count():
    # The with: block ends at its next sibling key, so the key under env: is
    # not read by checkout even though a with: block came first.
    text = GOOD.replace(
        "        with:\n          fetch-depth: 0\n          persist-credentials: false\n",
        "        with:\n          fetch-depth: 0\n        env:\n          persist-credentials: false\n",
    )
    assert any("persist-credentials: false" in p for p in cw.check_text("ci.yml", text))


def test_a_trailing_comment_on_the_with_line_is_allowed():
    text = GOOD.replace(
        "        with:\n          fetch-depth: 0\n", "        with:  # full history\n          fetch-depth: 0\n"
    )
    assert cw.check_text("ci.yml", text) == []
