"""Post-deploy check: a deployed dashboard answers and refuses a signed-out visitor.

    python scripts/postdeploy_check.py <url> [--timeout SECONDS]

Contract C8. Loads the page in headless Chromium (Playwright) as a visitor
who is not signed in, and passes only when the sign-in screen shows and no
dashboard tab does. It never signs in, never types into the page and never
writes data. While the host's sleep or waking page shows, it waits and
retries until the timeout.

Exit codes: 0 passed, 1 an assertion failed, 2 bad usage, 3 the app did not
answer, was still waking or never settled when the timeout ran out, 4 the
browser could not start or stopped working (no verdict on the app).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import markers

EXIT_PASS, EXIT_FAIL, EXIT_USAGE, EXIT_NO_ANSWER, EXIT_BROWSER = 0, 1, 2, 3, 4
EXIT_CODES = (
    "exit codes: 0 passed; 1 a check failed; 2 bad usage; 3 no answer, still waking or never settled "
    "at the timeout; 4 the browser could not start"
)
DEFAULT_TIMEOUT = 120.0

PASS, WAKING, NOT_GATED, NOT_APP = "pass", "waking", "not-gated", "not-app"
# A frame failed mid-read, or the page never went quiet: nothing is known yet.
UNSETTLED = "unsettled"
# Streamlit gives a keyed container the CSS class `st-key-<key>`, so the
# selectors come straight from the markers the app uses (contract C6).
SIGN_IN_SELECTOR = ".st-key-" + markers.SIGN_IN_SCREEN
APP_TABS_SELECTOR = ".st-key-" + markers.APP_TABS
TAB_SELECTOR = '[role="tab"]'
# A script run still going: the app root's script state, which Streamlit sets
# in every mode, and the "Running..." icon, which it doesn't draw when the app
# is embedded (`?embed=true`).
RUNNING_SELECTOR = '[data-testid="stApp"][data-test-script-state="running"], [data-testid="stStatusWidgetRunningIcon"]'
# Streamlit Community Cloud's own pages while an app sleeps or starts. Never a
# pass: the check waits them out until the timeout.
WAKE_WORDING = ("gone to sleep", "get this app back up", "Your app is in the oven", "waking up")
# The host's own wake button on its sleep page. Pressing it signs nobody in
# and writes no app data; it is the only click this check ever makes.
WAKE_BUTTON = re.compile("get this app back up", re.IGNORECASE)

SETTLE_SECONDS = 15  # how long one load may take to show something recognisable
POLL_SECONDS = 0.5
RETRY_SECONDS = 1  # between attempts while nothing answers
WAKE_WAIT_SECONDS = 5  # between reloads while the host wakes the app
FRAME_READ_MS = 1000
# Streamlit draws a run piece by piece, so a gate that forgets to stop can show
# the sign-in screen and add tabs a moment later. A pass needs the page
# unchanged, with no script running, for this long.
QUIET_SECONDS = 2


@dataclass(frozen=True)
class PageState:
    """What the browser saw, across every frame of the page."""

    sign_in_visible: bool
    app_tabs_block: bool
    tab_count: int
    text: str
    # False when any frame failed mid-read: "no tabs" is then unknown.
    reliable: bool = True


def classify(state: PageState) -> str:
    # Any tab means the dashboard rendered for a signed-out visitor, even if
    # the sign-in screen shows too or another frame couldn't be read.
    if state.app_tabs_block or state.tab_count:
        return NOT_GATED
    if not state.reliable:
        return UNSETTLED
    if state.sign_in_visible:
        return PASS
    text = state.text.lower()
    if any(wording.lower() in text for wording in WAKE_WORDING):
        return WAKING
    return NOT_APP


class _Parser(argparse.ArgumentParser):
    # argparse would raise SystemExit; main() returns its codes instead, so
    # callers (and the tests) get the C8 exit code without catching anything.
    def error(self, message):
        self.print_usage(sys.stderr)
        raise _UsageError(message)


class _UsageError(Exception):
    pass


def _timeout(text):
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of seconds: {text!r}") from None
    if value <= 0:
        raise argparse.ArgumentTypeError("must be more than 0 seconds")
    return value


def parse_args(argv):
    parser = _Parser(
        prog="postdeploy_check.py", description="Read-only post-deploy check of the dashboard.", epilog=EXIT_CODES
    )
    parser.add_argument("url", help="the app's address, http:// or https://")
    parser.add_argument("--timeout", type=_timeout, default=DEFAULT_TIMEOUT, help="seconds to wait (default 120)")
    args = parser.parse_args(argv)
    parsed = urlparse(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        parser.error(f"url must start with http:// or https://: {args.url!r}")
    return args


# ------------------------------------------------------------------ browser
def _read_frame(frame):
    return (
        frame.locator(SIGN_IN_SELECTOR).first.is_visible(),
        frame.locator(APP_TABS_SELECTOR).count() > 0,
        frame.locator(TAB_SELECTOR).count(),
        frame.locator("body").inner_text(timeout=FRAME_READ_MS),
    )


def _gather(page, errors) -> PageState:
    """Read every frame: the hosted app runs inside the host's own page. A
    frame's values count only when all of its reads succeed."""
    sign_in = tabs_block = False
    tabs = 0
    texts = []
    reliable = True
    for frame in page.frames:
        try:
            frame_sign_in, frame_tabs_block, frame_tabs, frame_text = _read_frame(frame)
        except errors:
            # A frame can navigate or detach mid-read while the page loads.
            # The state is then unreliable and is polled again, never passed.
            reliable = False
            continue
        sign_in = sign_in or frame_sign_in
        tabs_block = tabs_block or frame_tabs_block
        tabs += frame_tabs
        texts.append(frame_text)
    return PageState(sign_in, tabs_block, tabs, "\n".join(texts), reliable)


