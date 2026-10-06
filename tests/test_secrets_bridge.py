"""
The secrets bridge (dashboard/secrets_bridge.py; unit U3, US2.5, BR1.1-BR1.5).

The bridge sets HSM_SIGNING_SECRET from the first source that has it: an
exported value, then the hosted Streamlit secrets, then .env.local. These
tests call it with a plain mapping and the environment set through
monkeypatch; no real secret is used.
"""

import ast
import secrets as pysecrets
import sys
from pathlib import Path

import pytest
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import secrets_bridge
from dashboard.secrets_bridge import bridge_signing_secret, cookie_secret_conflict, read_hosted_secrets
from mock_hsm import auth

ENV = auth.SECRET_ENV
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def no_local_file(monkeypatch, tmp_path):
    """Point .env.local at a file that doesn't exist, so a developer's real
    one is never read."""
    monkeypatch.setattr(auth, "default_local_secret_path", lambda: tmp_path / "missing.env")


def _value():
    return pysecrets.token_urlsafe(32)


def test_an_exported_value_is_never_overwritten_by_a_hosted_one(monkeypatch, no_local_file):
    exported = _value()
    monkeypatch.setenv(ENV, exported)
    bridge_signing_secret({ENV: _value()})
    assert auth.os.environ[ENV] == exported


@pytest.mark.parametrize("unset", [True, False], ids=["unset", "empty"])
def test_a_hosted_value_is_copied_when_the_variable_is_unset_or_empty(monkeypatch, no_local_file, unset):
    if unset:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, "")
    hosted = _value()
    bridge_signing_secret({ENV: hosted})
    assert auth.os.environ[ENV] == hosted
    claims = auth.verify_token(auth.mint_token("user_rm_midtown"))
    assert claims["sub"] == "user_rm_midtown"


def test_with_neither_source_the_local_file_is_read(monkeypatch, tmp_path):
    local = _value()
    env_file = tmp_path / ".env.local"
    env_file.write_text(f"{ENV}={local}\n")
    monkeypatch.setattr(auth, "default_local_secret_path", lambda: env_file)
    monkeypatch.delenv(ENV, raising=False)
    bridge_signing_secret({})
    assert auth.os.environ[ENV] == local


def test_a_present_value_is_never_replaced_by_the_local_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text(f"{ENV}={_value()}\n")
    monkeypatch.setattr(auth, "default_local_secret_path", lambda: env_file)
    exported = _value()
    monkeypatch.setenv(ENV, exported)
    bridge_signing_secret({})
    assert auth.os.environ[ENV] == exported


def test_a_non_string_hosted_value_is_ignored(monkeypatch, no_local_file):
    monkeypatch.delenv(ENV, raising=False)
    bridge_signing_secret({ENV: 12345})
    assert ENV not in auth.os.environ


class _Unreadable:
    def to_dict(self):
        raise FileNotFoundError("no secrets.toml")


class _Readable:
    def to_dict(self):
        return {"HSM_ALLOWED_EMAILS": ["a@example.com"], "auth": {"redirect_uri": "x"}}


def test_unreadable_hosted_secrets_count_as_absent(monkeypatch):
    monkeypatch.setattr(st, "secrets", _Unreadable())
    assert read_hosted_secrets() == {}


def test_readable_hosted_secrets_are_returned_as_a_plain_mapping(monkeypatch):
    monkeypatch.setattr(st, "secrets", _Readable())
    assert read_hosted_secrets() == {"HSM_ALLOWED_EMAILS": ["a@example.com"], "auth": {"redirect_uri": "x"}}


@pytest.mark.parametrize(
    ("signing", "cookie", "clash"),
    [
        ("same-value", "same-value", True),
        ("one", "two", False),
        ("", "", False),
        ("x", None, False),
        (None, "x", False),
    ],
    ids=["equal", "different", "both-empty", "no-cookie", "no-signing"],
)
def test_cookie_secret_conflict_only_for_equal_non_empty_values(signing, cookie, clash):
    assert cookie_secret_conflict(signing, cookie) is clash


def test_mock_hsm_imports_no_streamlit():
    offenders = []
    for path in sorted((PROJECT_ROOT / "mock_hsm").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            offenders += [f"{path.name}:{node.lineno}" for n in names if n.split(".")[0] == "streamlit"]
    assert offenders == []


def test_the_bridge_module_is_in_the_dashboard_package():
    assert Path(secrets_bridge.__file__).resolve().parent == PROJECT_ROOT / "dashboard"
