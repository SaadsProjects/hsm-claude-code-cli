"""
Bridge the hosted signing secret into the environment (unit U3, US2.5).

``mock_hsm.auth`` reads ``HSM_SIGNING_SECRET`` from the environment only and
stays standard-library only, so the Streamlit-specific step lives here. On
every rerun, before the gate, the secret is taken from the first source that
has it:

1. an exported value, which this module never overwrites;
2. ``st.secrets["HSM_SIGNING_SECRET"]`` when the variable is unset or empty
   (the hosted apps);
3. ``.env.local`` through ``mock_hsm.auth.load_local_secret`` (local runs).

Streamlit itself copies every top-level string secret into ``os.environ``
when it loads ``secrets.toml``, before this bridge runs and over any exported
value. So a ``HSM_SIGNING_SECRET`` line in ``secrets.toml`` replaces an
exported one, and removing that line while the app runs unsets the variable
for the rest of the process. The committed example leaves the key unset, so a
local run keeps the exported value or ``.env.local``.

Hosted secrets that can't be read count as absent (BR1.5). No value is ever
logged or shown.
"""

from __future__ import annotations

import hmac
import logging
import os

import streamlit as st

from mock_hsm.auth import SECRET_ENV, load_local_secret

log = logging.getLogger(__name__)


def read_hosted_secrets() -> dict:
    """The app's Streamlit secrets as a plain dict, or ``{}`` when there is no
    secrets file or it doesn't parse."""
    try:
        return st.secrets.to_dict()
    except Exception as exc:  # noqa: BLE001 -- unreadable secrets count as absent, and the gate then shows Screen 5
        log.debug("hosted secrets unavailable: %s", type(exc).__name__)
        return {}


def bridge_signing_secret(hosted) -> None:
    if not os.environ.get(SECRET_ENV):
        value = hosted.get(SECRET_ENV)
        if isinstance(value, str) and value:
            os.environ[SECRET_ENV] = value
            return
    load_local_secret()


def cookie_secret_conflict(signing, cookie) -> bool:
    """True when the token-signing secret and the sign-in cookie secret are
    the same non-empty value; each must be unique (team.md Deployment)."""
    if not (isinstance(signing, str) and isinstance(cookie, str) and signing and cookie):
        return False
    return hmac.compare_digest(signing.encode(), cookie.encode())
