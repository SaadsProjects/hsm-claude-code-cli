"""
Dashboard data writes for the mock HSM backend (unit U1).

Login sessions plus add / update / delete / bulk / CSV-template operations
for the 11 writable kinds of record, with metadata kept beside the records.
Route handlers in ``mock_hsm/server.py`` stay thin and call the functions
here, so every rule is testable without HTTP.

Components (NFR design, logical-components.md):
- KindCatalog   -- ``KINDS``: fields, types, references, scope, collection,
                   CSV columns and cell forms of each kind.
- RecordStore   -- reads and writes the existing ``db`` collections, so the
                   read routes, the reorder calculation and the Claude Code
                   tools see added records unchanged (BR11.1).
- MetaStore     -- one RecordMeta per stored record; seeded meta is built
                   at import (BR7.1).
- IdCounters    -- per-site generated employee ids (BR8.4, NFR2.4).
- Validator     -- envelope, nesting depth, fields, injection shapes, cell
                   forms and references; collects every problem (BR4, BR5).
- SessionStore, QuotaStore, RequestLog -- in-memory, swept and bounded.
- AuditAdapter  -- builds U2 entries that always fit ``audit.append`` and
                   ``audit.append_batch`` and maps failures to 503.
- WriteService  -- ``write``, ``bulk``, ``start_session``, ``end_session``,
                   ``session_status`` and ``template``.

Every operation runs while holding ``db._lock`` (an RLock). U2's audit lock
is only ever taken inside it, so the lock order is db._lock -> audit lock.
One write attempt is checked, has any id allocated, is audited and is then
applied as one step under the lock (BR8.2).

Request handling order (NFR design, security-design.md, final): envelope,
replay, session (after the idle sweep), request id, then the functional
checks of BR8.1 steps 4-14. For bulk files, the 1-500 row-count check runs
right after replay, before any refusal is spread across rows (NFR2.1).

State is in memory and lost on restart. The clock is injectable
(``set_clock``) and ``reset_for_tests`` returns everything to its seeded
state.
"""
import copy
import hashlib
import json
import math
import re
import secrets
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from mock_hsm import audit, db
from mock_hsm.auth import site_allowed

# ------------------------------------------------------------------ constants
ENTRY_LIMIT = 100                       # BR6.1: accepted adds per kind per session
IDLE_TIMEOUT = timedelta(minutes=15)    # BR1.2: session idle limit
REQUEST_TTL = timedelta(minutes=15)     # BR9.1: request records are kept this long
REQUEST_CAP = 1000                      # NFR1.8: request records kept per user
BULK_MIN_ROWS = 1                       # BR10.5
BULK_MAX_ROWS = 500                     # BR10.5
MAX_DEPTH = 32                          # NFR2.2: nesting limit for a data-write body
MAX_TEXT = 100                          # BR4.2: text and id length
MAX_NUMBER = 1_000_000_000              # BR4.3: largest value of any number field, so float math stays finite
MAX_NUMBER_TEXT = 32                    # BR4.3: longest CSV number cell read before parsing
MAX_REQUEST_ID = 100                    # BR9.2: request id length
MAX_BODY_BYTES = 1024 * 1024            # dispatcher: largest body that is read and parsed
MAX_DRAIN_BYTES = 8 * 1024 * 1024       # dispatcher: largest body drained before a 400
DRAIN_CHUNK_BYTES = 64 * 1024           # dispatcher: drain chunk size
MAX_AUDIT_TEXT = 1024                   # clip for every text value of an audit entry (NFR2.7)
MAX_ENVELOPE_PROBLEMS = 50              # problems listed for one malformed request
IDLE_TIMEOUT_SECONDS = int(IDLE_TIMEOUT.total_seconds())

SOURCE = "dashboard"
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
RESERVED_IDS = frozenset({"template", "bulk"})
WIRE_META_FIELDS = ("origin", "created_by", "created_at", "updated_by", "updated_at", "version")

# Stored in place of attempted values that can't be recorded as JSON at all
# (a body nested too deeply, a body that is not an object, review R-04).
UNRECORDABLE_CHANGES = {"truncated": True, "unserializable": True}


# ---------------------------------------------------------------------- clock

def _utc_now():
    return datetime.now(timezone.utc)


_clock = {"now": _utc_now}


def set_clock(clock=None):
    """Use ``clock`` (returns an aware UTC datetime) for sessions, request
    records and metadata timestamps; ``None`` restores the real clock."""
    _clock["now"] = clock or _utc_now


def _now():
    return _clock["now"]()


def _iso(ts):
    return ts.astimezone(timezone.utc).isoformat()


# ------------------------------------------------------------ shared helpers

def clip_text(text):
    """Bound a client-influenced string (an error message echoing a huge id,
    say) so an audit entry always fits the audit cap. The result, marker
    included, is at most MAX_AUDIT_TEXT characters, so the audit module's own
    1,024-character cut (NFR2.3) never removes the marker. ``None`` passes."""
    if text is None or len(text) <= MAX_AUDIT_TEXT:
        return text
    marker = "...(truncated)"
    return text[:MAX_AUDIT_TEXT - len(marker)] + marker


def json_safe(value):
    """json.loads accepts NaN/Infinity but the audit trail stores strict JSON,
    so record non-finite floats as their repr rather than refusing the entry."""
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


# A ``changes`` value nests at most one level deeper than the 32-level body
# it was taken from ({"record": <record>}); anything deeper is unrecordable.
_MAX_CHANGES_DEPTH = MAX_DEPTH + 1


class _Unrecordable(ValueError):
    """A value that cannot be stored as strict JSON in an audit entry."""


def _clip_deep(value, depth):
    if isinstance(value, str):
        return clip_text(value)
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict | list) and depth > _MAX_CHANGES_DEPTH:
        raise _Unrecordable(f"nested deeper than {_MAX_CHANGES_DEPTH} levels")
    if isinstance(value, dict):
        clipped = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _Unrecordable("object key is not text")
            clipped[clip_text(key)] = _clip_deep(item, depth + 1)
        return clipped
    if isinstance(value, list):
        return [_clip_deep(item, depth + 1) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    raise _Unrecordable(f"cannot store {type(value).__name__} as JSON")


def clip_value(value):
    """A copy of ``value`` safe to send as an audit entry's ``changes``
    (BR8.3, NFR2.7). Every text value and every object key is clipped to
    MAX_AUDIT_TEXT characters, marker included; non-finite numbers are kept as
    their repr, as ``json_safe`` does. A value that still cannot be stored as
    strict JSON (too deep, a non-text key, a set, ...) becomes the marker.
    Recursion is bounded by the 32-level body cap, so it never nears Python's
    own limit. ``None`` passes."""
    if value is None:
        return None
    try:
        clipped = _clip_deep(value, 1)
        json.dumps(clipped, allow_nan=False)
    except (_Unrecordable, TypeError, ValueError, RecursionError):
        return dict(UNRECORDABLE_CHANGES)
    return clipped


def _clip_optional(value):
    """``clip_text`` for a text field of an entry; anything not text is None."""
    return clip_text(value) if isinstance(value, str) and value else None


def _bounded(value):
    """Text of 1-100 characters, else None (audit identity fields, review R-13)."""
    return value if isinstance(value, str) and 1 <= len(value) <= MAX_TEXT else None


_CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f]")


def _log_key(key):
    """Sanitized record key for a log line: no control characters, at most 100
    characters, or ``none`` (NFR2.5)."""
    if not isinstance(key, str):
        return "none"
    return _CONTROL_RE.sub("", key)[:MAX_TEXT] or "none"


def _log_error(message):
    """One stderr line. Never record contents, tokens or session ids."""
    print(f"[mock-hsm] ERROR writes: {message}", file=sys.stderr, flush=True)


def _known_site(site_id):
    return site_id if isinstance(site_id, str) and site_id in db.SITES else None


def _whole(value, minimum):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _region_wide(claims):
    return bool(claims.get("region_id")) or claims.get("persona") == "SYSTEM_ADMIN"


# ================================================================ KindCatalog

