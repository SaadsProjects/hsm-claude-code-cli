"""
Test-only entry script for the browser tests: the real dashboard/app.py
behind a fake identity (plan K4).

    HSM_TEST_IDENTITY='{"signed_in": false}' streamlit run tests/browser_app.py

Only the identity seam is replaced: ``auth_gate.current_identity`` returns the
identity in the ``HSM_TEST_IDENTITY`` environment variable (JSON with
``signed_in`` and, when signed in, ``email`` and ``email_verified``). The rest
of the gate, the sign-in settings check and the app run as they do hosted, so
Google is never contacted and the app code holds no test hook. A missing or
malformed variable stops the script with an error rather than letting anyone in.

Not collected as tests (its name doesn't start with ``test_``).
"""

import json
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard import auth_gate  # noqa: E402 -- the repo root must be on the path first

IDENTITY_ENV = "HSM_TEST_IDENTITY"


def identity_from_env():
    raw = json.loads(os.environ[IDENTITY_ENV])
    return auth_gate.Identity(
        signed_in=raw["signed_in"] is True,
        email=raw.get("email"),
        email_verified=raw.get("email_verified"),
    )


auth_gate.current_identity = identity_from_env
runpy.run_path(str(ROOT / "dashboard" / "app.py"), run_name="__main__")
