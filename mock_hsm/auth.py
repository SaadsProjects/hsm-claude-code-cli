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
import time

from mock_hsm import db

_SECRET = b"demo-shared-secret-not-for-production"
_TTL_SECONDS = 3600


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
    sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


class TokenError(Exception):
    pass


def verify_token(token: str) -> dict:
    try:
        payload, sig = token.split(".")
    except ValueError:
        raise TokenError("malformed token") from None
    expected_sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
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