@dataclass(frozen=True)
class Field:
    """One attribute of a kind. ``type`` is text, id, ref, number, integer,
    gl_code, days, price_list or lines; ``ref`` names the referenced kind."""

    name: str
    type: str
    ref: str | None = None


@dataclass(frozen=True)
class Kind:
    """Static schema of one writable kind (DataSetSchema in entities.md)."""

    name: str
    label: str
    scope: str            # "shared" or "site"
    attr: str             # the db collection holding it
    key: str              # key field
    key_mode: str         # "typed" (user types it), "ref" (the referenced record's id) or "generated"
    shape: str            # "record" (a dict), "lines" (recipe line list) or "qty" (a bare number)
    fields: tuple         # the fields a request supplies, key first unless generated
    csv_columns: tuple
    collection_path: str
    item_path: str


_N, _I, _T = "number", "integer", "text"
_LINE_FIELDS = (Field("raw_material_id", "ref", "raw_material"), Field("qty", _N), Field("uom", "ref", "uom"))
_RECIPE_ROW_FIELDS = (Field("menu_item_id", "ref", "menu_item"), *_LINE_FIELDS)
_STOCK_FIELDS = (Field("raw_material_id", "ref", "raw_material"), Field("qty", _N))

KINDS = {kind.name: kind for kind in (
    Kind("menu_item", "menu item", "shared", "MENU_ITEMS", "menu_item_id", "typed", "record",
         (Field("menu_item_id", "id"), Field("name", _T), Field("gl_code", "gl_code")),
         ("menu_item_id", "name", "gl_code"),
         "/catalog/menu-items", "/catalog/menu-items/{record_id}"),
    Kind("recipe", "recipe", "shared", "RECIPES", "menu_item_id", "ref", "lines",
         (Field("menu_item_id", "ref", "menu_item"), Field("lines", "lines")),
         ("menu_item_id", "raw_material_id", "qty", "uom"),
         "/inventory/recipes", "/inventory/recipes/{record_id}"),
    Kind("raw_material", "raw material", "shared", "RAW_MATERIALS", "raw_material_id", "typed", "record",
         (Field("raw_material_id", "id"), Field("name", _T), Field("uom", "ref", "uom")),
         ("raw_material_id", "name", "uom"),
         "/inventory/raw-materials", "/inventory/raw-materials/{record_id}"),
    Kind("uom", "unit of measure", "shared", "UOM", "uom_id", "typed", "record",
         (Field("uom_id", "id"), Field("name", _T), Field("base", "ref", "uom"), Field("factor_to_base", _N)),
         ("uom_id", "name", "base", "factor_to_base"),
         "/inventory/uom", "/inventory/uom/{record_id}"),
    Kind("vendor", "vendor", "shared", "VENDORS", "vendor_id", "typed", "record",
         (Field("vendor_id", "id"), Field("name", _T), Field("lead_time_days", _I),
          Field("price_list", "price_list", "raw_material"), Field("min_order_value", _N)),
         ("vendor_id", "name", "lead_time_days", "price_list", "min_order_value"),
         "/inventory/vendors", "/inventory/vendors/{record_id}"),
    Kind("employee", "employee", "site", "EMPLOYEES", "employee_id", "generated", "record",
         (Field("name", _T), Field("job_code", "ref", "job_code"), Field("hourly_rate", _N),
          Field("max_weekly_hours_preference", _I), Field("available_days", "days")),
         ("name", "job_code", "hourly_rate", "max_weekly_hours_preference", "available_days"),
         "/labor/sites/{site_id}/employees", "/labor/sites/{site_id}/employees/{record_id}"),
    Kind("job_code", "job code", "shared", "JOB_CODES", "job_code", "typed", "record",
         (Field("job_code", "id"), Field("title", _T)),
         ("job_code", "title"),
         "/sales/job-codes", "/sales/job-codes/{record_id}"),
    Kind("on_hand", "on-hand count", "site", "ON_HAND", "raw_material_id", "ref", "qty",
         _STOCK_FIELDS, ("raw_material_id", "qty"),
         "/inventory/sites/{site_id}/on-hand", "/inventory/sites/{site_id}/on-hand/{record_id}"),
    Kind("par_level", "par level", "shared", "PAR_LEVELS", "raw_material_id", "ref", "qty",
         _STOCK_FIELDS, ("raw_material_id", "qty"),
         "/inventory/par-levels", "/inventory/par-levels/{record_id}"),
    Kind("reorder_point", "reorder point", "shared", "REORDER_POINTS", "raw_material_id", "ref", "qty",
         _STOCK_FIELDS, ("raw_material_id", "qty"),
         "/inventory/reorder-points", "/inventory/reorder-points/{record_id}"),
    Kind("labor_rule", "labor rule", "shared", "LABOR_RULES_BY_JURISDICTION", "jurisdiction", "typed", "record",
         (Field("jurisdiction", "id"), Field("weekly_ot_threshold_hours", _N), Field("daily_ot_threshold_hours", _N),
          Field("ot_multiplier", _N), Field("max_consecutive_days", _I),
          Field("min_rest_hours_between_shifts", _N), Field("max_shift_length_hours", _N), Field("note", _T)),
         ("jurisdiction", "weekly_ot_threshold_hours", "daily_ot_threshold_hours", "ot_multiplier",
          "max_consecutive_days", "min_rest_hours_between_shifts", "max_shift_length_hours", "note"),
         "/labor/rules", "/labor/rules/{record_id}"),
)}


def template_for(kind):
    """BR10.4: the kind's CSV columns and header line."""
    return {"columns": list(kind.csv_columns), "csv": ",".join(kind.csv_columns) + "\n"}


# ================================================================ RecordStore
# Writers always replace a stored value; they never mutate one in place, so a
# read that copied a collection under the lock never sees a half change.

def _collection(kind, site_id):
    table = getattr(db, kind.attr)
    return table[site_id] if kind.name == "on_hand" else table


def find(kind, site_id, key):
    """``(True, stored)`` for the record keyed ``key``, else ``(False, None)``.
    A site kind's record is found only at its own site (BR2.3)."""
    if not isinstance(key, str):
        return False, None
    if kind.scope == "site" and site_id not in db.SITES:
        return False, None
    coll = _collection(kind, site_id)
    if key not in coll:
        return False, None
    stored = coll[key]
    if kind.name == "employee" and stored.get("site_id") != site_id:
        return False, None
    return True, stored


def _exists(kind, site_id, key):
    return find(kind, site_id, key)[0]


def iter_keys(kind):
    """Every stored ``(site_id, key)`` of a kind; site_id is None for shared kinds."""
    if kind.name == "on_hand":
        return [(site_id, key) for site_id, table in db.ON_HAND.items() for key in table]
    if kind.name == "employee":
        return [(record.get("site_id"), key) for key, record in db.EMPLOYEES.items()]
    return [(None, key) for key in getattr(db, kind.attr)]


def _meta_site(kind, site_id):
    return site_id if kind.scope == "site" else None


def record_view(kind, site_id, key, stored):
    """The record as a write response shows it (a copy)."""
    if kind.shape == "lines":
        return {"menu_item_id": key, "lines": copy.deepcopy(stored)}
    if kind.shape == "qty":
        view = {"raw_material_id": key, "qty": stored}
        return {"site_id": site_id, **view} if kind.scope == "site" else view
    return copy.deepcopy(stored)


def build_stored(kind, site_id, key, clean):
    """Build the value stored for a record, without touching shared state.
    Update keeps the id and, for site kinds, the site (BR4.1, BR5.4)."""
    if kind.shape == "lines":
        return [dict(line) for line in clean["lines"]]
    if kind.shape == "qty":
        return clean["qty"]
    if kind.name == "employee":
        return {
            "employee_id": key, "name": clean["name"], "site_id": site_id, "job_code": clean["job_code"],
            "hourly_rate": clean["hourly_rate"], "jurisdiction": db.SITES[site_id]["jurisdiction"],
            "max_weekly_hours_preference": clean["max_weekly_hours_preference"],
            "available_days": list(clean["available_days"]),
        }
    stored = {kind.key: key}
    for fld in kind.fields:
        if fld.name != kind.key:
            stored[fld.name] = copy.deepcopy(clean[fld.name])
    return stored


