"""
The Manage data tab (unit U4, WF4-WF6).

Pick a data set and a kind of record, see its records with who added and
changed them, then add, edit, delete or bulk-upload records. Every button
runs its action from ``dashboard.actions`` inline, where it is drawn, and
then reruns the script (``actions.then_rerun``), so the next completed
render shows the outcome (NFR2.3, NFR-design Q2: B). Records are read
through this browser session's own cache (``session.records_for``, 60 s;
Q3: B). The backend decides every rule; this tab
only hides controls the persona cannot use (Q5) and never refuses a value
itself (BR2.1, NFR1.1).

Untrusted text (record keys, backend messages) reaches Markdown-capable
elements only through ``escape_md``; record values are drawn as data frames
(NFR1.5). Every client comes from ``session.client_for`` (NFR6.2).
"""
import json

import pandas as pd
import streamlit as st

from agents.hsm_client import HsmApiError, HsmUnavailable
from dashboard import actions, kind_forms, session
from dashboard.kind_forms import KIND_FORMS
from dashboard.safe_text import escape_md

HELD_NOTE = "Confirm or discard the unsaved write first"
READ_ONLY_NOTE = "Only regional roles can change this data."
META_COLUMNS = (("created_by", "added by"), ("created_at", "added at"), ("updated_by", "changed by"),
                ("updated_at", "changed at"), ("origin", "origin"), ("version", "version"))


def load_records(user_id, kind, site):
    """``{records, meta}`` of one kind, from this session's cache: reused for
    60 s, cleared after this session's write outcomes, by Refresh data and on
    logout (performance-design, Caching)."""
    return session.records_for(user_id, kind, site)


def _read_error(error):
    return actions.UNREACHABLE if isinstance(error, HsmUnavailable) else error.message


def _kind_changed():
    """Picking another data set or kind clears the delete prompt and the
    notice, but keeps an unconfirmed write (frontend-components, Kind changes)."""
    session.set_item("pending_delete", None)
    session.set_notice(None)


def _cell(value):
    """Nested values (recipe lines, price lists, days) as one text cell."""
    return json.dumps(value) if isinstance(value, dict | list) else value


def _record_frame(form, listing):
    meta = listing["meta"]
    rows = []
    for record in listing["records"]:
        row = {name: _cell(value) for name, value in record.items()}
        record_meta = meta.get(record.get(form.key), {})
        row.update({label: record_meta.get(name) for name, label in META_COLUMNS})
        rows.append(row)
    return pd.DataFrame(rows)


def _site_of(form, site_id):
    return site_id if form.site_scoped else None


# ------------------------------------------------------------- references

def _reference_options(user_id, kind):
    """``{referenced kind: [dashboard-added keys]}``. Only dashboard-added
    records can be referenced (FR2.6); all referenced kinds are shared."""
    options = {}
    for ref in kind_forms.referenced_kinds(kind):
        listing = load_records(user_id, ref, None)
        key = KIND_FORMS[ref].key
        options[ref] = [record[key] for record in listing["records"]
                        if listing["meta"].get(record[key], {}).get("origin") == "dashboard"]
    return options


def _missing_references(kind, options):
    """Referenced kinds with no dashboard-added record. A unit of measure can
    name itself as its base, so its own kind is never missing."""
    return [ref for ref, keys in options.items() if not keys and not (kind == "uom" and ref == "uom")]


# ----------------------------------------------------------------- fields

def _ref_options(kind, fld, options):
    keys = list(options.get(fld.ref, []))
    if kind == "uom" and fld.name == "base":
        keys = [kind_forms.SELF_BASE, *keys]
    return keys


