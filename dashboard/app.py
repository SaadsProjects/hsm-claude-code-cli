"""
Streamlit dashboard over the HSM labor and inventory services.

    streamlit run dashboard/app.py --server.address 127.0.0.1

The dashboard runs its own mock backend on 127.0.0.1 inside this process
(mock_hsm/embedded.py), started at the top of every render; no separate
backend is needed and HSM_BASE_URL is not read. If that start fails, the page
shows only a short "didn't start" message and the cause goes to the log.

The user logs in as a persona (a backend session); the tabs appear only while
logged in. Every read and write goes through HsmClient with a token minted for
the logged-in persona, so the backend's site/region scope and write rules
decide what is visible and what is saved. Overview, Labor and Inventory are
read-only; Manage data adds, edits, deletes and bulk-uploads reference data,
and Audit lists the audit trail (unit U4; see dashboard/README.md). The
dashboard never publishes schedules or submits purchase orders.
"""

import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

from agents.hsm_client import HsmApiError
from dashboard import actions, audit_tab, data, manage_tab, session
from dashboard.safe_text import escape_md
from mock_hsm import embedded

# Persona list for the picker. Token minting is already tied to the mock's
# user table (mock_hsm.auth), so reading it here adds no new coupling; no
# dashboard *data* comes from mock_hsm.db.
from mock_hsm.db import USERS

CACHE_TTL_SECONDS = 60
# Screen 4: fixed text only; the cause is in the log (mock_hsm.embedded logs it).
BACKEND_FAILED = "The demo backend didn't start. Reload the page or try again later."

# Categorical slots in fixed order, plus the reserved "critical" status color.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
CRITICAL = "#d03b3b"
ROLE_ORDER = ["JC-LEAD", "JC-COOK", "JC-SERVER", "JC-CASHIER"]
ROLE_TITLES = {"JC-LEAD": "Shift Lead", "JC-COOK": "Cook", "JC-SERVER": "Server", "JC-CASHIER": "Cashier"}


