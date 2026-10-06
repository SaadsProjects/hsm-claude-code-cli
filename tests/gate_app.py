"""
The one way to build a dashboard ``AppTest`` (plan D6; NFR3.11, AC4.8.1).

``gate_app`` gives the app dummy sign-in settings and an allowlist as
``AppTest`` secrets, and patches the identity seam in ``dashboard.auth_gate``
(``current_identity``, ``sign_in``, ``sign_out``) to a fake identity, allowed
by default. Nothing else of the gate is patched, so the dashboard runs through
the real gate, and sign-out still runs ``end_visitor_session``.

This module is not collected as tests (its name doesn't start with
``test_``). The signing secret comes from tests/conftest.py.
"""

import copy
import sys
from dataclasses import dataclass, field
from pathlib import Path

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import auth_gate

ALLOWED_EMAIL = "allowed@example.com"
# The five C7 sign-in keys, placeholders only. The cookie secret is fixed and
# so always differs from the per-run signing secret (tests/conftest.py).
DUMMY_AUTH = {
    "redirect_uri": "http://localhost:8501/oauth2callback",
    "cookie_secret": "test-cookie-secret-not-the-signing-secret",
    "google": {
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-client-secret",
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
    },
}
SIGNED_OUT = auth_gate.Identity(signed_in=False, email=None, email_verified=None)


def identity(email=ALLOWED_EMAIL, verified=True, signed_in=True):
    return auth_gate.Identity(signed_in=signed_in, email=email, email_verified=verified)


def allowed_identity():
    return identity()


def default_secrets():
    return {"auth": copy.deepcopy(DUMMY_AUTH), "HSM_ALLOWED_EMAILS": [ALLOWED_EMAIL]}


@dataclass
class Seam:
    """The fake identity provider. ``identity`` is an ``Identity`` or a
    callable that returns one (or raises). ``calls`` records ``sign_in`` and
    ``sign_out``; a fake sign-out signs the visitor out, as Google's would."""

    identity: object
    calls: list = field(default_factory=list)
    sign_out_error: BaseException | None = None

    def current_identity(self):
        return self.identity() if callable(self.identity) else self.identity

    def sign_in(self):
        self.calls.append("sign_in")

    def sign_out(self):
        self.calls.append("sign_out")
        if self.sign_out_error is not None:
            raise self.sign_out_error
        self.identity = SIGNED_OUT


def gate_app(path, monkeypatch, identity=None, secrets=None, timeout=30):
    """An ``AppTest`` of ``path`` behind the gate, not yet run. The seam is
    reachable as ``at.seam``, so a test can change the identity between runs."""
    at = AppTest.from_file(str(path), default_timeout=timeout)
    secrets = default_secrets() if secrets is None else secrets
    # AppTest swaps in its own secrets only when the dict is non-empty; an
    # unused key keeps a developer's real secrets.toml out of the test.
    at.secrets = secrets or {"_gate_app_no_secrets": ""}
    seam = Seam(identity=allowed_identity() if identity is None else identity)
    monkeypatch.setattr(auth_gate, "current_identity", seam.current_identity)
    monkeypatch.setattr(auth_gate, "sign_in", seam.sign_in)
    monkeypatch.setattr(auth_gate, "sign_out", seam.sign_out)
    at.seam = seam
    return at