def _swap_collection(kind, site_id, new_table):
    """Install a rebuilt collection with single assignments (bulk copy-and-swap)."""
    if kind.name == "on_hand":
        outer = dict(db.ON_HAND)
        outer[site_id] = new_table
        db.ON_HAND = outer
    else:
        setattr(db, kind.attr, new_table)


def users_of(kind, key):
    """Records that still refer to ``kind``/``key`` (BR3.5), as ``(kind, key)``."""
    users = []
    if kind.name == "raw_material":
        users += [("recipe", mi) for mi, lines in db.RECIPES.items()
                  if any(line.get("raw_material_id") == key for line in lines)]
        users += [("vendor", vid) for vid, v in db.VENDORS.items() if key in v.get("price_list", {})]
        users += [("on_hand", f"{site_id}/{key}") for site_id, table in db.ON_HAND.items() if key in table]
        users += [(name, key) for name, table in (("par_level", db.PAR_LEVELS), ("reorder_point", db.REORDER_POINTS))
                  if key in table]
    elif kind.name == "uom":
        users += [("raw_material", rm) for rm, r in db.RAW_MATERIALS.items() if r.get("uom") == key]
        users += [("recipe", mi) for mi, lines in db.RECIPES.items() if any(line.get("uom") == key for line in lines)]
        users += [("uom", uid) for uid, u in db.UOM.items() if u.get("base") == key and uid != key]
    elif kind.name == "job_code":
        users += [("employee", eid) for eid, e in db.EMPLOYEES.items() if e.get("job_code") == key]
    elif kind.name == "menu_item" and key in db.RECIPES:
        users.append(("recipe", key))
    return users


# ================================================================== MetaStore

def _new_meta(origin, created_by, created_at, session_id=None, site_id=None):
    return {"origin": origin, "created_by": created_by, "created_at": created_at,
            "updated_by": None, "updated_at": None, "version": 1,
            "created_session": session_id, "site_id": site_id}


def wire_meta(meta):
    """Meta on the wire: exactly the six NQ3 fields, never a session id (NFR1.6)."""
    return {name: meta[name] for name in WIRE_META_FIELDS}


def _seeded_meta(created_at):
    meta = {}
    for kind in KINDS.values():
        meta[kind.name] = {(_meta_site(kind, site_id), key): _new_meta("seeded", "system", created_at,
                                                                       site_id=_meta_site(kind, site_id))
                           for site_id, key in iter_keys(kind)}
    return meta


def get_meta(kind, site_id, key):
    return _state["meta"][kind.name].get((_meta_site(kind, site_id), key))


def meta_map(kind_name, site_id=None):
    """``{record key: Meta}`` for one kind (site kinds: that site only), BR7.2."""
    kind = KINDS[kind_name]
    return {key: wire_meta(meta) for (meta_site, key), meta in _state["meta"][kind_name].items()
            if kind.scope == "shared" or meta_site == site_id}


def wants_meta(qs):
    return "meta" in qs.get("with", [])


def _is_dashboard(kind_name, key):
    """A stored shared record that the dashboard added (BR5.1)."""
    kind = KINDS[kind_name]
    meta = get_meta(kind, None, key)
    return meta is not None and meta["origin"] == "dashboard" and _exists(kind, None, key)


# ================================================================= IdCounters

_EMPLOYEE_D_ID_RE = re.compile(r"emp_(?P<site>.+)_d(?P<number>[0-9]+)")


def _seed_id_counters():
    counters = dict.fromkeys(db.SITES, 0)
    for key, record in db.EMPLOYEES.items():
        match = _EMPLOYEE_D_ID_RE.fullmatch(key)
        site_id = record.get("site_id")
        if match and match["site"] == site_id and site_id in counters:
            counters[site_id] = max(counters[site_id], int(match["number"]))
    return counters


def allocate_employee_id(site_id):
    """Next ``emp_<site>_d<NNN>`` for the site (BR8.4). Only a 503 gives it back."""
    number = _state["id_counters"].get(site_id, 0) + 1
    _state["id_counters"][site_id] = number
    return f"emp_{site_id}_d{number:03d}"


def release_employee_ids(site_id, count):
    """Return ids allocated for an attempt whose audit failed (NFR2.4)."""
    _state["id_counters"][site_id] -= count


# ================================================================== Validator

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}")
_TAG_RE = re.compile(r"<[^<>]*>")
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_INT_TEXT_RE = re.compile(r"[0-9]+")
_DECIMAL_TEXT_RE = re.compile(r"[0-9]+(\.[0-9]+)?|\.[0-9]+")


def _problem(name, reason, row=None):
    problem = {"field": name, "reason": reason} if name else {"reason": reason}
    return {"row": row, **problem} if row is not None else problem


def depth_exceeds(value, limit=MAX_DEPTH):
    """True when ``value`` nests containers deeper than ``limit`` levels.
    Measured with an explicit stack, never by recursion (NFR2.2)."""
    stack = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if isinstance(current, dict):
            children = current.values()
        elif isinstance(current, list):
            children = current
        else:
            continue
        if depth > limit:
            return True
        stack.extend((child, depth + 1) for child in children)
    return False


def _injection_problem(value, cell):
    if _CONTROL_RE.search(value):
        return "not allowed: control character"
    if _TAG_RE.search(value):
        return "not allowed: markup such as <...>"
    # Checked for form and API writes too: stored text reaches CSV exports.
    if value.lstrip().startswith(_FORMULA_PREFIXES):
        return "not allowed: a cell may not start with =, +, - or @"
    return None


def _text_problem(value, cell):
    """BR4.2, BR4.5: text of 1-100 characters with no injection shapes."""
    if not isinstance(value, str):
        return "must be text"
    if not value.strip():
        return "is required"
    if len(value) > MAX_TEXT:
        return "too long (max 100 characters)"
    return _injection_problem(value, cell)


def _id_problem(value, cell):
    """BR4.4: the seeded id style."""
    problem = _text_problem(value, cell)
    if problem is None and not _ID_RE.fullmatch(value):
        problem = "must be letters, digits, _ or -, starting with a letter or digit"
    return problem


def _number(value, cell, integer):
    """BR4.3: finite, zero to MAX_NUMBER; integer fields take whole numbers. A
    CSV cell arrives as text and is read as a number first."""
    if cell and isinstance(value, str):
        # Plain ASCII decimals only: no digit separators, signs, exponents or
        # non-ASCII digits, and whole numbers read exactly with int(). Overlong
        # cells are refused before int(), which rejects over 4,300 digits.
        text = value.strip()
        if len(text) > MAX_NUMBER_TEXT:
            return None, f"must be at most {MAX_NUMBER:,}"
        if _INT_TEXT_RE.fullmatch(text):
            value = int(text)
        elif _DECIMAL_TEXT_RE.fullmatch(text):
            value = float(text)
        else:
            return None, "must be a number"
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None, "must be a number"
    if isinstance(value, float) and not math.isfinite(value):
        return None, "must be a finite number"
    if value < 0:
        return None, "must be zero or more"
    if value > MAX_NUMBER:
        return None, f"must be at most {MAX_NUMBER:,}"
    if integer and isinstance(value, float):
        if not value.is_integer():
            return None, "must be a whole number"
        value = int(value)
    return value, None


def _cell_text_problem(value):
    """A list field's CSV cell: text without injection shapes (BR4.8)."""
    if not isinstance(value, str):
        return "must be the cell text from the file"
    return _injection_problem(value, cell=True)


def _days(name, value, cell):
    if cell:
        problem = _cell_text_problem(value)
        if problem:
            return None, [_problem(name, problem)]
        value = [part.strip() for part in value.split("|")]
    if not isinstance(value, list) or not value:
        return None, [_problem(name, "must list at least one day" + (" (form Mon|Tue)" if cell else ""))]
    if not all(isinstance(day, str) and day in DAYS for day in value):
        return None, [_problem(name, "days must be Mon, Tue, Wed, Thu, Fri, Sat or Sun")]
    if len(set(value)) != len(value):
        return None, [_problem(name, "must not repeat a day")]
    return list(value), []


