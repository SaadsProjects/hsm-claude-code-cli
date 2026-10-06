"""Tests for scripts/postdeploy_check.py that need no browser (contract C8).

The browser half is in tests/test_postdeploy_browser.py (marked `browser`).
These cover the command line and its exit codes, the page classification,
the selectors built from dashboard/markers.py, and a source scan that keeps
the check read-only by construction.
"""

import ast
import sys
from pathlib import Path

import pytest
from ci_scripts import load

pdc = load("postdeploy_check")


# ------------------------------------------------------------ command line
@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="missing-url"),
        pytest.param(["ftp://x"], id="non-http-url"),
        pytest.param(["https://x", "--timeout", "-1"], id="negative-timeout"),
    ],
)
def test_usage_errors_exit_2(argv, capsys):
    assert pdc.main(argv) == pdc.EXIT_USAGE == 2
    assert "usage:" in capsys.readouterr().err


def test_non_numeric_timeout_exits_2(capsys):
    assert pdc.main(["https://x", "--timeout", "soon"]) == 2
    assert "usage:" in capsys.readouterr().err


# ---------------------------------------------------------- classification
def page(sign_in=False, app_tabs_block=False, tab_count=0, text=""):
    return pdc.PageState(sign_in_visible=sign_in, app_tabs_block=app_tabs_block, tab_count=tab_count, text=text)


def test_sign_in_screen_without_tabs_passes():
    assert pdc.classify(page(sign_in=True, text="Access to this demo is by invitation.")) == pdc.PASS == "pass"


def test_any_tab_without_the_gate_is_not_gated():
    assert pdc.classify(page(tab_count=5, text="Overview Labor Inventory")) == pdc.NOT_GATED == "not-gated"


def test_tabs_next_to_the_sign_in_marker_are_still_not_gated():
    # A gate that draws its screen and then the dashboard anyway is a leak.
    assert pdc.classify(page(sign_in=True, tab_count=1)) == pdc.NOT_GATED
    assert pdc.classify(page(sign_in=True, app_tabs_block=True)) == pdc.NOT_GATED


@pytest.mark.parametrize("wording", pdc.WAKE_WORDING)
def test_each_host_wake_wording_is_waking(wording):
    assert pdc.classify(page(text=f"Hmm. {wording.upper()} ...")) == pdc.WAKING == "waking"


def test_anything_else_is_not_the_app():
    assert pdc.classify(page(text="Directory listing for /")) == pdc.NOT_APP == "not-app"
    assert pdc.classify(page()) == pdc.NOT_APP


# ------------------------------------------------- gathering across frames
class FrameGone(Exception):
    """Stands in for Playwright's error when a frame detaches mid-read."""


class FakeLocator:
    def __init__(self, frame, selector):
        self.frame, self.selector = frame, selector

    @property
    def first(self):
        return self

    def _read(self, value):
        if self.selector in self.frame.failing:
            raise FrameGone(self.selector)
        return value

    def is_visible(self):
        return self._read(self.selector in self.frame.visible)

    def count(self):
        return self._read(self.frame.counts.get(self.selector, 0))

    def inner_text(self, timeout=None):
        return self._read(self.frame.text)


class FakeFrame:
    def __init__(self, visible=(), counts=None, text="", failing=()):
        self.visible, self.counts, self.text, self.failing = set(visible), counts or {}, text, set(failing)

    def locator(self, selector):
        return FakeLocator(self, selector)


class FakePage:
    def __init__(self, *frames):
        self.frames = list(frames)
        self.loads = 0

    def goto(self, url, **kwargs):
        self.loads += 1


def test_gather_reads_every_frame():
    page = FakePage(FakeFrame(text="host"), FakeFrame(visible={pdc.SIGN_IN_SELECTOR}, text="Access"))
    state = pdc._gather(page, FrameGone)
    assert state.reliable
    assert pdc.classify(state) == pdc.PASS


