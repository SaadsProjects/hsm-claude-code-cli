"""
Mock HSM REST backend.

Stands in for the real HSM microservices (Labor, Labor Rules Engine, Labor
Scheduling, Inventory/UOM/Raw Material/Recipe/Vendor/Invoice, Sales, Admin)
plus the platform-layer services agents also depend on (Catalog, Menu,
Transaction Data, Identity) and the AI/ML forecast table (normally BigQuery).

Every route is plain JSON over HTTP, exactly like the real REST surface --
an agent built against this file talks to a real HSM deployment by changing
only the base URL and the token-minting call in mock_hsm/auth.py.

Persona scoping is enforced server-side on every call, the same way HSM
would trust Apigee-passed claims: a Restaurant Manager token cannot read or
write another site's data, and a Regional Manager token is bounded to its
region.

The dashboard data writes (unit U1) add login sessions and add / update /
delete / bulk / template routes for 11 kinds of record. Their rules live in
mock_hsm/writes.py; the routes here stay thin. Reads of writable data copy
what they return under db._lock (ReadGuard) and add record metadata when
asked with ``?with=meta``.
"""

import argparse
import copy
import json
import re
import sys
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from urllib.parse import parse_qs, urlparse

from mock_hsm import audit, db, writes
from mock_hsm.auth import (
    SecretMissingError,
    TokenError,
    load_local_secret,
    region_allowed,
    require_secret,
    site_allowed,
    verify_token,
)


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


ROUTES = []  # (method, compiled_regex, handler)


def route(method, pattern, first=False):
    """Register a handler. ``first`` puts it ahead of every route registered so
    far, so a literal path (``/inventory/recipes/template``) is matched before
    an item pattern (``/inventory/recipes/{menu_item_id}``) that would take it."""
    regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")

    def deco(fn):
        if first:
            ROUTES.insert(0, (method, regex, fn))
        else:
            ROUTES.append((method, regex, fn))
        return fn

    return deco


def _require_site(claims, site_id):
    if site_id not in db.SITES:
        raise ApiError(404, f"unknown site {site_id}")
    if not site_allowed(claims, site_id):
        raise ApiError(403, f"persona {claims['persona']} not scoped to site {site_id}")


def _require_region(claims, region_id):
    if region_id not in db.REGIONS:
        raise ApiError(404, f"unknown region {region_id}")
    if not region_allowed(claims, region_id):
        raise ApiError(403, f"persona {claims['persona']} not scoped to region {region_id}")


def _int_qs(qs, key, default):
    if key in qs:
        return int(qs[key][0])
    return default


# ------------------------------------------------------- gated-route auditing
# The two gated routes (schedule publish, PO submit) check, audit and apply as
# one step while holding db._lock (BR3.2); audit.append takes the audit lock
# inside it, so the lock order is always db._lock -> audit lock. Every attempt
# that reaches the route is audited once: a refused attempt as a violation
# carrying the route's existing error message, an accepted one as allowed
# (BR3.1). Responses are unchanged except for the new 503 (BR3.5, NFR4.1).

_GATED_SOURCE = "claude_code_workflow"


def _known_site(site_id):
    """A site id that exists, else None: unknown ids never go in site_id (BR3.4)."""
    return site_id if isinstance(site_id, str) and site_id in db.SITES else None


# reason/record_id echo client input; _clip bounds them (1,024 characters) so
# the entry always fits the audit cap and the attempt is still audited with its
# usual response. The full attempted values stay in ``changes``, which the
# audit module cuts down to a marker if oversized. _json_safe records
# non-finite floats as their repr, since the trail stores strict JSON (review
# R-01). Both helpers live in mock_hsm/writes.py and are shared with the
# dashboard data writes; their behaviour here is unchanged.
_clip = writes.clip_text
_json_safe = writes.json_safe


def _refusal_reason(error):
    if isinstance(error, ApiError):
        return error.message
    return str(error) or type(error).__name__


# Stored in place of attempted values that can't be recorded as JSON at all
# (e.g. a body nested deeper than the recursion limit, review R-04).
_UNRECORDABLE_CHANGES = writes.UNRECORDABLE_CHANGES