def _price_pairs(name, value, cell):
    """The price list as ``[(raw_material_id, price)]`` before checks, or a problem."""
    if not cell:
        if not isinstance(value, dict):
            return None, _problem(name, "must map raw material ids to prices")
        return list(value.items()), None
    problem = _cell_text_problem(value)
    if problem:
        return None, _problem(name, problem)
    pairs = []
    for part in value.split(";"):
        if part.count("=") != 1:
            return None, _problem(name, "must have the form rm_id=price;rm_id=price")
        rm_id, price = part.split("=")
        pairs.append((rm_id.strip(), price.strip()))
    return pairs, None


def _price_list(name, value, cell):
    pairs, problem = _price_pairs(name, value, cell)
    if problem:
        return None, [problem]
    if not pairs:
        return None, [_problem(name, "must list at least one raw material")]
    clean, problems = {}, []
    for i, (rm_id, price) in enumerate(pairs, start=1):
        id_problem = _id_problem(rm_id, cell=False)
        number, number_problem = _number(price, cell, integer=False)
        if id_problem:
            problems.append(_problem(name, f"entry {i}: raw material id {id_problem}"))
        elif rm_id in clean:
            problems.append(_problem(name, f"entry {i}: repeats raw material {rm_id}"))
        if number_problem:
            problems.append(_problem(name, f"entry {i}: price {number_problem}"))
        if not id_problem and not number_problem:
            clean[rm_id] = number
    return (clean if not problems else None), problems


def _lines(name, value):
    if not isinstance(value, list) or not value:
        return None, [_problem(name, "must list at least one line")]
    clean, problems = [], []
    for i, line in enumerate(value):
        prefix = f"{name}[{i}]"
        if not isinstance(line, dict):
            problems.append(_problem(prefix, "must be an object"))
            continue
        line_clean, line_problems = check_fields(_LINE_FIELDS, line, cell=False, prefix=prefix + ".")
        problems += line_problems
        clean.append(line_clean)
    return (clean if not problems else None), problems


def _check_field(fld, name, value, cell):
    """``(clean value, [problems])`` for one present field."""
    if fld.type == _T:
        problem = _text_problem(value, cell)
    elif fld.type in ("id", "ref"):
        problem = _id_problem(value, cell)
    elif fld.type in (_N, _I):
        value, problem = _number(value, cell, integer=fld.type == _I)
    elif fld.type == "gl_code":
        problem = None if isinstance(value, str) and value in db.GL_CODES else (
            f"must be one of {', '.join(db.GL_CODES)}")
    elif fld.type == "days":
        return _days(name, value, cell)
    elif fld.type == "price_list":
        return _price_list(name, value, cell)
    elif fld.type == "lines":
        return _lines(name, value)
    else:  # pragma: no cover -- the catalog only uses the types above
        raise ValueError(f"unknown field type {fld.type}")
    return (None, [_problem(name, problem)]) if problem else (value, [])


def check_fields(fields, record, *, cell, prefix="", skip=()):
    """Check every field; returns ``(clean, problems)``. Unknown fields are
    ignored and never stored (BR4.1); every problem is reported (BR4.6)."""
    clean, problems = {}, []
    for fld in fields:
        if fld.name in skip:
            continue
        name = prefix + fld.name
        value = record.get(fld.name)
        if value is None or (cell and isinstance(value, str) and not value.strip() and fld.type != _T):
            problems.append(_problem(name, "is required"))
            continue
        value, field_problems = _check_field(fld, name, value, cell)
        if field_problems:
            problems += field_problems
        else:
            clean[fld.name] = value
    return clean, problems


def validate_record(kind, record, *, action, cell=False):
    """Fields and injection checks for an add or update (BR4). An update's id
    comes from the path, so the record's key field is not read."""
    skip = (kind.key,) if action == "update" else ()
    clean, problems = check_fields(kind.fields, record, cell=cell, skip=skip)
    if action == "add" and kind.key_mode == "typed" and clean.get(kind.key) in RESERVED_IDS:
        problems.append(_problem(kind.key, "is reserved"))
        del clean[kind.key]
    return clean, problems


def _base_loops(uom_id, base, pending=None):
    """True when following base links from ``base`` comes back to ``uom_id``
    through another unit (BR5.5). A unit that is its own base ends a chain."""
    pending = pending or {}
    current, visited = base, set()
    while current != uom_id:
        visited.add(current)
        record = db.UOM.get(current)
        following = pending.get(current, record.get("base") if record else None)
        if following is None or following == current or following in visited:
            return False
        current = following
    return base != uom_id


def reference_problems(kind, key, clean, *, pending_units=None):
    """BR5.1, BR5.5: references name dashboard-added records; a unit may be its
    own base or name a unit added by an earlier row of the same file; base
    links may not loop. Only fields that passed their checks are looked at."""
    pending_units = pending_units or {}
    problems = []

    def need(name, ref_kind, value):
        if ref_kind == "uom" and value in pending_units:
            return
        if not _is_dashboard(ref_kind, value):
            problems.append(_problem(name, f"must be a dashboard-added {KINDS[ref_kind].label}"))

    for fld in kind.fields:
        if fld.name not in clean:
            continue
        value = clean[fld.name]
        if fld.type == "ref":
            if not (kind.name == "uom" and fld.name == "base" and value == key):
                need(fld.name, fld.ref, value)
        elif fld.type == "price_list":
            for rm_id in value:
                need(fld.name, fld.ref, rm_id)
        elif fld.type == "lines":
            for i, line in enumerate(value):
                need(f"{fld.name}[{i}].raw_material_id", "raw_material", line["raw_material_id"])
                need(f"{fld.name}[{i}].uom", "uom", line["uom"])
    if kind.name == "uom" and "base" in clean and isinstance(key, str) and _base_loops(key, clean["base"], pending_units):
        problems.append(_problem("base", "base units may not loop"))
    return problems


def envelope_problems(body, action):
    """The request envelope (NFR2.2, BR4.7), checked before anything else.
    Returns ``[]`` when well formed. ``action`` is add, update, delete or bulk."""
    if not isinstance(body, dict):
        return [_problem("body", "must be an object")]
    if depth_exceeds(body):
        return [_problem("body", f"nested deeper than {MAX_DEPTH} levels")]
    problems = [_problem(name, "must be text") for name in ("session_id", "request_id")
                if body.get(name) is not None and not isinstance(body[name], str)]
    if action in ("add", "update") and not isinstance(body.get("record"), dict):
        problems.append(_problem("record", "must be an object"))
    if action in ("update", "delete") and not _whole(body.get("version"), 1):
        problems.append(_problem("version", "must be a whole number from 1"))
    if action == "bulk":
        problems += _rows_envelope_problems(body)
    return problems[:MAX_ENVELOPE_PROBLEMS]


def _rows_envelope_problems(body):
    if body.get("file_name") is not None and not isinstance(body["file_name"], str):
        return [_problem("file_name", "must be text")]
    rows = body.get("rows")
    if not isinstance(rows, list):
        return [_problem("rows", "must be a list")]
    problems, seen = [], set()
    for i, row in enumerate(rows):
        if len(problems) >= MAX_ENVELOPE_PROBLEMS:
            break
        if not isinstance(row, dict):
            problems.append(_problem(f"rows[{i}]", "must be an object"))
            continue
        number = row.get("row")
        if not _whole(number, 1) or number in seen:
            problems.append(_problem(f"rows[{i}].row", "must be a whole number from 1, not repeated"))
        else:
            seen.add(number)
        if isinstance(row.get("record"), dict) == isinstance(row.get("parse_error"), str):
            problems.append(_problem(f"rows[{i}]", "needs exactly one of record (an object) or parse_error (text)"))
    return problems


# ================================================== SessionStore / QuotaStore

def _end_session(session_id, reason, now):
    session = _state["sessions"].pop(session_id)
    for kind_name in KINDS:
        _state["quota"].pop((session_id, kind_name), None)
    _state["ended"][session_id] = {"user_id": session["user_id"], "reason": reason, "ended_at": now}