def test_a_frame_that_fails_mid_read_makes_the_state_unreliable():
    # The sign-in marker reads fine; the tab query in the same frame raises,
    # so "no tabs" is unknown and the state must never pass (review R-02).
    page = FakePage(FakeFrame(visible={pdc.SIGN_IN_SELECTOR}, failing={pdc.TAB_SELECTOR}, text="Access"))
    state = pdc._gather(page, FrameGone)
    assert not state.reliable
    assert pdc.classify(state) == pdc.UNSETTLED


def test_tabs_seen_in_one_frame_fail_even_if_another_frame_errs():
    page = FakePage(FakeFrame(counts={pdc.TAB_SELECTOR: 2}), FakeFrame(failing={pdc.TAB_SELECTOR}))
    assert pdc.classify(pdc._gather(page, FrameGone)) == pdc.NOT_GATED


def test_a_page_still_starting_at_the_timeout_is_no_answer_not_a_failure(capsys):
    # Text but no gate marker yet, and the overall timeout ends the settle
    # window early: the app may be cold-starting, so exit 3, not 1 (review C-2).
    page = FakePage(FakeFrame(text="Please wait..."))
    assert pdc._Watch(page, "https://x", 1, FrameGone).run() == pdc.EXIT_NO_ANSWER
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("FAIL: ")
    assert "within 1 s" in last


def test_a_page_that_stays_wrong_for_the_whole_settle_window_fails(monkeypatch, capsys):
    monkeypatch.setattr(pdc, "SETTLE_SECONDS", 0.2)
    page = FakePage(FakeFrame(text="Directory listing for /"))
    assert pdc._Watch(page, "https://x", 30, FrameGone).run() == pdc.EXIT_FAIL
    assert "sign-in screen" in capsys.readouterr().out.strip().splitlines()[-1]


def test_selectors_come_from_the_dashboard_markers():
    from dashboard import markers

    assert pdc.SIGN_IN_SELECTOR == ".st-key-" + markers.SIGN_IN_SCREEN
    assert pdc.APP_TABS_SELECTOR == ".st-key-" + markers.APP_TABS


# ------------------------------------------------- read-only by construction
SCRIPT = Path(pdc.__file__)
# Playwright calls that type, press keys, tick boxes, upload or send requests.
INPUT_CALLS = {
    "fill",
    "type",
    "press",
    "press_sequentially",
    "insert_text",
    "check",
    "uncheck",
    "set_checked",
    "select_option",
    "set_input_files",
    "dblclick",
    "tap",
    "dispatch_event",
    "evaluate",
    "post",
    "put",
    "patch",
    "delete",
    "fetch",
}
CREDENTIAL_WORDS = ("secret", "password", "passwd", "credential", "token", "cookie", "api_key", "storage_state")
SIGN_IN_WORDS = ("login", "logout", "sign_in", "signin", "sign_out", "signout")
WRITE_TOOLS = ("publish_schedule", "submit_purchase_order")
WAKE_FUNCTION = "_press_wake_button"


def _call_name(node):
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _docstrings(tree):
    nodes = [tree, *(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef)))]
    return {id(n.body[0].value) for n in nodes if ast.get_docstring(n) is not None}


def _identifiers_and_strings(tree):
    skip = _docstrings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.arg, ast.keyword)):
            yield node.name if isinstance(node, ast.FunctionDef) else (node.arg or "")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield node.value


