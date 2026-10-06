"""The post-deploy check and the sign-in gate in a real browser (marked `browser`).

Run with ``python3 -m pytest tests/test_postdeploy_browser.py -m browser -q``
after ``python -m playwright install chromium``. Every app here is the real
dashboard/app.py, started by ``streamlit run tests/browser_app.py`` on
127.0.0.1 with a fake identity (tests/browser_app.py) and placeholder sign-in
settings in a temp secrets file, so Google is never contacted. These tests
don't count toward .test-floor.
"""

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parent.parent
BROWSER_APP = ROOT / "tests" / "browser_app.py"
IDENTITY_ENV = "HSM_TEST_IDENTITY"
ALLOWED_EMAIL = "allowed@example.com"
HEALTH_TIMEOUT = 60
# Placeholder sign-in settings in the shape the gate requires (contract C7);
# none of them is a real credential.
SECRETS_TOML = f"""\
HSM_ALLOWED_EMAILS = ["{ALLOWED_EMAIL}"]

[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "test-cookie-secret-not-the-signing-secret"

[auth.google]
client_id = "test-client-id.apps.googleusercontent.com"
client_secret = "test-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
"""

SIGNED_OUT = {"signed_in": False}


def free_port():
    """A loopback port nobody is listening on: bind port 0, read it, release it."""
    # Not left to Streamlit (--server.port=0): it can't report the port it picked.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_answers(url, process, timeout=HEALTH_TIMEOUT):
    """Poll ``url`` until it answers 200; fail early if ``process`` exits."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the server exited early with code {process.returncode}")
        with contextlib.suppress(OSError), urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                return
        time.sleep(0.25)
    raise RuntimeError(f"no answer from {url} within {timeout} s")


def stop(process):
    """Terminate a test server, and kill it if it doesn't exit within 10 s."""
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@contextlib.contextmanager
def streamlit_app(script, workdir, env=None):
    """``streamlit run script`` on 127.0.0.1 and a free port, with the temp
    secrets file; yields the base URL once /_stcore/health answers, and stops
    the process afterwards."""
    secrets_file = workdir / "secrets.toml"
    secrets_file.write_text(SECRETS_TOML)
    port = free_port()
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script),
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        f"--secrets.files={secrets_file}",
    ]
    log_path = workdir / "streamlit.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            command, cwd=workdir, env={**os.environ, **(env or {})}, stdout=log, stderr=subprocess.STDOUT
        )
        url = f"http://127.0.0.1:{port}"
        try:
            wait_until_answers(f"{url}/_stcore/health", process)
            yield url
        except RuntimeError as exc:
            raise RuntimeError(f"{exc}\n--- streamlit log ---\n{log_path.read_text()}") from exc
        finally:
            stop(process)


@contextlib.contextmanager
def dashboard(tmp_path_factory, identity):
    workdir = tmp_path_factory.mktemp("browser-app")
    with streamlit_app(BROWSER_APP, workdir, env={IDENTITY_ENV: json.dumps(identity)}) as url:
        yield url


@pytest.fixture(scope="module")
def signed_out_app(tmp_path_factory):
    with dashboard(tmp_path_factory, SIGNED_OUT) as url:
        yield url


# ------------------------------------------------------------------ harness
def test_harness_serves_the_dashboard_on_loopback(signed_out_app):
    assert signed_out_app.startswith("http://127.0.0.1:")
    with urllib.request.urlopen(f"{signed_out_app}/_stcore/health", timeout=5) as response:
        assert response.read().decode().strip() == "ok"


# ---------------------------------------------------------------- the check
CHECK = ROOT / "scripts" / "postdeploy_check.py"
CHECK_TIMEOUT = 30
# Renders the dashboard's tabs in the APP_TABS block with no gate at all: the
# leak the check exists to catch.
UNGATED_APP = """\
import sys
sys.path.insert(0, {root!r})
import streamlit as st
from dashboard import markers
with st.container(key=markers.APP_TABS):
    overview, labor = st.tabs(["Overview", "Labor"])
    overview.write("Everything, for anyone.")
"""
# A gate that draws the sign-in screen but forgets to stop: the tabs arrive
# later in the same script run, after more than the check's 2 s quiet window
# (reviews R-01 and C-1).
LEAKY_GATE_APP = """\
import sys
import time
sys.path.insert(0, {root!r})
import streamlit as st
from dashboard import markers
with st.container(key=markers.SIGN_IN_SCREEN):
    st.markdown("Access to this demo is by invitation.")
time.sleep(4)
overview, labor = st.tabs(["Overview", "Labor"])
overview.write("Everything, for anyone.")
"""


