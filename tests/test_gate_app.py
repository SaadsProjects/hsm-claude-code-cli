"""
The shared dashboard AppTest helper (tests/gate_app.py; plan D6, AC4.8.1).

These tests prove the two things every dashboard AppTest relies on: the
helper's secrets, including the nested ``auth`` and ``auth.google`` tables,
reach ``st.secrets`` inside the script, and the identity seam is patched to
the fake identity.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate_app import ALLOWED_EMAIL, DUMMY_AUTH, gate_app, identity

SCRIPT = """
import streamlit as st
from dashboard import auth_gate

st.text(st.secrets["auth"]["google"]["client_id"])
st.text(st.secrets["auth"]["cookie_secret"])
st.text(",".join(st.secrets["HSM_ALLOWED_EMAILS"]))
who = auth_gate.current_identity()
st.text(f"{who.signed_in}|{who.email}|{who.email_verified!r}")
"""


def _script(tmp_path):
    path = tmp_path / "probe.py"
    path.write_text(SCRIPT)
    return str(path)


def test_nested_secrets_reach_the_script(tmp_path, monkeypatch):
    at = gate_app(_script(tmp_path), monkeypatch)
    at.run()
    assert not at.exception, at.exception
    texts = [t.value for t in at.text]
    assert texts[0] == DUMMY_AUTH["google"]["client_id"]
    assert texts[1] == DUMMY_AUTH["cookie_secret"]
    assert texts[2] == ALLOWED_EMAIL


def test_the_seam_reports_the_fake_identity(tmp_path, monkeypatch):
    at = gate_app(_script(tmp_path), monkeypatch)
    at.run()
    assert at.text[3].value == f"True|{ALLOWED_EMAIL}|True"

    at.seam.identity = identity("someone@example.com", verified="true")
    at.run()
    assert at.text[3].value == "True|someone@example.com|'true'"


def test_custom_secrets_replace_the_defaults(tmp_path, monkeypatch):
    at = gate_app(
        _script(tmp_path),
        monkeypatch,
        secrets={
            "auth": {**DUMMY_AUTH, "google": {**DUMMY_AUTH["google"], "client_id": "other"}},
            "HSM_ALLOWED_EMAILS": ["x@y.z"],
        },
    )
    at.run()
    assert [t.value for t in at.text][:3] == ["other", DUMMY_AUTH["cookie_secret"], "x@y.z"]
