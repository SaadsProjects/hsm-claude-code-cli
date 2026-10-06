"""
Stable markers for the dashboard's screens and controls (contract C6).

The app uses each value as a container key or a button's widget key, so the
AppTest suite, the browser tests and the post-deploy check all find the same
element the same way. Values are never reused for a different element, and
removing or renaming one changes every consumer. Constants only: this module
imports nothing else and never Streamlit.
"""

from __future__ import annotations

SIGN_IN_SCREEN = "hsm-sign-in-screen"
SIGN_IN_BUTTON = "hsm-sign-in-button"
REFUSAL_SCREEN = "hsm-refusal-screen"
UNAVAILABLE_SCREEN = "hsm-unavailable-screen"
BACKEND_FAILED_SCREEN = "hsm-backend-failed-screen"
ACCOUNT_SECTION = "hsm-account-section"
SIGN_OUT_BUTTON = "hsm-sign-out-button"
RESET_BANNER = "hsm-reset-banner"
BUILD_CAPTION = "hsm-build-caption"
APP_TABS = "hsm-app-tabs"
