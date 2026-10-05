"""Tests for the dependency-audit gate: scripts/check_exceptions.py,
scripts/filter_audit.py and scripts/run_pip_audit.sh."""

import datetime as dt
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from ci_scripts import load

exc = load("check_exceptions")
fa = load("filter_audit")

TODAY = dt.date(2026, 10, 4)
ROOT = Path(__file__).resolve().parent.parent


# --- check_exceptions -------------------------------------------------------


def _exceptions(tmp_path, body):
    path = tmp_path / "security-exceptions.toml"
    path.write_text(body)
    return path


def _entry(id_="GHSA-aaaa", tool="pip-audit", added="2026-09-01", expires="2026-11-01", reason="no fix yet"):
    return f'[[exception]]\nid = "{id_}"\ntool = "{tool}"\nreason = "{reason}"\nadded = {added}\nexpires = {expires}\n'


def test_no_file_means_no_exceptions(tmp_path):
    assert exc.load_exceptions(tmp_path / "absent.toml", today=TODAY) == (set(), [], [])


def test_valid_entry_is_accepted(tmp_path):
    path = _exceptions(tmp_path, _entry())
    ids, problems, warnings = exc.load_exceptions(path, today=TODAY)
    assert ids == {("pip-audit", "GHSA-aaaa")}
    assert problems == []
    assert warnings == []


def test_expired_entry_fails(tmp_path):
    path = _exceptions(tmp_path, _entry(expires="2026-10-03"))
    _, problems, _ = exc.load_exceptions(path, today=TODAY)
    assert any("expired" in p for p in problems)


def test_entry_longer_than_90_days_fails(tmp_path):
    path = _exceptions(tmp_path, _entry(added="2026-09-01", expires="2026-12-15"))
    _, problems, _ = exc.load_exceptions(path, today=TODAY)
    assert any("90 days" in p for p in problems)


def test_entry_added_in_the_future_fails(tmp_path):
    # A future `added` date would let `expires` sit years away while still
    # being "90 days after added".
    path = _exceptions(tmp_path, _entry(added="2029-01-01", expires="2029-03-01"))
    ids, problems, _ = exc.load_exceptions(path, today=TODAY)
    assert any("added date is in the future" in p for p in problems)
    assert ids == set()


def test_entry_expiring_more_than_90_days_from_today_fails(tmp_path):
    path = _exceptions(tmp_path, _entry(added="2026-10-04", expires="2027-01-03"))
    _, problems, _ = exc.load_exceptions(path, today=TODAY)
    assert any("90 days" in p for p in problems)


def test_invalid_entry_is_not_accepted(tmp_path):
    path = _exceptions(tmp_path, _entry(expires="2026-10-03"))
    ids, _, _ = exc.load_exceptions(path, today=TODAY)
    assert ids == set()


def test_entry_missing_reason_fails(tmp_path):
    path = _exceptions(tmp_path, _entry(reason=""))
    _, problems, _ = exc.load_exceptions(path, today=TODAY)
    assert any("reason" in p for p in problems)


def test_unknown_tool_fails(tmp_path):
    path = _exceptions(tmp_path, _entry(tool="npm"))
    _, problems, _ = exc.load_exceptions(path, today=TODAY)
    assert any("tool" in p for p in problems)


def test_entry_expiring_soon_warns(tmp_path):
    path = _exceptions(tmp_path, _entry(expires="2026-10-10"))
    _, problems, warnings = exc.load_exceptions(path, today=TODAY)
    assert problems == []
    assert any("expires" in w for w in warnings)


def test_malformed_toml_fails(tmp_path):
    path = _exceptions(tmp_path, "[[exception]\n")
    _, problems, _ = exc.load_exceptions(path, today=TODAY)
    assert problems


# --- filter_audit -----------------------------------------------------------


def _report(*vulns):
    return {"dependencies": [{"name": "pkg", "version": "1.0", "vulns": list(vulns)}]}


def _vuln(id_="PYSEC-1", aliases=()):
    return {"id": id_, "aliases": list(aliases), "fix_versions": ["1.1"]}


def test_label_high_blocks():
    fetch = {"PYSEC-1": {"database_specific": {"severity": "HIGH"}}}.get
    blocking = fa.blocking(_report(_vuln()), fetch=fetch, excepted=set())
    assert [b.id for b in blocking] == ["PYSEC-1"]


def test_label_moderate_passes():
    fetch = {"PYSEC-1": {"database_specific": {"severity": "MODERATE"}}}.get
    assert fa.blocking(_report(_vuln()), fetch=fetch, excepted=set()) == []


def test_label_from_an_alias_is_used():
    records = {"PYSEC-1": {}, "GHSA-x": {"database_specific": {"severity": "CRITICAL"}}}
    blocking = fa.blocking(_report(_vuln(aliases=["GHSA-x"])), fetch=records.get, excepted=set())
    assert len(blocking) == 1


