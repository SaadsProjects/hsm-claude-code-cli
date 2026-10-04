"""
REST client the agents use to talk to HSM.

Zero third-party dependencies on purpose (urllib only) so this runs anywhere
with plain Python 3. Pointed at http://127.0.0.1:8770 by default (the mock
server); pointed at a real HSM deployment, this file does not change --
only HSM_BASE_URL and the token source (mock_hsm.auth -> a real OIDC/Apigee
client) would.
"""

import http.client
import json
import os
import urllib.error
import urllib.request
import uuid
import weakref
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from urllib.parse import quote, urlencode

HSM_BASE_URL = os.environ.get("HSM_BASE_URL", "http://127.0.0.1:8770")

# A write whose outcome is unknown may be re-sent until this long after its
# first attempt: one minute inside the backend's 15-minute request-id replay
# window (mock_hsm/writes.py REQUEST_TTL), so a retry is always answered from
# the stored response rather than applied a second time.
RETRY_WINDOW = timedelta(minutes=14)

# What counts as "no answer" (reliability-design.md, NFR2.3). urllib wraps a
# connect failure or connect timeout in URLError; a read timeout arrives as a
# bare TimeoutError. HTTPError is a URLError but is an answer, so it is caught
# first. Anything else (InvalidURL included) is a caller bug and propagates.
_TRANSPORT_ERRORS = (
    urllib.error.URLError,
    TimeoutError,
    ConnectionError,
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
    http.client.BadStatusLine,
)

_NO_ACTIVE_SESSION = "no active session"


def _now():
    """Timezone-aware UTC now. Module level so tests can monkeypatch it; no
    client instance holds clock state (review R-04)."""
    return datetime.now(timezone.utc)


class HsmApiError(RuntimeError):
    def __init__(self, status, message, problems=None):
        super().__init__(f"HSM API error {status}: {message}")
        self.status = status
        self.message = message
        self.problems = list(problems) if problems is not None else []


class SessionExpired(HsmApiError):
    """A data write got 401 "no active session": the login session ended.
    Only that exact refusal maps here; a token problem stays HsmApiError,
    because logging in again would not fix it (BR2.2, NFR7.1)."""

    def __init__(self, message=_NO_ACTIVE_SESSION, problems=None):
        super().__init__(401, message, problems)


class HsmUnavailable(HsmApiError):
    """No HTTP answer came back (timeout, refused or reset connection, cut-off
    or unparseable 2xx reply). Status is always 0.

    ``outcome_unknown`` is True only for data writes, which then also carry
    ``request_id`` and ``retry_deadline`` (aware UTC). The exact request to
    re-send is kept outside this object, in the module's RetryStore, so it
    never shows in ``str``, ``repr`` or ``vars()`` (NFR1.2, NFR2.4)."""

    def __init__(self, message, *, outcome_unknown=False, request_id=None, retry_deadline=None):
        super().__init__(0, message)
        self.outcome_unknown = outcome_unknown
        self.request_id = request_id
        self.retry_deadline = retry_deadline