def _script_running(page, errors) -> bool:
    try:
        return any(frame.locator(RUNNING_SELECTOR).count() > 0 for frame in page.frames)
    except errors:
        return True  # unknown counts as still running


def _settle(page, deadline, errors) -> PageState:
    """Poll until the page shows something ``classify`` recognises, or the
    settle window (bounded by the deadline) ends. A pass is confirmed only
    once the page has gone quiet."""
    end = min(deadline, time.monotonic() + SETTLE_SECONDS)
    while True:
        state = _gather(page, errors)
        verdict = classify(state)
        if verdict == PASS:
            return _confirm_pass(page, deadline, errors, state)
        if verdict not in (NOT_APP, UNSETTLED) or time.monotonic() >= end:
            return state
        time.sleep(POLL_SECONDS)


def _confirm_pass(page, deadline, errors, state) -> PageState:
    """Wait until the script run has finished and the page has stayed the same
    for QUIET_SECONDS, then return that state. Tabs end the wait at once; a
    deadline reached first gives an unreliable state, never a pass."""
    quiet_since = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        current = _gather(page, errors)
        if classify(current) == NOT_GATED:
            return current
        if current != state or not current.reliable or _script_running(page, errors):
            state, quiet_since = current, time.monotonic()
        elif time.monotonic() - quiet_since >= QUIET_SECONDS:
            return state
    return replace(state, reliable=False)


def _press_wake_button(page, errors) -> bool:
    for frame in page.frames:
        try:
            button = frame.get_by_role("button", name=WAKE_BUTTON)
            if button.count():
                button.first.click(timeout=FRAME_READ_MS * 5)
                return True
        except errors as exc:
            print(f"note: the host's wake button didn't respond ({type(exc).__name__}); waiting anyway")
            return True
    return False


class _Watch:
    """One check run: load, classify, and wait out the host's sleep page."""

    def __init__(self, page, url, timeout, errors):
        self.page, self.url, self.timeout, self.errors = page, url, timeout, errors
        self.deadline = time.monotonic() + timeout
        self.answered = self.waking = self.woke = self.unsettled = self.starting = False

    def _load(self) -> bool:
        remaining_ms = max(1, int((self.deadline - time.monotonic()) * 1000))
        try:
            self.page.goto(self.url, wait_until="domcontentloaded", timeout=remaining_ms)
        except self.errors:
            return False
        if not self.answered:
            self.answered = True
            print(f"ok: the app answered at {self.url}")
        return True

    def _wait(self, seconds):
        time.sleep(max(0.0, min(seconds, self.deadline - time.monotonic())))

    def _on_waking(self):
        if not self.waking:
            self.waking = True
            print("waiting: the host shows its sleep or waking page")
        if not self.woke and _press_wake_button(self.page, self.errors):
            self.woke = True
            print("pressed the host's wake button")
        self._wait(WAKE_WAIT_SECONDS)

    def run(self) -> int:
        while time.monotonic() < self.deadline:
            if not self._load():
                self._wait(RETRY_SECONDS)
                continue
            state = _settle(self.page, self.deadline, self.errors)
            verdict = classify(state)
            if verdict == PASS:
                print("ok: the sign-in screen shows")
                print("ok: no dashboard tab shows")
                print("PASS")
                return EXIT_PASS
            if verdict == NOT_GATED:
                print("FAIL: dashboard tabs show to a visitor who is not signed in")
                return EXIT_FAIL
            if verdict == WAKING:
                self._on_waking()
            elif verdict == UNSETTLED:
                self.unsettled = True
            elif state.text.strip():
                # Not the dashboard only if the whole settle window ran out;
                # if the timeout cut it short, the page may still be starting.
                if time.monotonic() >= self.deadline:
                    self.starting = True
                    break
                print("FAIL: the page shows neither the dashboard's sign-in screen nor the host's wake page")
                return EXIT_FAIL
        return self._timed_out()

    def _timed_out(self) -> int:
        if not self.answered:
            print(f"FAIL: no answer from {self.url} within {self.timeout:g} s")
        elif self.waking:
            print(f"FAIL: the app was still waking after {self.timeout:g} s")
        elif self.unsettled:
            print(f"FAIL: the page never settled enough to check within {self.timeout:g} s")
        elif self.starting:
            print(f"FAIL: the page showed no sign-in screen within {self.timeout:g} s; it may still be starting")
        else:
            print(f"FAIL: the page rendered nothing within {self.timeout:g} s")
        return EXIT_NO_ANSWER


def check(url, timeout) -> int:
    """Run the check in headless Chromium, in a fresh context that holds no
    cookies or stored sign-in, so the page sees a visitor who is not signed in."""
    # Imported here so the command line and classify() work without Playwright.
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"FAIL: the browser could not start ({type(exc).__name__})")
        return EXIT_BROWSER

    # A broken browser is exit 4, never 1: it says nothing about the app.
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_context().new_page()
                return _Watch(page, url, timeout, PlaywrightError).run()
            except PlaywrightError as exc:
                print(f"FAIL: the browser stopped working ({type(exc).__name__})")
                return EXIT_BROWSER
            finally:
                browser.close()
    except PlaywrightError as exc:
        print(f"FAIL: the browser could not start ({type(exc).__name__})")
        return EXIT_BROWSER


def main(argv=None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except _UsageError as exc:
        print(f"postdeploy_check.py: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    return check(args.url, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
