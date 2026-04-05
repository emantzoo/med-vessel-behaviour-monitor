"""Med Vessel Behaviour Monitor — orchestrator."""

import streamlit as st
import pandas as pd
import folium
from folium.utilities import normalize
from streamlit_folium import st_folium
from branca.element import MacroElement, Template
from datetime import datetime

from config import (
    EVENT_COLORS, DEFAULT_EVENT_WEIGHTS, FLAG_RISKS,
    SPECIES_NAMES, assign_csquare,
)
from data_loading import (
    load_knowledge_base, load_static_data, load_live_data,
    load_fdi_effort, load_fdi_landings, load_iuu_vessels, load_iccat_vessels,
    lookup_vessel_imos,
)
from risk_model import compute_risk_score, get_fdi_context, match_iuu_vessels, match_iccat_vessels
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

include_delisted = st.sidebar.toggle(
    "Include delisted IUU vessels", value=False,
    help="Also match against vessels removed from IUU registries.",
)

resolve_imos = st.sidebar.toggle(
    "Resolve vessel IMOs (live)", value=True,
    help="Query GFW Vessels API for IMO numbers. Slower but enables stronger IUU/ICCAT matching.",
)

show_fdi_layer = st.sidebar.toggle(
    "Show FDI fishing effort layer", value=False,
    help="Overlay officially reported fishing effort (days) per c-square grid cell.",
)

# ========================= DATA LOADING =========================
if use_live and token:
    df = load_live_data(token, date_range[0], date_range[1], min_duration)
else:
    df = load_static_data()

fdi_effort = load_fdi_effort()
fdi_landings = load_fdi_landings()
iuu_vessels = load_iuu_vessels()
iccat_vessels = load_iccat_vessels()
knowledge_base = load_knowledge_base()

# ========================= FILTER & SCORE =========================
# Clip events to selected date range (± 3 day buffer for long-running events)
if "date" in df.columns and len(date_range) == 2:
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True).dt.tz_localize(None)
    buffer_start = pd.Timestamp(date_range[0]) - pd.Timedelta(days=3)
    buffer_end = pd.Timestamp(date_range[1]) + pd.Timedelta(days=3)
    df = df[df["date"].between(buffer_start, buffer_end) | df["date"].isna()]

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

# IMO enrichment via GFW Vessels API (live mode only)
if use_live and token and resolve_imos and not df_filtered.empty:
    unique_mmsis = df_filtered["mmsi"].dropna().unique().tolist()
    cache_key = f"imo_map_{hash(tuple(sorted(str(m) for m in unique_mmsis)))}"
    if cache_key in st.session_state:
        imo_map = st.session_state[cache_key]
    else:
        progress_bar = st.progress(0, text="Resolving vessel IMOs via GFW API...")
        def _update_progress(current, total):
            progress_bar.progress(current / total, text=f"Resolving vessel IMOs... {current}/{total}")
        imo_map = lookup_vessel_imos(unique_mmsis, token, progress_callback=_update_progress)
        st.session_state[cache_key] = imo_map
        progress_bar.empty()
    if imo_map:
        df_filtered["imo"] = df_filtered["mmsi"].astype(str).map(imo_map).fillna("")

# Ensure IMO column exists (static CSV may lack it)
if "imo" not in df_filtered.columns:
    df_filtered["imo"] = ""

# Preserve base risk score before IUU/ICCAT multipliers
df_filtered["base_risk_score"] = df_filtered["risk_score"].copy()

# IUU cross-reference (after risk scoring)
if not df_filtered.empty and not iuu_vessels.empty:
    df_filtered = match_iuu_vessels(df_filtered, iuu_vessels, include_delisted)
    total_risk = df_filtered["risk_score"].sum()

# ICCAT cross-reference (after IUU matching)
if not df_filtered.empty and not iccat_vessels.empty:
    df_filtered = match_iccat_vessels(df_filtered, iccat_vessels)
    total_risk = df_filtered["risk_score"].sum()

