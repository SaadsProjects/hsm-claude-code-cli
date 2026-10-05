"""
Tests for the token-signing secret gate in mock_hsm/auth.py (contract C1)
and its local loader (contract C2), plus the per-run test secret.

No tracked test file holds the burned value: the tests that need it read it
from .gitleaks.toml, which the burned-secret check excludes permanently.
"""

import ast
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import conftest
import pytest
from ci_scripts import load

from mock_hsm import auth

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRET_ENV = "HSM_SIGNING_SECRET"


def _burned_value():
    """The burned value, read from the gitleaks allowlist (its first entry)."""
    text = (PROJECT_ROOT / ".gitleaks.toml").read_text()
    return re.findall(r"'''(.+?)'''", text)[0]


def _refusal(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(SECRET_ENV, raising=False)
    else:
        monkeypatch.setenv(SECRET_ENV, value)
    with pytest.raises(auth.SecretMissingError) as info:
        auth.require_secret()
    return info.value


# ------------------------------------------------------- test-session secret
def test_session_secret_is_set_and_long_enough():
    value = os.environ.get(SECRET_ENV, "")
    assert len(value.encode()) >= 32


def test_session_secret_generator_returns_a_fresh_value_each_call():
    first, second = conftest.new_test_secret(), conftest.new_test_secret()
    assert first != second
    assert len(first.encode()) >= 32


# ------------------------------------------------------------- the secret gate
def test_importing_auth_without_a_secret_raises_nothing():
    env = {k: v for k, v in os.environ.items() if k != SECRET_ENV}
    proc = subprocess.run(
        [sys.executable, "-c", "import mock_hsm.auth"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (None, "missing"),
        ("", "missing"),
        ("a" * 31, "too_short"),
        ("é" * 15 + "a", "too_short"),  # 16 characters but 31 UTF-8 bytes
    ],
)
def test_require_secret_refuses_missing_and_short_values(monkeypatch, value, reason):
    error = _refusal(monkeypatch, value)
    assert error.reason == reason
    assert SECRET_ENV in str(error)
    if value:
        assert value not in str(error)


@pytest.mark.parametrize("value", ["a" * 32, "é" * 16])  # 32 UTF-8 bytes each
def test_require_secret_accepts_exactly_32_bytes(monkeypatch, value):
    monkeypatch.setenv(SECRET_ENV, value)
    assert auth.require_secret() is None


def test_require_secret_refuses_the_burned_value(monkeypatch):
    burned = _burned_value()
    assert len(burned.encode()) >= 32  # long enough: only the hash check can refuse it
    error = _refusal(monkeypatch, burned)
    assert error.reason == "burned"
    assert SECRET_ENV in str(error)
    assert burned not in str(error)


def test_burned_hash_matches_the_ci_check_and_the_gitleaks_value():
    check = load("check_burned_secret")
    assert auth.BURNED_SECRET_SHA256 == check.BURNED_SECRET_SHA256
    assert hashlib.sha256(_burned_value().encode()).hexdigest() == auth.BURNED_SECRET_SHA256


def test_secret_missing_error_is_a_runtime_error_not_a_token_error():
    assert issubclass(auth.SecretMissingError, RuntimeError)
    assert not issubclass(auth.SecretMissingError, auth.TokenError)
    assert auth.SECRET_ENV == SECRET_ENV
    assert auth.MIN_SECRET_BYTES == 32


def test_mint_and_verify_refuse_without_a_secret(monkeypatch):
    token = auth.mint_token("user_rm_midtown")  # minted under the session secret
    monkeypatch.setenv(SECRET_ENV, "")
    with pytest.raises(auth.SecretMissingError):
        auth.mint_token("user_rm_midtown")
    with pytest.raises(auth.SecretMissingError):
        auth.verify_token(token)


def test_secret_is_read_on_every_call(monkeypatch):
    monkeypatch.setenv(SECRET_ENV, "first-secret-" + "x" * 32)
    token = auth.mint_token("user_rm_midtown")
    assert auth.verify_token(token)["sub"] == "user_rm_midtown"
    monkeypatch.setenv(SECRET_ENV, "second-secret-" + "y" * 32)
    with pytest.raises(auth.TokenError, match="bad signature"):
        auth.verify_token(token)


def test_unknown_user_still_raises_value_error():
    with pytest.raises(ValueError, match="unknown user_id"):
        auth.mint_token("nobody")


def test_auth_imports_only_the_standard_library_and_mock_hsm():
    tree = ast.parse((PROJECT_ROOT / "mock_hsm" / "auth.py").read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    third_party = {name for name in roots if name != "mock_hsm" and name not in sys.stdlib_module_names}
    assert third_party == set()


# ----------------------------------------------------------- the local loader
LOADED = "loaded-from-file-" + "z" * 32


def _write_env_file(tmp_path, text):
    path = tmp_path / ".env.local"
    path.write_text(text)
    return path


def test_loader_sets_an_unset_variable_from_the_file(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(SECRET_ENV, raising=False)
    path = _write_env_file(tmp_path, f"# local only\nHSM_UNRELATED_KEY=1\n{SECRET_ENV}={LOADED}\n")
    auth.load_local_secret(path)
    assert os.environ[SECRET_ENV] == LOADED
    assert os.environ.get("HSM_UNRELATED_KEY") != "1"  # other lines are ignored, not loaded
    captured = capsys.readouterr()
    assert LOADED not in captured.out + captured.err


@pytest.mark.parametrize("present", ["already-set-" + "q" * 32, ""])
def test_loader_never_overrides_a_present_variable(monkeypatch, tmp_path, present):
    monkeypatch.setenv(SECRET_ENV, present)
    auth.load_local_secret(_write_env_file(tmp_path, f"{SECRET_ENV}={LOADED}\n"))
    assert os.environ[SECRET_ENV] == present


@pytest.mark.parametrize(
    "text", [None, "HSM_UNRELATED_KEY=1\n# HSM_SIGNING_SECRET=commented\n", "HSM_SIGNING_SECRET_OLD=x\n"]
)
def test_loader_is_a_no_op_without_a_file_or_an_entry(monkeypatch, tmp_path, text):
    monkeypatch.delenv(SECRET_ENV, raising=False)
    path = tmp_path / ".env.local" if text is None else _write_env_file(tmp_path, text)
    auth.load_local_secret(path)
    assert SECRET_ENV not in os.environ


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f'"{LOADED}"', LOADED),
        (f"'{LOADED}'", LOADED),
        (f"\"{LOADED}'", f"\"{LOADED}'"),  # mismatched quotes are kept
        ("$HOME-and-`whoami`-" + "k" * 24, "$HOME-and-`whoami`-" + "k" * 24),
    ],
)
def test_loader_strips_one_pair_of_quotes_and_never_expands(monkeypatch, tmp_path, raw, expected):
    monkeypatch.delenv(SECRET_ENV, raising=False)
    auth.load_local_secret(_write_env_file(tmp_path, f"{SECRET_ENV}={raw}\n"))
    assert os.environ[SECRET_ENV] == expected


def test_loader_default_path_is_the_project_root_not_the_working_directory(monkeypatch, tmp_path):
    assert auth.default_local_secret_path() == PROJECT_ROOT / ".env.local"
    monkeypatch.chdir(tmp_path)
    assert auth.default_local_secret_path() == PROJECT_ROOT / ".env.local"


def test_loader_reads_the_default_path_when_none_is_given(monkeypatch, tmp_path):
    monkeypatch.delenv(SECRET_ENV, raising=False)
    path = _write_env_file(tmp_path, f"{SECRET_ENV}={LOADED}\n")
    monkeypatch.setattr(auth, "default_local_secret_path", lambda: path)
    auth.load_local_secret()
    assert os.environ[SECRET_ENV] == LOADED
