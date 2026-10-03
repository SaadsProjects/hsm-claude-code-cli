"""
In-memory data store + seed data for the mock HSM backend.

This stands in for HSM's real Postgres-per-service + BigQuery reporting layer.
Everything lives in one process/dict for demo simplicity, but it is organized
by "service" (the dict keys mirror the real microservice boundaries) so the
mapping back to the real architecture stays obvious.
"""
import random
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_lock = threading.RLock()

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

ORG = {"org_id": "org_001", "name": "Riverside Hospitality Group"}

REGIONS = {
    "region_atl": {"region_id": "region_atl", "name": "Atlanta Metro", "org_id": "org_001"},
}

SITES = {
    "site_001": {"site_id": "site_001", "name": "Midtown", "region_id": "region_atl", "org_id": "org_001", "jurisdiction": "GA",
                 "timezone": "America/New_York"},
    "site_002": {"site_id": "site_002", "name": "Buckhead", "region_id": "region_atl", "org_id": "org_001", "jurisdiction": "GA",
                 "timezone": "America/New_York"},
    "site_003": {"site_id": "site_003", "name": "Decatur", "region_id": "region_atl", "org_id": "org_001", "jurisdiction": "GA",
                 "timezone": "America/New_York"},
}

# Demo users / personas (System of Record for this would be the platform OIDC
# service in the real system; simulated here as a static table).
USERS = {
    "user_rm_midtown": {"user_id": "user_rm_midtown", "name": "Jordan (Restaurant Manager)",
                         "persona": "RESTAURANT_MANAGER", "org_id": "org_001",
                         "site_ids": ["site_001"], "region_id": None},
    "user_regional_atl": {"user_id": "user_regional_atl", "name": "Sam (Regional Manager)",
                           "persona": "REGIONAL_MANAGER", "org_id": "org_001",
                           "site_ids": ["site_001", "site_002", "site_003"], "region_id": "region_atl"},
    # Developer/tester login for the dashboard data writes (U1, BR2.1): the
    # Regional Manager's persona value and scope, told apart in the audit
    # trail by its own user id. The gated routes check persona values, so
    # they treat it exactly like the Regional Manager.
    "user_dev_tester": {"user_id": "user_dev_tester", "name": "Dev (Developer/Tester)",
                         "persona": "REGIONAL_MANAGER", "org_id": "org_001",
                         "site_ids": ["site_001", "site_002", "site_003"], "region_id": "region_atl"},
}

# The fixed, read-only GL code list (BR5.2). GET /sales/gl-codes returns
# exactly these, and a dashboard-added menu item may use only these.
GL_CODES = ("GL-BEV", "GL-FOOD")

UOM = {
    "lb": {"uom_id": "lb", "name": "pound", "base": "oz", "factor_to_base": 16},
    "oz": {"uom_id": "oz", "name": "ounce", "base": "oz", "factor_to_base": 1},
    "each": {"uom_id": "each", "name": "each", "base": "each", "factor_to_base": 1},
}

RAW_MATERIALS = {
    "rm_ground_beef": {"raw_material_id": "rm_ground_beef", "name": "Ground Beef", "uom": "lb"},
    "rm_bun": {"raw_material_id": "rm_bun", "name": "Burger Bun", "uom": "each"},
    "rm_cheese": {"raw_material_id": "rm_cheese", "name": "Cheese Slice", "uom": "each"},
    "rm_lettuce": {"raw_material_id": "rm_lettuce", "name": "Lettuce", "uom": "lb"},
    "rm_tomato": {"raw_material_id": "rm_tomato", "name": "Tomato", "uom": "lb"},
    "rm_fries": {"raw_material_id": "rm_fries", "name": "Frozen Fries", "uom": "lb"},
    "rm_chicken": {"raw_material_id": "rm_chicken", "name": "Chicken Breast", "uom": "lb"},
    "rm_taco_shell": {"raw_material_id": "rm_taco_shell", "name": "Taco Shell", "uom": "each"},
    "rm_salsa": {"raw_material_id": "rm_salsa", "name": "Salsa", "uom": "oz"},
    "rm_rice": {"raw_material_id": "rm_rice", "name": "Rice", "uom": "lb"},
    "rm_beans": {"raw_material_id": "rm_beans", "name": "Black Beans", "uom": "lb"},
    "rm_soda_syrup": {"raw_material_id": "rm_soda_syrup", "name": "Soda Syrup", "uom": "oz"},
}