def sweep_sessions(now=None):
    """End every session idle for 15 minutes or more, dropping its counters
    (ND Q1). Nothing is audited: nobody acted. Ended-session reasons are
    kept for 15 minutes so a status check can report them."""
    now = now or _now()
    cutoff = now - IDLE_TIMEOUT
    for session_id, session in list(_state["sessions"].items()):
        if session["last_activity_at"] <= cutoff:
            _end_session(session_id, "idle", now)
    for session_id, ended in list(_state["ended"].items()):
        if ended["ended_at"] <= cutoff:
            del _state["ended"][session_id]


def _quota_count(session_id, kind):
    return _state["quota"].get((session_id, kind.name), 0)


# ================================================================= RequestLog

def _request_log(user_id, now):
    """The user's live request records, oldest first; expired ones dropped."""
    log = _state["requests"].get(user_id)
    if log is None:
        return None
    cutoff = now - REQUEST_TTL
    while log and next(iter(log.values()))["stored_at"] <= cutoff:
        log.popitem(last=False)
    if not log:
        del _state["requests"][user_id]
        return None
    return log


def lookup_request(user_id, request_id, now):
    log = _request_log(user_id, now)
    return log.get(request_id) if log is not None and isinstance(request_id, str) else None


def remember_request(user_id, request_id, fingerprint, response, now):
    """Store an audited outcome under its request id. An existing record is
    never replaced; the oldest record goes first past 1,000 (NFR1.8)."""
    log = _request_log(user_id, now)
    if log is None:
        log = _state["requests"][user_id] = OrderedDict()
    if request_id in log:
        return
    status, payload = response
    log[request_id] = {"fingerprint": fingerprint, "status": status,
                       "payload": copy.deepcopy(payload), "stored_at": now}
    while len(log) > REQUEST_CAP:
        log.popitem(last=False)


def _fingerprint(*parts):
    text = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def _valid_request_id(request_id):
    return isinstance(request_id, str) and 1 <= len(request_id) <= MAX_REQUEST_ID


# =============================================================== AuditAdapter

class AuditFailure(Exception):
    """The attempt could not be audited; nothing was applied (503)."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _recorded_session(session_id, issued, caller):
    """BR8.3: a session id is recorded only when it names an existing session
    that belongs to the caller, so one user's entry never carries another
    user's live session id. ``issued`` marks an id the backend itself just
    issued or ended (the login and logout entries), which is recorded as it is."""
    if not isinstance(session_id, str) or not session_id:
        return None
    if issued:
        return session_id
    session = _state["sessions"].get(session_id)
    return session_id if session is not None and caller is not None and session["user_id"] == caller else None


def build_entry(*, user_id, persona, session_id, action, outcome, kind=None, record_id=None, site_id=None,
                changes=None, reason=None, file_row=None, issued_session=False, caller=None):
    """One U1 entry, every field kept within what U2 accepts (BR8.3, NFR2.7).

    ``record_id``, ``site_id``, ``kind``, ``reason`` and every text value in
    ``changes`` are clipped to MAX_AUDIT_TEXT characters, marker included.
    ``user_id``, ``persona`` and ``session_id`` come from the token or a
    backend-issued session and are never clipped."""
    return {
        "user_id": _bounded(user_id) or audit.UNKNOWN_USER, "persona": _bounded(persona),
        "session_id": _recorded_session(session_id, issued_session, caller), "source": SOURCE, "action": action,
        "outcome": outcome, "kind": _clip_optional(kind), "record_id": _clip_optional(record_id),
        "site_id": _clip_optional(site_id), "changes": clip_value(changes), "reason": clip_text(reason),
        "file_row": file_row,
    }


def _append_entries(entries, batch):
    if batch:
        audit.append_batch(entries)
    else:
        audit.append(entries[0])


def record_audit(entries, what, *, batch=False, log=True):
    """Append the entries (one with ``append``, a file's with one
    ``append_batch``). There is no retry (BR8.2): every entry was already made
    safe by ``build_entry``, and U2 itself replaces oversized or
    unserializable ``changes``. Raises ``AuditFailure`` with one of the two
    distinct 503 messages, after one ERROR line (NFR2.5)."""
    try:
        _append_entries(entries, batch)
    except audit.AuditUnavailable as e:
        if log:
            _log_error(f"audit unavailable for {what}")
        raise AuditFailure("audit unavailable") from e
    except (audit.InvalidEntry, RecursionError) as e:
        if log:
            _log_error(f"audit could not record {what}")
        raise AuditFailure("audit could not record the attempt") from e


def _compensate(allowed_entries, error, what, kind_key):
    """BR8.2, NFR2.4: an apply failed after its allowed entries were stored.
    Append one compensating violation per attempted record in one batch;
    if that fails too, log one line for the attempt."""
    error_type = type(error).__name__
    _log_error(f"apply failed after audit for {what} ({error_type})")
    reason = clip_text(f"failed after audit: {error_type}")
    # BR8.6: every other field repeats its allowed entry exactly.
    compensating = [{**e, "outcome": "violation", "reason": reason} for e in allowed_entries]
    try:
        record_audit(compensating, what, batch=True, log=False)
    except AuditFailure:
        _log_error(f"compensating entry failed for {kind_key}")


# ============================================================== WriteService

@dataclass
class Refusal:
    """A refused attempt: its status, response and audit reason."""

    status: int
    error: str
    problems: list = field(default_factory=list)
    store: bool = True      # stored under the request id (BR9.1)
    reason: str | None = None

    def payload(self):
        return {"error": self.error, "problems": self.problems} if self.problems else {"error": self.error}

    def audit_reason(self):
        if self.reason:
            return self.reason
        if self.problems:
            return f"{self.error}: " + "; ".join(_problem_text(p) for p in self.problems)
        return self.error


def _problem_text(problem):
    label = " ".join(str(part) for part in (
        f"row {problem['row']}" if "row" in problem else None, problem.get("field")) if part)
    return f"{label}: {problem['reason']}" if label else problem["reason"]


class _Attempt:
    """Everything one write attempt carries through the pipeline."""

    def __init__(self, kind, action, claims, site_id, path_key, body):
        self.kind = kind
        self.action = action            # add, update, delete or bulk
        self.claims = claims
        self.site_id = site_id
        self.body = body
        self.now = _now()
        self.key = path_key             # update/delete: from the path; add: set by the checks
        self.user_id = audit.UNKNOWN_USER
        self.persona = None
        self.session_id = None
        self.session = None             # set once the session check passes
        self.stored = None
        self.meta = None
        self.clean = None
        self.unrecordable = not isinstance(body, dict) or depth_exceeds(body)
        self.fingerprint = None if self.unrecordable else _fingerprint(action, kind.name, site_id, path_key, body)

    @property
    def request_id(self):
        return self.body.get("request_id") if isinstance(self.body, dict) else None

    @property
    def audit_action(self):
        return "bulk_row" if self.action == "bulk" else self.action

    def what(self, key=None):
        return f"{self.audit_action} {self.kind.name}/{_log_key(key if key is not None else self.record_key())}"

    def record_key(self):
        """The record id for the entry: the path id, the typed id, or a generated id."""
        if isinstance(self.key, str):
            return self.key
        if self.action == "add" and self.kind.key_mode != "generated" and isinstance(self.body, dict):
            record = self.body.get("record")
            typed = record.get(self.kind.key) if isinstance(record, dict) else None
            return typed if isinstance(typed, str) else None
        return None

    def site_note(self):
        """BR2.3, BR8.3: a violation on a site kind whose path site is unknown
        or outside the token's sites keeps that site id in ``changes``, since
        the entry's own site field holds only an existing site."""
        kind, site_id = self.kind, self.site_id
        if kind.scope != "site":
            return {}
        if site_id in db.SITES and site_allowed(self.claims, site_id):
            return {}
        return {"site_id": site_id}

    def _update_diff(self):
        """``{before, after}`` holding only the fields the update changes.
        Built from the stored record and the checked fields (which become the
        new record's values), without touching the apply path, so building
        the entry can't fail after the checks passed."""
        before = record_view(self.kind, self.site_id, self.key, self.stored)
        changed = [name for name, value in self.clean.items()
                   if name != self.kind.key and before.get(name) != value]
        return {"before": {name: before[name] for name in changed if name in before},
                "after": {name: copy.deepcopy(self.clean[name]) for name in changed}}

    def changes(self, outcome):
        """``changes`` for this attempt's entry (FD Q8, BR8.3). ``build_entry``
        clips it; an unreadable envelope records the marker."""
        if self.unrecordable:
            return dict(UNRECORDABLE_CHANGES)
        if self.action == "bulk":
            # The single entry for a whole file (malformed or wrong row count).
            rows = self.body.get("rows")
            changes = {"file_name": self.body.get("file_name"),
                       "row_count": len(rows) if isinstance(rows, list) else None}
        elif outcome == "allowed" and self.action == "update":
            changes = self._update_diff()
        elif outcome == "allowed" and self.action == "delete":
            changes = {"record": record_view(self.kind, self.site_id, self.key, self.stored)}
        elif self.action == "delete":
            changes = {"version": self.body.get("version")}
        else:  # an allowed add, or a refused add or update: what was submitted
            changes = {"record": self.body.get("record")}
        if outcome == "violation":
            changes.update(self.site_note())
        return changes

    def entry(self, outcome, reason=None, **overrides):
        fields = {"user_id": self.user_id, "persona": self.persona, "session_id": self.session_id,
                  "action": self.audit_action, "outcome": outcome, "kind": self.kind.name,
                  "record_id": self.record_key(), "site_id": _known_site(self.site_id), "reason": reason,
                  "caller": self.claims.get("sub")}
        if "changes" not in overrides:
            fields["changes"] = self.changes(outcome)
        return build_entry(**{**fields, **overrides})