def _input(key, label, spec, kind, options, default):
    """Draw one typed input. ``spec`` is a FormField or a SlotPart."""
    if spec.input == kind_forms.TEXT:
        st.text_input(label, value="" if default is None else str(default), key=key)
    elif spec.input == kind_forms.NUMBER:
        st.number_input(label, value=None if default is None else float(default), format="%g", key=key)
    elif spec.input == kind_forms.WHOLE:
        st.number_input(label, value=None if default is None else int(default), step=1, key=key)
    elif spec.input in (kind_forms.REF, kind_forms.GL_CODE):
        choices = (list(kind_forms.GL_CODES) if spec.input == kind_forms.GL_CODE
                   else _ref_options(kind, spec, options))
        if default is not None and default not in choices:
            choices.append(default)  # a stored value always stays selectable
        st.selectbox(label, choices, index=choices.index(default) if default is not None else None,
                     key=key)
    elif spec.input == kind_forms.DAYS_INPUT:
        st.multiselect(label, kind_forms.DAYS, default=list(default or []), key=key)
    else:  # pragma: no cover -- slot fields are drawn by _slots
        raise ValueError(f"unknown input {spec.input}")


def _slots(mode, kind, site, record_id, version, fld, options, stored):
    """Numbered line slots for recipe lines and price lists (R-12): never
    fewer than a stored record holds. Returns how many were drawn."""
    count = kind_forms.slot_count(len(stored))
    parts = kind_forms.SLOT_PARTS[fld.input]
    st.caption(escape_md(fld.label))
    for slot in range(count):
        values = stored[slot] if slot < len(stored) else {}
        for column, part in zip(st.columns(len(parts)), parts, strict=True):
            with column:
                key = kind_forms.field_key(mode, kind, site, record_id, version,
                                           kind_forms.slot_field(fld.name, slot, part.name))
                _input(key, escape_md(f"{part.label} {slot + 1}"), part, kind, options, values.get(part.name))
    return count


def _fields(mode, kind, site, record_id, version, options, record=None):
    """Draw a form's inputs; returns the slot counts its callback needs."""
    form = KIND_FORMS[kind]
    slots = {}
    for fld in form.fields:
        if mode == "edit" and fld.name == form.key:
            continue  # the key cannot be changed; it is shown above the form
        if fld.input in kind_forms.SLOT_PARTS:
            stored = kind_forms.stored_slots(kind, fld, record) if record else []
            slots[fld.name] = _slots(mode, kind, site, record_id, version, fld, options, stored)
        else:
            key = kind_forms.field_key(mode, kind, site, record_id, version, fld.name)
            _input(key, escape_md(fld.label), fld, kind, options, (record or {}).get(fld.name))
    return slots


# ------------------------------------------------------------------ forms

def _add_form(kind, site, options, missing, region_wide, held):
    form = KIND_FORMS[kind]
    with st.form(key=f"manage-{kind}-add-form"):
        st.markdown(f"**Add a {escape_md(form.label)}**")
        version = session.add_form_version(kind, site)
        slots = _fields("add", kind, site, None, version, options)
        for ref in missing:  # the submit stays disabled until the list has a record (WF5 step 1)
            label = KIND_FORMS[ref].label
            if region_wide:
                st.caption(f"Add a {escape_md(label)} first")
            else:
                st.caption(f"No dashboard-added {escape_md(label)} exists yet; a regional role must add one first")
        if st.form_submit_button("Add", key=f"manage-{kind}-add-submit", disabled=held or bool(missing)):
            actions.then_rerun(actions.submit_add, kind, site, slots, version)


def _edit_form(kind, site, listing, options, held):
    form = KIND_FORMS[kind]
    records = {record[form.key]: record for record in listing["records"]}
    editable = [key for key in records if listing["meta"].get(key, {}).get("origin") == "dashboard"]
    if not editable:
        st.caption("No dashboard-added records to edit yet. Seeded records are read-only.")
        return
    picked = st.selectbox("Record to edit", editable, index=None, key=f"manage-{kind}-edit-pick@{site or ''}")
    if picked is None:
        return
    version = listing["meta"][picked]["version"]
    with st.form(key=f"manage-{kind}-edit-form"):
        st.markdown(f"**Edit {escape_md(form.label)} {escape_md(picked)}** (version {escape_md(version)})")
        slots = _fields("edit", kind, site, picked, version, options, records[picked])
        if st.form_submit_button("Save", key=f"manage-{kind}-edit-submit", disabled=held):
            actions.then_rerun(actions.submit_edit, kind, site, picked, version, slots)


