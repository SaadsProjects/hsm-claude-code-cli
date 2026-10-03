"""
Per-kind form definitions for the dashboard's Manage data tab (unit U4).

The five data sets, their 11 kinds of record, and for each kind the fields a
form asks for, how each field is entered, which kind a reference field
points at, and the numbered line slots that stand in for row editors
(security-design.md, Form values). ``field_key`` names every form widget and
``build_record`` turns the widgets' values into the record the backend gets.

The fields mirror ``mock_hsm.writes.KINDS``; tests/test_dashboard_units.py
fails on drift. Nothing here imports mock_hsm or Streamlit: the backend
decides every rule, and these definitions only shape the forms.
"""
import json
from dataclasses import dataclass

# The fixed GL code list (U1 BR5.2). The shared client has no GL code call, so
# the dashboard holds it to fill the selector; the backend still checks it.
GL_CODES = ("GL-BEV", "GL-FOOD")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# The base-unit option that names the unit itself (BR2.4: a unit may be its
# own base). build_record replaces it with the unit's own id.
SELF_BASE = "(itself)"

# Line slots for recipe lines and vendor price lists (NFR-design review R-12).
MIN_SLOTS = 10
EXTRA_SLOTS = 3

# Input types: text, number, whole (a whole number), ref (a dashboard-added
# record of ``ref``), gl_code, days, lines (recipe line slots) and
# price_list (raw material and price slots).
TEXT, NUMBER, WHOLE, REF, GL_CODE, DAYS_INPUT, LINES, PRICE_LIST = (
    "text", "number", "whole", "ref", "gl_code", "days", "lines", "price_list")


@dataclass(frozen=True)
class FormField:
    """One field of a kind's form. ``name`` is the record's field name."""

    name: str
    label: str
    input: str
    ref: str | None = None


@dataclass(frozen=True)
class SlotPart:
    """One input of a line slot (a recipe line or a price-list entry)."""

    name: str
    label: str
    input: str
    ref: str | None = None


@dataclass(frozen=True)
class KindForm:
    """The form definition of one kind of record."""

    name: str
    label: str
    data_set: str
    scope: str          # "shared" or "site"
    key: str            # the record's key field
    key_mode: str       # "typed", "ref" (the referenced record's id) or "generated"
    fields: tuple       # FormFields, key first unless generated

    @property
    def site_scoped(self):
        return self.scope == "site"

    def field(self, name):
        return next(fld for fld in self.fields if fld.name == name)


LINE_PARTS = (
    SlotPart("raw_material_id", "Raw material", REF, "raw_material"),
    SlotPart("qty", "Quantity", NUMBER),
    SlotPart("uom", "Unit", REF, "uom"),
)
PRICE_PARTS = (
    SlotPart("raw_material_id", "Raw material", REF, "raw_material"),
    SlotPart("price", "Price", NUMBER),
)
SLOT_PARTS = {LINES: LINE_PARTS, PRICE_LIST: PRICE_PARTS}

_STOCK = (FormField("raw_material_id", "Raw material", REF, "raw_material"), FormField("qty", "Quantity", NUMBER))

KIND_FORMS = {form.name: form for form in (
    KindForm("menu_item", "menu item", "Menu", "shared", "menu_item_id", "typed", (
        FormField("menu_item_id", "Menu item id", TEXT), FormField("name", "Name", TEXT),
        FormField("gl_code", "GL code", GL_CODE))),
    KindForm("recipe", "recipe", "Menu", "shared", "menu_item_id", "ref", (
        FormField("menu_item_id", "Menu item", REF, "menu_item"), FormField("lines", "Lines", LINES))),
    KindForm("raw_material", "raw material", "Ingredients and suppliers", "shared", "raw_material_id", "typed", (
        FormField("raw_material_id", "Raw material id", TEXT), FormField("name", "Name", TEXT),
        FormField("uom", "Unit", REF, "uom"))),
    KindForm("uom", "unit of measure", "Ingredients and suppliers", "shared", "uom_id", "typed", (
        FormField("uom_id", "Unit id", TEXT), FormField("name", "Name", TEXT),
        FormField("base", "Base unit", REF, "uom"), FormField("factor_to_base", "Factor to base", NUMBER))),
    KindForm("vendor", "vendor", "Ingredients and suppliers", "shared", "vendor_id", "typed", (
        FormField("vendor_id", "Vendor id", TEXT), FormField("name", "Name", TEXT),
        FormField("lead_time_days", "Lead time (days)", WHOLE),
        FormField("price_list", "Price list", PRICE_LIST, "raw_material"),
        FormField("min_order_value", "Minimum order value", NUMBER))),
    KindForm("employee", "employee", "Staff", "site", "employee_id", "generated", (
        FormField("name", "Name", TEXT), FormField("job_code", "Job code", REF, "job_code"),
        FormField("hourly_rate", "Hourly rate", NUMBER),
        FormField("max_weekly_hours_preference", "Max weekly hours", WHOLE),
        FormField("available_days", "Available days", DAYS_INPUT))),
    KindForm("job_code", "job code", "Staff", "shared", "job_code", "typed", (
        FormField("job_code", "Job code", TEXT), FormField("title", "Title", TEXT))),
    KindForm("on_hand", "on-hand count", "Stock levels", "site", "raw_material_id", "ref", _STOCK),
    KindForm("par_level", "par level", "Stock levels", "shared", "raw_material_id", "ref", _STOCK),
    KindForm("reorder_point", "reorder point", "Stock levels", "shared", "raw_material_id", "ref", _STOCK),
    KindForm("labor_rule", "labor rule", "Labor rules", "shared", "jurisdiction", "typed", (
        FormField("jurisdiction", "Jurisdiction", TEXT),
        FormField("weekly_ot_threshold_hours", "Weekly overtime threshold (hours)", NUMBER),
        FormField("daily_ot_threshold_hours", "Daily overtime threshold (hours)", NUMBER),
        FormField("ot_multiplier", "Overtime multiplier", NUMBER),
        FormField("max_consecutive_days", "Max consecutive days", WHOLE),
        FormField("min_rest_hours_between_shifts", "Min rest between shifts (hours)", NUMBER),
        FormField("max_shift_length_hours", "Max shift length (hours)", NUMBER),
        FormField("note", "Note", TEXT))),
)}

