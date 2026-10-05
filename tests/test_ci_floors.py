"""Tests for the ratcheting CI floors: scripts/test_floor.py and scripts/coverage_gate.py."""

import json

import pytest
from ci_scripts import load

floors = load("floor_ratchet")
test_floor = load("test_floor")
coverage_gate = load("coverage_gate")


def _junit(path, tests=10, failures=0, errors=0, skipped=0):
    path.write_text(
        f'<?xml version="1.0"?><testsuites><testsuite name="pytest" tests="{tests}" '
        f'failures="{failures}" errors="{errors}" skipped="{skipped}"></testsuite></testsuites>'
    )
    return path


# --- floor_ratchet ---------------------------------------------------------


def test_read_floor_parses_a_number(tmp_path):
    f = tmp_path / ".test-floor"
    f.write_text("745\n")
    assert floors.read_floor(f) == 745.0


@pytest.mark.parametrize("text", ["", "abc", "-1", "nan"])
def test_read_floor_rejects_malformed_values(tmp_path, text):
    f = tmp_path / ".floor"
    f.write_text(text)
    with pytest.raises(floors.FloorError):
        floors.read_floor(f)


def test_read_floor_missing_file_is_an_error(tmp_path):
    with pytest.raises(floors.FloorError):
        floors.read_floor(tmp_path / "absent")


def test_lowered_floor_is_detected():
    assert floors.lowered(base=745.0, current=744.0)
    assert not floors.lowered(base=745.0, current=745.0)
    assert not floors.lowered(base=745.0, current=800.0)
    assert not floors.lowered(base=None, current=10.0)  # file is new on this branch


# --- test_floor -------------------------------------------------------------


def test_counts_passed_tests_across_files(tmp_path):
    a = _junit(tmp_path / "a.xml", tests=10, skipped=2)
    b = _junit(tmp_path / "b.xml", tests=5, skipped=1)
    counts = test_floor.count([a, b])
    assert counts.passed == 12
    assert counts.failed == 0


def test_passes_at_the_floor(tmp_path):
    junit = _junit(tmp_path / "j.xml", tests=750, skipped=5)
    assert test_floor.check([junit], floor=745) == []


def test_fails_below_the_floor(tmp_path):
    junit = _junit(tmp_path / "j.xml", tests=744)
    problems = test_floor.check([junit], floor=745)
    assert any("744 passed" in p and "745" in p for p in problems)


def test_fails_on_any_failure_or_error(tmp_path):
    junit = _junit(tmp_path / "j.xml", tests=800, failures=1, errors=1)
    problems = test_floor.check([junit], floor=745)
    assert any("2 failed" in p for p in problems)


def test_unreadable_junit_is_an_error(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("not xml")
    with pytest.raises(floors.FloorError):
        test_floor.count([bad])


# --- coverage_gate ----------------------------------------------------------


def _coverage(path, percent):
    path.write_text(json.dumps({"totals": {"percent_covered": percent}}))
    return path


def test_coverage_at_or_above_floor_passes(tmp_path):
    report = _coverage(tmp_path / "coverage.json", 96.4)
    assert coverage_gate.check(report, floor=95.0) == []


def test_coverage_below_floor_fails(tmp_path):
    report = _coverage(tmp_path / "coverage.json", 94.99)
    problems = coverage_gate.check(report, floor=95.0)
    assert any("94.99" in p and "95.00" in p for p in problems)


def test_eighty_percent_applies_once_floor_reaches_it(tmp_path):
    # A floor below 80 is a ratchet only; at 80 or more the 80% gate is on too.
    report = _coverage(tmp_path / "coverage.json", 79.0)
    assert coverage_gate.check(report, floor=70.0) == []
    assert coverage_gate.gate_80_on(80.0)
    assert not coverage_gate.gate_80_on(79.99)


def test_malformed_coverage_report_is_an_error(tmp_path):
    bad = tmp_path / "coverage.json"
    bad.write_text("{}")
    with pytest.raises(floors.FloorError):
        coverage_gate.check(bad, floor=80.0)


def test_main_reports_a_lowered_floor_file(tmp_path, monkeypatch, capsys):
    floor_file = tmp_path / ".coverage-floor"
    floor_file.write_text("90.00\n")
    report = _coverage(tmp_path / "coverage.json", 99.0)
    monkeypatch.setattr(floors, "floor_at_ref", lambda ref, path: 95.0)
    code = coverage_gate.main(
        ["--coverage-json", str(report), "--floor-file", str(floor_file), "--base-ref", "origin/main"]
    )
    assert code == 1
    assert "lowered" in capsys.readouterr().out