# --------------------------------------------------------------- the checks

def _replayed(attempt):
    """BR9.1: the stored response for the same request from the same user."""
    if attempt.fingerprint is None:
        return None
    record = lookup_request(attempt.claims["sub"], attempt.request_id, attempt.now)
    if record is None or record["fingerprint"] != attempt.fingerprint:
        return None
    return record["status"], copy.deepcopy(record["payload"])


def _check_session(attempt):
    """BR1.4, NFR1.9: the caller's own active session, after the idle sweep."""
    sweep_sessions(attempt.now)
    session_id = attempt.body.get("session_id")
    session = _state["sessions"].get(session_id) if isinstance(session_id, str) else None
    if session is None or session["user_id"] != attempt.claims["sub"]:
        # Not stored under the request id: after a fresh login the client may
        # retry the same request id with its new session (review R-01).
        return Refusal(401, "no active session", store=False)
    attempt.session, attempt.session_id = session, session_id
    attempt.user_id, attempt.persona = attempt.claims["sub"], attempt.claims.get("persona")
    return None


def _check_request_id(attempt):
    """BR9.2, BR9.1: a request id is required and never reused."""
    if not _valid_request_id(attempt.request_id):
        return Refusal(400, "missing or malformed request id", store=False)
    record = lookup_request(attempt.claims["sub"], attempt.request_id, attempt.now)
    if record is not None and record["fingerprint"] != attempt.fingerprint:
        return Refusal(409, "request id reused", store=False)
    return None


def _check_site_and_rights(attempt):
    """BR8.1 step 5 (site) is checked here; the caller runs step 6 (record)
    before step 7 (rights) through ``_check_rights``."""
    kind, claims, site_id = attempt.kind, attempt.claims, attempt.site_id
    if kind.scope == "site":
        if site_id not in db.SITES:
            return Refusal(404, f"unknown site {site_id}")
        if not site_allowed(claims, site_id):
            return Refusal(403, f"persona {claims.get('persona')} not scoped to site {site_id}")
    return None


def _check_rights(attempt):
    if attempt.kind.scope == "shared" and not _region_wide(attempt.claims):
        return Refusal(403, f"persona {attempt.claims.get('persona')} cannot write shared data")
    return None


def _check_record(attempt):
    found, stored = find(attempt.kind, attempt.site_id, attempt.key)
    if not found:
        return Refusal(404, f"no {attempt.kind.label} {attempt.key}")
    attempt.stored = stored
    attempt.meta = get_meta(attempt.kind, attempt.site_id, attempt.key)
    return None


def _check_policy(attempt):
    """BR3.1 seeded records are read-only; BR3.3 delete ownership."""
    if attempt.meta is None or attempt.meta["origin"] == "seeded":
        return Refusal(403, "seeded records are read-only")
    if attempt.action == "delete" and (attempt.meta["created_by"] != attempt.claims["sub"]
                                       or attempt.meta["created_session"] != attempt.session_id):
        return Refusal(403, "not your record from this session")
    return None


def _check_input(attempt):
    """BR4 fields and injection, then BR5 references; every problem listed."""
    kind = attempt.kind
    clean, problems = validate_record(kind, attempt.body["record"], action=attempt.action)
    if attempt.action == "add" and kind.key_mode != "generated" and kind.key in clean:
        attempt.key = clean[kind.key]
        if _exists(kind, attempt.site_id, attempt.key):
            problems.append(_problem(kind.key, "already exists"))
    problems += reference_problems(kind, attempt.key, clean)
    if problems:
        return Refusal(400, "invalid record", problems)
    attempt.clean = clean
    return None


def _check_version(attempt):
    if attempt.body["version"] != attempt.meta["version"]:
        return Refusal(409, "this record changed since you opened it; reload and try again")
    return None


def _check_in_use(attempt):
    users = users_of(attempt.kind, attempt.key)
    if users:
        return Refusal(409, "record is still in use",
                       [_problem(user_kind, f"still used by {KINDS[user_kind].label} {user_key}")
                        for user_kind, user_key in users])
    return None


def _check_limit(attempt, adding=1):
    if _quota_count(attempt.session_id, attempt.kind) + adding > ENTRY_LIMIT:
        return Refusal(429, f"entry limit reached for {attempt.kind.name}")
    return None


def _single_steps(action):
    """BR8.1 steps 5-14 for one action, in order."""
    steps = [_check_site_and_rights]
    if action in ("update", "delete"):
        steps.append(_check_record)
    steps.append(_check_rights)
    if action in ("update", "delete"):
        steps.append(_check_policy)
    if action in ("add", "update"):
        steps.append(_check_input)
    if action in ("update", "delete"):
        steps.append(_check_version)
    if action == "delete":
        steps.append(_check_in_use)
    if action == "add":
        steps.append(_check_limit)
    return steps


def _first_refusal(attempt, steps):
    """Run the steps in order; the first refusal decides the outcome. An
    unexpected error is refused (and audited) as 500, never left unaudited."""
    try:
        for step in steps:
            refusal = step(attempt)
            if refusal is not None:
                return refusal
    except Exception as e:  # noqa: BLE001 -- turned into an audited 500 refusal
        _log_error(f"check failed for {attempt.what()} ({type(e).__name__})")
        return Refusal(500, "internal error", store=False, reason=f"internal error: {type(e).__name__}")
    return None


# ---------------------------------------------------------- finishing steps

def _malformed(attempt, problems):
    """BR4.7: 400 "malformed request" with one audit entry; never stored."""
    entry = attempt.entry("violation", Refusal(400, "malformed request", problems).audit_reason(),
                          session_id=attempt.body.get("session_id") if isinstance(attempt.body, dict) else None)
    try:
        record_audit([entry], attempt.what(), batch=attempt.action == "bulk")
    except AuditFailure as e:
        return 503, {"error": e.message}
    return 400, {"error": "malformed request", "problems": problems}


def _respond(attempt, response, store):
    """Refresh a valid session (single and bulk alike) and store the response."""
    if attempt.session is not None:
        attempt.session["last_activity_at"] = attempt.now
    if store and _valid_request_id(attempt.request_id):
        remember_request(attempt.claims["sub"], attempt.request_id, attempt.fingerprint, response, attempt.now)
    return response


def _refuse(attempt, refusal, entries=None):
    entries = entries or [attempt.entry("violation", refusal.audit_reason())]
    try:
        record_audit(entries, attempt.what(), batch=attempt.action == "bulk")
    except AuditFailure as e:
        return 503, {"error": e.message}
    return _respond(attempt, (refusal.status, refusal.payload()), refusal.store)