def _audit_gated(claims, action, outcome, *, kind, record_id, site_id, changes, reason=None):
    """Append one gated-route entry (BR3.4). An unavailable trail becomes 503.

    If the attempted values can't be stored, the entry is still written with a
    marker in their place, so every attempt is audited with its usual response."""
    entry = {
        "user_id": claims["sub"],
        "persona": claims["persona"],
        "session_id": None,
        "source": _GATED_SOURCE,
        "action": action,
        "outcome": outcome,
        "kind": kind,
        "record_id": _clip(record_id),
        "site_id": site_id,
        "reason": _clip(reason),
    }
    try:
        try:
            audit.append({**entry, "changes": _json_safe(changes)})
        except (audit.InvalidEntry, RecursionError):
            audit.append({**entry, "changes": _UNRECORDABLE_CHANGES})
    except (audit.AuditUnavailable, audit.InvalidEntry) as e:
        raise ApiError(503, "audit unavailable") from e


def _audit_failed_after_audit(claims, action, error, **fields):
    """Compensating entry for an accepted attempt whose apply step failed (BR3.3).

    The caller re-raises the original error afterwards, keeping today's 500, so
    a failed compensating append is only logged (review R-05)."""
    try:
        _audit_gated(claims, action, "violation", reason=f"failed after audit: {_refusal_reason(error)}", **fields)
    except (ApiError, RecursionError, OSError, ValueError):
        print(
            f"[mock-hsm] ERROR audit: compensating entry failed for {action} {fields['record_id']}",
            file=sys.stderr,
            flush=True,
        )


# --------------------------------------------------------------- ReadGuard
# Every read of writable data copies what it returns while holding db._lock
# and responds from the copy, so it sees a write (a whole bulk file included)
# fully or not at all, and never fails because a write changed a collection
# under it (BR8.5). JSON encoding happens after the lock is released.
# Payloads are unchanged; ``?with=meta`` adds one ``meta`` field (BR7.2).


def _with_meta(payload, qs, *kinds, site_id=None):
    """Add ``meta: {kind: {record key: Meta}}`` when asked. Call under db._lock."""
    if writes.wants_meta(qs):
        payload["meta"] = {kind: writes.meta_map(kind, site_id) for kind in kinds}
    return payload


# --------------------------------------------------------------------- Admin
@route("GET", "/admin/orgs/{org_id}")
def admin_org(m, claims, qs, body):
    org_id = m["org_id"]
    if org_id != claims["org_id"] and claims["persona"] != "SYSTEM_ADMIN":
        raise ApiError(403, "org mismatch")
    return 200, db.ORG


@route("GET", "/admin/sites")
def admin_sites(m, claims, qs, body):
    region_id = qs.get("region_id", [None])[0]
    sites = list(db.SITES.values())
    if region_id:
        if not region_allowed(claims, region_id):
            raise ApiError(403, "region not in scope")
        sites = [s for s in sites if s["region_id"] == region_id]
    else:
        sites = [s for s in sites if site_allowed(claims, s["site_id"])]
    return 200, {"sites": sites}


@route("GET", "/admin/sites/{site_id}")
def admin_site(m, claims, qs, body):
    _require_site(claims, m["site_id"])
    return 200, db.SITES[m["site_id"]]


# ------------------------------------------------------------- Catalog/Menu
@route("GET", "/catalog/menu-items")
def catalog_menu_items(m, claims, qs, body):
    with db._lock:
        return 200, _with_meta({"menu_items": copy.deepcopy(list(db.MENU_ITEMS.values()))}, qs, "menu_item")


# ----------------------------------------------------------------- Sales
@route("GET", "/sales/gl-codes")
def sales_gl_codes(m, claims, qs, body):
    # The fixed, read-only list (BR5.2): exactly the codes the seeded menu
    # items carry, no longer derived from (now writable) menu items.
    return 200, {"gl_codes": list(db.GL_CODES)}


@route("GET", "/sales/job-codes")
def sales_job_codes(m, claims, qs, body):
    with db._lock:
        return 200, _with_meta({"job_codes": copy.deepcopy(list(db.JOB_CODES.values()))}, qs, "job_code")