class _NoAnswer(Exception):
    """Internal signal from ``_send``: no usable answer. Callers turn it into
    a public HsmUnavailable; it never leaves this module."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class _RetryRequest(NamedTuple):
    """The exact bytes of one data write, re-sent unchanged by a retry."""

    method: str
    path: str
    data: bytes


# RetryStore: outcome-unknown HsmUnavailable -> its _RetryRequest. Weak keys,
# so an entry disappears with its error. Each entry is written once by the
# thread that raised the error, so no lock is needed.
_RETRY_STORE = weakref.WeakKeyDictionary()


class KindRoute(NamedTuple):
    """One row of the kind table (functional-spec.md). ``collection`` may hold
    ``{site_id}``. ``shape`` says how list_records turns the payload into
    records: list (used as is), lines (recipe map), qty (stock map) or rules
    (labor rules by jurisdiction)."""

    collection: str
    list_key: str
    id_field: str
    site_scoped: bool
    shape: str

    @property
    def item_path(self):
        return self.collection + "/{record_id}"


# Mirrors mock_hsm.writes.KINDS; tests/test_hsm_client_writes.py fails on drift.
# Never import mock_hsm here: the client must work against a remote backend.
KIND_TABLE = {
    "menu_item": KindRoute("/catalog/menu-items", "menu_items", "menu_item_id", False, "list"),
    "recipe": KindRoute("/inventory/recipes", "recipes", "menu_item_id", False, "lines"),
    "raw_material": KindRoute("/inventory/raw-materials", "raw_materials", "raw_material_id", False, "list"),
    "uom": KindRoute("/inventory/uom", "uom", "uom_id", False, "list"),
    "vendor": KindRoute("/inventory/vendors", "vendors", "vendor_id", False, "list"),
    "employee": KindRoute("/labor/sites/{site_id}/employees", "employees", "employee_id", True, "list"),
    "job_code": KindRoute("/sales/job-codes", "job_codes", "job_code", False, "list"),
    "on_hand": KindRoute("/inventory/sites/{site_id}/on-hand", "on_hand", "raw_material_id", True, "qty"),
    "par_level": KindRoute("/inventory/par-levels", "par_levels", "raw_material_id", False, "qty"),
    "reorder_point": KindRoute("/inventory/reorder-points", "reorder_points", "raw_material_id", False, "qty"),
    "labor_rule": KindRoute("/labor/rules", "rules", "jurisdiction", False, "rules"),
}


class HsmClient:
    """A persona-scoped client: every call carries one user's token, so every
    call is bounded by that user's site/region scope exactly as it would be
    against the real, Apigee-fronted HSM services."""

    def __init__(self, token: str, base_url: str = HSM_BASE_URL, timeout: float = 15):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method, path, params=None, json_body=None):
        url = f"{self.base_url}{path}"
        if params:
            from urllib.parse import urlencode

            url += "?" + urlencode(params, doseq=True)
        data = json.dumps(json_body).encode() if json_body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                message = json.loads(body).get("error", body)
            except json.JSONDecodeError:
                message = body
            raise HsmApiError(e.code, message) from e

    # ---- Admin -----------------------------------------------------------
    def get_sites(self, region_id=None):
        params = {"region_id": region_id} if region_id else None
        return self._request("GET", "/admin/sites", params=params)["sites"]

    def get_site(self, site_id):
        return self._request("GET", f"/admin/sites/{site_id}")

    # ---- Catalog / Menu ----------------------------------------------------
    def get_menu_items(self):
        return self._request("GET", "/catalog/menu-items")["menu_items"]

    # ---- Forecast (AI/ML -> BigQuery) --------------------------------------
    def get_forecast(self, site_id, start_offset_days=0, days=7):
        return self._request(
            "GET", f"/forecast/sites/{site_id}/sales", params={"start_offset_days": start_offset_days, "days": days}
        )["forecast"]

    # ---- Transaction Data ---------------------------------------------------
    def get_actual_sales(self, site_id, start_offset_days=-7, days=7):
        return self._request(
            "GET",
            f"/transaction-data/sites/{site_id}/sales",
            params={"start_offset_days": start_offset_days, "days": days},
        )["actual_sales"]

    # ---- Inventory ----------------------------------------------------------
    def get_raw_materials(self):
        return self._request("GET", "/inventory/raw-materials")["raw_materials"]

    def get_recipe(self, menu_item_id):
        return self._request("GET", f"/inventory/recipes/{menu_item_id}")["lines"]

    def get_vendors(self):
        return self._request("GET", "/inventory/vendors")["vendors"]

    def get_on_hand(self, site_id):
        return self._request("GET", f"/inventory/sites/{site_id}/on-hand")

    def get_usage(self, site_id, start_offset_days=-7, days=7):
        return self._request(
            "GET", f"/inventory/sites/{site_id}/usage", params={"start_offset_days": start_offset_days, "days": days}
        )

    def submit_purchase_order(self, vendor_id, line_items, site_id=None, region_id=None):
        body = {"vendor_id": vendor_id, "line_items": line_items}
        if site_id:
            body["site_id"] = site_id
        if region_id:
            body["region_id"] = region_id
        return self._request("POST", "/inventory/purchase-orders", json_body=body)

    def get_purchase_orders(self, site_id=None, region_id=None):
        params = {k: v for k, v in (("site_id", site_id), ("region_id", region_id)) if v}
        return self._request("GET", "/inventory/purchase-orders", params=params or None)["purchase_orders"]

    # ---- Labor ----------------------------------------------------------------
    def get_employees(self, site_id):
        return self._request("GET", f"/labor/sites/{site_id}/employees")["employees"]

    def get_labor_rules(self, jurisdiction):
        return self._request("GET", "/labor/rules", params={"jurisdiction": jurisdiction})

    def validate_schedule(self, jurisdiction, shifts):
        return self._request(
            "POST", "/labor/rules/validate", json_body={"jurisdiction": jurisdiction, "shifts": shifts}
        )

    def publish_schedule(self, site_id, shifts):
        return self._request("POST", f"/labor/sites/{site_id}/schedules/publish", json_body={"shifts": shifts})

    def get_published_schedule(self, site_id):
        return self._request("GET", f"/labor/sites/{site_id}/schedules")["published"]

    # ======================================================================
    # Dashboard data writes (unit U3, contract C5 as amended). Everything
    # below is new; the methods above and _request are unchanged (BR1.1).
    # ======================================================================

    # ---- Sender ------------------------------------------------------------
    def _send(self, method, path, data=None, params=None, write=False):
        """One HTTP attempt (reliability-design.md). Returns the parsed JSON
        body of a 2xx reply, raises the mapped HsmApiError / SessionExpired
        for an error status, or raises _NoAnswer when no usable answer came
        back. ``data`` is the already-encoded JSON body, if any."""
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode(params, doseq=True)
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            raise _error_from_reply(e, write) from None
        except _TRANSPORT_ERRORS as e:
            raise _NoAnswer(type(e).__name__) from None
        with resp:
            try:
                raw = resp.read()
            except _TRANSPORT_ERRORS:
                raise _NoAnswer("invalid response body") from None
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):  # bad UTF-8 and bad JSON are both ValueErrors
            raise _NoAnswer("invalid response body") from None

    def _call(self, method, path, params=None):
        """A read, session call, template or audit page: one attempt, no
        retry. No answer raises HsmUnavailable(outcome_unknown=False)."""
        try:
            return self._send(method, path, params=params)
        except _NoAnswer as signal:
            raise HsmUnavailable(_no_answer_message(signal.reason)) from None

    # ---- Writer --------------------------------------------------------------
    def _write(self, method, path, fields, session_id, request_id=None):
        """One data write (WF1, BR3.1, NFR2.1, NFR2.2). The body carries
        ``session_id``, ``request_id`` (the caller's, or a fresh uuid4) and the
        method's own ``fields``. It is encoded once, so a retry re-sends the
        identical bytes. With no answer the request is sent once more at once;
        if that also gets none, the outcome is unknown: HsmUnavailable with
        the request id and the retry deadline, and the request kept for
        retry_write. Any HTTP answer, 5xx included, is final."""
        request_id = request_id or uuid.uuid4().hex
        body = {"session_id": session_id, "request_id": request_id, **fields}
        request = _RetryRequest(method, path, json.dumps(body).encode())
        retry_deadline = _now() + RETRY_WINDOW
        try:
            return self._send(*request, write=True)
        except _NoAnswer:
            pass  # attempt 2 below, immediately and identical
        try:
            return self._send(*request, write=True)
        except _NoAnswer as signal:
            raise _outcome_unknown(request, request_id, retry_deadline, signal.reason) from None

    # ---- Sessions (C1, BR2.1): one attempt each, never retried --------------
    def start_session(self):
        """Returns ``{session_id, user_id, persona, idle_timeout_seconds}``."""
        return self._call("POST", "/sessions")

    def end_session(self, session_id):
        """Returns ``{active, ended_reason}``. An already-ended session raises
        plain HsmApiError (401), never SessionExpired."""
        return self._call("POST", f"/sessions/{_quoted(session_id)}/logout")

    def session_status(self, session_id):
        """Returns ``{active, ended_reason}``; never refreshes the idle timer."""
        return self._call("GET", f"/sessions/{_quoted(session_id)}")

    # ---- Records (C2, BR3.2, BR4.1) ------------------------------------------
    def list_records(self, kind, site_id=None):
        """Returns ``{records, meta}`` for every kind: map payloads become
        record lists and ``meta`` is this kind's ``{record key: Meta}``."""
        _, collection = _kind_route(kind, site_id)
        return _reshape(kind, self._call("GET", collection, params={"with": "meta"}), site_id)

    def add_record(self, kind, record, session_id, site_id=None, request_id=None):
        """Returns ``{record, meta}``."""
        _, collection = _kind_route(kind, site_id)
        return self._write("POST", collection, {"record": record}, session_id, request_id)

    def update_record(self, kind, record_id, record, version, session_id, site_id=None, request_id=None):
        """Returns ``{record, meta}``. ``version`` is the one the caller read."""
        _, collection = _kind_route(kind, site_id)
        return self._write(
            "PUT", f"{collection}/{_quoted(record_id)}", {"record": record, "version": version}, session_id, request_id
        )

    def delete_record(self, kind, record_id, version, session_id, site_id=None, request_id=None):
        """Returns ``{deleted, kind, record_id}``. The version goes in a JSON body."""
        _, collection = _kind_route(kind, site_id)
        return self._write("DELETE", f"{collection}/{_quoted(record_id)}", {"version": version}, session_id, request_id)

    def bulk_add(self, kind, rows, file_name, session_id, site_id=None, request_id=None):
        """Adds the rows of one CSV file, all or none (BR4.2). ``rows`` are
        sent as the caller parsed them: ``{row, record}`` or ``{row,
        parse_error}``; the client never parses CSV. Returns ``{added,
        records}``; a refused file raises HsmApiError with its ``problems``."""
        _, collection = _kind_route(kind, site_id)
        fields = {"source": "csv", "file_name": file_name, "rows": rows}
        return self._write("POST", f"{collection}/bulk", fields, session_id, request_id)

    def csv_template(self, kind, site_id=None):
        """Returns ``{columns, csv}`` (BR4.3)."""
        _, collection = _kind_route(kind, site_id)
        return self._call("GET", f"{collection}/template")

    # ---- Audit view (C3, BR4.3) ----------------------------------------------
    def audit_page(self, before=None):
        """Returns ``{entries, next_before, limit, total}``, newest first;
        pass the previous page's ``next_before`` to get the next one."""
        params = {"before": before} if before is not None else None
        return self._call("GET", "/audit", params=params)

    def retry_write(self, error):
        """Re-send the exact request behind an outcome-unknown HsmUnavailable
        ("Try again"). The backend answers a repeated request id from its
        stored response before it checks the session, so a write that did
        reach it is never applied twice, even after a logout. A first attempt
        that never reached it now gets SessionExpired if the session ended.

        Refused with ValueError, sending nothing, for any other error or once
        ``_now()`` is past ``error.retry_deadline``. A retry that gets no
        answer raises a new outcome-unknown HsmUnavailable with the same
        request id and deadline, which can itself be retried."""
        request = _RETRY_STORE.get(error) if isinstance(error, HsmUnavailable) and error.outcome_unknown else None
        if request is None or _now() > error.retry_deadline:
            raise ValueError(f"retry not allowed for request {getattr(error, 'request_id', None)}")
        try:
            return self._send(*request, write=True)
        except _NoAnswer as signal:
            raise _outcome_unknown(request, error.request_id, error.retry_deadline, signal.reason) from None


# ---- Sender helpers ---------------------------------------------------------


def _no_answer_message(reason):
    # Only the exception type name or "invalid response body": never the
    # partial bytes of a cut-off reply.
    return f"no answer from HSM: {reason}"


def _outcome_unknown(request, request_id, retry_deadline, reason):
    """The public error for a write with no answer, its retry request kept
    in RetryStore rather than on the error (NFR1.2)."""
    error = HsmUnavailable(
        _no_answer_message(reason), outcome_unknown=True, request_id=request_id, retry_deadline=retry_deadline
    )
    _RETRY_STORE[error] = request
    return error


def _error_from_reply(error, write):
    """Map an error-status reply (the error-body table in reliability-design.md).
    Only a data write's exact 401 "no active session" becomes SessionExpired."""
    try:
        with error:
            raw = error.read()
    except (OSError, http.client.HTTPException):
        return HsmApiError(error.code, "unreadable error body")
    text = raw.decode("utf-8", errors="replace")
    try:
        body = json.loads(text)
    except (ValueError, RecursionError):
        body = None
    if not isinstance(body, dict):
        return HsmApiError(error.code, text)
    message = body.get("error")
    message = message if isinstance(message, str) else text
    problems = body.get("problems")
    problems = problems if isinstance(problems, list) else []
    if write and error.code == 401 and body.get("error") == _NO_ACTIVE_SESSION:
        return SessionExpired(message, problems)
    return HsmApiError(error.code, message, problems)


# ---- Paths ------------------------------------------------------------------


def _quoted(value):
    """A path segment that can't change the route (NFR1.1)."""
    return quote(value, safe="")


def _kind_route(kind, site_id):
    """``(KindRoute, collection path)`` for a kind, checked before any request
    (BR3.2): an unknown kind, or a site kind without ``site_id``, raises
    ValueError. Shared kinds ignore ``site_id``."""
    route = KIND_TABLE.get(kind)
    if route is None:
        raise ValueError(f"unknown kind {kind!r}")
    if not route.site_scoped:
        return route, route.collection
    if not site_id:
        raise ValueError(f"kind {kind!r} needs a site_id")
    return route, route.collection.format(site_id=_quoted(site_id))


# ---- Reshaper ---------------------------------------------------------------


def _reshape(kind, payload, site_id=None):
    """``{records, meta}`` for list_records (BR4.1). A list payload is used
    as is; a map payload becomes one object per entry. ``meta`` is the
    backend's meta for this kind only (the on-hand read also carries par
    levels and reorder points; only ``on_hand`` is kept). A payload without
    the kind's key raises KeyError: that is contract drift, not a user error."""
    route = KIND_TABLE[kind]
    data = payload[route.list_key]
    if route.shape == "list":
        records = data
    elif route.shape == "lines":
        records = [{"menu_item_id": key, "lines": lines} for key, lines in data.items()]
    elif route.shape == "rules":
        records = [{"jurisdiction": key, **rule} for key, rule in data.items()]
    elif route.site_scoped:
        records = [{"site_id": site_id, "raw_material_id": key, "qty": qty} for key, qty in data.items()]
    else:
        records = [{"raw_material_id": key, "qty": qty} for key, qty in data.items()]
    return {"records": records, "meta": payload.get("meta", {}).get(kind, {})}