def _apply_single(attempt):
    """Build the new record, meta and counter first, then assign them; a
    failure while building leaves shared state unchanged (NFR2.4)."""
    kind, site_id, key, user = attempt.kind, attempt.site_id, attempt.key, attempt.claims["sub"]
    meta_key = (_meta_site(kind, site_id), key)
    kind_meta = _state["meta"][kind.name]
    if attempt.action == "delete":
        del _collection(kind, site_id)[key]
        del kind_meta[meta_key]
        return 200, {"deleted": True, "kind": kind.name, "record_id": key}
    stored = build_stored(kind, site_id, key, attempt.clean)
    if attempt.action == "add":
        meta = _new_meta("dashboard", user, _iso(attempt.now), attempt.session_id, _meta_site(kind, site_id))
        count = _quota_count(attempt.session_id, kind) + 1
        status = 201
    else:
        meta = {**attempt.meta, "updated_by": user, "updated_at": _iso(attempt.now),
                "version": attempt.meta["version"] + 1}
        count = None
        status = 200
    response = (status, {"record": record_view(kind, site_id, key, stored), "meta": wire_meta(meta)})
    _collection(kind, site_id)[key] = stored
    kind_meta[meta_key] = meta
    if count is not None:
        _state["quota"][(attempt.session_id, kind.name)] = count
    return response


def _allow_single(attempt):
    kind = attempt.kind
    allocated = attempt.action == "add" and kind.key_mode == "generated"
    if allocated:
        attempt.key = allocate_employee_id(attempt.site_id)
    entry = attempt.entry("allowed")
    try:
        record_audit([entry], attempt.what())
    except AuditFailure as e:
        if allocated:
            release_employee_ids(attempt.site_id, 1)
            attempt.key = None
        return 503, {"error": e.message}
    try:
        response = _apply_single(attempt)
    except Exception as e:  # noqa: BLE001 -- compensated in the audit trail, answered 500
        _compensate([entry], e, attempt.what(), f"{kind.name}/{_log_key(attempt.key)}")
        return _respond(attempt, (500, {"error": "failed after audit"}), store=False)
    return _respond(attempt, response, store=True)


def write(kind_name, action, claims, site_id, record_id, body):
    """One add, update or delete (WF4). Returns ``(status, payload)``."""
    kind = KINDS[kind_name]
    with db._lock:
        attempt = _Attempt(kind, action, claims, site_id, record_id if action != "add" else None, body)
        problems = envelope_problems(body, action)
        if problems:
            return _malformed(attempt, problems)
        replayed = _replayed(attempt)
        if replayed is not None:
            return replayed
        refusal = _first_refusal(attempt, [_check_session, _check_request_id, *_single_steps(action)])
        if refusal is not None:
            return _refuse(attempt, refusal)
        return _allow_single(attempt)


# ----------------------------------------------------------------------- bulk

@dataclass
class _Item:
    """One record a bulk file would add, with the rows it came from."""

    key: str | None
    clean: dict
    rows: list


def _row_record(row):
    return row.get("record") if isinstance(row.get("record"), dict) else None


def _parse_error_problem(row):
    return _problem(None, f"could not read line: {_CONTROL_RE.sub(' ', row['parse_error'])[:MAX_TEXT]}", row["row"])


def _check_plain_rows(attempt, rows):
    """Row checks for every kind but recipes (BR10.1, BR5.5)."""
    kind, site_id = attempt.kind, attempt.site_id
    problems, items, seen, pending_units = {}, [], {}, {}
    for row in rows:
        number = row["row"]
        record = _row_record(row)
        if record is None:
            problems[number] = [_parse_error_problem(row)]
            continue
        clean, row_problems = validate_record(kind, record, action="add", cell=True)
        key = clean.get(kind.key) if kind.key_mode != "generated" else None
        if key is not None:
            if _exists(kind, site_id, key):
                row_problems.append(_problem(kind.key, "already exists"))
            elif key in seen:
                row_problems.append(_problem(kind.key, f"repeats row {seen[key]}"))
            seen.setdefault(key, number)
        row_problems += reference_problems(kind, key, clean, pending_units=pending_units)
        if row_problems:
            problems[number] = [{"row": number, **p} for p in row_problems]
            continue
        items.append(_Item(key, clean, [row]))
        if kind.name == "uom":
            pending_units[key] = clean["base"]
    return problems, items


def _check_recipe_rows(rows):
    """Recipe rows are single lines grouped by menu_item_id (FD Q7); a group's
    problems are reported on each of its rows."""
    recipe = KINDS["recipe"]
    problems, groups = {}, OrderedDict()
    for row in rows:
        number = row["row"]
        record = _row_record(row)
        if record is None:
            problems[number] = [_parse_error_problem(row)]
            continue
        clean, row_problems = check_fields(_RECIPE_ROW_FIELDS, record, cell=True)
        for name, ref_kind in (("raw_material_id", "raw_material"), ("uom", "uom")):
            if name in clean and not _is_dashboard(ref_kind, clean[name]):
                row_problems.append(_problem(name, f"must be a dashboard-added {KINDS[ref_kind].label}"))
        if row_problems:
            problems[number] = [{"row": number, **p} for p in row_problems]
        if "menu_item_id" in clean:
            groups.setdefault(clean["menu_item_id"], []).append((row, clean))
    items = []
    for menu_item_id, members in groups.items():
        group_problems = []
        if not _is_dashboard("menu_item", menu_item_id):
            group_problems.append(_problem("menu_item_id", "must be a dashboard-added menu item"))
        if _exists(recipe, None, menu_item_id):
            group_problems.append(_problem("menu_item_id", "already exists"))
        for row, _ in members:
            if group_problems:
                problems.setdefault(row["row"], []).extend({"row": row["row"], **p} for p in group_problems)
        if not group_problems and not any(row["row"] in problems for row, _ in members):
            lines = [{name: clean[name] for name in ("raw_material_id", "qty", "uom")} for _, clean in members]
            items.append(_Item(menu_item_id, {"menu_item_id": menu_item_id, "lines": lines}, [r for r, _ in members]))
    return problems, items


def _row_entry(attempt, row, outcome, reason=None, record_id=None):
    """One bulk row's entry (BR10.2). ``changes`` is the submitted row:
    ``{record}``, or ``{parse_error}`` for an unreadable CSV line, plus the
    path site for a violation at an unknown or out-of-scope site (BR8.3)."""
    record = _row_record(row)
    changes = {"record": record} if record is not None else {"parse_error": row.get("parse_error")}
    if outcome == "violation":
        changes.update(attempt.site_note())
    if record_id is None and record is not None and attempt.kind.key_mode != "generated":
        typed = record.get(attempt.kind.key)
        record_id = typed if isinstance(typed, str) else None
    return attempt.entry(outcome, reason, record_id=record_id, changes=changes, file_row=row["row"])


def _refuse_rows(attempt, refusal, reasons=None):
    """A refused file: one violation per row (BR10.2, FD Q5)."""
    reasons = reasons or {}
    default = refusal.audit_reason()
    entries = [_row_entry(attempt, row, "violation", reasons.get(row["row"], default))
               for row in attempt.body["rows"]]
    return _refuse(attempt, refusal, entries)


def _apply_bulk(attempt, items):
    """Apply the file to copies of the touched collection and meta, then swap
    them in with single assignments (NFR2.4)."""
    kind, site_id = attempt.kind, attempt.site_id
    table = dict(_collection(kind, site_id))
    kind_meta = dict(_state["meta"][kind.name])
    records = []
    for item in items:
        stored = build_stored(kind, site_id, item.key, item.clean)
        meta = _new_meta("dashboard", attempt.claims["sub"], _iso(attempt.now), attempt.session_id,
                         _meta_site(kind, site_id))
        records.append({"record": record_view(kind, site_id, item.key, stored), "meta": wire_meta(meta)})
        table[item.key] = stored
        kind_meta[(_meta_site(kind, site_id), item.key)] = meta
    count = _quota_count(attempt.session_id, kind) + len(items)
    _swap_collection(kind, site_id, table)
    _state["meta"][kind.name] = kind_meta
    _state["quota"][(attempt.session_id, kind.name)] = count
    return 201, {"added": len(items), "records": records}


