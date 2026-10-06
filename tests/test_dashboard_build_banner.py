"""
Unit U4 on the running dashboard: the build caption at the bottom of the
sidebar (US5.1, AC5.1.2) and the demo-data reset banner above the tabs
(US6.1, AC6.1.1, AC6.1.2, FR6.2), in the frame slots of contract C5.

Every app is built with tests/gate_app.py (the real gate, a fake identity),
so Screen 3 runs the real embedded backend on an ephemeral port. Screen 4 is
forced by patching ``embedded.start``, as test_dashboard_embedded.py does.
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate_app import SIGNED_OUT, default_secrets, gate_app, identity

from agents import build_info
from dashboard import markers
from mock_hsm import embedded

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP = str(PROJECT_ROOT / "dashboard" / "app.py")
RM = "user_rm_midtown"
SCREEN_4 = "The demo backend didn't start. Reload the page or try again later."
FIXED = build_info.BuildInfo(kind="commit", value="0123456789abcdef0123456789abcdef01234567")
GATE_MARKERS = {markers.SIGN_IN_SCREEN, markers.REFUSAL_SCREEN, markers.UNAVAILABLE_SCREEN}


@pytest.fixture(autouse=True)
def holder():
    embedded.reset_for_tests()
    st.cache_data.clear()
    yield
    embedded.reset_for_tests()


@pytest.fixture
def failed_start(monkeypatch):
    handle = embedded.BackendHandle(
        address="http://127.0.0.1:1",
        host="127.0.0.1",
        port=1,
        started_at=datetime.now(timezone.utc),
        status="failed",
        failure_cause="forced for the test",
    )
    monkeypatch.setattr(embedded, "start", lambda port=0: handle)


def _run(at):
    at.run()
    assert not at.exception, at.exception
    return at


def _persona_login(at, user_id=RM):
    at.selectbox(key="session-persona").set_value(user_id)
    at.button(key="session-login").click().run()
    assert not at.exception, at.exception
    return at


def _block_keys(node):
    keys = set()
    key = getattr(node, "key", None)
    if type(node).__name__ == "Block" and key:
        keys.add(key)
    for child in getattr(node, "children", {}).values():
        keys |= _block_keys(child)
    return keys


def _last_sidebar_block(at):
    last = list(at.sidebar.children.values())[-1]
    assert type(last).__name__ == "Block" and last.key == markers.BUILD_CAPTION, last
    return last


def _gate_screen(monkeypatch, name):
    if name == "screen-1":
        return gate_app(APP, monkeypatch, identity=SIGNED_OUT)
    if name == "screen-2":
        return gate_app(APP, monkeypatch, identity=identity(email="stranger@example.com"))
    secrets = default_secrets()
    secrets["HSM_ALLOWED_EMAILS"] = []  # an empty allowlist is a system failure: Screen 5
    return gate_app(APP, monkeypatch, secrets=secrets)


# --------------------------------------------------- build caption (B5, B7)


def test_the_build_caption_is_the_last_sidebar_block_before_a_persona_login(monkeypatch):
    at = _run(gate_app(APP, monkeypatch))
    caption = _last_sidebar_block(at)
    assert [c.value for c in caption.caption] == [build_info.build_info().label]


def test_the_build_caption_follows_the_backend_caption_after_a_persona_login(monkeypatch):
    monkeypatch.setattr(build_info, "build_info", lambda root=None: FIXED)
    at = _persona_login(_run(gate_app(APP, monkeypatch)))
    assert len(at.tabs) == 5
    caption = _last_sidebar_block(at)
    assert [c.value for c in caption.caption] == ["Build 0123456"]
    sidebar_captions = [c.value for c in at.sidebar.caption]
    assert sidebar_captions[-1] == "Build 0123456"
    assert sidebar_captions[-2].startswith("Backend: ")


def test_screen_4_shows_the_account_section_then_the_build_caption(monkeypatch, failed_start):
    monkeypatch.setattr(build_info, "build_info", lambda root=None: FIXED)
    at = _run(gate_app(APP, monkeypatch))
    assert [m.value for m in at.markdown] == [SCREEN_4]
    blocks = list(at.sidebar.children.values())
    assert [b.key for b in blocks] == [markers.ACCOUNT_SECTION, markers.BUILD_CAPTION]
    assert [c.value for c in blocks[1].caption] == ["Build 0123456"]


def test_the_build_caption_stays_last_when_a_persona_has_no_sites(monkeypatch):
    # main() stops the run early here; the caption must still be drawn (commit review 2).
    from agents.hsm_client import HsmClient

    monkeypatch.setattr(build_info, "build_info", lambda root=None: FIXED)
    monkeypatch.setattr(HsmClient, "get_sites", lambda self: [])
    at = _persona_login(_run(gate_app(APP, monkeypatch)))
    assert "This persona has no sites in scope." in [w.value for w in at.sidebar.warning]
    caption = _last_sidebar_block(at)
    assert [c.value for c in caption.caption] == ["Build 0123456"]


@pytest.mark.parametrize("screen", ["screen-1", "screen-2", "screen-5"])
def test_no_gate_screen_shows_the_build_caption(monkeypatch, screen):
    at = _run(_gate_screen(monkeypatch, screen))
    keys = _block_keys(at._tree)
    assert len(keys & GATE_MARKERS) == 1
    assert markers.BUILD_CAPTION not in keys
    assert len(at.sidebar.children) == 0
    assert not any(str(c.value).startswith("Build ") for c in at.caption)


def test_a_failing_build_computation_shows_build_unknown_and_logs_only_the_type(monkeypatch, caplog):
    def broken(root=None):
        raise OSError("/secret/path/.git/HEAD: permission denied")

    monkeypatch.setattr(build_info, "build_info", broken)
    with caplog.at_level(logging.WARNING):
        at = _persona_login(_run(gate_app(APP, monkeypatch)))
    assert len(at.tabs) == 5  # the frame still renders
    assert [c.value for c in _last_sidebar_block(at).caption] == ["Build unknown"]
    assert "OSError" in caplog.text
    assert "/secret/path" not in caplog.text and "permission denied" not in caplog.text


# ---------------------------------------------------- reset banner (B6, US6.1)

BANNER = "Demo data: changes you make are reset periodically."
INFO_ICON = "\u2139\ufe0f"  # the "information source" emoji the plan specifies (B6)


def _walk(node):
    """Every node under ``node`` in the order the page draws them."""
    yield node
    for child in getattr(node, "children", {}).values():
        yield from _walk(child)


def _banner_infos(at):
    return [i for i in at.info if i.value == BANNER]


def _index(nodes, match):
    hits = [i for i, n in enumerate(nodes) if match(n)]
    assert len(hits) == 1, hits
    return hits[0]


def _is_banner_block(node):
    return type(node).__name__ == "Block" and getattr(node, "key", None) == markers.RESET_BANNER


def test_the_banner_renders_once_with_its_copy_and_icon_in_its_marked_block(monkeypatch):
    at = _persona_login(_run(gate_app(APP, monkeypatch)))
    (info,) = _banner_infos(at)
    assert info.icon == INFO_ICON  # text and an icon, not colour alone (AC6.1.2)
    blocks = [n for n in _walk(at.main) if _is_banner_block(n)]
    assert len(blocks) == 1
    assert [i.value for i in blocks[0].info] == [BANNER]


def test_the_banner_comes_after_the_title_and_before_and_outside_the_tabs(monkeypatch):
    at = _persona_login(_run(gate_app(APP, monkeypatch)))
    assert len(at.tabs) == 5
    nodes = list(_walk(at.main))
    title = _index(nodes, lambda n: type(n).__name__ == "Title")
    banner = _index(nodes, _is_banner_block)
    site = _index(nodes, lambda n: type(n).__name__ == "Caption" and " · site_001 · " in n.value)
    first_tab = min(i for i, n in enumerate(nodes) if type(n).__name__ == "Tab")
    assert title < banner < site < first_tab
    # Outside the tabs, so the same notice shows whichever tab is open (FR6.2).
    for tab in at.tabs:
        assert not any(_is_banner_block(n) for n in _walk(tab))
        assert BANNER not in [i.value for i in tab.info]


def test_the_banner_shows_before_a_persona_logs_in(monkeypatch):
    at = _run(gate_app(APP, monkeypatch))
    assert len(at.tabs) == 0
    assert len(_banner_infos(at)) == 1
    nodes = list(_walk(at.main))
    login_note = _index(nodes, lambda n: type(n).__name__ == "Info" and n.value == "Log in to see the dashboard.")
    assert _index(nodes, _is_banner_block) < login_note


def test_screen_4_shows_no_banner(monkeypatch, failed_start):
    at = _run(gate_app(APP, monkeypatch))
    assert [m.value for m in at.markdown] == [SCREEN_4]
    assert _banner_infos(at) == []
    assert markers.RESET_BANNER not in _block_keys(at._tree)


def test_a_backend_lost_mid_render_shows_screen_4_text_without_the_banner(monkeypatch):
    # The same "didn't start" page as a failed start: no reset banner above it,
    # and the build caption still last in the sidebar (commit review 2).
    from agents.hsm_client import HsmClient

    def lost(self):
        raise embedded.BackendNotRunning("lost between the start and a read")

    monkeypatch.setattr(build_info, "build_info", lambda root=None: FIXED)
    at = _run(gate_app(APP, monkeypatch))
    monkeypatch.setattr(HsmClient, "get_sites", lost)
    at = _persona_login(at)
    assert SCREEN_4 in [m.value for m in at.markdown]
    assert _banner_infos(at) == []
    assert markers.RESET_BANNER not in _block_keys(at._tree)
    _last_sidebar_block(at)


@pytest.mark.parametrize("screen", ["screen-1", "screen-2", "screen-5"])
def test_no_gate_screen_shows_the_banner(monkeypatch, screen):
    at = _run(_gate_screen(monkeypatch, screen))
    assert _banner_infos(at) == []
    assert markers.RESET_BANNER not in _block_keys(at._tree)


def test_the_unsaved_write_notice_renders_below_the_banner(monkeypatch):
    from dashboard import actions, session

    monkeypatch.setattr(session, "pending_retry", lambda state=None: {"describe": "add job code jc_r"})
    monkeypatch.setattr(actions, "retry_expired", lambda state=None: False)
    at = _persona_login(_run(gate_app(APP, monkeypatch)))
    nodes = list(_walk(at.main))
    notice = _index(
        nodes, lambda n: type(n).__name__ == "Warning" and n.value.startswith("We couldn't confirm this was saved")
    )
    assert _index(nodes, _is_banner_block) < notice < min(i for i, n in enumerate(nodes) if type(n).__name__ == "Tab")