# ------------------------------------------------------ Forecast (AI/ML -> BQ)
@route("GET", "/forecast/sites/{site_id}/sales")
def forecast_sales(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    start = _int_qs(qs, "start_offset_days", 0)
    days = _int_qs(qs, "days", 7)
    return 200, {"site_id": site_id, "forecast": db.get_forecast(site_id, start, days)}


# ---------------------------------------------------------- Transaction Data
@route("GET", "/transaction-data/sites/{site_id}/sales")
def transaction_data_sales(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    start = _int_qs(qs, "start_offset_days", -7)
    days = _int_qs(qs, "days", 7)
    return 200, {"site_id": site_id, "actual_sales": db.get_actual_sales(site_id, start, days)}


# -------------------------------------------------------------- Inventory
@route("GET", "/inventory/uom")
def inventory_uom(m, claims, qs, body):
    with db._lock:
        return 200, _with_meta({"uom": copy.deepcopy(list(db.UOM.values()))}, qs, "uom")


@route("GET", "/inventory/raw-materials")
def inventory_raw_materials(m, claims, qs, body):
    with db._lock:
        return 200, _with_meta({"raw_materials": copy.deepcopy(list(db.RAW_MATERIALS.values()))}, qs, "raw_material")


@route("GET", "/inventory/recipes")
def inventory_recipes(m, claims, qs, body):
    with db._lock:
        return 200, _with_meta({"recipes": copy.deepcopy(db.RECIPES)}, qs, "recipe")


@route("GET", "/inventory/recipes/{menu_item_id}")
def inventory_recipe(m, claims, qs, body):
    mi = m["menu_item_id"]
    with db._lock:
        if mi not in db.RECIPES:
            raise ApiError(404, f"no recipe for {mi}")
        return 200, {"menu_item_id": mi, "lines": copy.deepcopy(db.RECIPES[mi])}


@route("GET", "/inventory/vendors")
def inventory_vendors(m, claims, qs, body):
    with db._lock:
        return 200, _with_meta({"vendors": copy.deepcopy(list(db.VENDORS.values()))}, qs, "vendor")


@route("GET", "/inventory/sites/{site_id}/on-hand")
def inventory_on_hand(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    with db._lock:
        payload = {
            "site_id": site_id,
            "on_hand": copy.deepcopy(db.ON_HAND[site_id]),
            "par_levels": copy.deepcopy(db.PAR_LEVELS),
            "reorder_points": copy.deepcopy(db.REORDER_POINTS),
        }
        return 200, _with_meta(payload, qs, "on_hand", "par_level", "reorder_point", site_id=site_id)


@route("GET", "/inventory/par-levels")
def inventory_par_levels(m, claims, qs, body):
    with db._lock:
        return 200, _with_meta({"par_levels": copy.deepcopy(db.PAR_LEVELS)}, qs, "par_level")


@route("GET", "/inventory/reorder-points")
def inventory_reorder_points(m, claims, qs, body):
    with db._lock:
        return 200, _with_meta({"reorder_points": copy.deepcopy(db.REORDER_POINTS)}, qs, "reorder_point")


@route("GET", "/inventory/sites/{site_id}/usage")
def inventory_usage(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    start = _int_qs(qs, "start_offset_days", -7)
    days = _int_qs(qs, "days", 7)
    with db._lock:  # reads the (writable) recipe table
        actual, expected = db.get_actual_usage(site_id, start, days)
    return 200, {"site_id": site_id, "actual_usage": actual, "expected_usage": expected}


@route("POST", "/inventory/purchase-orders")
def inventory_create_po(m, claims, qs, body):
    fields = body if isinstance(body, dict) else {}
    audit_fields = {
        "kind": "purchase_order",
        "site_id": _known_site(fields.get("site_id")),
        "changes": {
            "vendor_id": fields.get("vendor_id"),
            "site_id": fields.get("site_id"),
            "region_id": fields.get("region_id"),
            "line_items": fields.get("line_items", []),
        },
    }
    with db._lock:
        try:
            site_id, region_id = body.get("site_id"), body.get("region_id")
            if not all(isinstance(v, str) for v in (site_id, region_id) if v is not None):
                raise ApiError(400, "site_id and region_id must be strings")
            if not site_id and not region_id:
                raise ApiError(400, "purchase order needs a site_id or region_id")
            if site_id:
                _require_site(claims, site_id)
            if region_id:
                _require_region(claims, region_id)
                if not site_id and claims["persona"] not in ("REGIONAL_MANAGER", "SYSTEM_ADMIN"):
                    raise ApiError(403, "region-level PO requires a regional or admin persona")
                if site_id and db.SITES[site_id]["region_id"] != region_id:
                    raise ApiError(400, f"site {site_id} is not in region {region_id}")
            vendor_id = body.get("vendor_id")
            if vendor_id not in db.VENDORS:
                raise ApiError(400, f"unknown vendor {vendor_id}")
        except Exception as e:  # audited as a violation, then re-raised unchanged
            _audit_gated(
                claims, "submit_purchase_order", "violation", record_id=None, reason=_refusal_reason(e), **audit_fields
            )
            raise
        po_id = db.next_po_id()  # allocated first so the allowed entry records it (BR3.2)
        _audit_gated(claims, "submit_purchase_order", "allowed", record_id=po_id, **audit_fields)
        try:
            po = {
                "po_id": po_id,
                "vendor_id": vendor_id,
                "site_id": site_id,
                "region_id": body.get("region_id"),
                "line_items": body.get("line_items", []),
                "status": "SUBMITTED",
                "submitted_by": claims["sub"],
            }
            db.PURCHASE_ORDERS.append(po)
        except Exception as e:
            _audit_failed_after_audit(claims, "submit_purchase_order", e, record_id=po_id, **audit_fields)
            raise
    return 201, po


@route("GET", "/inventory/purchase-orders")
def inventory_list_pos(m, claims, qs, body):
    site_id = qs.get("site_id", [None])[0]
    region_id = qs.get("region_id", [None])[0]
    if site_id:
        _require_site(claims, site_id)
    if region_id:
        _require_region(claims, region_id)
    with db._lock:
        pos = [dict(po) for po in db.PURCHASE_ORDERS]

    def visible(po):
        # A site PO follows site scope; a region-level PO follows region scope.
        if po["site_id"]:
            return site_allowed(claims, po["site_id"])
        return region_allowed(claims, po["region_id"])

    pos = [
        po
        for po in pos
        if visible(po) and (not site_id or po["site_id"] == site_id) and (not region_id or po["region_id"] == region_id)
    ]
    return 200, {"purchase_orders": pos}


# ------------------------------------------------------------------- Labor
@route("GET", "/labor/sites/{site_id}/employees")
def labor_employees(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    with db._lock:
        emps = [copy.deepcopy(e) for e in db.EMPLOYEES.values() if e["site_id"] == site_id]
        return 200, _with_meta({"site_id": site_id, "employees": emps}, qs, "employee", site_id=site_id)


@route("GET", "/labor/rules")
def labor_rules(m, claims, qs, body):
    """``?jurisdiction=X`` returns that rule, unchanged. ``?with=meta`` alone
    lists every rule plus meta; with both, the one rule plus its meta (NFR4.6)."""
    jurisdiction = qs.get("jurisdiction", [None])[0]
    with db._lock:
        if jurisdiction is None and writes.wants_meta(qs):
            return 200, {
                "rules": copy.deepcopy(db.LABOR_RULES_BY_JURISDICTION),
                "meta": {"labor_rule": writes.meta_map("labor_rule")},
            }
        rules = db.LABOR_RULES_BY_JURISDICTION.get(jurisdiction)
        if not rules:
            raise ApiError(404, f"no rules for jurisdiction {jurisdiction}")
        payload = copy.deepcopy(rules)
        if writes.wants_meta(qs):
            payload["meta"] = {"labor_rule": {jurisdiction: writes.meta_map("labor_rule")[jurisdiction]}}
        return 200, payload


def _shift_span(shift):
    """(start, end) datetimes for a shift. An end_time at or before start_time
    means the shift runs past midnight into the next day.

    Parsed strictly as YYYY-MM-DD + HH:MM wall-clock time: fromisoformat would
    also accept UTC offsets ("20:00+04:00"), letting a shift that's 12h on the
    clock validate as 8h of absolute time."""
    try:
        # Naive on purpose: shift times are site-local wall clock with no zone.
        start = datetime.strptime(f"{shift['date']} {shift['start_time']}", "%Y-%m-%d %H:%M")  # noqa: DTZ007
        end = datetime.strptime(f"{shift['date']} {shift['end_time']}", "%Y-%m-%d %H:%M")  # noqa: DTZ007
    except (KeyError, TypeError, ValueError) as e:
        raise ApiError(400, f"malformed shift {shift!r}: {e}") from e
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _hours(start, end):
    return (end - start).total_seconds() / 3600.0


@route("POST", "/labor/rules/validate")
def labor_rules_validate(m, claims, qs, body):
    """Labor Scheduling service -> Labor Rules Engine call, simulated inline.

    Same-day split shifts are allowed (rest is checked between days, not
    between shifts on one date), but their combined hours are capped at
    max_shift_length_hours and no two shifts may overlap."""
    jurisdiction = body.get("jurisdiction")
    with db._lock:  # a copy, so a concurrent write can't change the rules mid-check
        rules = copy.deepcopy(db.LABOR_RULES_BY_JURISDICTION.get(jurisdiction))
    if not rules:
        raise ApiError(404, f"no rules for jurisdiction {jurisdiction}")
    shifts = body.get("shifts", [])
    if not isinstance(shifts, list):
        raise ApiError(400, "shifts must be a list")
    violations = []

    by_emp = {}
    for s in shifts:
        if not isinstance(s, dict) or "employee_id" not in s:
            raise ApiError(400, f"malformed shift {s!r}: missing employee_id")
        by_emp.setdefault(s["employee_id"], []).append((*_shift_span(s), s))

    for emp_id, spans in by_emp.items():
        spans.sort(key=lambda span: span[0])

        def violate(rule, detail, emp_id=emp_id):
            violations.append({"employee_id": emp_id, "rule": rule, "detail": detail})

        weekly_hours = sum(_hours(start, end) for start, end, _ in spans)
        if weekly_hours > rules["weekly_ot_threshold_hours"]:
            violate(
                "weekly_overtime", f"{weekly_hours:.1f}h scheduled vs {rules['weekly_ot_threshold_hours']}h threshold"
            )

        daily_hours = {}
        for start, end, s in spans:
            h = _hours(start, end)
            daily_hours[s["date"]] = daily_hours.get(s["date"], 0.0) + h
            if h > rules["max_shift_length_hours"]:
                violate("max_shift_length", f"{s['date']} shift is {h:.1f}h vs {rules['max_shift_length_hours']}h max")
        for day, h in sorted(daily_hours.items()):
            shifts_that_day = sum(1 for _, _, s in spans if s["date"] == day)
            if shifts_that_day > 1 and h > rules["max_shift_length_hours"]:
                violate(
                    "max_daily_hours",
                    f"{day}: {h:.1f}h across {shifts_that_day} shifts vs {rules['max_shift_length_hours']}h max",
                )

        dates = sorted(daily_hours)
        consecutive = 1
        for i in range(1, len(dates)):
            if (date.fromisoformat(dates[i]) - date.fromisoformat(dates[i - 1])).days == 1:
                consecutive += 1
                if consecutive > rules["max_consecutive_days"]:
                    violate(
                        "max_consecutive_days",
                        f"{consecutive} consecutive days scheduled vs {rules['max_consecutive_days']} max",
                    )
            else:
                consecutive = 1

        for (_, prev_end, prev), (curr_start, _, curr) in pairwise(spans):
            gap_hours = _hours(prev_end, curr_start)
            if gap_hours < 0:
                violate(
                    "overlapping_shifts",
                    f"{curr['date']} {curr['start_time']} shift starts before the "
                    f"{prev['date']} {prev['start_time']} shift ends",
                )
            elif prev["date"] != curr["date"] and gap_hours < rules["min_rest_hours_between_shifts"]:
                violate(
                    "min_rest_between_shifts",
                    f"only {gap_hours:.1f}h rest before {curr['date']} shift vs "
                    f"{rules['min_rest_hours_between_shifts']}h min",
                )

    return 200, {"violations": violations, "rules": rules}


@route("POST", "/labor/sites/{site_id}/schedules/publish")
def labor_publish_schedule(m, claims, qs, body):
    site_id = m["site_id"]
    attempted = body.get("shifts", []) if isinstance(body, dict) else None
    audit_fields = {
        "kind": "schedule",
        "record_id": site_id,
        "site_id": _known_site(site_id),
        "changes": {"shift_count": len(attempted) if isinstance(attempted, list) else None, "shifts": attempted},
    }
    with db._lock:
        try:
            _require_site(claims, site_id)
            if claims["persona"] not in ("RESTAURANT_MANAGER", "REGIONAL_MANAGER"):
                raise ApiError(403, "persona cannot publish schedules")
            shifts = body.get("shifts", [])
            if not isinstance(shifts, list):  # checked before storing, so a bad publish leaves nothing behind
                raise ApiError(400, "shifts must be a list")
        except Exception as e:  # audited as a violation, then re-raised unchanged
            _audit_gated(claims, "publish_schedule", "violation", reason=_refusal_reason(e), **audit_fields)
            raise
        _audit_gated(claims, "publish_schedule", "allowed", **audit_fields)
        try:
            db.SCHEDULES.setdefault(site_id, {})["published"] = shifts
        except Exception as e:
            _audit_failed_after_audit(claims, "publish_schedule", e, **audit_fields)
            raise
    return 200, {"site_id": site_id, "status": "PUBLISHED", "shift_count": len(shifts), "published_by": claims["sub"]}


@route("GET", "/labor/sites/{site_id}/schedules")
def labor_get_schedules(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    return 200, {"site_id": site_id, "published": db.SCHEDULES.get(site_id, {}).get("published", [])}


# ------------------------------------------------------------------- Audit
@route("GET", "/audit")
def audit_view(m, claims, qs, body):
    """C3 (as amended): newest first, 50 per page, positioned by ``before``.

    The viewer's scope comes only from the verified token, so no query
    parameter can widen what it sees (NFR4.3). Read-only: there is no other
    method on this path (NFR3.10). Any well-formed ``before`` is accepted,
    even one whose entry was purged; a malformed one is a 400 (BR4.3)."""
    viewer = {
        "user_id": claims["sub"],
        "persona": claims["persona"],
        "site_ids": claims.get("site_ids") or [],
        "region_id": claims.get("region_id"),
    }
    try:
        return 200, audit.page(viewer, qs.get("before", [None])[0])
    except audit.InvalidPageRequest as e:
        raise ApiError(400, str(e)) from e
    except audit.AuditUnavailable as e:
        raise ApiError(503, "audit unavailable") from e


# ------------------------------------------------- Dashboard data writes (U1)
# C1 sessions and C2 writes. The rules (check order, audit, apply, request-id
# replay) live in mock_hsm/writes.py; every handler returns its
# (status, payload) as is, refusals included ({error, problems}).


@route("POST", "/sessions")
def sessions_start(m, claims, qs, body):
    return writes.start_session(claims)


@route("POST", "/sessions/{session_id}/logout")
def sessions_logout(m, claims, qs, body):
    return writes.end_session(claims, m["session_id"])


@route("GET", "/sessions/{session_id}")
def sessions_status(m, claims, qs, body):
    return writes.session_status(claims, m["session_id"])


def _write_route(kind_name, action):
    def handler(m, claims, qs, body):
        return writes.write(kind_name, action, claims, m.get("site_id"), m.get("record_id"), body)

    handler.__name__ = f"{kind_name}_{action}"
    return handler


def _bulk_route(kind_name):
    def handler(m, claims, qs, body):
        return writes.bulk(kind_name, claims, m.get("site_id"), body)

    handler.__name__ = f"{kind_name}_bulk"
    return handler


def _template_route(kind_name):
    def handler(m, claims, qs, body):
        return writes.template(kind_name, claims, m.get("site_id"))

    handler.__name__ = f"{kind_name}_template"
    return handler


def _register_write_routes():
    """C2 for each kind: template and bulk go ahead of every other route, so
    ``template`` and ``bulk`` (reserved ids) never reach an item route."""
    for kind in writes.KINDS.values():
        route("GET", kind.collection_path + "/template", first=True)(_template_route(kind.name))
        route("POST", kind.collection_path + "/bulk", first=True)(_bulk_route(kind.name))
        route("POST", kind.collection_path)(_write_route(kind.name, "add"))
        route("PUT", kind.item_path)(_write_route(kind.name, "update"))
        route("DELETE", kind.item_path)(_write_route(kind.name, "delete"))


_register_write_routes()


# --------------------------------------------------------------------- Health
@route("GET", "/healthz")
def healthz(m, claims, qs, body):
    return 200, {"status": "ok"}


_PUBLIC_ROUTES = {("GET", "/healthz")}
_CONTENT_LENGTH_RE = re.compile(r"[0-9]+")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # keep demo output quiet; flip on for debugging

    def _read_body(self):
        """DispatcherGuard: ``(body, None)``, or ``(None, (status, payload))``
        for a refusal. Never audited, like the dispatcher's 401s (NFR2.2).

        A missing Content-Length means no body, as before (every GET from the
        shared client). A value that is not a whole number gets 400 without
        reading the body. A body over 1 MiB is drained (up to 8 MiB, in 64 KiB
        chunks) so the client sees the 400 rather than a reset; above 8 MiB
        the connection is closed without reading. A body that won't parse --
        bad JSON, bad UTF-8, a 5,000-digit integer, nesting too deep for the
        parser -- gets 400."""
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return {}, None
        text = raw_length.strip()
        if not _CONTENT_LENGTH_RE.fullmatch(text):
            self.close_connection = True
            return None, (400, {"error": "invalid Content-Length"})
        digits = text.lstrip("0") or "0"  # leading zeros don't change the length
        length = int(digits) if len(digits) <= 10 else writes.MAX_DRAIN_BYTES + 1
        if length > writes.MAX_DRAIN_BYTES:
            self.close_connection = True
            return None, (400, {"error": "request too large"})
        if length > writes.MAX_BODY_BYTES:
            self._drain(length)
            return None, (400, {"error": "request too large"})
        if not length:
            return {}, None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode() or "{}"), None
        except (ValueError, RecursionError):  # JSONDecodeError and UnicodeDecodeError are ValueErrors
            return None, (400, {"error": "invalid JSON body"})

    def _drain(self, length):
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, writes.DRAIN_CHUNK_BYTES))
            if not chunk:
                break
            remaining -= len(chunk)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        body, refusal = self._read_body()
        if refusal is not None:
            return self._send(*refusal)

        claims = None
        if (method, parsed.path) not in _PUBLIC_ROUTES:
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return self._send(401, {"error": "missing bearer token"})
            try:
                claims = verify_token(auth_header[len("Bearer ") :])
            except TokenError as e:
                return self._send(401, {"error": f"invalid token: {e}"})
            except SecretMissingError as e:
                return self._secret_unavailable(method, parsed.path, e)

        for m, regex, handler in ROUTES:
            if m != method:
                continue
            match = regex.match(parsed.path)
            if match:
                try:
                    status, payload = handler(match.groupdict(), claims, qs, body)
                except ApiError as e:
                    return self._send(e.status, {"error": e.message})
                except SecretMissingError as e:
                    return self._secret_unavailable(method, parsed.path, e)
                except Exception as e:  # noqa: BLE001 -- any handler bug becomes a 500, not a dropped connection
                    return self._send(500, {"error": str(e)})
                return self._send(status, payload)
        self._send(404, {"error": f"no route for {method} {parsed.path}"})

    def _secret_unavailable(self, method, path, error):
        """The backend lost its signing secret mid-run: 503 naming the variable,
        not a 500, and keep serving. The warning carries the path without the
        query string, and neither it nor the body ever holds the value (the
        message is fixed text from mock_hsm.auth)."""
        print(f"[mock-hsm] WARNING {method} {path}: 503, signing secret unavailable ({error.reason})", file=sys.stderr)
        return self._send(503, {"error": str(error)})

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


def run(host="127.0.0.1", port=8770):
    # Initialize the audit trail at boot so loading it, dropping a torn last
    # line and the startup retention purge don't wait for the first audited
    # request. Later purges run lazily, at most once per 24 hours, at the start
    # of an audit append or page call (mock_hsm/audit.py).
    audit.configure()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[mock-hsm] listening on http://{host}:{port}", flush=True)
    server.serve_forever()


def main(argv=None):
    """Separate-process start: fail closed before binding when there is no
    usable signing secret (taken from .env.local if the variable is unset)."""
    parser = argparse.ArgumentParser(prog="python3 -m mock_hsm.server", description="Run the mock HSM backend.")
    parser.add_argument("--port", type=int, default=8770, help="port to listen on (default 8770)")
    args = parser.parse_args(argv)
    load_local_secret()
    try:
        require_secret()
    except SecretMissingError as e:
        print(f"[mock-hsm] refusing to start: {e}", file=sys.stderr)
        return 1
    run(port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
