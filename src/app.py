"""CoolCheck approval App (Databricks Apps, Streamlit; docs/design/agent_app.md).

A coordinator picks the briefing date, the call capacity and a region; the App calls the three Unity Catalog functions
through the SQL warehouse, shows the draft plan, and the Approve button writes one row to <catalog>.gold.pending_approval.
Nothing is ever sent. Everything runs as the App's service principal; the approver is recorded as the Databricks user ID
the Apps proxy passes (X-Forwarded-User), never a name or e-mail. Settings come from the bundle (resources/coolcheck_app.app.yml).
"""
import datetime as dt
import os

import streamlit as st

from coolcheck import plan as P

st.set_page_config(page_title="CoolCheck: outreach plan", layout="wide")

CATALOG = os.environ.get("COOLCHECK_CATALOG", "coolcheck")
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID")
EXPERIMENT_ID = os.environ.get("MLFLOW_EXPERIMENT_ID")
APP_COMMIT = os.environ.get("APP_COMMIT")
DEFAULT_CAPACITY = int(os.environ.get("DEFAULT_CALL_CAPACITY", "800"))
CALLS_PER_VOLUNTEER = int(os.environ.get("CALLS_PER_VOLUNTEER", "25"))
LLM_MODEL = os.environ.get("LLM_MODEL", "system.ai.meta-llama-3-3-70b-instruct")
REGION_CHOICES = ["Whole island", "Central", "East", "North", "North-East", "West"]


@st.cache_resource
def warehouse():
    from databricks.sdk import WorkspaceClient
    return P.Warehouse(WorkspaceClient(), WAREHOUSE_ID)


@st.cache_resource
def tracing_ready():
    """Point MLflow at the workspace experiment; returns a note if tracing is off."""
    if not EXPERIMENT_ID:
        return "no MLFLOW_EXPERIMENT_ID: drafts are not traced"
    try:
        import mlflow
        mlflow.set_tracking_uri("databricks")
        mlflow.set_experiment(experiment_id=EXPERIMENT_ID)
        return None
    except Exception as e:  # shown in Diagnostics
        return f"tracing off: {type(e).__name__}: {e}"


@st.cache_data(ttl=600)
def dates():
    return P.briefing_dates(warehouse(), CATALOG)


def approver():
    try:
        return (st.context.headers.get("X-Forwarded-User") or "").strip()
    except Exception:
        return ""


def show_draft(d):
    st.subheader(f"Draft plan for {d.target_date:%d %b %Y}")
    if d.source == P.AGENT:
        st.caption(f"Summary written by {d.llm_model}; every number in it was found in a tool result.")
    elif d.fallback_reason:
        st.info(f"Template version (decision 4): {d.fallback_reason}")
    for n in d.notices:
        st.warning(n)
    st.text(d.draft_text)
    others = [r for r in d.rows if r["calls_allocated"] == 0]
    with st.expander(f"Areas without calls ({len(others)})"):
        st.dataframe([{"tier": r["tier"], "area": P.area_name(r["planning_area"]), "region": P.region_name(r["region"]),
                       "heat level": r["heat_level"], "vulnerability third": r["third"], "reason": r["reason"]}
                      for r in others], hide_index=True, width="stretch")
    with st.expander(f"Tool calls ({len(d.tool_calls)})"):
        for c in d.tool_calls:
            asked = f" (the model asked for `{c.llm_arguments}`)" if c.llm_arguments is not None else ""
            st.markdown(f"**{c.name}** `{c.arguments}`{asked}: {len(c.rows)} rows in {c.elapsed_ms} ms"
                        f"{'; error: ' + c.error if c.error else ''}")
        if d.checks:
            st.write("Checks:", d.checks)
            st.json(c.rows, expanded=False)
    st.caption(f"MLflow trace: {d.trace_id or 'none'} · approval id {d.approval_id}")