DATA_SETS = {}
for _form in KIND_FORMS.values():
    DATA_SETS.setdefault(_form.data_set, []).append(_form.name)
DATA_SETS = {name: tuple(kinds) for name, kinds in DATA_SETS.items()}


def is_region_wide(user):
    """A persona is region-wide when its user-table entry has a non-empty
    ``region_id`` (functional-spec, Region-Wide Personas). Only used to pick
    which controls to show; the backend decides who may write."""
    return bool((user or {}).get("region_id"))


def field_key(mode, kind, site, record, version, field):
    """The Streamlit widget key of one form input (security-design, Form
    values). ``mode`` is add or edit; ``record`` and ``version`` are empty
    for add forms. A slot input's ``field`` is ``<field>.<slot>.<part>``.
    JSON keeps every part distinct, whatever characters a record key holds."""
    return "form:" + json.dumps([mode, kind, site or "", record or "", version or "", field])


def form_key_prefix(mode, kind, site, record, version):
    """The prefix every ``field_key`` of one form starts with."""
    return field_key(mode, kind, site, record, version, "")[:-len('""]')]


def slot_field(field, slot, part):
    return f"{field}.{slot}.{part}"


def slot_count(stored_count=0):
    """Line slots to draw: never fewer than a stored record holds, so an edit
    never truncates it (NFR-design review R-12)."""
    return max(MIN_SLOTS, stored_count + EXTRA_SLOTS)


def stored_slots(kind, field, record):
    """A stored record's line slots as a list of ``{part: value}``."""
    value = (record or {}).get(field.name)
    if field.input == LINES:
        return [dict(line) for line in value or []]
    if field.input == PRICE_LIST:
        return [{"raw_material_id": rm_id, "price": price} for rm_id, price in (value or {}).items()]
    raise ValueError(f"{kind}.{field.name} has no line slots")


def referenced_kinds(kind):
    """The kinds whose dashboard-added records fill this kind's selectors."""
    refs = []
    for fld in KIND_FORMS[kind].fields:
        parts = SLOT_PARTS.get(fld.input, (fld,))
        refs += [part.ref for part in parts if part.input == REF and part.ref not in refs]
    return refs


def _empty(value):
    return value is None or value == "" or value == []


def _slot_is_empty(slot):
    return all(_empty(value) for value in slot.values())


def _price_list(slots):
    """Price-list slots as the backend's ``{raw_material_id: price}`` map. A
    slot with no raw material is sent under an empty id, so the backend
    reports it rather than the dashboard dropping it. A JSON object cannot
    hold one id twice: a repeated raw material keeps its last price."""
    return {slot.get("raw_material_id") or "": slot.get("price") for slot in slots}


def build_record(kind, values):
    """The record a form sends, from ``{field name: widget value}``.

    Line-slot fields take a list of ``{part: value}`` slots; fully empty
    slots are dropped and partial ones are sent as entered. Every other value
    is sent as the widget gave it (the backend checks it). A generated key is
    never sent."""
    form = KIND_FORMS[kind]
    record = {}
    for fld in form.fields:
        value = values.get(fld.name)
        if fld.input in SLOT_PARTS:
            slots = [dict(slot) for slot in value or [] if not _slot_is_empty(slot)]
            value = _price_list(slots) if fld.input == PRICE_LIST else slots
        elif fld.input == DAYS_INPUT:
            value = list(value or [])
        elif kind == "uom" and fld.name == "base" and value == SELF_BASE:
            value = values.get(form.key)
        record[fld.name] = value
    return record


def is_blank(kind, values, skip=()):
    """True when every field the form asks for is empty: the second callback
    of a double click after the add form was cleared (NFR-design review R-11)."""
    for fld in KIND_FORMS[kind].fields:
        if fld.name in skip:
            continue
        value = values.get(fld.name)
        if fld.input in SLOT_PARTS:
            if any(not _slot_is_empty(slot) for slot in value or []):
                return False
        elif not _empty(value):
            return False
    return True