def _allow_bulk(attempt, items):
    kind = attempt.kind
    if kind.key_mode == "generated":
        for item in items:
            item.key = allocate_employee_id(attempt.site_id)
    entries = [_row_entry(attempt, row, "allowed", record_id=item.key) for item in items for row in item.rows]
    entries.sort(key=lambda e: e["file_row"])
    try:
        record_audit(entries, attempt.what(), batch=True)
    except AuditFailure as e:
        if kind.key_mode == "generated":
            release_employee_ids(attempt.site_id, len(items))
        return 503, {"error": e.message}
    try:
        response = _apply_bulk(attempt, items)
    except Exception as e:  # noqa: BLE001 -- compensated in the audit trail, answered 500
        _compensate(entries, e, attempt.what(), f"{kind.name}/none")
        return _respond(attempt, (500, {"error": "failed after audit"}), store=False)
    return _respond(attempt, response, store=True)


def bulk(kind_name, claims, site_id, body):
    """All-or-nothing add of the rows of one CSV file (WF5)."""
    kind = KINDS[kind_name]
    with db._lock:
        attempt = _Attempt(kind, "bulk", claims, site_id, None, body)
        problems = envelope_problems(body, "bulk")
        if problems:
            return _malformed(attempt, problems)
        replayed = _replayed(attempt)
        if replayed is not None:
            return replayed
        rows = body["rows"]
        if not BULK_MIN_ROWS <= len(rows) <= BULK_MAX_ROWS:
            # One entry for the file: its rows are never examined (BR10.5).
            return _refuse(attempt, Refusal(400, "file must hold 1 to 500 rows",
                                            [_problem(None, "file must hold 1 to 500 rows")]))
        refusal = _first_refusal(attempt, [_check_session, _check_request_id, _check_site_and_rights, _check_rights])
        if refusal is not None:
            refusal.problems = refusal.problems or [_problem(None, refusal.error)]
            return _refuse_rows(attempt, refusal)
        return _bulk_rows(attempt, rows)


def _bulk_rows(attempt, rows):
    try:
        if attempt.kind.name == "recipe":
            problems, items = _check_recipe_rows(rows)
        else:
            problems, items = _check_plain_rows(attempt, rows)
    except Exception as e:  # noqa: BLE001 -- turned into an audited 500 refusal
        _log_error(f"check failed for {attempt.what()} ({type(e).__name__})")
        return _refuse_rows(attempt, Refusal(500, "internal error", store=False,
                                             reason=f"internal error: {type(e).__name__}"))
    if problems:
        listed = [p for number in sorted(problems) for p in problems[number]]
        reasons = {number: "; ".join(_problem_text({k: v for k, v in p.items() if k != "row"}) for p in found)
                   for number, found in problems.items()}
        default = "not saved: other rows in the file failed"
        reasons = {row["row"]: reasons.get(row["row"], default) for row in rows}
        return _refuse_rows(attempt, Refusal(400, "invalid rows", listed), reasons)
    limit = _check_limit(attempt, adding=len(items))
    if limit is not None:
        limit.problems = [_problem(None, "file over the entry limit")]
        return _refuse_rows(attempt, limit, {row["row"]: "file over the entry limit" for row in rows})
    return _allow_bulk(attempt, items)


# ------------------------------------------------------------------- sessions

def start_session(claims):
    """WF1: audit the login (with the new id) first, then activate."""
    with db._lock:
        now = _now()
        sweep_sessions(now)
        session_id = secrets.token_urlsafe(32)
        while session_id in _state["sessions"] or session_id in _state["ended"]:
            session_id = secrets.token_urlsafe(32)
        entry = build_entry(user_id=claims["sub"], persona=claims.get("persona"), session_id=session_id,
                            action="login", outcome="allowed", issued_session=True)
        try:
            record_audit([entry], "login session/none")
        except AuditFailure as e:
            return 503, {"error": e.message}
        _state["sessions"][session_id] = {"user_id": claims["sub"], "persona": claims.get("persona"),
                                          "started_at": now, "last_activity_at": now}
        return 201, {"session_id": session_id, "user_id": claims["sub"], "persona": claims.get("persona"),
                     "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS}


def end_session(claims, session_id):
    """WF2: end the caller's own session, then audit the logout."""
    with db._lock:
        now = _now()
        sweep_sessions(now)
        session = _state["sessions"].get(session_id)
        if session is None:
            return 401, {"error": "unknown or ended session"}
        if session["user_id"] != claims["sub"]:
            return 403, {"error": "not your session"}
        _end_session(session_id, "logout", now)
        entry = build_entry(user_id=claims["sub"], persona=claims.get("persona"), session_id=session_id,
                            action="logout", outcome="allowed", issued_session=True)
        try:
            record_audit([entry], "logout session/none")
        except AuditFailure:
            return 503, {"error": "session ended, audit unavailable"}
        return 200, {"active": False, "ended_reason": "logout"}


def session_status(claims, session_id):
    """WF3: never refreshes the idle timer; only the session's own persona may check it."""
    with db._lock:
        now = _now()
        session = _state["sessions"].get(session_id)
        if session is not None and session["user_id"] != claims["sub"]:
            return 403, {"error": "not your session"}
        sweep_sessions(now)
        if session_id in _state["sessions"]:
            return 200, {"active": True, "ended_reason": None}
        ended = _state["ended"].get(session_id)
        if ended is None:
            return 200, {"active": False, "ended_reason": None}
        if ended["user_id"] != claims["sub"]:
            return 403, {"error": "not your session"}
        return 200, {"active": False, "ended_reason": ended["reason"]}


def template(kind_name, claims, site_id=None):
    """WF6: a read; not audited and refreshes no session."""
    kind = KINDS[kind_name]
    if kind.scope == "site":
        if site_id not in db.SITES:
            return 404, {"error": f"unknown site {site_id}"}
        if not site_allowed(claims, site_id):
            return 403, {"error": f"persona {claims.get('persona')} not scoped to site {site_id}"}
    return 200, template_for(kind)


# ============================================================= state + reset

def _snapshot_seeded_keys():
    keys = {}
    for kind in KINDS.values():
        table = getattr(db, kind.attr)
        if kind.name == "on_hand":
            keys[kind.attr] = {site_id: frozenset(site_table) for site_id, site_table in table.items()}
        else:
            keys[kind.attr] = frozenset(table)
    return keys


_started_at = _iso(_utc_now())
with db._lock:
    _state = {
        "seeded_keys": _snapshot_seeded_keys(),
        "meta": _seeded_meta(_started_at),     # kind -> {(site or None, key): meta}
        "sessions": {},                        # session_id -> session
        "ended": {},                           # session_id -> {user_id, reason, ended_at}
        "quota": {},                           # (session_id, kind) -> accepted adds
        "requests": {},                        # user_id -> OrderedDict(request_id -> record)
        "id_counters": _seed_id_counters(),    # site_id -> last employee d-number
    }


def reset_for_tests():
    """WriteTestReset: clear sessions, counters, request records, added meta
    and id counters, remove every key not present at seeding from the shared
    collections, and restore the real clock (NFR5.2)."""
    with db._lock:
        seeded = _state["seeded_keys"]
        for kind in KINDS.values():
            table = getattr(db, kind.attr)
            if kind.name == "on_hand":
                for site_id in [s for s in table if s not in seeded[kind.attr]]:
                    del table[site_id]
                for site_id, site_table in table.items():
                    for key in [k for k in site_table if k not in seeded[kind.attr][site_id]]:
                        del site_table[key]
            else:
                for key in [k for k in table if k not in seeded[kind.attr]]:
                    del table[key]
        _state["meta"] = _seeded_meta(_started_at)
        for name in ("sessions", "ended", "quota", "requests"):
            _state[name].clear()
        _state["id_counters"] = _seed_id_counters()
        set_clock(None)
