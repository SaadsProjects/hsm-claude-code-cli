"""
Simulated identity/token layer.

In real HSM: browser -> Okta (OIDC) -> Firebase Cloud Function -> platform
auth service issues a claims-bearing token -> Apigee fronts every call ->
HSM microservices trust the claims (persona, org_id, site_ids/region_id).

For this demo we collapse that chain into one signed token minted from the
static USERS table (which stands in for the platform OIDC system being the
source of truth for personas). The mock HSM server verifies the signature
and enforces scope exactly like the real services would trust Apigee-passed
claims -- swap this module for a real OIDC/Apigee client and nothing else
in the demo has to change.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from mock_hsm import db

_SECRET = b"demo-shared-secret-not-for-production"
_TTL_SECONDS = 3600

# The signing secret comes only from the environment (Streamlit secrets when
# hosted, .env.local locally via load_local_secret). There is no default: a
# process without a valid secret can't mint or verify a token.
SECRET_ENV = "HSM_SIGNING_SECRET"
MIN_SECRET_BYTES = 32
# SHA-256 of the old secret that was committed to this public repository.
# Equal to the constant in scripts/check_burned_secret.py; only the digest
# lives here, never the value.
BURNED_SECRET_SHA256 = "2afa3c5c080b9584be9548e7d8ac9ac6bc2868c33bf3bf058307f09022a76907"

_REFUSAL_MESSAGES = {
    "missing": (
        f"{SECRET_ENV} is not set. Run scripts/dev-secret.sh to create .env.local for local use, "
        "or set it in the environment (Streamlit secrets when hosted)."
    ),
    "too_short": f"{SECRET_ENV} must be at least {MIN_SECRET_BYTES} bytes; run scripts/dev-secret.sh --force for a new one.",
    "burned": (
        f"{SECRET_ENV} holds the old demo secret, which was published and must never be used; "
        "run scripts/dev-secret.sh --force for a new one."
    ),
}


class SecretMissingError(RuntimeError):
    """No usable signing secret. ``reason`` is ``missing``, ``too_short`` or
    ``burned``. The message names the variable and the rule broken, never the
    value, so it is safe to show in a deny, a tool error or an HTTP body."""

    def __init__(self, reason: str):
        super().__init__(_REFUSAL_MESSAGES[reason])
        self.reason = reason


def _secret_bytes() -> bytes:
    # Read on every call, never cached, so a process never signs with a value
    # its environment no longer holds.
    value = os.environ.get(SECRET_ENV, "")
    if not value:
        raise SecretMissingError("missing")
    raw = value.encode()
    if len(raw) < MIN_SECRET_BYTES:
        raise SecretMissingError("too_short")
    if hmac.compare_digest(hashlib.sha256(raw).hexdigest(), BURNED_SECRET_SHA256):
        raise SecretMissingError("burned")
    return raw


def default_local_secret_path() -> Path:
    """``.env.local`` in the project root, found from this file's location so
    it doesn't depend on the working directory."""
    return Path(__file__).resolve().parents[1] / ".env.local"


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def load_local_secret(path=None) -> None:
    """Local development only: if HSM_SIGNING_SECRET is not in the environment
    at all, take it from the ``HSM_SIGNING_SECRET=<value>`` line of
    ``.env.local`` (written by scripts/dev-secret.sh).

    A variable that is present, even empty, is never overridden. A missing file
    or line does nothing; require_secret() then refuses. Only that one line is
    read: one pair of matching quotes is stripped and nothing is expanded or
    executed. The value is never printed."""
    if SECRET_ENV in os.environ:
        return
    path = Path(path) if path is not None else default_local_secret_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    prefix = f"{SECRET_ENV}="
    for line in (raw.strip() for raw in lines):
        if line.startswith(prefix):
            os.environ[SECRET_ENV] = _unquote(line[len(prefix) :])
            return


def require_secret() -> None:
    """Raise SecretMissingError unless a usable signing secret is set.

    Entry points call this at start-up to fail closed before doing any work;
    mint_token and verify_token run the same checks on every call."""
    _secret_bytes()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def mint_token(user_id: str) -> str:
    user = db.USERS.get(user_id)
    if not user:
        raise ValueError(f"unknown user_id {user_id}")
    claims = {
        "sub": user_id,
        "persona": user["persona"],
        "org_id": user["org_id"],
        "site_ids": user["site_ids"],
        "region_id": user["region_id"],
        "iat": int(time.time()),
        "exp": int(time.time()) + _TTL_SECONDS,
    }
    payload = _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret_bytes(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


class TokenError(Exception):
    pass


def verify_token(token: str) -> dict:
    secret = _secret_bytes()
    try:
        payload, sig = token.split(".")
    except ValueError:
        raise TokenError("malformed token") from None
    expected_sig = _b64(hmac.new(secret, payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected_sig):
        raise TokenError("bad signature")
    claims = json.loads(_unb64(payload))
    if claims["exp"] < time.time():
        raise TokenError("expired")
    return claims


def site_allowed(claims: dict, site_id: str) -> bool:
    if claims["persona"] == "SYSTEM_ADMIN":
        return True
    return site_id in (claims.get("site_ids") or [])


def region_allowed(claims: dict, region_id: str) -> bool:
    if claims["persona"] == "SYSTEM_ADMIN":
        return True
    return claims.get("region_id") == region_id
