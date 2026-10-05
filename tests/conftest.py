"""
Shared test configuration: a throwaway signing secret per run, and every
test's audit trail in a temporary file.

There is no default signing secret anywhere (mock_hsm/auth.py), so this
module generates one per run and puts it in the environment at import time,
before any mock_hsm import, server or subprocess; subprocess tests inherit
it. It always overwrites, so a developer's own shell secret is never used.

The mock backend audits gated writes into the file named by HSM_AUDIT_PATH
(mock_hsm/audit.py). Without this, any test that publishes a schedule or
submits a PO -- directly or through an in-process HTTP server -- would write
to the real default file, mock_hsm/audit/audit.jsonl.
"""

import os
import secrets
import sys
from pathlib import Path

import pytest


def new_test_secret():
    """A fresh 43-character URL-safe value: 32 random bytes, comfortably over the 32-byte minimum."""
    return secrets.token_urlsafe(32)


os.environ["HSM_SIGNING_SECRET"] = new_test_secret()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mock_hsm import audit, writes  # noqa: E402 -- the secret must be in the environment before mock_hsm loads


def pytest_configure(config):
    config.addinivalue_line("markers", "perf: timing test against a measurable NFR target")
    config.addinivalue_line("markers", "browser: needs Playwright and Chromium; run with -m browser")


def skip_reason(markexpr, keywords):
    """Why a test is skipped by default, or None.

    Timing budgets (fsync p95, render times) depend on the machine, so `perf`
    tests don't run by default; a slow disk or busy CI runner must not fail the
    suite. Any `-m` expression turns that default off. `browser` tests need
    Playwright and Chromium, which plain CI doesn't install, so they run only
    when the `-m` expression names them (`-m browser`).
    """
    if "browser" in keywords and "browser" not in (markexpr or ""):
        return "browser test; run with -m browser"
    if "perf" in keywords and not markexpr:
        return "timing test; run with -m perf"
    return None


def pytest_collection_modifyitems(config, items):
    markexpr = config.getoption("markexpr")
    for item in items:
        reason = skip_reason(markexpr, item.keywords)
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(scope="session", autouse=True)
def _session_audit_trail(tmp_path_factory):
    # Session-scoped autouse fixtures are set up before module-scoped ones, so
    # a module-scoped server fixture can never lazily initialize the module
    # against the default path before the per-test fixture below runs.
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(audit.ENV_PATH, str(tmp_path_factory.mktemp("audit-session") / "audit.jsonl"))
        audit.configure()
        yield


@pytest.fixture(autouse=True)
def audit_path(monkeypatch, tmp_path):
    """Per-test audit file (NFR5.1): the default audit file is never touched."""
    path = tmp_path / "audit" / "audit.jsonl"
    monkeypatch.setenv(audit.ENV_PATH, str(path))
    audit.configure()
    return path


@pytest.fixture(autouse=True)
def write_test_reset():
    """WriteTestReset (NFR5.2): after each test, clear U1's sessions, counters,
    request records, added metadata and id counters, and remove every record
    added to the shared ``db`` collections, so no test (including the
    in-process MCP and dashboard tests) sees another test's writes."""
    yield
    writes.reset_for_tests()