def approve_box(d):
    done = st.session_state.get("approved", {})
    if d.approval_id in done:
        row = done[d.approval_id]
        st.success(f"Approved {row['approved_sgt']} SGT (approval {row['approval_id']}). Nothing has been sent.")
        return
    who = approver()
    if not who:
        st.button("Approve", disabled=True, help="Approval needs the Databricks Apps sign-in.")
        st.caption("Approve is off: no Databricks Apps sign-in header (X-Forwarded-User).")
        return
    if st.button("Approve", type="primary"):
        try:
            row = P.approve(warehouse(), d, who, CATALOG, APP_COMMIT)
        except Exception as e:
            st.error(f"Not approved: {type(e).__name__}: {e}")
            return
        done[d.approval_id] = row
        st.session_state["approved"] = done
        st.rerun()
    st.caption("Approving records this plan for the Active Ageing Centre team. CoolCheck sends nothing: no e-mail, SMS "
               "or message of any kind.")


def refuge_tools():
    with st.expander("Nearest refuges and what-if (direct tool calls)"):
        st.caption("A confirmed HDB block, e.g. 208A and WOODLEIGH LINK. Distances are straight lines, not walking distances.")
        c1, c2 = st.columns([1, 3])
        blk = c1.text_input("Block", key="blk")
        street = c2.text_input("Street, as people write it (e.g. Jalan Kukoh or JLN KUKOH)", key="street")
        b1, b2 = st.columns(2)
        tools = P.Tools(warehouse(), CATALOG)
        if b1.button("Find the 5 nearest refuges", disabled=not (blk and street)):
            call = tools.find_refuges(blk, street)
            if call.error:
                st.error(call.error)
            elif not call.rows:
                st.info("No rows: the block is not found or its coordinate is not confirmed.")
            else:
                st.dataframe([{"rank": r["refuge_rank"], "refuge": r["refuge_name"], "type": r["refuge_type"],
                               "address": r["address"], "distance": P.metres(r["distance_m"]),
                               "within 400 m": r["within_400m"]} for r in call.rows], hide_index=True)
        if b2.button("What if a refuge opened here?", disabled=not (blk and street)):
            call = tools.what_if_add_refuge(blk, street)
            if call.error:
                st.error(call.error)
            elif not call.rows:
                st.info("No rows: the block is not found or its coordinate is not confirmed.")
            else:
                st.dataframe([{"area": P.area_name(r["planning_area"]), "site area": r["is_site_area"],
                               "dwelling units within 400 m": f"{r['du_within_400m_before']} -> {r['du_within_400m_after']}",
                               "share within 400 m": f"{r['share_within_400m_before']:.0%} -> {r['share_within_400m_after']:.0%}",
                               "1-2 room rental flats beyond 400 m":
                                   f"{r['rental_flats_beyond_400m_before']} -> {r['rental_flats_beyond_400m_after']}",
                               "blocks newly within": r["blocks_newly_within"]} for r in call.rows], hide_index=True)


def diagnostics():
    with st.expander("Diagnostics", expanded=False):
        st.caption("Runs as the App's service principal. Positive checks must pass; negative checks must be refused.")
        note = tracing_ready()
        st.write(f"Catalog `{CATALOG}`, commit `{APP_COMMIT}`, warehouse set: {bool(WAREHOUSE_ID)}, tracing: {note or 'on'}")
        who = approver()
        shape = ("none" if not who else "numeric ID" if who.replace("@", "").isdigit()
                 else "looks like an e-mail" if "@" in who and any(c.isalpha() for c in who) else "other")
        st.write(f"Approver header (X-Forwarded-User): {shape}")
        if st.button("Run self-check"):
            d = (dates() or [None])[0]
            wh = warehouse()
            checks = [
                ("SELECT on gold.area_heat_risk", True, f"SELECT max(target_date) AS d FROM {CATALOG}.gold.area_heat_risk", None),
                ("EXECUTE get_priority_areas", True, f"SELECT count(*) AS n FROM {CATALOG}.gold.get_priority_areas(:d, 0)",
                 {"d": (str(d), "DATE")}),
                ("EXECUTE find_refuges", True, f"SELECT count(*) AS n FROM {CATALOG}.gold.find_refuges('208A', 'WOODLEIGH LINK')", None),
                ("EXECUTE what_if_add_refuge", True,
                 f"SELECT count(*) AS n FROM {CATALOG}.gold.what_if_add_refuge('3', 'JLN KUKOH')", None),
                ("SELECT and MODIFY on gold.pending_approval (writes no row)", True,
                 f"INSERT INTO {CATALOG}.gold.pending_approval SELECT * FROM {CATALOG}.gold.pending_approval WHERE false", None),
                ("no access to gold.heat_forecast (P(High))", False, f"SELECT count(*) AS n FROM {CATALOG}.gold.heat_forecast", None),
                ("no access to silver.block_access", False, f"SELECT count(*) AS n FROM {CATALOG}.silver.block_access", None),
            ]
            out = []
            for name, should_pass, sql, params in checks:
                try:
                    rows = wh.query(sql, params)
                    ok, detail = should_pass, f"ran: {rows[:1]}"
                except Exception as e:
                    ok, detail = not should_pass, f"refused: {str(e)[:200]}"
                out.append({"check": name, "result": "OK" if ok else "FAIL", "detail": detail})
            if note is None:
                with P.span("self_check", "UNKNOWN", {"checks": len(checks)}) as s:
                    s.set_outputs({"results": out})
                tid = P.trace_id_of(s)
                out.append({"check": "MLflow trace written", "result": "OK" if tid else "FAIL", "detail": f"trace {tid}"})
            st.dataframe(out, hide_index=True, width="stretch")


