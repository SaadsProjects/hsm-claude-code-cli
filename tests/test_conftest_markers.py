"""The default-skip rules for the `perf` and `browser` markers (tests/conftest.py)."""

from conftest import skip_reason


def test_plain_run_skips_perf_and_browser():
    assert skip_reason("", {"perf"}) == "timing test; run with -m perf"
    assert skip_reason("", {"browser"}) == "browser test; run with -m browser"
    assert skip_reason("", {"other"}) is None


def test_m_perf_runs_perf_but_still_skips_browser():
    assert skip_reason("perf", {"perf"}) is None
    assert skip_reason("perf", {"browser"}) == "browser test; run with -m browser"


def test_m_browser_runs_browser_tests():
    assert skip_reason("browser", {"browser"}) is None


def test_unrelated_m_expression_still_skips_browser():
    # The team rule is plain `pytest tests/` in CI; an unrelated -m must not
    # pull the Playwright tests in either.
    assert skip_reason("not slow", {"browser"}) == "browser test; run with -m browser"