# ========================= MAIN MAP & METRICS =========================
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Behavioral Risk Map")
    if not df_filtered.empty:
        m = folium.Map(location=[37.0, 18.0], zoom_start=5, tiles="CartoDB positron")
        color_map = {"GAP": "red", "LOITERING": "orange", "ENCOUNTER": "purple"}

        # Create toggleable layer groups
        fg_gap = folium.FeatureGroup(name="AIS Gap", show=True)
        fg_loiter = folium.FeatureGroup(name="Loitering", show=True)
        fg_encounter = folium.FeatureGroup(name="Encounter", show=True)
        fg_iuu = folium.FeatureGroup(name="IUU-Listed", show=True)
        fg_iccat = folium.FeatureGroup(name="ICCAT Authorized", show=True)
        fg_fdi = folium.FeatureGroup(name="FDI Fishing Effort", show=show_fdi_layer)

        # FDI fishing effort choropleth layer (only near events)
        if not fdi_effort.empty and "csq_lon" in df_filtered.columns:
            latest_year = fdi_effort["year"].max()
            fdi_agg = (
                fdi_effort[fdi_effort["year"] == latest_year]
                .groupby(["rectangle_lon", "rectangle_lat"])["totfishdays"]
                .sum()
                .reset_index()
            )
            event_lons = df_filtered["lon"].values
            event_lats = df_filtered["lat"].values
            for _, cell in fdi_agg.iterrows():
                sw_lon = cell["rectangle_lon"]
                sw_lat = cell["rectangle_lat"]
                centre_lon = sw_lon + 0.25
                centre_lat = sw_lat + 0.25
                if not ((abs(event_lons - centre_lon) < 1.0) & (abs(event_lats - centre_lat) < 1.0)).any():
                    continue
                days = cell["totfishdays"]
                if days >= 2000:
                    color = "#e31a1c"
                elif days >= 500:
                    color = "#fd8d3c"
                elif days >= 50:
                    color = "#fecc5c"
                else:
                    color = "#ffffb2"
                folium.Rectangle(
                    bounds=[[sw_lat, sw_lon], [sw_lat + 0.5, sw_lon + 0.5]],
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.2,
                    weight=0,
                    popup=f"Fishing days ({latest_year}): {days:,.0f}",
                ).add_to(fg_fdi)

        # Pre-compute FDI context per unique c-square (avoid repeated 83K-row scans)
        fdi_cache = {}
        if not fdi_effort.empty and "csq_lon" in df_filtered.columns:
            for csq_lon, csq_lat in df_filtered[["csq_lon", "csq_lat"]].drop_duplicates().values:
                fdi_cache[(csq_lon, csq_lat)] = get_fdi_context(csq_lon, csq_lat, fdi_effort, fdi_landings)

        for _, row in df_filtered.iterrows():
            is_iuu = row.get("iuu_matched", False)
            is_iccat = row.get("iccat_authorized", False)
            vname = row.get("vessel_name", "")
            tooltip = f"{vname} | {row['event_type']} | {row['flag']}" if pd.notna(vname) else f"{row['event_type']} | {row['flag']}"

            if is_iuu:
                marker_color = "black"
                marker_radius = 12
            elif is_iccat:
                marker_color = "blue"
                marker_radius = 10
            else:
                marker_color = color_map.get(row["event_type"], "blue")
                marker_radius = 8

            marker = folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=marker_radius,
                color=marker_color,
                tooltip=tooltip,
                fill=True,
            )

            # Add marker to appropriate layer group
            if is_iuu:
                marker.add_to(fg_iuu)
            elif is_iccat:
                marker.add_to(fg_iccat)
            elif row["event_type"] == "GAP":
                marker.add_to(fg_gap)
            elif row["event_type"] == "LOITERING":
                marker.add_to(fg_loiter)
            else:
                marker.add_to(fg_encounter)

        # Add all layer groups to map (FDI first so it renders behind markers)
        fg_fdi.add_to(m)
        fg_gap.add_to(m)
        fg_loiter.add_to(m)
        fg_encounter.add_to(m)
        fg_iccat.add_to(m)
        fg_iuu.add_to(m)
        folium.LayerControl(collapsed=True).add_to(m)

        map_data = st_folium(m, width=700, height=500)

        # Color legend below map
        dot = '<span style="display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:4px;vertical-align:middle;background:{c}"></span>'
        sq = '<span style="display:inline-block;width:11px;height:11px;margin-right:4px;vertical-align:middle;background:{c};border:1px solid #ccc"></span>'
        legend_md = (
            f'{dot.format(c="red")} AIS Gap&ensp;'
            f'{dot.format(c="orange")} Loitering&ensp;'
            f'{dot.format(c="purple")} Encounter&ensp;'
            f'{dot.format(c="blue")} ICCAT&ensp;'
            f'{dot.format(c="black")} IUU&ensp;&ensp;'
            f'{sq.format(c="#ffffb2")} <small>&lt;50d</small>&ensp;'
            f'{sq.format(c="#fecc5c")} <small>50-500d</small>&ensp;'
            f'{sq.format(c="#fd8d3c")} <small>500-2kd</small>&ensp;'
            f'{sq.format(c="#e31a1c")} <small>&gt;2kd</small>'
        )
        st.markdown(f'<div style="font-size:13px;line-height:1.8">{legend_md}</div>', unsafe_allow_html=True)

        # Event detail card on click
        clicked = map_data.get("last_object_clicked") if map_data else None
        if clicked:
            clat, clng = clicked.get("lat"), clicked.get("lng")
            if clat is not None and clng is not None:
                dist = ((df_filtered["lat"] - clat)**2 + (df_filtered["lon"] - clng)**2)
                nearest_idx = dist.idxmin()
                if dist[nearest_idx] < 0.01:
                    ev = df_filtered.loc[nearest_idx]
                    is_iuu_ev = ev.get("iuu_matched", False)
                    is_iccat_ev = ev.get("iccat_authorized", False)

                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Vessel", ev.get("vessel_name", "Unknown"))
                    c2.metric("Event", ev["event_type"])
                    c3.metric("Risk Score", f"{ev['risk_score']:.1f}")

                    c4, c5, c6 = st.columns(3)
                    c4.metric("Flag", ev["flag"])
                    c5.metric("Duration", f"{ev['duration_h']} h")
                    c6.metric("Date", str(ev.get("date", ""))[:10])

                    if is_iuu_ev:
                        tier = "GFCM (Med)" if ev.get("iuu_is_gfcm") else "Other RFMO"
                        st.error(
                            f"**IUU-LISTED VESSEL** | Name: {ev.get('iuu_vessel_name', 'N/A')} | "
                            f"Match: {ev.get('iuu_match_type', '')} ({ev.get('iuu_match_confidence', '')}) | "
                            f"Tier: {tier} | Listed by: {ev.get('iuu_listing_rfmos', 'N/A')} | "
                            f"Multiplier: {ev.get('iuu_multiplier', 1.0):.1f}x"
                        )
                        reason = ev.get("iuu_listing_reason", "")
                        if reason and pd.notna(reason) and str(reason).strip().lower() != "nan":
                            st.caption(f"Reason: {str(reason)[:300]}")

                    if is_iccat_ev:
                        st.info(
                            f"**ICCAT AUTHORIZED** | Authorizations: {ev.get('iccat_authorizations', 'N/A')} | "
                            f"Risk tier: {ev.get('iccat_risk_tier', 'N/A')} | "
                            f"Multiplier: {ev.get('iccat_multiplier', 1.0):.1f}x"
                        )
                        if is_iuu_ev:
                            st.warning("**DUAL FLAG: IUU-listed + ICCAT-authorized**")

                    if "csq_lon" in ev.index:
                        ctx = fdi_cache.get((ev["csq_lon"], ev["csq_lat"]))
                        if ctx and ctx["total_fishing_days"] > 0:
                            top_sp_str = ", ".join(
                                SPECIES_NAMES.get(s[0], s[0]) for s in ctx["top_species"][:3]
                            )
                            tonnes = ctx["total_landings_tonnes"]
                            level = "High" if tonnes > 1000 else ("Moderate" if tonnes > 10 else "Low")
                            st.caption(
                                f"FDI Baseline: {'Known fishing ground' if ctx['is_known_fishing_ground'] else 'Not a known fishing ground'} | "
                                f"Fishing days: {ctx['total_fishing_days']:,.0f} | "
                                f"Top species: {top_sp_str} | "
                                f"Landings: {tonnes:,.0f} t ({level})"
                            )
    else:
        st.info("No events match the selected filters.")