st.title("CoolCheck: next-day heat outreach plan")
st.caption("Draft only. A person approves; nothing is sent. Heat is forecast per planning area; blocks rank vulnerability, "
           "never heat. Tier actions are a proposal, not yet reviewed by a practitioner.")

if not WAREHOUSE_ID:
    st.error("No SQL warehouse is set (DATABRICKS_WAREHOUSE_ID).")
    st.stop()

tracing_ready()
available = dates()
stale = P.stale_notice(available[0] if available else None)
if stale:
    st.warning(stale)
with st.form("inputs"):
    request = st.text_area("Request (optional), e.g. \"Only 8 volunteers tomorrow, North-East only\"", max_chars=500,
                           help="Do not enter names or personal details.")
    st.caption("Do not enter names or personal details. " + P.MASK_NOTE)
    c1, c2, c3, c4 = st.columns(4)
    target_date = c1.selectbox("Briefing date", available, format_func=lambda d: f"{d:%a %d %b %Y}")
    capacity = c2.number_input("Call capacity (placeholder: replace with your team's figure)", min_value=0,
                               max_value=100000, value=DEFAULT_CAPACITY, step=50)
    cpv = c3.number_input("Calls per volunteer (assumption: replace with your team's figure)", min_value=1,
                          max_value=500, value=CALLS_PER_VOLUNTEER)
    region = c4.selectbox("Region", REGION_CHOICES)
    b1, b2 = st.columns(2)
    with_agent = b1.form_submit_button("Draft with the agent", type="primary")
    tools_only = b2.form_submit_button("Draft from the tools only")

if (with_agent or tools_only) and target_date:
    region_value = None if region == "Whole island" else region.upper()
    try:
        forecast = P.forecast_info(warehouse(), target_date, CATALOG)
        if with_agent:
            from databricks.sdk import WorkspaceClient
            from coolcheck import agent as A
            with st.spinner("The agent is drafting (up to 90 s)..."):
                st.session_state["draft"] = A.draft_plan(
                    request, target_date=target_date, default_capacity=int(capacity), calls_per_volunteer=int(cpv),
                    region=region_value, catalog=CATALOG, runner=warehouse(), workspace_client=WorkspaceClient(),
                    model=LLM_MODEL, forecast=forecast)
        else:
            _, basis = P.capacity_from(int(capacity), int(cpv))
            st.session_state["draft"] = P.draft_direct(P.Tools(warehouse(), CATALOG), target_date, int(capacity), basis,
                                                       region_value, forecast, reason="direct tool calls, no model")
    except Exception as e:
        st.error(f"The tools could not be called: {type(e).__name__}: {e}")

draft = st.session_state.get("draft")
if draft:
    show_draft(draft)
    approve_box(draft)
refuge_tools()
diagnostics()
