"""
The Audit tab (unit U4, WF9, BR5.1).

A read-only list of audit entries, newest first, already filtered by the
backend for the logged-in persona (FR10.2). A page is loaded only when the
loaded entries were emptied (after login, after every write outcome, or by
Refresh), so a plain rerun makes no audit call (NFR4.3). Refresh and Load
older run inline and then rerun (NFR-design Q2: B). The outcome and
kind filters narrow the loaded entries only. There is no edit, delete or
export control (FR9.4).

Entries and their changes are drawn as data frames, which do not interpret
Markdown (NFR1.5); session ids were dropped when the page was loaded (NFR1.4).
"""

import json

import pandas as pd
import streamlit as st

from dashboard import actions, session
from dashboard.safe_text import escape_md

ALL = "All"
OUTCOMES = (ALL, "allowed", "violation")
COLUMNS = (
    ("timestamp", "time"),
    ("user_id", "user"),
    ("persona", "persona"),
    ("action", "action"),
    ("kind", "kind of record"),
    ("record_id", "record"),
    ("site_id", "site"),
    ("outcome", "outcome"),
    ("reason", "reason"),
    ("file_row", "row"),
)


def _frame(entries):
    return pd.DataFrame(
        [{label: entry.get(name) for name, label in COLUMNS} for entry in entries],
        columns=[label for _, label in COLUMNS],
    )


def _flatten(value, prefix=""):
    """An entry's changes as ``(path, value)`` pairs, one per leaf."""
    if isinstance(value, dict) and value:
        pairs = []
        for key, inner in value.items():
            pairs += _flatten(inner, f"{prefix}.{key}" if prefix else str(key))
        return pairs
    return [(prefix or "(value)", json.dumps(value) if isinstance(value, list | dict) else value)]


def _changes(entry):
    pairs = _flatten(entry.get("changes") or {})
    return pd.DataFrame(
        [{"change": path, "value": "" if value is None else str(value)} for path, value in pairs],
        columns=["change", "value"],
    )


def _filtered(entries):
    kinds = sorted({entry.get("kind") for entry in entries if entry.get("kind")})
    outcome, kind = st.columns(2)
    picked_outcome = outcome.selectbox("Outcome", OUTCOMES, key="audit-outcome")
    picked_kind = kind.selectbox("Kind of record", [ALL, *kinds], key="audit-kind")
    return [
        entry
        for entry in entries
        if picked_outcome in (ALL, entry.get("outcome")) and picked_kind in (ALL, entry.get("kind"))
    ]


def render():
    """Draw the Audit tab for the logged-in persona."""
    refresh, older = st.columns(2)
    if refresh.button("Refresh", key="audit-refresh"):
        actions.then_rerun(actions.audit_refresh)
    problem = actions.load_audit()
    if problem is not None:
        st.error(escape_md(problem))
        return
    loaded = session.audit()
    entries = loaded.get("entries", [])
    if loaded.get("next_before") is not None and older.button("Load older", key="audit-load-older"):
        actions.then_rerun(actions.audit_load_older)
    st.caption(f"Showing {escape_md(len(entries))} of {escape_md(loaded.get('total', 0))} entries")
    shown = _filtered(entries)
    st.dataframe(_frame(shown), hide_index=True, width="stretch")
    by_id = {entry["entry_id"]: entry for entry in shown}
    picked = st.selectbox("Entry", list(by_id), index=None, key="audit-entry")
    if picked is not None:
        st.markdown(f"**Changes in entry {escape_md(picked)}**")
        st.dataframe(_changes(by_id[picked]), hide_index=True, width="stretch")