def _delete_controls(kind, site, listing, held):
    """Delete only this login session's records (Q3), after a confirmation (Q4)."""
    form = KIND_FORMS[kind]
    added = session.added().get(session.added_key(kind, site, form.site_scoped), [])
    present = [key for key in added if key in listing["meta"]]
    if not present:
        return
    st.markdown("**Records you added this session**")
    for key in present:
        name, button = st.columns([4, 1])
        name.caption(escape_md(key))
        if button.button("Delete", key=f"manage-{kind}-delete-{key}", disabled=held):
            actions.then_rerun(actions.ask_delete, kind, site, key, listing["meta"][key]["version"])
    pending = session.pending_delete()
    if pending and (pending["kind"], pending["site"]) == (kind, site):
        st.warning(f"Delete {escape_md(pending['record_id'])}?")
        confirm, cancel = st.columns(2)
        if confirm.button("Confirm", key=f"manage-{kind}-delete-confirm", disabled=held):
            actions.then_rerun(actions.confirm_delete)
        if cancel.button("Cancel", key=f"manage-{kind}-delete-cancel"):
            actions.then_rerun(actions.cancel_delete)


def _upload_panel(user_id, kind, site, held):
    """The CSV panel (WF6): the template is fetched once per kind and site."""
    st.markdown("**Bulk upload from a CSV file**")
    templates = session.templates()
    if (kind, site) not in templates:
        try:
            templates[(kind, site)] = session.client_for(user_id).csv_template(kind, site_id=site)
        except HsmApiError as e:
            st.error(escape_md(_read_error(e)))
            return
    template = templates[(kind, site)]
    st.download_button("Download template", data=template["csv"], file_name=f"{kind}.csv", mime="text/csv",
                       key=f"manage-{kind}-template")
    uploader_key = session.uploader_key(kind, site)
    st.file_uploader("CSV file", type=["csv"], key=uploader_key)
    if st.button("Upload", key=f"manage-{kind}-upload", disabled=held):
        actions.then_rerun(actions.upload, kind, site, uploader_key)


# ------------------------------------------------------------------- tab

def _pick_kind():
    data_set = st.selectbox("Data set", list(kind_forms.DATA_SETS), key="manage-data-set",
                            on_change=_kind_changed)
    return st.selectbox("Kind of record", kind_forms.DATA_SETS[data_set], key=f"manage-kind@{data_set}",
                        on_change=_kind_changed, format_func=lambda kind: KIND_FORMS[kind].label)


def render(user, site_id):
    """Draw the Manage data tab for the logged-in ``user`` at ``site_id``."""
    kind = _pick_kind()
    form = KIND_FORMS[kind]
    site = _site_of(form, site_id)
    try:
        listing = load_records(user["user_id"], kind, site)
    except HsmApiError as e:
        st.error(escape_md(_read_error(e)))
        return
    st.dataframe(_record_frame(form, listing), hide_index=True, width="stretch")
    region_wide = kind_forms.is_region_wide(user)
    if not form.site_scoped and not region_wide:
        st.info(escape_md(READ_ONLY_NOTE))
        return
    try:
        options = _reference_options(user["user_id"], kind)
    except HsmApiError as e:
        st.error(escape_md(_read_error(e)))
        return
    held = session.pending_retry() is not None
    if held:
        st.caption(escape_md(HELD_NOTE))
    _add_form(kind, site, options, _missing_references(kind, options), region_wide, held)
    _edit_form(kind, site, listing, options, held)
    _delete_controls(kind, site, listing, held)
    _upload_panel(user["user_id"], kind, site, held)