with col2:
    st.metric("Mediterranean Behavioral Risk Index", f"{total_risk:.0f}")
    st.caption("Encounters weighted highest . Russian/Iranian flags boosted")
    if not df_filtered.empty:
        st.metric("Events", len(df_filtered))
        st.metric("Unique Vessels", df_filtered["mmsi"].nunique())
        st.metric("Flags", df_filtered["flag"].nunique())
        if "iuu_matched" in df_filtered.columns:
            iuu_count = int(df_filtered["iuu_matched"].sum())
            if iuu_count > 0:
                st.metric("IUU-Listed Vessels", iuu_count)

# IUU Alert Box (full width, below map)
if not df_filtered.empty and "iuu_matched" in df_filtered.columns:
    iuu_events = df_filtered[df_filtered["iuu_matched"] == True]
    if not iuu_events.empty:
        st.error(f"**IUU ALERT:** {len(iuu_events)} event(s) involve IUU-listed vessels")
        with st.expander("IUU Match Details", expanded=True):
            display_cols = [
                "vessel_name", "mmsi", "flag", "event_type", "duration_h",
                "risk_score", "iuu_vessel_name", "iuu_listing_rfmos",
                "iuu_match_type", "iuu_match_confidence", "iuu_multiplier",
            ]
            display_cols = [c for c in display_cols if c in iuu_events.columns]
            st.dataframe(
                iuu_events[display_cols].sort_values("risk_score", ascending=False),
                use_container_width=True,
            )

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
with tab12: render_ai_analyst(df_filtered, fdi_effort, fdi_landings, knowledge_base, gemini_key, iuu_vessels, iccat_vessels)

# ========================= SIDEBAR METHODOLOGY =========================
with st.sidebar.expander("Methodology & About"):
    st.markdown("""
**GFW-Aligned Risk Scoring**

Risk model replicates Global Fishing Watch transshipment detection
methodology (Miller et al. 2018).

`risk = duration^0.75 x event_weight x flag_mult x shore_factor x event_factors x iuu_mult x iccat_mult`

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

**IUU Cross-Reference:**
- Source: Combined IUU Vessel List (iuu-vessels.org / TMT)
- GFCM-listed vessel in Med: 3.0x risk multiplier
- Other RFMO-listed vessel in Med: 2.0x risk multiplier
- Matching: MMSI (exact) > vessel name (exact) > name (substring)

**ICCAT Authorized Vessels:**
- Source: ICCAT Record of Vessels (iccat.int)
- Carrier: 1.4x | BFT-Catching: 1.3x | BFT-Other: 1.3x
- SWO-Med: 1.2x | ALB-Med: 1.2x
- Matching: vessel name (exact, min 4 chars)

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
