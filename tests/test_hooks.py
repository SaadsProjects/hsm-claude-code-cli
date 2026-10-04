"""
Tests for .claude/hooks/require_no_violations.py, driven the way Claude Code
drives it: a JSON payload on stdin, a JSON decision on stdout. The hook must
deny on violations AND on every failure to validate -- a crashed or
timed-out hook is non-blocking in Claude Code, i.e. it fails open.
"""

import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

HOOK = PROJECT_ROOT / ".claude" / "hooks" / "require_no_violations.py"
TEST_PORT = 8773


@pytest.fixture(scope="module")
def backend_url():
    from mock_hsm.server import Handler, ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", TEST_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{TEST_PORT}"
    server.shutdown()
    server.server_close()


def _run_hook(shifts, base_url, user="user_rm_midtown", stdin=None):
    env = {**os.environ, "HSM_BASE_URL": base_url}
    env.pop("HSM_ACTIVE_USER", None)
    if user is not None:
        env["HSM_ACTIVE_USER"] = user
    if stdin is None:
        stdin = json.dumps({"tool_name": "mcp__hsm__publish_schedule", "tool_input": {"shifts": shifts}})
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, env=env, timeout=25, check=False
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout).get("hookSpecificOutput", {}).get("permissionDecision")


CLEAN = [{"employee_id": "emp_1", "date": "2026-10-01", "role": "JC-COOK", "start_time": "09:00", "end_time": "17:00"}]
OVERNIGHT_TOO_LONG = [
    {"employee_id": "emp_1", "date": "2026-10-01", "role": "JC-COOK", "start_time": "20:00", "end_time": "08:00"}
]


def test_clean_schedule_falls_through(backend_url):
    assert _run_hook(CLEAN, backend_url) is None


def test_violation_denied(backend_url):
    assert _run_hook(OVERNIGHT_TOO_LONG, backend_url) == "deny"


def test_unset_user_denied(backend_url):
    assert _run_hook(CLEAN, backend_url, user=None) == "deny"


def test_unknown_user_denied(backend_url):
    assert _run_hook(CLEAN, backend_url, user="nobody") == "deny"


def test_malformed_payload_denied(backend_url):
    assert _run_hook(CLEAN, backend_url, stdin="not json") == "deny"


def test_unreachable_backend_denied():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]  # nothing listens here once closed
    assert _run_hook(CLEAN, f"http://127.0.0.1:{free_port}") == "deny"


def test_hung_backend_denied_before_hook_timeout():
    # Accepts the connection but never replies.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert _run_hook(CLEAN, f"http://127.0.0.1:{s.getsockname()[1]}") == "deny"