# ------------------------------------------------------------------ loaders
def _client(user_id):
    # One factory for every client, so the screen tests point every read and
    # write at their own backend with one patch (NFR6.2).
    return session.client_for(user_id)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_sites(user_id):
    return _client(user_id).get_sites()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_site_bundle(user_id, site_id, demand_offset):
    client = _client(user_id)
    site = client.get_site(site_id)
    employees = client.get_employees(site_id)
    shifts = client.get_published_schedule(site_id)
    validation = None
    if shifts and isinstance(shifts, list):  # a non-list is reported by labor_tab; nothing to validate
        try:
            validation = client.validate_schedule(site["jurisdiction"], shifts)
        except HsmApiError as e:
            # e.g. a malformed time published straight through the API: report it, keep the rest of the page.
            validation = {"error": f"{e.status}: {e.message}"}
    return {
        "site": site,
        "demand": data.labor_demand(client, site_id, start_offset=demand_offset),
        "sales": data.sales_vs_forecast(client, site_id),
        "employees": employees,
        "rules": client.get_labor_rules(site["jurisdiction"]),
        "shifts": shifts,
        "validation": validation,
        "on_hand": data.on_hand_frame(client.get_on_hand(site_id), client.get_raw_materials()),
        "anomalies": data.usage_anomalies(client, site_id),
        "reorder": data.reorder_needs(client, site_id),
        "vendors": client.get_vendors(),
        "purchase_orders": client.get_purchase_orders(site_id=site_id),
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_region(user_id, region_id):
    client = _client(user_id)
    return (
        data.region_rollup(client, client.get_sites(region_id=region_id)),
        client.get_purchase_orders(region_id=region_id),
    )


# ------------------------------------------------------------------- charts
def _covers_chart(demand):
    df = pd.DataFrame(
        [{"date": d["date"], "day": f"{d['weekday']} {d['date'][5:]}", "covers": d["covers"]} for d in demand]
    )
    return (
        alt.Chart(df)
        .mark_bar(color=SERIES[0], cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("day:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("covers:Q", title="Forecast covers"),
            tooltip=["date", alt.Tooltip("covers:Q", format=",.1f")],
        )
    )


def _role_hours_chart(demand):
    rows = [
        {
            "day": f"{d['weekday']} {d['date'][5:]}",
            "role": ROLE_TITLES[jc],
            "order": ROLE_ORDER.index(jc),
            "hours": hours,
        }
        for d in demand
        for jc, hours in d["role_hours_needed"].items()
    ]
    titles = [ROLE_TITLES[jc] for jc in ROLE_ORDER]
    return (
        alt.Chart(pd.DataFrame(rows))
        .mark_bar(stroke="white", strokeWidth=2)
        .encode(
            x=alt.X("day:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("hours:Q", title="Labor hours needed"),
            color=alt.Color(
                "role:N", scale=alt.Scale(domain=titles, range=SERIES), title="Role", legend=alt.Legend(orient="top")
            ),
            order=alt.Order("order:Q"),
            tooltip=["day", "role", alt.Tooltip("hours:Q", format=",.1f")],
        )
    )


def _sales_chart(sales):
    long = sales.melt("date", var_name="series", value_name="units").dropna()
    long["series"] = long["series"].map({"actual": "Actual", "forecast": "Forecast"})
    long["day"] = pd.to_datetime(long["date"]).dt.strftime("%a %m-%d")
    base = alt.Chart(long).encode(
        x=alt.X("day:N", sort=alt.EncodingSortField("date"), title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("units:Q", title="Units sold", scale=alt.Scale(zero=False)),
        color=alt.Color(
            "series:N",
            scale=alt.Scale(domain=["Actual", "Forecast"], range=SERIES[:2]),
            title=None,
            legend=alt.Legend(orient="top"),
        ),
        tooltip=["date", "series", alt.Tooltip("units:Q", format=",.1f")],
    )
    return base.mark_line(strokeWidth=2) + base.mark_point(size=64, filled=True)


def _on_hand_chart(on_hand, reorder):
    projected = {n["raw_material_id"]: n["projected_qty_at_delivery"] for n in reorder}
    df = on_hand.assign(
        pct_of_par=(on_hand["on_hand"] / on_hand["par"] * 100).round(1),
        rop_pct=(on_hand["reorder_point"] / on_hand["par"] * 100).round(1),
        projected=on_hand["raw_material_id"].map(projected),
        status=on_hand["raw_material_id"].map(lambda rm: "Reorder needed" if rm in projected else "OK"),
    )
    df["projected_pct"] = (df["projected"] / df["par"] * 100).round(1)
    # Most urgent first: lowest projected stock at delivery, then everything that doesn't need a reorder.
    order = df.sort_values(["projected_pct", "pct_of_par"], na_position="last")["name"].tolist()
    y = alt.Y("name:N", sort=order, title=None)
    bars = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            y=y,
            x=alt.X("pct_of_par:Q", title="% of par"),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(domain=["OK", "Reorder needed"], range=[SERIES[0], CRITICAL]),
                title=None,
                legend=alt.Legend(orient="top"),
            ),
            tooltip=[
                "name",
                "uom",
                "on_hand",
                "reorder_point",
                "par",
                alt.Tooltip("pct_of_par:Q", title="On hand, % of par"),
            ],
        )
    )
    rop = (
        alt.Chart(df)
        .mark_tick(color="#52514e", thickness=2, size=18)
        .encode(
            y=y,
            x="rop_pct:Q",
            tooltip=["name", alt.Tooltip("reorder_point:Q", title="Reorder point")],
        )
    )
    proj = (
        alt.Chart(df.dropna(subset=["projected"]))
        .mark_point(
            shape="diamond",
            size=90,
            filled=True,
            color="#0b0b0b",
            stroke="white",
            strokeWidth=1.5,
        )
        .encode(
            y=y,
            x="projected_pct:Q",
            tooltip=[
                "name",
                "uom",
                alt.Tooltip("projected:Q", title="Projected at delivery"),
                alt.Tooltip("projected_pct:Q", title="Projected, % of par"),
            ],
        )
    )
    return bars + rop + proj


# --------------------------------------------------------------------- tabs
def _money(x):
    return f"${x:,.2f}"


def overview_tab(bundle, user):
    demand, anomalies, reorder = bundle["demand"], bundle["anomalies"], bundle["reorder"]
    cols = st.columns(4)
    cols[0].metric("Forecast covers (selected week)", f"{sum(d['covers'] for d in demand):,.0f}")
    cols[1].metric("Usage anomalies (past 7 days)", len(anomalies))
    cols[2].metric("Anomaly cost impact", _money(sum(a["cost_impact"] for a in anomalies)))
    cols[3].metric("Items needing reorder", len(reorder))

    st.subheader("Actual vs forecast sales, past 7 days")
    st.altair_chart(_sales_chart(bundle["sales"]), width="stretch")

    if user["region_id"]:
        st.subheader(f"Region roll-up: {user['region_id']}")
        rollup, region_pos = load_region(user["user_id"], user["region_id"])
        st.dataframe(
            rollup,
            hide_index=True,
            column_config={
                "anomaly_cost_impact": st.column_config.NumberColumn("Anomaly cost impact", format="$%.2f"),
                "suggested_order_value": st.column_config.NumberColumn("Suggested order value", format="$%.2f"),
            },
        )
        st.subheader("Region-level purchase orders")
        _po_table(region_pos)


def _total_or_blank(values):
    """Sum that stays blank if any value is unknown, rather than reading as a complete (or zero) total."""
    return values.sum(skipna=False)


def labor_tab(bundle):
    demand = bundle["demand"]
    left, right = st.columns(2)
    with left:
        st.subheader("Forecast covers per day")
        st.altair_chart(_covers_chart(demand), width="stretch")
    with right:
        st.subheader("Labor hours needed by role")
        st.altair_chart(_role_hours_chart(demand), width="stretch")

    st.subheader("Published schedule")
    shifts = bundle["shifts"]
    if not isinstance(shifts, list):
        # Another backend may not reject this at publish time the way the mock now does.
        st.error(f"✖ The published schedule is malformed: expected a list of shifts, got {type(shifts).__name__}")
    elif not shifts:
        st.info("No schedule has been published for this site yet.")
    else:
        validation = bundle["validation"]
        violations = validation.get("violations", [])
        if "error" in validation:
            st.error(f"✖ Labor Rules Engine could not validate the published shifts ({validation['error']})")
        elif violations:
            st.error(f"✖ {len(violations)} labor-rule violation(s) reported by the Labor Rules Engine")
            st.dataframe(pd.DataFrame(violations), hide_index=True, width="stretch")
        else:
            st.success("✔ Labor Rules Engine reports no violations for the published shifts")
        sched = data.schedule_frame(shifts, bundle["employees"])
        c = st.columns(3)
        c[0].metric("Shifts", len(sched))
        hours, cost = _total_or_blank(sched["hours"]), _total_or_blank(sched["est_cost"])
        no_hours, no_cost = sched["hours"].isna().sum(), sched["est_cost"].isna().sum()
        c[1].metric(
            "Scheduled hours",
            "—" if pd.isna(hours) else f"{hours:,.1f}",
            help=f"{no_hours} shift(s) have no usable start/end time" if no_hours else None,
        )
        c[2].metric(
            "Est. straight-time cost",
            "—" if pd.isna(cost) else _money(cost),
            help=f"{no_cost} shift(s) lack usable hours or a rostered hourly rate" if no_cost else None,
        )
        per_emp = sched.groupby(["employee_id", "name", "role"], as_index=False, dropna=False).agg(
            shifts=("hours", "size"), hours=("hours", _total_or_blank), est_cost=("est_cost", _total_or_blank)
        )
        st.dataframe(per_emp, hide_index=True, width="stretch")
        with st.expander("All shifts"):
            st.dataframe(sched, hide_index=True, width="stretch")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Roster")
        roster = pd.DataFrame(bundle["employees"])
        roster["available_days"] = roster["available_days"].str.join(", ")
        st.dataframe(roster, hide_index=True, width="stretch")
    with right:
        st.subheader(f"Labor rules ({bundle['rules']['jurisdiction']})")
        st.dataframe(pd.Series(bundle["rules"], name="value").astype(str), width="stretch")


def inventory_tab(bundle):
    st.subheader("On hand vs par")
    st.caption(
        "Bar = on hand now. Tick = reorder point. Diamond = projected stock when the vendor's next "
        "delivery lands (shown for items that need reordering). All as % of par; "
        "below 0 means a projected stockout before the delivery arrives."
    )
    st.altair_chart(_on_hand_chart(bundle["on_hand"], bundle["reorder"]), width="stretch")
    with st.expander("On-hand table"):
        st.dataframe(bundle["on_hand"], hide_index=True, width="stretch")

    st.subheader("Usage anomalies (past 7 days, >15% variance)")
    if bundle["anomalies"]:
        anomalies = pd.DataFrame(bundle["anomalies"])
        anomalies["variance"] = anomalies["variance_pct"].map(
            lambda v: "unexplained usage" if pd.isna(v) else f"{v:+.1f}%"
        )
        st.dataframe(
            anomalies.drop(columns=["variance_pct"]),
            hide_index=True,
            column_config={"cost_impact": st.column_config.NumberColumn("cost_impact", format="$%.2f")},
        )
    else:
        st.info("No usage anomalies above threshold.")

    st.subheader("Reorder needs (next 7 days)")
    if bundle["reorder"]:
        st.dataframe(pd.DataFrame(bundle["reorder"]), hide_index=True, width="stretch")
    else:
        st.info("Nothing at or below its reorder point.")

    left, right = st.columns(2)
    with left:
        st.subheader("Vendors")
        vendors = pd.DataFrame(bundle["vendors"])
        vendors["materials"] = vendors["price_list"].map(lambda p: ", ".join(sorted(p)))
        st.dataframe(vendors.drop(columns=["price_list"]), hide_index=True, width="stretch")
    with right:
        st.subheader("Submitted purchase orders")
        _po_table(bundle["purchase_orders"])


def _po_table(pos):
    if not pos:
        st.info("No purchase orders submitted.")
        return
    df = pd.DataFrame(pos)
    df["lines"] = df["line_items"].map(len)
    st.dataframe(df.drop(columns=["line_items"]), hide_index=True, width="stretch")


# ------------------------------------------------- login, banner, notice (U4)
PERSONA_KEY = "session-persona"
# Every button below runs its action inline and then reruns, so the next
# completed render shows the outcome (NFR2.3, NFR-design Q2: B).


def _login_panel():
    """Logged out: only the persona selector and Log in (WF1)."""
    user_ids = list(USERS)
    default_user = os.environ.get("HSM_ACTIVE_USER")
    st.selectbox(
        "Persona",
        user_ids,
        index=user_ids.index(default_user) if default_user in user_ids else 0,
        key=PERSONA_KEY,
        format_func=lambda u: USERS[u]["name"],
    )
    if st.button("Log in", key="session-login", type="primary"):
        actions.then_rerun(actions.log_in, st.session_state[PERSONA_KEY])


def _session_panel(login):
    """Logged in: who is logged in, and Log out (WF3). Log out always ends
    the login at once; a held write is dropped and the logged-out page says
    so (NFR2.4 as amended by NFR-design Q1: B)."""
    name = USERS.get(login["user_id"], {}).get("name", login["user_id"])
    st.caption(f"Logged in as {escape_md(name)} ({escape_md(login['persona'])})")
    if st.button("Log out", key="session-logout"):
        actions.then_rerun(actions.log_out)


def _banner():
    """The unsaved-write banner (WF8), drawn above the tabs on every run."""
    held = session.pending_retry()
    if held is None or actions.retry_expired():
        return
    st.warning(f"We couldn't confirm this was saved ({escape_md(held.get('describe'))}).")
    again, drop = st.columns(2)
    if again.button("Try again", key="notice-try-again"):
        actions.then_rerun(actions.try_again)
    if drop.button("Discard", key="notice-discard"):
        actions.then_rerun(actions.discard)


def _notice_panel():
    """The last outcome (WF7): the message, any problems, and Reload for a stale record."""
    notice = session.notice()
    if not notice:
        return
    level = notice["level"]
    if level == "success":
        st.success(escape_md(notice["message"]))
    elif level == "error":
        st.error(escape_md(notice["message"]))
    elif level == "warning":
        st.warning(escape_md(notice["message"]))
    else:
        st.info(escape_md(notice["message"]))
    if notice["problems"]:
        problems = pd.DataFrame(notice["problems"])
        st.dataframe(problems[[c for c in ("row", "field", "reason") if c in problems]], hide_index=True)
    if notice.get("note"):
        st.caption(escape_md(notice["note"]))
    if notice.get("stale") and st.button("Reload", key="notice-reload"):
        actions.then_rerun(actions.reload)


def _guarded_tab(draw, *args):
    """Anything unexpected is shown in place of the part that failed; the
    login and the other tabs are kept (WF7)."""
    try:
        draw(*args)
    except Exception as e:  # noqa: BLE001 -- shown in place of the tab
        st.error(f"Something went wrong: {escape_md(type(e).__name__)}")


# --------------------------------------------------------------------- main
def _page_header():
    st.set_page_config(page_title="HSM Dashboard", layout="wide")
    st.title("HSM labor & inventory")


def main():
    _page_header()

    problem = actions.check_session()  # every run while logged in; may log out (WF2)
    login = session.login()
    with st.sidebar:
        if login is None:
            _login_panel()
        else:
            _session_panel(login)
    _banner()
    _notice_panel()
    if login is None:
        st.info("Log in to see the dashboard.")
        return
    if problem is not None:
        st.error(escape_md(problem))
        return

    user_id = login["user_id"]
    user = USERS[user_id]
    with st.sidebar:
        sites = load_sites(user_id)
        if not sites:
            st.warning("This persona has no sites in scope.")
            st.stop()
        site_id = st.selectbox(
            "Site",
            [s["site_id"] for s in sites],
            format_func=lambda s: next(x["name"] for x in sites if x["site_id"] == s) + f" ({s})",
        )
        week = st.radio("Labor demand week", ["This week", "Next week"], index=1, horizontal=True)
        if st.button("Refresh data"):
            # The shared cache and this session's Manage data reads (Q3: B).
            actions.then_rerun(actions.clear_cached_reads)
        backend = embedded.current()  # read at render time: a replaced backend has a new port
        st.caption(f"Backend: {backend.address if backend else 'not running'} · cached {CACHE_TTL_SECONDS}s")

    with st.spinner("Loading…"):
        bundle = load_site_bundle(user_id, site_id, 0 if week == "This week" else 7)
    site = bundle["site"]
    st.caption(f"{site['name']} · {site_id} · {site['jurisdiction']} · {site['timezone']}")

    overview, labor, inventory, manage, audit = st.tabs(["Overview", "Labor", "Inventory", "Manage data", "Audit"])
    with overview:
        overview_tab(bundle, user)
    with labor:
        labor_tab(bundle)
    with inventory:
        inventory_tab(bundle)
    with manage:
        _guarded_tab(manage_tab.render, user, site_id)
    with audit:
        _guarded_tab(audit_tab.render)


def run():
    # The backend start is the first step of every render, before any screen
    # reads data (BR5.4); module state makes every rerun after the first a
    # liveness check. A failure shows only Screen 4.
    if embedded.start().status != "running":
        _page_header()
        st.markdown(BACKEND_FAILED)
        return
    try:
        main()
    except embedded.BackendNotRunning:
        st.markdown(BACKEND_FAILED)  # lost between the start and a read; the next rerun replaces it
    except HsmApiError as e:
        st.warning(f"HSM API refused the request ({e.status}): {e.message}")
    except urllib.error.URLError as e:
        st.error(f"Can't reach the demo backend ({escape_md(str(e.reason))}). Reload the page or try again later.")


run()
