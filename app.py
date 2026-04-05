"""Med Vessel Behaviour Monitor — orchestrator."""

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime

from config import (
    EVENT_COLORS, DEFAULT_EVENT_WEIGHTS, FLAG_RISKS,
    SPECIES_NAMES, assign_csquare,
)
from data_loading import (
    load_knowledge_base, load_static_data, load_live_data,
    load_fdi_effort, load_fdi_landings,
)
from risk_model import compute_risk_score, get_fdi_context
from tabs import (
    render_daily_trend, render_flag_breakdown, render_event_types,
    render_duration_analysis, render_geographic_risk, render_risk_heatmap,
    render_repeat_offenders, render_gap_behaviour, render_encounter_analysis,
    render_top_vessels, render_fisheries_context,
)
from ai_analyst import render_ai_analyst

# ========================= PAGE CONFIG =========================
st.set_page_config(
    page_title="Med Vessel Behaviour Monitor",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Med Vessel Behaviour Monitor")
st.markdown("**Behavioral risk intelligence for the Mediterranean Sea** — AIS gaps, encounters and loitering events")

# ========================= SIDEBAR =========================
st.sidebar.header("Filters & Controls")

try:
    token = st.secrets["gfw_token"]
except (FileNotFoundError, KeyError):
    token = st.sidebar.text_input(
        "GFW API Token (free)", type="password",
        help="Register at globalfishingwatch.org -> Our APIs",
    )

use_live = st.sidebar.toggle(
    "Use Live GFW API", value=False,
    help="Requires valid token. Static demo data is always available.",
)

date_range = st.sidebar.date_input(
    "Date range",
    value=(datetime(2026, 3, 1), datetime(2026, 3, 31)),
    min_value=datetime(2024, 1, 1),
    max_value=datetime.today(),
)

if len(date_range) < 2:
    st.warning("Please select both start and end dates.")
    st.stop()

min_duration = st.sidebar.slider(
    "Minimum event duration (hours)", 2, 48, 2,
    help="GFW encounter threshold is 2h",
)

with st.sidebar.expander("Advanced -- Risk Weights (optional)"):
    gap_weight = st.number_input("Gap weight", value=DEFAULT_EVENT_WEIGHTS["GAP"], min_value=0.1, step=0.1)
    loitering_weight = st.number_input("Loitering weight", value=DEFAULT_EVENT_WEIGHTS["LOITERING"], min_value=0.1, step=0.1)
    encounter_weight = st.number_input("Encounter weight", value=DEFAULT_EVENT_WEIGHTS["ENCOUNTER"], min_value=0.1, step=0.1)

event_weights = {"GAP": gap_weight, "LOITERING": loitering_weight, "ENCOUNTER": encounter_weight}

# ========================= DATA LOADING =========================
if use_live and token:
    df = load_live_data(token, date_range[0], date_range[1], min_duration)
else:
    df = load_static_data()

fdi_effort = load_fdi_effort()
fdi_landings = load_fdi_landings()
knowledge_base = load_knowledge_base()

# ========================= FILTER & SCORE =========================
df_filtered = df[df["duration_h"] >= min_duration].copy()
df_filtered["risk_score"] = df_filtered.apply(
    compute_risk_score, axis=1, event_weights=event_weights, flag_risks=FLAG_RISKS,
).round(1)
total_risk = df_filtered["risk_score"].sum()

# Assign c-square cells for FDI joins
if not df_filtered.empty:
    csq = df_filtered.apply(lambda r: assign_csquare(r["lat"], r["lon"]), axis=1)
    df_filtered["csq_lon"] = csq.apply(lambda x: x[0])
    df_filtered["csq_lat"] = csq.apply(lambda x: x[1])

# ========================= MAIN MAP & METRICS =========================
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Behavioral Risk Map")
    if not df_filtered.empty:
        m = folium.Map(location=[37.0, 18.0], zoom_start=5, tiles="CartoDB positron")
        color_map = {"GAP": "red", "LOITERING": "orange", "ENCOUNTER": "purple"}

        for _, row in df_filtered.iterrows():
            popup_text = f"""
            <b>Event:</b> {row['event_type']}<br>
            <b>Flag:</b> {row['flag']}<br>
            <b>Duration:</b> {row['duration_h']} h<br>
            <b>Risk Score:</b> {row['risk_score']:.1f}
            """
            if "vessel_name" in row and pd.notna(row.get("vessel_name")):
                popup_text = f"<b>{row['vessel_name']}</b><br>" + popup_text

            if not fdi_effort.empty and "csq_lon" in row.index:
                ctx = get_fdi_context(row["csq_lon"], row["csq_lat"], fdi_effort, fdi_landings)
                if ctx and ctx["total_fishing_days"] > 0:
                    top_sp_str = ", ".join(
                        SPECIES_NAMES.get(s[0], s[0]) for s in ctx["top_species"][:3]
                    )
                    popup_text += f"""
                    <hr style='margin:4px 0'>
                    <b>FDI Baseline</b><br>
                    <b>Fishing ground:</b> {'Yes' if ctx['is_known_fishing_ground'] else 'No'}<br>
                    <b>Fishing days:</b> {ctx['total_fishing_days']:,.0f}<br>
                    <b>Top species:</b> {top_sp_str}<br>
                    <b>Landings:</b> {ctx['total_landings_tonnes']:,.0f} t
                    """

            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=8,
                color=color_map.get(row["event_type"], "blue"),
                popup=popup_text,
                fill=True,
            ).add_to(m)

        st_folium(m, width=700, height=500)
    else:
        st.info("No events match the selected filters.")