VENDORS = {
    "vendor_protein_co": {
        "vendor_id": "vendor_protein_co", "name": "Protein Co.", "lead_time_days": 2,
        "price_list": {"rm_ground_beef": 4.25, "rm_chicken": 3.60},
        "min_order_value": 150.0,
    },
    "vendor_fresh_produce": {
        "vendor_id": "vendor_fresh_produce", "name": "Fresh Produce Partners", "lead_time_days": 1,
        "price_list": {"rm_lettuce": 1.10, "rm_tomato": 1.45},
        "min_order_value": 75.0,
    },
    "vendor_dry_goods": {
        "vendor_id": "vendor_dry_goods", "name": "Metro Dry Goods", "lead_time_days": 3,
        "price_list": {"rm_bun": 0.32, "rm_cheese": 0.18, "rm_fries": 0.95, "rm_taco_shell": 0.14,
                        "rm_salsa": 0.09, "rm_rice": 0.85, "rm_beans": 0.95},
        "min_order_value": 100.0,
    },
    "vendor_beverage_supply": {
        "vendor_id": "vendor_beverage_supply", "name": "Southeast Beverage Supply", "lead_time_days": 2,
        "price_list": {"rm_soda_syrup": 0.22},
        "min_order_value": 50.0,
    },
}

MENU_ITEMS = {
    "mi_burger": {"menu_item_id": "mi_burger", "name": "Classic Burger", "gl_code": "GL-FOOD"},
    "mi_cheeseburger": {"menu_item_id": "mi_cheeseburger", "name": "Cheeseburger", "gl_code": "GL-FOOD"},
    "mi_fries": {"menu_item_id": "mi_fries", "name": "Fries", "gl_code": "GL-FOOD"},
    "mi_chicken_sandwich": {"menu_item_id": "mi_chicken_sandwich", "name": "Chicken Sandwich", "gl_code": "GL-FOOD"},
    "mi_taco": {"menu_item_id": "mi_taco", "name": "Taco", "gl_code": "GL-FOOD"},
    "mi_burrito": {"menu_item_id": "mi_burrito", "name": "Burrito Bowl", "gl_code": "GL-FOOD"},
    "mi_soda": {"menu_item_id": "mi_soda", "name": "Fountain Soda", "gl_code": "GL-BEV"},
}

RECIPES = {
    "mi_burger": [{"raw_material_id": "rm_ground_beef", "qty": 0.33, "uom": "lb"},
                  {"raw_material_id": "rm_bun", "qty": 1, "uom": "each"},
                  {"raw_material_id": "rm_lettuce", "qty": 0.05, "uom": "lb"},
                  {"raw_material_id": "rm_tomato", "qty": 0.08, "uom": "lb"}],
    "mi_cheeseburger": [{"raw_material_id": "rm_ground_beef", "qty": 0.33, "uom": "lb"},
                        {"raw_material_id": "rm_bun", "qty": 1, "uom": "each"},
                        {"raw_material_id": "rm_cheese", "qty": 1, "uom": "each"},
                        {"raw_material_id": "rm_lettuce", "qty": 0.05, "uom": "lb"}],
    "mi_fries": [{"raw_material_id": "rm_fries", "qty": 0.28, "uom": "lb"}],
    "mi_chicken_sandwich": [{"raw_material_id": "rm_chicken", "qty": 0.4, "uom": "lb"},
                            {"raw_material_id": "rm_bun", "qty": 1, "uom": "each"},
                            {"raw_material_id": "rm_lettuce", "qty": 0.05, "uom": "lb"}],
    "mi_taco": [{"raw_material_id": "rm_taco_shell", "qty": 2, "uom": "each"},
                {"raw_material_id": "rm_ground_beef", "qty": 0.2, "uom": "lb"},
                {"raw_material_id": "rm_salsa", "qty": 1, "uom": "oz"}],
    "mi_burrito": [{"raw_material_id": "rm_rice", "qty": 0.35, "uom": "lb"},
                   {"raw_material_id": "rm_beans", "qty": 0.25, "uom": "lb"},
                   {"raw_material_id": "rm_chicken", "qty": 0.3, "uom": "lb"},
                   {"raw_material_id": "rm_salsa", "qty": 1.5, "uom": "oz"}],
    "mi_soda": [{"raw_material_id": "rm_soda_syrup", "qty": 4, "uom": "oz"}],
}