def test_cvss_vector_scores_the_severity():
    high = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"  # 9.8
    low = "CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N"  # 1.8
    for vector, expect in ((high, 1), (low, 0)):
        record = {"severity": [{"type": "CVSS_V3", "score": vector}]}
        blocking = fa.blocking(_report(_vuln()), fetch=lambda _id, r=record: r, excepted=set())
        assert len(blocking) == expect


def test_worst_label_across_aliases_wins():
    records = {
        "PYSEC-1": {"database_specific": {"severity": "MODERATE"}},
        "GHSA-x": {"database_specific": {"severity": "CRITICAL"}},
    }
    blocking = fa.blocking(_report(_vuln(aliases=["GHSA-x"])), fetch=records.get, excepted=set())
    assert len(blocking) == 1
    assert "CRITICAL" in blocking[0].reason


def test_high_cvss_blocks_even_with_a_low_label():
    record = {
        "database_specific": {"severity": "LOW"},
        "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}],
    }
    blocking = fa.blocking(_report(_vuln()), fetch=lambda _id: record, excepted=set())
    assert len(blocking) == 1


def test_malformed_cvss_vector_is_reported_not_a_crash():
    record = {"severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/garbage"}]}
    blocking = fa.blocking(_report(_vuln()), fetch=lambda _id: record, excepted=set())
    assert blocking[0].reason == "no severity found (fail closed)"


def test_missing_alias_is_skipped_when_the_primary_record_scores():
    records = {"PYSEC-1": {"database_specific": {"severity": "MODERATE"}}}
    # fetch returns None for an id OSV doesn't know (HTTP 404)
    assert fa.blocking(_report(_vuln(aliases=["GHSA-missing"])), fetch=records.get, excepted=set()) == []


@pytest.mark.parametrize(("code", "expect_none"), [(404, True), (500, False)])
def test_osv_fetch_treats_only_404_as_unknown(monkeypatch, code, expect_none):
    import urllib.error

    def fake_urlopen(url, timeout):
        raise urllib.error.HTTPError(url, code, "x", {}, None)

    monkeypatch.setattr(fa.urllib.request, "urlopen", fake_urlopen)
    if expect_none:
        assert fa.osv_fetch("GHSA-x") is None
    else:
        with pytest.raises(urllib.error.HTTPError):
            fa.osv_fetch("GHSA-x")


def test_no_severity_fails_closed():
    blocking = fa.blocking(_report(_vuln()), fetch=lambda _id: {}, excepted=set())
    assert blocking[0].reason == "no severity found (fail closed)"


def test_lookup_error_fails_closed():
    def boom(_id):
        raise OSError("network down")

    blocking = fa.blocking(_report(_vuln()), fetch=boom, excepted=set())
    assert "lookup failed" in blocking[0].reason


def test_excepted_vulnerability_is_skipped():
    fetch = {"PYSEC-1": {"database_specific": {"severity": "HIGH"}}}.get
    assert fa.blocking(_report(_vuln()), fetch=fetch, excepted={("pip-audit", "PYSEC-1")}) == []


def test_excepted_by_alias_is_skipped():
    fetch = {"PYSEC-1": {"database_specific": {"severity": "HIGH"}}}.get
    report = _report(_vuln(aliases=["GHSA-x"]))
    assert fa.blocking(report, fetch=fetch, excepted={("pip-audit", "GHSA-x")}) == []


# --- run_pip_audit.sh -------------------------------------------------------


@pytest.mark.parametrize(("stub_exit", "expected"), [(0, 0), (1, 0), (2, 2)])
def test_wrapper_tolerates_only_exit_code_one(tmp_path, stub_exit, expected):
    stub = tmp_path / "pip-audit"
    stub.write_text(f"#!/bin/sh\necho '{{}}' > \"$OUT\"\nexit {stub_exit}\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PIP_AUDIT_BIN": str(stub), "OUT": str(tmp_path / "audit.json")}
    result = subprocess.run(
        ["sh", str(ROOT / "scripts" / "run_pip_audit.sh"), str(tmp_path / "audit.json")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    if stub_exit == 2:
        assert "exit code 2" in result.stdout + result.stderr


def test_filter_main_reads_report_and_reports_blockers(tmp_path, capsys, monkeypatch):
    report = tmp_path / "audit.json"
    report.write_text(json.dumps(_report(_vuln())))
    monkeypatch.setattr(fa, "osv_fetch", lambda _id: {"database_specific": {"severity": "HIGH"}})
    code = fa.main([str(report), "--exceptions", str(tmp_path / "none.toml")])
    assert code == 1
    assert "PYSEC-1" in capsys.readouterr().out