def read_only_violations(source):
    """Every way ``source`` could sign in, type, click (other than the host's
    wake button, once, in ``_press_wake_button``), hold a credential or call a
    gated write tool."""
    tree = ast.parse(source)
    problems = []
    for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)] + [tree]:
        body = func.body if func is not tree else [n for n in tree.body if not isinstance(n, ast.FunctionDef)]
        calls = [n for stmt in body for n in ast.walk(stmt) if isinstance(n, ast.Call)]
        for call in calls:
            name = _call_name(call)
            # Playwright input methods are attribute calls; a bare type(exc)
            # is the builtin, not page.type().
            if isinstance(call.func, ast.Attribute) and name in INPUT_CALLS:
                problems.append(f"input call .{name}()")
            if name == "click" and getattr(func, "name", None) != WAKE_FUNCTION:
                problems.append("click outside the wake button")
            if any(word in name.lower() for word in SIGN_IN_WORDS):
                problems.append(f"sign-in call {name}()")
    wake = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == WAKE_FUNCTION]
    clicks = [n for f in wake for n in ast.walk(f) if isinstance(n, ast.Call) and _call_name(n) == "click"]
    if len(clicks) > 1:
        problems.append("more than one wake-button click")
    if clicks and "WAKE_BUTTON" not in ast.unparse(wake[0]):
        problems.append("the wake click is not on WAKE_BUTTON")
    for word in _identifiers_and_strings(tree):
        lowered = word.lower()
        problems += [f"credential name {word!r}" for w in CREDENTIAL_WORDS if w in lowered]
        problems += [f"write tool {word!r}" for w in WRITE_TOOLS if w in lowered]
    return problems


@pytest.mark.parametrize(
    "snippet",
    [
        pytest.param("def f(page):\n    page.fill('#email', 'x')\n", id="fill"),
        pytest.param("def f(page):\n    page.keyboard.type('x')\n", id="type"),
        pytest.param("def f(page):\n    page.keyboard.press('Enter')\n", id="press"),
        pytest.param("def f(page):\n    page.get_by_text('Sign in').click()\n", id="click-elsewhere"),
        pytest.param(
            "def _press_wake_button(frame):\n    frame.locator(OTHER).click()\n", id="wake-click-not-on-wake-button"
        ),
        pytest.param(
            "def _press_wake_button(f):\n    f.locator(WAKE_BUTTON).click()\n    f.locator(WAKE_BUTTON).click()\n",
            id="two-wake-clicks",
        ),
        pytest.param("def f(st):\n    st.login('google')\n", id="login"),
        pytest.param("def f(gate):\n    gate.sign_in()\n", id="sign-in"),
        pytest.param("CLIENT_SECRET = 'x'\n", id="secret-name"),
        pytest.param("def f(ctx):\n    ctx.add_cookies([])\n", id="cookie"),
        pytest.param("TOOL = 'mcp__hsm__publish_schedule'\n", id="publish"),
        pytest.param("def f(c):\n    c.submit_purchase_order({})\n", id="submit-po"),
        pytest.param("def f(page):\n    page.request.post('/x')\n", id="http-post"),
        pytest.param("def f(loc):\n    loc.check()\n", id="tick-a-box"),
    ],
)
def test_the_scan_catches_each_forbidden_pattern(snippet):
    assert read_only_violations(snippet)


def test_the_scan_ignores_builtins_named_like_input_methods():
    assert read_only_violations("def f(exc):\n    return type(exc).__name__\n") == []


def test_the_scan_allows_one_click_on_the_wake_button():
    assert (
        read_only_violations("def _press_wake_button(f):\n    f.get_by_role('button', name=WAKE_BUTTON).click()\n")
        == []
    )


def test_the_check_is_read_only_by_construction():
    assert read_only_violations(SCRIPT.read_text()) == []


# --------------------------------------------------------- a broken browser
class _FakePlaywright:
    """``sync_playwright()`` whose Chromium can't launch."""

    def __init__(self, error):
        self.chromium = self
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def launch(self, **kwargs):
        raise self.error


def test_a_browser_that_cannot_launch_exits_4(monkeypatch, capsys):
    import playwright.sync_api as sync_api

    error = sync_api.Error("Executable doesn't exist at /nowhere/chrome")
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: _FakePlaywright(error))
    assert pdc.main(["https://x", "--timeout", "5"]) == pdc.EXIT_BROWSER == 4
    assert capsys.readouterr().out.strip().splitlines()[-1] == "FAIL: the browser could not start (Error)"


def test_missing_playwright_exits_4(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    assert pdc.main(["https://x"]) == 4
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("FAIL: the browser could not start (")
