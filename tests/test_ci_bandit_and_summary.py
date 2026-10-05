"""Tests for scripts/filter_bandit.py and scripts/job_summary.py."""

import json

from ci_scripts import load

fb = load("filter_bandit")
js = load("job_summary")


def _result(test_id="B602", severity="HIGH", path="mock_hsm/x.py", line=3):
    return {"test_id": test_id, "issue_severity": severity, "filename": path, "line_number": line, "issue_text": "t"}


def test_high_finding_blocks():
    found = fb.blocking({"results": [_result()]}, excepted=set())
    assert [f.key for f in found] == ["B602:mock_hsm/x.py"]


def test_medium_and_low_findings_pass():
    report = {"results": [_result(severity="MEDIUM"), _result(severity="LOW")]}
    assert fb.blocking(report, excepted=set()) == []


def test_excepted_high_finding_is_skipped():
    excepted = {("bandit", "B602:mock_hsm/x.py")}
    assert fb.blocking({"results": [_result()]}, excepted=excepted) == []


def test_bandit_errors_block():
    report = {"results": [], "errors": [{"filename": "a.py", "reason": "syntax error"}]}
    found = fb.blocking(report, excepted=set())
    assert found and "could not scan" in found[0].reason


def test_filter_bandit_main(tmp_path, capsys):
    report = tmp_path / "bandit.json"
    report.write_text(json.dumps({"results": [_result()]}))
    assert fb.main([str(report), "--exceptions", str(tmp_path / "none.toml")]) == 1
    assert "B602" in capsys.readouterr().out


# --- job_summary --------------------------------------------------------------


def _junit(path, body):
    path.write_text(
        f'<?xml version="1.0"?><testsuites><testsuite tests="3" failures="0" errors="0" skipped="1">{body}</testsuite></testsuites>'
    )
    return path


def test_summary_lists_counts_coverage_and_reruns(tmp_path):
    # What pytest 9.1 + pytest-rerunfailures 16.7 actually write for a test
    # that failed once and passed on retry: the testcase appears twice, with no
    # rerun element (captured from a real run).
    junit = _junit(
        tmp_path / "j.xml",
        '<testcase classname="tests.test_a" name="test_flaky" time="0.000"/>'
        '<testcase classname="tests.test_a" name="test_flaky" time="0.000"/>'
        '<testcase classname="tests.test_a" name="test_ok" time="0.000"/>',
    )
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps({"totals": {"percent_covered": 96.37}}))
    floor = tmp_path / ".coverage-floor"
    floor.write_text("95.00\n")
    text = js.ci_summary(python="3.14", sha="abc123", junit=[junit], coverage_json=coverage, coverage_floor=floor)
    assert "3.14" in text
    assert "abc123" in text
    assert "| Passed | 2 |" in text
    assert "| Skipped | 1 |" in text
    assert "96.37%" in text
    assert "95.00%" in text
    assert "tests.test_a::test_flaky" in text


def test_rerun_elements_are_also_recognised(tmp_path):
    junit = _junit(tmp_path / "j.xml", '<testcase classname="t" name="x"><rerunFailure message="m"/></testcase>')
    assert js.reruns([junit]) == ["t::x"]


def test_summary_without_coverage_or_reruns(tmp_path):
    junit = _junit(tmp_path / "j.xml", '<testcase classname="t" name="ok"/>')
    text = js.ci_summary(python="3.10", sha="def", junit=[junit])
    assert "Coverage" not in text
    assert "Reruns: none" in text


def test_summary_never_includes_environment_values(tmp_path, monkeypatch):
    monkeypatch.setenv("HSM_SIGNING_SECRET", "should-never-appear-anywhere-0000")
    junit = _junit(tmp_path / "j.xml", "")
    text = js.ci_summary(python="3.10", sha="def", junit=[junit])
    assert "should-never-appear" not in text
