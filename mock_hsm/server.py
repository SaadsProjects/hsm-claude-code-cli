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
"""
import json
import re
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from urllib.parse import parse_qs, urlparse

from mock_hsm import db
from mock_hsm.auth import TokenError, region_allowed, site_allowed, verify_token


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


ROUTES = []  # (method, compiled_regex, handler)


def route(method, pattern):
    regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")

    def deco(fn):
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
    return 200, {"menu_items": list(db.MENU_ITEMS.values())}


# ----------------------------------------------------------------- Sales
@route("GET", "/sales/gl-codes")
def sales_gl_codes(m, claims, qs, body):
    codes = sorted({mi["gl_code"] for mi in db.MENU_ITEMS.values()})
    return 200, {"gl_codes": codes}


@route("GET", "/sales/job-codes")
def sales_job_codes(m, claims, qs, body):
    return 200, {"job_codes": list(db.JOB_CODES.values())}


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
    return 200, {"uom": list(db.UOM.values())}


@route("GET", "/inventory/raw-materials")
def inventory_raw_materials(m, claims, qs, body):
    return 200, {"raw_materials": list(db.RAW_MATERIALS.values())}


@route("GET", "/inventory/recipes/{menu_item_id}")
def inventory_recipe(m, claims, qs, body):
    mi = m["menu_item_id"]
    if mi not in db.RECIPES:
        raise ApiError(404, f"no recipe for {mi}")
    return 200, {"menu_item_id": mi, "lines": db.RECIPES[mi]}

@route("GET", "/inventory/vendors")
def inventory_vendors(m, claims, qs, body):
    return 200, {"vendors": list(db.VENDORS.values())}


@route("GET", "/inventory/sites/{site_id}/on-hand")
def inventory_on_hand(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    return 200, {
        "site_id": site_id,
        "on_hand": db.ON_HAND[site_id],
        "par_levels": db.PAR_LEVELS,
        "reorder_points": db.REORDER_POINTS,
    }


@route("GET", "/inventory/sites/{site_id}/usage")
def inventory_usage(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    start = _int_qs(qs, "start_offset_days", -7)
    days = _int_qs(qs, "days", 7)
    actual, expected = db.get_actual_usage(site_id, start, days)
    return 200, {"site_id": site_id, "actual_usage": actual, "expected_usage": expected}


@route("POST", "/inventory/purchase-orders")
def inventory_create_po(m, claims, qs, body):
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
    po = {
        "po_id": db.next_po_id(),
        "vendor_id": vendor_id,
        "site_id": site_id,
        "region_id": body.get("region_id"),
        "line_items": body.get("line_items", []),
        "status": "SUBMITTED",
        "submitted_by": claims["sub"],
    }
    db.PURCHASE_ORDERS.append(po)
    return 201, po


# ------------------------------------------------------------------- Labor
@route("GET", "/labor/sites/{site_id}/employees")
def labor_employees(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    emps = [e for e in db.EMPLOYEES.values() if e["site_id"] == site_id]
    return 200, {"site_id": site_id, "employees": emps}


@route("GET", "/labor/rules")
def labor_rules(m, claims, qs, body):
    jurisdiction = qs.get("jurisdiction", [None])[0]
    rules = db.LABOR_RULES_BY_JURISDICTION.get(jurisdiction)
    if not rules:
        raise ApiError(404, f"no rules for jurisdiction {jurisdiction}")
    return 200, rules


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
    rules = db.LABOR_RULES_BY_JURISDICTION.get(jurisdiction)
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
            violate("weekly_overtime",
                    f"{weekly_hours:.1f}h scheduled vs {rules['weekly_ot_threshold_hours']}h threshold")

        daily_hours = {}
        for start, end, s in spans:
            h = _hours(start, end)
            daily_hours[s["date"]] = daily_hours.get(s["date"], 0.0) + h
            if h > rules["max_shift_length_hours"]:
                violate("max_shift_length",
                        f"{s['date']} shift is {h:.1f}h vs {rules['max_shift_length_hours']}h max")
        for day, h in sorted(daily_hours.items()):
            shifts_that_day = sum(1 for _, _, s in spans if s["date"] == day)
            if shifts_that_day > 1 and h > rules["max_shift_length_hours"]:
                violate("max_daily_hours",
                        f"{day}: {h:.1f}h across {shifts_that_day} shifts vs {rules['max_shift_length_hours']}h max")

        dates = sorted(daily_hours)
        consecutive = 1
        for i in range(1, len(dates)):
            if (date.fromisoformat(dates[i]) - date.fromisoformat(dates[i - 1])).days == 1:
                consecutive += 1
                if consecutive > rules["max_consecutive_days"]:
                    violate("max_consecutive_days",
                            f"{consecutive} consecutive days scheduled vs {rules['max_consecutive_days']} max")
            else:
                consecutive = 1

        for (_, prev_end, prev), (curr_start, _, curr) in pairwise(spans):
            gap_hours = _hours(prev_end, curr_start)
            if gap_hours < 0:
                violate("overlapping_shifts",
                        f"{curr['date']} {curr['start_time']} shift starts before the "
                        f"{prev['date']} {prev['start_time']} shift ends")
            elif prev["date"] != curr["date"] and gap_hours < rules["min_rest_hours_between_shifts"]:
                violate("min_rest_between_shifts",
                        f"only {gap_hours:.1f}h rest before {curr['date']} shift vs "
                        f"{rules['min_rest_hours_between_shifts']}h min")

    return 200, {"violations": violations, "rules": rules}


@route("POST", "/labor/sites/{site_id}/schedules/publish")
def labor_publish_schedule(m, claims, qs, body):
    site_id = m["site_id"]
    _require_site(claims, site_id)
    if claims["persona"] not in ("RESTAURANT_MANAGER", "REGIONAL_MANAGER"):
        raise ApiError(403, "persona cannot publish schedules")
    shifts = body.get("shifts", [])
    db.SCHEDULES.setdefault(site_id, {})["published"] = shifts
    return 200, {"site_id": site_id, "status": "PUBLISHED", "shift_count": len(shifts), "published_by": claims["sub"]}


# --------------------------------------------------------------------- Health
@route("GET", "/healthz")
def healthz(m, claims, qs, body):
    return 200, {"status": "ok"}


_PUBLIC_ROUTES = {("GET", "/healthz")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # keep demo output quiet; flip on for debugging

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        body = {}
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "invalid JSON body"})

        claims = None
        if (method, parsed.path) not in _PUBLIC_ROUTES:
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return self._send(401, {"error": "missing bearer token"})
            try:
                claims = verify_token(auth_header[len("Bearer "):])
            except TokenError as e:
                return self._send(401, {"error": f"invalid token: {e}"})

        for m, regex, handler in ROUTES:
            if m != method:
                continue
            match = regex.match(parsed.path)
            if match:
                try:
                    status, payload = handler(match.groupdict(), claims, qs, body)
                except ApiError as e:
                    return self._send(e.status, {"error": e.message})
                except Exception as e:  # noqa: BLE001 -- any handler bug becomes a 500, not a dropped connection
                    return self._send(500, {"error": str(e)})
                return self._send(status, payload)
        self._send(404, {"error": f"no route for {method} {parsed.path}"})

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


def run(host="127.0.0.1", port=8770):
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[mock-hsm] listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
