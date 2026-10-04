"""
Shared test configuration: keep every test's audit trail in a temporary file.

The mock backend audits gated writes into the file named by HSM_AUDIT_PATH
(mock_hsm/audit.py). Without this, any test that publishes a schedule or
submits a PO -- directly or through an in-process HTTP server -- would write
to the real default file, mock_hsm/audit/audit.jsonl.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mock_hsm import audit, writes


def pytest_configure(config):
    config.addinivalue_line("markers", "perf: timing test against a measurable NFR target")


def pytest_collection_modifyitems(config, items):
    # Timing budgets (fsync p95, render times) depend on the machine, so they
    # don't run by default; a slow disk or busy CI runner must not fail the
    # suite. Run them on purpose with `-m perf`.
    if config.getoption("markexpr"):
        return
    skip = pytest.mark.skip(reason="timing test; run with -m perf")
    for item in items:
        if "perf" in item.keywords:
            item.add_marker(skip)


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
