"""
REST client the agents use to talk to HSM.

Zero third-party dependencies on purpose (urllib only) so this runs anywhere
with plain Python 3. Pointed at http://127.0.0.1:8770 by default (the mock
server); pointed at a real HSM deployment, this file does not change --
only HSM_BASE_URL and the token source (mock_hsm.auth -> a real OIDC/Apigee
client) would.
"""
import json
import os
import urllib.error
import urllib.request

HSM_BASE_URL = os.environ.get("HSM_BASE_URL", "http://127.0.0.1:8770")


class HsmApiError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(f"HSM API error {status}: {message}")
        self.status = status
        self.message = message


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
        return self._request("GET", f"/forecast/sites/{site_id}/sales",
                              params={"start_offset_days": start_offset_days, "days": days})["forecast"]

    # ---- Transaction Data ---------------------------------------------------
    def get_actual_sales(self, site_id, start_offset_days=-7, days=7):
        return self._request("GET", f"/transaction-data/sites/{site_id}/sales",
                              params={"start_offset_days": start_offset_days, "days": days})["actual_sales"]

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
        return self._request("GET", f"/inventory/sites/{site_id}/usage",
                              params={"start_offset_days": start_offset_days, "days": days})

    def submit_purchase_order(self, vendor_id, line_items, site_id=None, region_id=None):
        body = {"vendor_id": vendor_id, "line_items": line_items}
        if site_id:
            body["site_id"] = site_id
        if region_id:
            body["region_id"] = region_id
        return self._request("POST", "/inventory/purchase-orders", json_body=body)

    # ---- Labor ----------------------------------------------------------------
    def get_employees(self, site_id):
        return self._request("GET", f"/labor/sites/{site_id}/employees")["employees"]

    def get_labor_rules(self, jurisdiction):
        return self._request("GET", "/labor/rules", params={"jurisdiction": jurisdiction})

    def validate_schedule(self, jurisdiction, shifts):
        return self._request("POST", "/labor/rules/validate",
                              json_body={"jurisdiction": jurisdiction, "shifts": shifts})

    def publish_schedule(self, site_id, shifts):
        return self._request("POST", f"/labor/sites/{site_id}/schedules/publish",
                              json_body={"shifts": shifts})