JOB_CODES = {
    "JC-COOK": {"job_code": "JC-COOK", "title": "Cook"},
    "JC-SERVER": {"job_code": "JC-SERVER", "title": "Server"},
    "JC-CASHIER": {"job_code": "JC-CASHIER", "title": "Cashier"},
    "JC-LEAD": {"job_code": "JC-LEAD", "title": "Shift Lead"},
}

LABOR_RULES_BY_JURISDICTION = {
    "GA": {
        "jurisdiction": "GA",
        "weekly_ot_threshold_hours": 40,
        "daily_ot_threshold_hours": 8,
        "ot_multiplier": 1.5,
        "max_consecutive_days": 6,
        "min_rest_hours_between_shifts": 10,
        "max_shift_length_hours": 10,
        "note": "Simplified generic ruleset for demo purposes, not actual GA labor law.",
    }
}


def _gen_employees():
    employees = {}
    names = ["Alex", "Bailey", "Casey", "Drew", "Emerson", "Frankie", "Gray", "Harper",
             "Iman", "Jules", "Kai", "Logan", "Micah", "Noor", "Ora", "Parker", "Quinn", "Riley"]
    idx = 0
    for site_id in SITES:
        roles = ["JC-LEAD", "JC-COOK", "JC-COOK", "JC-SERVER", "JC-SERVER", "JC-CASHIER"]
        for i, role in enumerate(roles):
            emp_id = f"emp_{site_id}_{i+1:02d}"
            rate = {"JC-LEAD": 19.5, "JC-COOK": 16.0, "JC-SERVER": 13.0, "JC-CASHIER": 12.5}[role]
            employees[emp_id] = {
                "employee_id": emp_id,
                "name": names[idx % len(names)],
                "site_id": site_id,
                "job_code": role,
                "hourly_rate": rate,
                "jurisdiction": SITES[site_id]["jurisdiction"],
                "max_weekly_hours_preference": 35 if role != "JC-LEAD" else 40,
                "available_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            }
            idx += 1
    return employees


EMPLOYEES = _gen_employees()

# on-hand inventory per site (raw_material_id -> qty in the material's native uom)
_BASE_ON_HAND = {
    "rm_ground_beef": 40, "rm_bun": 220, "rm_cheese": 200, "rm_lettuce": 15, "rm_tomato": 12,
    "rm_fries": 60, "rm_chicken": 35, "rm_taco_shell": 300, "rm_salsa": 250, "rm_rice": 25,
    "rm_beans": 20, "rm_soda_syrup": 180,
}

ON_HAND = {site_id: dict(_BASE_ON_HAND) for site_id in SITES}

PAR_LEVELS = {rm_id: round(qty * 1.6) for rm_id, qty in _BASE_ON_HAND.items()}
REORDER_POINTS = {rm_id: round(qty * 0.5) for rm_id, qty in _BASE_ON_HAND.items()}

# Forecast & actual sales come from a seeded RNG, so each site/day differs but
# the noise is repeatable. Dates (and the Fri/Sat bump) follow the site's
# current calendar, so the numbers for a given day offset shift day to day.
_BASE_DAILY_UNITS = {
    "mi_burger": 30, "mi_cheeseburger": 25, "mi_fries": 45, "mi_chicken_sandwich": 20,
    "mi_taco": 28, "mi_burrito": 18, "mi_soda": 50,
}

_SITE_MULTIPLIER = {"site_001": 1.15, "site_002": 1.0, "site_003": 0.8}


def _seeded_rng(*parts):
    seed = "|".join(str(p) for p in parts)
    return random.Random(seed)


def site_today(site_id):
    """Today's calendar date in the site's own timezone."""
    return datetime.now(ZoneInfo(SITES[site_id]["timezone"])).date()


def _weekday_factor(day):
    return 1.25 if day.weekday() in (4, 5) else 1.0  # Fri/Sat bump


def get_forecast(site_id, start_offset_days, num_days):
    """AI/ML sales forecast, normally read from BigQuery. Returns per-day, per-item projected units."""
    rng = _seeded_rng("forecast", site_id)
    out = []
    today = site_today(site_id)
    for d in range(start_offset_days, start_offset_days + num_days):
        day = today + timedelta(days=d)
        day_row = {"day_index": d, "date": day.isoformat(), "items": {}}
        for item_id, base in _BASE_DAILY_UNITS.items():
            weekday_factor = _weekday_factor(day)
            noise = 1 + (rng.random() - 0.5) * 0.15
            units = base * _SITE_MULTIPLIER[site_id] * weekday_factor * noise
            day_row["items"][item_id] = round(units, 1)
        out.append(day_row)
    return out


def get_actual_sales(site_id, start_offset_days, num_days):
    """Actual POS sales for a past period (Transaction Data service)."""
    rng = _seeded_rng("actual_sales", site_id)
    out = []
    today = site_today(site_id)
    for d in range(start_offset_days, start_offset_days + num_days):
        day = today + timedelta(days=d)
        day_row = {"day_index": d, "date": day.isoformat(), "items": {}}
        for item_id, base in _BASE_DAILY_UNITS.items():
            weekday_factor = _weekday_factor(day)
            noise = 1 + (rng.random() - 0.5) * 0.2
            units = base * _SITE_MULTIPLIER[site_id] * weekday_factor * noise
            day_row["items"][item_id] = round(units, 1)
        out.append(day_row)
    return out


def get_actual_usage(site_id, start_offset_days, num_days):
    """
    Actual raw-material usage reported by Inventory (on-hand deltas + invoices),
    for the same period as get_actual_sales. Includes deliberately injected
    variance vs. recipe-expected usage so the demo has real anomalies to find:
      - rm_ground_beef: portioning drift, consistently ~20% over expected
      - rm_lettuce: one-off waste spike
      - everything else: normal +/-5% noise
    """
    sales = get_actual_sales(site_id, start_offset_days, num_days)
    totals = {}
    for day in sales:
        for item_id, units in day["items"].items():
            for line in RECIPES[item_id]:
                rm = line["raw_material_id"]
                totals[rm] = totals.get(rm, 0) + units * line["qty"]

    rng = _seeded_rng("actual_usage", site_id)
    actual = {}
    for rm, expected_qty in totals.items():
        noise = 1 + (rng.random() - 0.5) * 0.10
        factor = noise
        if rm == "rm_ground_beef":
            factor = 1.20 + (rng.random() - 0.5) * 0.05
        elif rm == "rm_lettuce" and site_id == "site_002":
            factor = 1.45
        actual[rm] = round(expected_qty * factor, 2)
    return actual, totals


PURCHASE_ORDERS = []
SCHEDULES = {}  # site_id -> {"draft": [...], "published": [...]}


def next_po_id():
    with _lock:
        return f"po_{len(PURCHASE_ORDERS) + 1:04d}"