with col2:
    st.metric("Mediterranean Behavioral Risk Index", f"{total_risk:.0f}")
    st.caption("Encounters weighted highest . Russian/Iranian flags boosted")
    if not df_filtered.empty:
        st.metric("Events", len(df_filtered))
        st.metric("Unique Vessels", df_filtered["mmsi"].nunique())
        st.metric("Flags", df_filtered["flag"].nunique())

# ========================= TABS =========================
tab_names = [
    "Daily Trend", "Flag Breakdown", "Event Types", "Duration Analysis",
    "Geographic Risk", "Risk Heatmap", "Repeat Offenders", "Gap Behaviour",
    "Encounter Analysis", "Top Vessels", "Fisheries Context", "AI Analyst",
]
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs(tab_names)

with tab1:  render_daily_trend(df_filtered)
with tab2:  render_flag_breakdown(df_filtered)
with tab3:  render_event_types(df_filtered)
with tab4:  render_duration_analysis(df_filtered)
with tab5:  render_geographic_risk(df_filtered)
with tab6:  render_risk_heatmap(df_filtered)
with tab7:  render_repeat_offenders(df_filtered)
with tab8:  render_gap_behaviour(df_filtered)
with tab9:  render_encounter_analysis(df_filtered)
with tab10: render_top_vessels(df_filtered)
with tab11: render_fisheries_context(df_filtered, fdi_effort, fdi_landings)

try:
    gemini_key = st.secrets["gemini_key"]
except (FileNotFoundError, KeyError):
    gemini_key = ""
with tab12: render_ai_analyst(df_filtered, fdi_effort, fdi_landings, knowledge_base, gemini_key)

# ========================= SIDEBAR METHODOLOGY =========================
with st.sidebar.expander("Methodology & About"):
    st.markdown("""
**GFW-Aligned Risk Scoring**

Risk model replicates Global Fishing Watch transshipment detection
methodology (Miller et al. 2018).

`risk = duration^0.75 x event_weight x flag_mult x shore_factor x event_factors`

**Encounter factors** (GFW criteria):
- Proximity: <500m = 1.8x (GFW threshold)
- Speed: <2kn = 1.5x (likely transfer)
- Vessel type: reefer/carrier = 1.4x

**Loitering factors** (potential transshipment):
- Reefer/carrier loitering = 1.6x
- Avg speed <2kn = 1.4x

**Gap factors** (evasion):
- Speed change >5kn across gap = 1.5x

**Shore distance** (all events):
- >20nm = 1.5x | >10km = 1.2x | <10km = 0.8x

**Data:** GFW Events API (GAP, ENCOUNTER, LOITERING)

*Not all dark activity is illegal. For educational use only.*
    """)

# ========================= DOWNLOAD =========================
if not df_filtered.empty:
    csv = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download filtered events as CSV",
        data=csv,
        file_name="med_vessel_events.csv",
        mime="text/csv",
    )

st.caption("Data: Global Fishing Watch Events API | Risk model: custom behavioural scoring | Built as a weekend portfolio project")
