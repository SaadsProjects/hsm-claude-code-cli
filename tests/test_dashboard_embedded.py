"""
Dashboard side of unit U2: the dashboard uses the backend running in its own
process (``mock_hsm/embedded.py``), never ``HSM_BASE_URL``.

``session.client_for`` is tested directly. The app is rendered with
``streamlit.testing.v1.AppTest``, which runs the script in this process, so
the embedded backend it starts is this module's. The ``holder`` fixture
resets that backend before and after each test.
"""

import ast
import logging
import os
import sys
import urllib.error
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hsm_client import HsmClient
from dashboard import session
from mock_hsm import embedded
from mock_hsm.auth import mint_token

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP = str(PROJECT_ROOT / "dashboard" / "app.py")
RM = "user_rm_midtown"
SCREEN_4 = "The demo backend didn't start. Reload the page or try again later."


@pytest.fixture(autouse=True)
def holder():
    embedded.reset_for_tests()
    yield
    embedded.reset_for_tests()


# --------------------------------------------------- client address (R4, BR4.1)


def test_client_for_takes_its_address_from_the_live_embedded_backend():
    handle = embedded.start()
    client = session.client_for(RM)
    assert client.base_url == handle.address
    assert [s["site_id"] for s in client.get_sites()] == ["site_001"]


def test_client_for_without_a_live_backend_raises_and_never_starts_one():
    with pytest.raises(embedded.BackendNotRunning, match="embedded backend is not running"):
        session.client_for(RM)
    assert embedded.current() is None and embedded.bound_address() is None


def test_no_dashboard_module_uses_hsm_base_url():
    offenders = []
    for path in sorted((PROJECT_ROOT / "dashboard").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            named = (
                (isinstance(node, ast.ImportFrom) and any(a.name == "HSM_BASE_URL" for a in node.names))
                or (isinstance(node, ast.Name) and node.id == "HSM_BASE_URL")
                or (isinstance(node, ast.Attribute) and node.attr == "HSM_BASE_URL")
            )
            if named:
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


# ------------------------------------------ dashboard wiring, Screen 4, caption (O2, O3)


@pytest.fixture
def servers(monkeypatch):
    made = []

    class CountingServer(ThreadingHTTPServer):
        def __init__(self, *args, **kwargs):
            made.append(self)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(embedded, "ThreadingHTTPServer", CountingServer)
    return made


def _render():
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def _log_in(at, user_id=RM):
    at.selectbox(key="session-persona").set_value(user_id)
    at.button(key="session-login").click().run()
    assert not at.exception, at.exception
    return at


def _screen_text(at):
    parts = []
    for group in (at.title, at.markdown, at.caption, at.error, at.warning, at.info, at.success):
        parts += [str(el.value) for el in group]
    parts += [str(el.message) for el in at.exception]
    return "\n".join(parts)


def _assert_only_screen_4(at):
    assert not at.exception, at.exception
    assert [t.value for t in at.title] == ["HSM labor & inventory"]
    assert [m.value for m in at.markdown] == [SCREEN_4]
    assert len(at.tabs) == 0 and len(at.selectbox) == 0 and len(at.button) == 0


def test_a_failed_start_shows_only_screen_4_with_no_cause_type_or_address(monkeypatch):
    cause = "PermissionError: /private/audit/audit.jsonl at http://127.0.0.1:4242"
    failed = embedded.BackendHandle(
        address="http://127.0.0.1:4242",
        host="127.0.0.1",
        port=4242,
        started_at=datetime.now(timezone.utc),
        status="failed",
        failure_cause=cause,
    )
    monkeypatch.setattr(embedded, "start", lambda port=0: failed)
    at = _render()
    _assert_only_screen_4(at)
    text = _screen_text(at)
    for leaked in ("PermissionError", "/private/audit", "127.0.0.1", "4242", "Traceback"):
        assert leaked not in text


def test_a_real_start_failure_logs_the_cause_and_keeps_it_off_the_screen(monkeypatch, caplog):
    monkeypatch.setenv("HSM_SIGNING_SECRET", "")
    with caplog.at_level(logging.WARNING, logger="mock_hsm.embedded"):
        at = _render()
    _assert_only_screen_4(at)
    assert "embedded backend failed to start: HSM_SIGNING_SECRET is not set" in caplog.text
    assert "HSM_SIGNING_SECRET" not in _screen_text(at)


def test_the_caption_shows_the_running_backends_address_and_reruns_keep_one_backend(servers):
    at = _log_in(_render())
    for _ in range(3):
        at.run()
    assert not at.exception, at.exception
    handle = embedded.current()
    assert handle is not None and len(servers) == 1
    assert f"Backend: {handle.address} · cached 60s" in [c.value for c in at.sidebar.caption]
    assert len(at.tabs) == 5
    assert os.environ["HSM_SIGNING_SECRET"] not in _screen_text(at)


def test_an_unreachable_backend_message_names_no_address_or_start_command(monkeypatch):
    at = _log_in(_render())

    def unreachable(user_id):
        client = HsmClient(mint_token(user_id), base_url=embedded.current().address)
        client.get_sites = lambda: (_ for _ in ()).throw(urllib.error.URLError("refused"))
        return client

    monkeypatch.setattr(session, "client_for", unreachable)
    st.cache_data.clear()
    at.run()
    assert [e.value for e in at.error] == [
        "Can't reach the demo backend (refused). Reload the page or try again later."
    ]
    assert "127.0.0.1" not in _screen_text(at) and "mock_hsm.server" not in _screen_text(at)


def test_a_backend_lost_between_start_and_render_shows_screen_4_text_not_a_trace(monkeypatch):
    at = _log_in(_render())
    real, calls = session.client_for, []

    def lost(user_id):
        # The session check (the first call) still answers; the sidebar's site
        # load, which has no handler of its own, then finds no live backend.
        calls.append(user_id)
        if len(calls) == 1:
            return real(user_id)
        raise embedded.BackendNotRunning("the embedded backend is not running")

    monkeypatch.setattr(session, "client_for", lost)
    st.cache_data.clear()
    at.run()
    assert not at.exception, at.exception
    assert SCREEN_4 in [m.value for m in at.markdown]
    assert "BackendNotRunning" not in _screen_text(at)
