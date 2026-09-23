"""
Unit tests for the mock Labor Rules Engine (mock_hsm/server.py's
/labor/rules/validate handler), called directly -- no HTTP server needed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mock_hsm.server import ApiError, labor_rules_validate


def _rules_hit(*shifts):
    _, result = labor_rules_validate({}, None, {}, {"jurisdiction": "GA", "shifts": list(shifts)})
    return sorted(v["rule"] for v in result["violations"])


def _shift(date, start, end, emp="emp_1"):
    return {"employee_id": emp, "date": date, "role": "JC-COOK", "start_time": start, "end_time": end}


def test_compliant_week_has_no_violations():
    week = [_shift(f"2026-10-0{d}", "09:00", "17:00") for d in range(1, 6)]
    assert _rules_hit(*week) == []


def test_overnight_shift_counts_hours_past_midnight():
    # 20:00-08:00 is 12h, not -12h.
    assert _rules_hit(_shift("2026-10-01", "20:00", "08:00")) == ["max_shift_length"]


def test_overnight_shifts_count_toward_weekly_overtime():
    week = [_shift(f"2026-10-0{d}", "22:00", "07:00") for d in range(1, 6)]  # 5 x 9h = 45h
    assert "weekly_overtime" in _rules_hit(*week)


def test_same_day_shifts_capped_by_daily_total():
    assert _rules_hit(_shift("2026-10-01", "00:00", "09:00"),
                      _shift("2026-10-01", "10:00", "19:00")) == ["max_daily_hours"]


def test_short_split_shift_is_allowed():
    assert _rules_hit(_shift("2026-10-01", "11:00", "14:00"),
                      _shift("2026-10-01", "17:00", "21:00")) == []


def test_overlapping_shifts_flagged():
    assert _rules_hit(_shift("2026-10-01", "09:00", "13:00"),
                      _shift("2026-10-01", "12:00", "15:00")) == ["overlapping_shifts"]


def test_overnight_shift_rest_measured_from_real_end():
    # Ends 06:00 on the 2nd; next starts 10:00 on the 2nd -> 4h rest.
    assert _rules_hit(_shift("2026-10-01", "22:00", "06:00"),
                      _shift("2026-10-02", "10:00", "16:00")) == ["min_rest_between_shifts"]


def test_consecutive_days():
    week = [_shift(f"2026-10-0{d}", "10:00", "14:00") for d in range(1, 8)]  # 7 days x 4h
    assert _rules_hit(*week) == ["max_consecutive_days"]


@pytest.mark.parametrize("shifts", [
    [_shift("2026-10-01", "9am", "17:00")],
    # UTC offsets would let a 12h clock-time shift validate as 8h absolute.
    [_shift("2026-10-01", "08:00+00:00", "20:00+04:00")],
    [_shift("2026-10-01", "09:00:00", "17:00")],
    [5],
    [None],
    None,
])
def test_malformed_input_rejected(shifts):
    with pytest.raises(ApiError) as exc:
        labor_rules_validate({}, None, {}, {"jurisdiction": "GA", "shifts": shifts})
    assert exc.value.status == 400