def run_check(url, timeout=CHECK_TIMEOUT):
    return subprocess.run(
        [sys.executable, str(CHECK), url, "--timeout", str(timeout)],
        capture_output=True,
        text=True,
        timeout=timeout + 60,
        check=False,
    )


def visible_screens(url):
    """Which gate screens and how many tabs a signed-out browser sees."""
    from playwright.sync_api import sync_playwright

    from dashboard import markers

    names = ("SIGN_IN_SCREEN", "REFUSAL_SCREEN", "UNAVAILABLE_SCREEN", "BACKEND_FAILED_SCREEN", "APP_TABS")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url)
            page.wait_for_selector(
                ", ".join(f".st-key-{getattr(markers, n)}" for n in names[:4]), timeout=CHECK_TIMEOUT * 1000
            )
            seen = {n for n in names if page.locator(f".st-key-{getattr(markers, n)}").first.is_visible()}
            return seen, page.locator('[role="tab"]').count()
        finally:
            browser.close()


@pytest.fixture
def plain_page(tmp_path):
    """A plain http.server page on loopback: something answers, but not the app."""
    (tmp_path / "index.html").write_text("<html><body><h1>Hello</h1><p>Not a dashboard.</p></body></html>")
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(tmp_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        wait_until_answers(url, process)
        yield url
    finally:
        stop(process)


def test_check_passes_on_the_sign_in_screen(signed_out_app):
    result = run_check(signed_out_app)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1] == "PASS"
    assert "sign-in screen" in result.stdout


def test_a_signed_out_visitor_sees_only_the_sign_in_screen(signed_out_app):
    assert visible_screens(signed_out_app) == ({"SIGN_IN_SCREEN"}, 0)


def check_against_double(tmp_path_factory, source, path=""):
    workdir = tmp_path_factory.mktemp("double")
    script = workdir / "double_app.py"
    script.write_text(source.format(root=str(ROOT)))
    with streamlit_app(script, workdir) as url:
        return run_check(url + path)


def assert_tabs_failure(result):
    assert result.returncode == 1, result.stdout + result.stderr
    last = result.stdout.strip().splitlines()[-1]
    assert last.startswith("FAIL: ")
    assert "tab" in last


def test_check_fails_when_tabs_render_without_the_gate(tmp_path_factory):
    assert_tabs_failure(check_against_double(tmp_path_factory, UNGATED_APP))


# Streamlit Cloud may serve the app embedded, where Streamlit draws no
# "Running..." icon, so the running-script guard must work there too.
@pytest.mark.parametrize("path", ["/", "/?embed=true"], ids=["page", "embedded"])
def test_check_fails_when_tabs_follow_the_sign_in_screen(tmp_path_factory, path):
    assert_tabs_failure(check_against_double(tmp_path_factory, LEAKY_GATE_APP, path))


def test_check_fails_on_a_page_that_is_not_the_app(plain_page):
    result = run_check(plain_page)
    assert result.returncode == 1, result.stdout + result.stderr
    last = result.stdout.strip().splitlines()[-1]
    assert last.startswith("FAIL: ")
    assert "sign-in screen" in last


def test_check_gives_up_on_a_closed_port_with_exit_3():
    url = f"http://127.0.0.1:{free_port()}"
    started = time.monotonic()
    result = run_check(url, timeout=3)
    elapsed = time.monotonic() - started
    assert result.returncode == 3, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1].startswith("FAIL: ")
    assert elapsed < 10


# ------------------------------------------------------------ refusal proof
@pytest.mark.parametrize(
    "identity",
    [
        pytest.param({"signed_in": True, "email": "stranger@example.com", "email_verified": True}, id="not-listed"),
        pytest.param({"signed_in": True, "email": ALLOWED_EMAIL, "email_verified": False}, id="unverified"),
    ],
)
def test_a_refused_visitor_sees_only_the_refusal_screen(tmp_path_factory, identity):
    with dashboard(tmp_path_factory, identity) as url:
        assert visible_screens(url) == ({"REFUSAL_SCREEN"}, 0)
