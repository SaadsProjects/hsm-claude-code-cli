"""
Every entry point fails closed without a valid signing secret (U1).

Processes, scripts and configuration are tested at their real boundaries:
the backend, the start script, the dev-secret script and the publish hook
run as subprocesses. A missing secret is simulated with HSM_SIGNING_SECRET=""
rather than by unsetting it, so the local loader never reads a developer's
real .env.local (an already-present variable, even an empty one, is kept).
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SECRET_ENV = "HSM_SIGNING_SECRET"
HOOK = PROJECT_ROOT / ".claude" / "hooks" / "require_no_violations.py"
SHIFTS = [{"employee_id": "emp_1", "date": "2026-10-01", "role": "JC-COOK", "start_time": "09:00", "end_time": "17:00"}]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(**overrides):
    env = {**os.environ, **overrides}
    return env


# ---------------------------------------------------------------- publish hook
def _run_hook(payload, **env_overrides):
    env = _env(
        HSM_BASE_URL=f"http://127.0.0.1:{_free_port()}",  # nothing listens: validation can't be what decides
        HSM_ACTIVE_USER="user_rm_midtown",
        **env_overrides,
    )
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=25,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout).get("hookSpecificOutput", {}), proc


def _publish_payload():
    return {"tool_name": "mcp__hsm__publish_schedule", "tool_input": {"site_id": "site_001", "shifts": SHIFTS}}


def test_hook_denies_publish_without_a_secret():
    out, _ = _run_hook(_publish_payload(), **{SECRET_ENV: ""})
    assert out.get("permissionDecision") == "deny"
    assert SECRET_ENV in out["permissionDecisionReason"]
    assert "is not set" in out["permissionDecisionReason"]


def test_hook_deny_for_a_short_secret_never_contains_the_value():
    short = "s3cr3t-value-that-is-too-short"  # 30 bytes
    out, proc = _run_hook(_publish_payload(), **{SECRET_ENV: short})
    assert out.get("permissionDecision") == "deny"
    assert SECRET_ENV in out["permissionDecisionReason"]
    assert "32 bytes" in out["permissionDecisionReason"]
    assert short not in proc.stdout + proc.stderr


def test_hook_lets_other_tools_fall_through_without_a_secret():
    out, proc = _run_hook({"tool_name": "mcp__hsm__get_forecast", "tool_input": {}}, **{SECRET_ENV: ""})
    assert out == {}
    assert json.loads(proc.stdout) == {}


# ------------------------------------------------------------ backend start
def _listening(port):
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_listening(port, proc, deadline_seconds=15):
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if _listening(port):
            return True
        if proc.poll() is not None:
            return False
        time.sleep(0.05)
    return False


def _run_to_exit(argv, timeout=20, **env_overrides):
    return subprocess.run(
        argv, cwd=PROJECT_ROOT, env=_env(**env_overrides), capture_output=True, text=True, timeout=timeout, check=False
    )


def test_server_refuses_to_start_without_a_secret():
    port = _free_port()
    proc = _run_to_exit([sys.executable, "-m", "mock_hsm.server", "--port", str(port)], **{SECRET_ENV: ""})
    assert proc.returncode == 1
    assert SECRET_ENV in proc.stderr
    assert "listening" not in proc.stdout
    assert not _listening(port)


def test_server_listens_on_the_given_port_with_a_secret():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "mock_hsm.server", "--port", str(port)],
        cwd=PROJECT_ROOT,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        listening = _wait_listening(port, proc)
    finally:
        proc.terminate()
        out, err = proc.communicate(timeout=10)
    assert listening, err
    assert f":{port}" in out
    assert os.environ[SECRET_ENV] not in out + err


def test_server_start_reads_env_local_when_the_variable_is_unset(monkeypatch, tmp_path):
    from mock_hsm import auth, server

    value = "server-env-local-" + "v" * 32
    env_file = tmp_path / ".env.local"
    env_file.write_text(f"{SECRET_ENV}={value}\n")
    monkeypatch.delenv(SECRET_ENV, raising=False)
    monkeypatch.setattr(auth, "default_local_secret_path", lambda: env_file)
    started = {}
    monkeypatch.setattr(server, "run", lambda port: started.update(port=port, secret=os.environ.get(SECRET_ENV)))
    assert server.main(["--port", "0"]) == 0
    assert started == {"port": 0, "secret": value}


def test_server_rejects_a_non_integer_port_as_a_usage_error():
    proc = _run_to_exit([sys.executable, "-m", "mock_hsm.server", "--port", "abc"])
    assert proc.returncode == 2
    assert "--port" in proc.stderr


# --------------------------------------------- running backend: 503, not 500
@pytest.fixture
def live_server():
    from mock_hsm.server import Handler, ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _request(url, method="GET", token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = b"{}" if method == "POST" else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_secret_lost_mid_run_answers_503_and_keeps_serving(live_server, monkeypatch, capfd):
    from mock_hsm.auth import mint_token

    token = mint_token("user_rm_midtown")
    good = os.environ[SECRET_ENV]
    monkeypatch.setenv(SECRET_ENV, "")

    status, body = _request(f"{live_server}/labor/sites/site_001/employees?token=hidden-query", token=token)
    assert status == 503
    assert SECRET_ENV in body["error"]
    status, body = _request(f"{live_server}/sessions", method="POST", token=token)
    assert status == 503
    assert SECRET_ENV in body["error"]

    err = capfd.readouterr().err
    assert "/labor/sites/site_001/employees" in err
    assert "hidden-query" not in err
    assert good not in err

    assert _request(f"{live_server}/healthz")[0] == 200  # still serving
    monkeypatch.setenv(SECRET_ENV, good)
    assert _request(f"{live_server}/labor/sites/site_001/employees", token=token)[0] == 200


def test_handler_that_hits_the_secret_gate_answers_503(live_server, monkeypatch):
    from mock_hsm import auth, server
    from mock_hsm.auth import mint_token

    def mints(m, claims, qs, body):
        auth.mint_token("user_rm_midtown")  # the mint path, inside a handler
        return 200, {}

    token = mint_token("user_rm_midtown")
    monkeypatch.setattr(server, "ROUTES", [("GET", re.compile("^/mint-probe$"), mints), *server.ROUTES])
    monkeypatch.setattr(server, "verify_token", lambda _token: {"sub": "user_rm_midtown", "persona": "RM"})
    monkeypatch.setenv(SECRET_ENV, "too-short")
    status, body = _request(f"{live_server}/mint-probe", token=token)
    assert status == 503
    assert SECRET_ENV in body["error"]
    assert "too-short" not in body["error"]


def test_short_secret_mid_run_never_reaches_the_body_or_the_log(live_server, monkeypatch, capfd):
    from mock_hsm.auth import mint_token

    token = mint_token("user_rm_midtown")
    short = "visible-if-leaked-123"
    monkeypatch.setenv(SECRET_ENV, short)
    status, body = _request(f"{live_server}/labor/sites/site_001/employees", token=token)
    assert status == 503
    assert "32 bytes" in body["error"]
    assert short not in json.dumps(body)
    assert short not in capfd.readouterr().err


# ------------------------------------------------------------- start script
START_SCRIPT = PROJECT_ROOT / "scripts" / "start_mock_server.sh"


def _script_path_env():
    # The scripts call `python3`; use the interpreter running the tests.
    return f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"


def test_start_script_refuses_without_a_secret():
    port = _free_port()
    proc = _run_to_exit(["bash", str(START_SCRIPT), "--port", str(port)], PATH=_script_path_env(), **{SECRET_ENV: ""})
    assert proc.returncode != 0
    assert SECRET_ENV in proc.stderr
    assert not _listening(port)


def test_start_script_listens_on_the_given_port_with_a_secret():
    port = _free_port()
    proc = subprocess.Popen(
        ["bash", str(START_SCRIPT), "--port", str(port)],
        cwd=PROJECT_ROOT,
        env=_env(PATH=_script_path_env()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        listening = _wait_listening(port, proc)
    finally:
        proc.terminate()
        out, err = proc.communicate(timeout=10)
    assert listening, err
    assert os.environ[SECRET_ENV] not in out + err


# ---------------------------------------------------------------- MCP tools
def test_mcp_tool_without_a_secret_is_a_tool_error_naming_the_variable(monkeypatch):
    import asyncio

    from mcp_server import hsm_tools
    from mock_hsm.auth import SecretMissingError

    monkeypatch.setenv("HSM_ACTIVE_USER", "user_rm_midtown")
    monkeypatch.setenv(SECRET_ENV, "")
    with pytest.raises(SecretMissingError, match=SECRET_ENV):
        hsm_tools._client()
    with pytest.raises(Exception, match=SECRET_ENV) as info:
        asyncio.run(hsm_tools.mcp.call_tool("get_employees", {"site_id": "site_001"}))
    assert type(info.value).__name__ == "ToolError"


def test_mcp_server_start_loads_the_local_secret_before_serving(monkeypatch, tmp_path):
    from mcp_server import hsm_tools
    from mock_hsm import auth

    value = "from-env-local-" + "m" * 32
    env_file = tmp_path / ".env.local"
    env_file.write_text(f"{SECRET_ENV}={value}\n")
    monkeypatch.delenv(SECRET_ENV, raising=False)
    monkeypatch.setattr(auth, "default_local_secret_path", lambda: env_file)
    seen = {}
    monkeypatch.setattr(hsm_tools.mcp, "run", lambda transport: seen.update(secret=os.environ.get(SECRET_ENV)))
    hsm_tools.main()
    assert seen == {"secret": value}


def test_mcp_json_holds_no_signing_secret():
    text = (PROJECT_ROOT / ".mcp.json").read_text()
    assert SECRET_ENV not in text
    for server in json.loads(text)["mcpServers"].values():
        assert SECRET_ENV not in server.get("env", {})


# ------------------------------------------------------- dev-secret script
DEV_SECRET = PROJECT_ROOT / "scripts" / "dev-secret.sh"


def _dev_secret(path, *args):
    return _run_to_exit(["bash", str(DEV_SECRET), "--file", str(path), *args], PATH=_script_path_env())


def _secret_line(path):
    lines = [line for line in path.read_text().splitlines() if line.startswith(f"{SECRET_ENV}=")]
    assert len(lines) == 1
    return lines[0].split("=", 1)[1]


def test_dev_secret_creates_an_owner_only_file_with_a_long_secret(tmp_path):
    path = tmp_path / ".env.local"
    proc = _dev_secret(path)
    assert proc.returncode == 0, proc.stderr
    assert path.stat().st_mode & 0o777 == 0o600
    value = _secret_line(path)
    assert len(value.encode()) >= 32
    assert value not in proc.stdout + proc.stderr


def test_dev_secret_never_replaces_an_existing_secret_without_force(tmp_path):
    path = tmp_path / ".env.local"
    assert _dev_secret(path).returncode == 0
    before = path.read_text()
    proc = _dev_secret(path)
    assert proc.returncode != 0
    assert "already set" in proc.stderr
    assert "--force" in proc.stderr
    assert path.read_text() == before


def test_dev_secret_force_replaces_the_value_keeps_other_lines_and_tightens_the_mode(tmp_path):
    path = tmp_path / ".env.local"
    path.write_text(f"# mine\nOTHER=keep\n{SECRET_ENV}=old-value-{'o' * 32}\n")
    path.chmod(0o644)
    proc = _dev_secret(path, "--force")
    assert proc.returncode == 0, proc.stderr
    text = path.read_text()
    assert "# mine\n" in text
    assert "OTHER=keep\n" in text
    assert _secret_line(path) != f"old-value-{'o' * 32}"
    assert path.stat().st_mode & 0o777 == 0o600


def test_dev_secret_adds_the_entry_to_a_file_without_one(tmp_path):
    path = tmp_path / ".env.local"
    path.write_text("OTHER=keep")  # no trailing newline
    proc = _dev_secret(path)
    assert proc.returncode == 0, proc.stderr
    assert path.read_text().splitlines()[0] == "OTHER=keep"
    assert len(_secret_line(path).encode()) >= 32
    assert path.stat().st_mode & 0o777 == 0o600


def test_dev_secret_rejects_an_unknown_option(tmp_path):
    proc = _dev_secret(tmp_path / ".env.local", "--bogus")
    assert proc.returncode == 2
    assert "usage" in proc.stderr.lower()
    assert not (tmp_path / ".env.local").exists()


# --------------------------------------------------------------- .gitignore
SECRET_FILES = (".env", ".env.local", ".env.prod", ".env.production", ".streamlit/secrets.toml")


def test_secret_files_are_git_ignored():
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", *SECRET_FILES],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert sorted(proc.stdout.split()) == sorted(SECRET_FILES), proc.stderr


def test_secret_ignore_lines_are_explicit_and_outside_the_ai_dlc_block():
    lines = (PROJECT_ROOT / ".gitignore").read_text().splitlines()
    block_start = lines.index("# BEGIN AI-DLC:gitignore")
    for pattern in (".env", ".env.local", ".env.*", ".streamlit/secrets.toml"):
        assert pattern in lines[:block_start], pattern


# --------------------------------------------------------------------- docs
DOCS = ("CLAUDE.md", "README.md", "dashboard/README.md")


@pytest.mark.parametrize("doc", DOCS)
def test_docs_explain_the_signing_secret_and_never_say_no_password(doc):
    text = (PROJECT_ROOT / doc).read_text()
    assert "scripts/dev-secret.sh" in text
    assert SECRET_ENV in text
    assert ".env.local" in text
    assert "no password" not in text.lower()
