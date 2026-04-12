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
    SPECIES_NAMES, assign_csquare, classify_risk_band,
)
from data_loading import (
    load_knowledge_base, load_static_data, load_live_data,
    load_fdi_effort, load_fdi_landings, load_iuu_vessels, load_iccat_vessels,
    load_ofac_vessels, lookup_vessel_metadata,
    load_fishing_events_static, load_fishing_events_live, aggregate_fishing_in_mpa,
)
from risk_model import compute_risk_score, get_fdi_context, match_iuu_vessels, match_iccat_vessels, match_ofac_vessels, compute_vessel_flags
from tabs import (
    render_daily_trend, render_flag_breakdown, render_event_types,
    render_duration_analysis, render_geographic_risk, render_risk_heatmap,
    render_repeat_offenders, render_gap_behaviour, render_encounter_analysis,
    render_vessel_summary, render_vessel_investigation,
    render_fisheries_context, render_reference,
    render_base_vs_compound_decomposition, render_risk_band_distribution,
    render_mpa_tier_exposure, render_top_vessels_segmented,
    render_fishing_in_mpa_map,
    render_vessel_class_composition, render_type_mismatch_by_class,
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
    fishing_df = load_fishing_events_live(token, date_range[0], date_range[1])
else:
    df = load_static_data()
    fishing_df = load_fishing_events_static()

fdi_effort = load_fdi_effort()
fdi_landings = load_fdi_landings()
iuu_vessels = load_iuu_vessels()
iccat_vessels = load_iccat_vessels()
ofac_vessels = load_ofac_vessels()
knowledge_base = load_knowledge_base()

# Per-vessel fishing-in-MPA aggregation (display-only, no risk multiplier)
fishing_mpa_agg = aggregate_fishing_in_mpa(fishing_df)

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

# Vessel metadata enrichment via GFW Vessels API (live mode only).
# Returns dict[mmsi] -> {"imo", "length_m", "tonnage_gt", "shiptypes"}.
# Each field is independently optional. Falls back gracefully on cache miss.
if use_live and token and resolve_imos and not df_filtered.empty:
    unique_mmsis = df_filtered["mmsi"].dropna().unique().tolist()
    cache_key = f"vessel_meta_{hash(tuple(sorted(str(m) for m in unique_mmsis)))}"
    if cache_key in st.session_state:
        meta_map = st.session_state[cache_key]
    else:
        progress_bar = st.progress(0, text="Resolving vessel metadata via GFW API...")
        def _update_progress(current, total):
            progress_bar.progress(current / total, text=f"Resolving vessel metadata... {current}/{total}")
        meta_map = lookup_vessel_metadata(unique_mmsis, token, progress_callback=_update_progress)
        st.session_state[cache_key] = meta_map
        progress_bar.empty()
    if meta_map:
        mmsi_str = df_filtered["mmsi"].astype(str)
        df_filtered["imo"] = mmsi_str.map(lambda m: (meta_map.get(m) or {}).get("imo") or "")
        df_filtered["length_m"] = mmsi_str.map(lambda m: (meta_map.get(m) or {}).get("length_m"))
        df_filtered["tonnage_gt"] = mmsi_str.map(lambda m: (meta_map.get(m) or {}).get("tonnage_gt"))
        df_filtered["shiptypes"] = mmsi_str.map(lambda m: (meta_map.get(m) or {}).get("shiptypes") or "")

# Ensure metadata columns exist (static CSV pre-populates length_m / tonnage_gt /
# shiptypes; live mode without enrichment skipped or no GFW match leaves them blank).
if "imo" not in df_filtered.columns:
    df_filtered["imo"] = ""
for _meta_col, _meta_default in [("length_m", None), ("tonnage_gt", None), ("shiptypes", "")]:
    if _meta_col not in df_filtered.columns:
        df_filtered[_meta_col] = _meta_default

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

# OFAC SDN cross-reference (after ICCAT matching — highest priority)
if not df_filtered.empty and not ofac_vessels.empty:
    df_filtered = match_ofac_vessels(df_filtered, ofac_vessels)
    total_risk = df_filtered["risk_score"].sum()

# Classify final compounded risk into Kpler-aligned bands
if not df_filtered.empty:
    df_filtered["risk_band"] = df_filtered["risk_score"].apply(classify_risk_band)

# Kpler-aligned display-only behavioural flags (do not multiply into risk_score)
df_filtered = compute_vessel_flags(df_filtered)

# Fishing-in-MPA join (display-only, no risk multiplier).
# fishing_mpa_agg is keyed on mmsi; both event and fishing loaders pull
# vessel.ssvid as mmsi from GFW so the join key is consistent.
if not df_filtered.empty and not fishing_mpa_agg.empty:
    df_filtered["mmsi"] = df_filtered["mmsi"].astype(str)
    fishing_mpa_agg["mmsi"] = fishing_mpa_agg["mmsi"].astype(str)
    df_filtered = df_filtered.merge(fishing_mpa_agg, on="mmsi", how="left")
# Ensure columns exist even when no fishing-in-MPA join hits
for _col, _default in [
    ("fishing_in_mpa_events", 0),
    ("fishing_in_mpa_hours", 0.0),
    ("fishing_in_mpa_top_tier", ""),
]:
    if _col not in df_filtered.columns:
        df_filtered[_col] = _default
df_filtered["fishing_in_mpa_events"] = df_filtered["fishing_in_mpa_events"].fillna(0).astype(int)
df_filtered["fishing_in_mpa_hours"] = df_filtered["fishing_in_mpa_hours"].fillna(0.0)
df_filtered["fishing_in_mpa_top_tier"] = df_filtered["fishing_in_mpa_top_tier"].fillna("")

# ========================= MAIN MAP & METRICS =========================
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Behavioral Risk Map")
    if not df_filtered.empty:
        # Vessel-scoped map filter: when the user clicks a row in the
        # Vessel Summary table (or a marker, or picks from the dropdown),
        # we stash the vessel name in session state. On the next rerun
        # we filter the map markers to that vessel only and auto-fit
        # the viewport to its events. df_filtered itself is left alone
        # so the fleet-level tabs still show the full picture.
        focus_vessel = st.session_state.get("map_clicked_vessel")
        if focus_vessel and focus_vessel in df_filtered["vessel_name"].values:
            df_map = df_filtered[df_filtered["vessel_name"] == focus_vessel]
            n_focus = len(df_map)
            fc1, fc2 = st.columns([5, 1])
            fc1.info(
                f"Map filtered to **{focus_vessel}** ({n_focus} event"
                f"{'s' if n_focus != 1 else ''}). Fleet tabs below still "
                f"show the full filtered fleet."
            )
            if fc2.button("Clear map filter", key="clear_map_filter"):
                st.session_state.pop("map_clicked_vessel", None)
                st.rerun()
        else:
            df_map = df_filtered

        # Centre + zoom: fit to the focused vessel's events when filtered,
        # otherwise default to the whole Med basin.
        if focus_vessel and len(df_map) > 0:
            centre_lat = float(df_map["lat"].mean())
            centre_lon = float(df_map["lon"].mean())
            zoom = 7 if len(df_map) > 1 else 8
            m = folium.Map(location=[centre_lat, centre_lon], zoom_start=zoom, tiles="CartoDB positron")
        else:
            m = folium.Map(location=[37.0, 18.0], zoom_start=5, tiles="CartoDB positron")

        # Dual visual encoding:
        #   shape = behaviour (GAP=circle, LOITERING=square, ENCOUNTER=triangle)
        #   fill colour = listing status (OFAC > IUU > ICCAT > clean-by-risk-band)
        #   size = Kpler risk band (Low..Critical)
        # Layer toggles are organised by listing status so the user can isolate,
        # e.g., all ICCAT-authorised events regardless of behaviour type.
        from config import RISK_BAND_COLORS

        band_size_px = {"Low": 14, "Emerging": 17, "Elevated": 20, "Severe": 24, "Critical": 28}

        fg_clean = folium.FeatureGroup(name="Clean (no listing)", show=True)
        fg_iccat = folium.FeatureGroup(name="ICCAT Authorized", show=True)
        fg_iuu = folium.FeatureGroup(name="IUU-Listed", show=True)
        fg_ofac = folium.FeatureGroup(name="OFAC Sanctioned", show=True)
        fg_fdi = folium.FeatureGroup(name="FDI Fishing Effort", show=show_fdi_layer)

        # FDI fishing effort choropleth layer (only near events)
        if not fdi_effort.empty and "csq_lon" in df_map.columns:
            latest_year = fdi_effort["year"].max()
            fdi_agg = (
                fdi_effort[fdi_effort["year"] == latest_year]
                .groupby(["rectangle_lon", "rectangle_lat"])["totfishdays"]
                .sum()
                .reset_index()
            )
            event_lons = df_map["lon"].values
            event_lats = df_map["lat"].values
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

        def _svg_shape(event_type, fill, size, stroke="#222", stroke_w=1.5, dashed=False):
            """Return an inline SVG shape for a Folium DivIcon.

            Circle = GAP, square = LOITERING, triangle = ENCOUNTER.
            `dashed=True` draws an amber dashed outline used to flag Kpler-aligned
            dark port call candidates (loitering within 10 km of shore).
            """
            s = size
            half = s / 2
            if dashed:
                stroke = "#ff9900"
                stroke_w = 2.0
                dash_attr = ' stroke-dasharray="3 2"'
            else:
                dash_attr = ""
            if event_type == "LOITERING":
                body = f'<rect x="1" y="1" width="{s-2}" height="{s-2}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"{dash_attr}/>'
            elif event_type == "ENCOUNTER":
                pts = f"{half},1 {s-1},{s-1} 1,{s-1}"
                body = f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"{dash_attr}/>'
            else:  # GAP or unknown -> circle
                r = half - 1
                body = f'<circle cx="{half}" cy="{half}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"{dash_attr}/>'
            return f'<svg width="{s}" height="{s}" xmlns="http://www.w3.org/2000/svg">{body}</svg>'

        for _, row in df_map.iterrows():
            is_ofac = row.get("ofac_sanctioned", False)
            is_iuu = row.get("iuu_matched", False)
            is_iccat = row.get("iccat_authorized", False)
            vname = row.get("vessel_name", "")
            band = row.get("risk_band", "Low")
            size = band_size_px.get(band, 14)

            # Listing status sets fill colour (priority OFAC > IUU > ICCAT > clean-by-band)
            if is_ofac:
                fill = "#8B0000"
                target = fg_ofac
            elif is_iuu:
                fill = "#000000"
                target = fg_iuu
            elif is_iccat:
                fill = "#1f77b4"
                target = fg_iccat
            else:
                fill = RISK_BAND_COLORS.get(band, "#2ecc71")
                target = fg_clean

            listings = []
            if is_ofac:
                listings.append("OFAC")
            if is_iuu:
                listings.append("IUU")
            if is_iccat:
                listings.append("ICCAT")
            listing_txt = ", ".join(listings) if listings else "clean"

            # Compound / temporal behavioural flags (display-only, do not modify fill/size)
            is_dpc = bool(row.get("dark_port_call_candidate", False))
            is_multi = bool(row.get("multi_behaviour_flag", False))
            is_repeat = bool(row.get("repeat_offender_90d", False))
            behavioural_flags = []
            if is_dpc:
                behavioural_flags.append("dark-port-candidate")
            if is_multi:
                behavioural_flags.append("multi-behaviour")
            if is_repeat:
                behavioural_flags.append("repeat-offender")

            tooltip_parts = [
                vname if pd.notna(vname) and vname else "(unknown)",
                f"{row['event_type']}",
                f"flag {row['flag']}",
                f"risk {row['risk_score']:.1f} ({band})",
                listing_txt,
            ]
            if behavioural_flags:
                tooltip_parts.append("Behavioural flags: " + ", ".join(behavioural_flags))
            tooltip = " | ".join(tooltip_parts)

            svg = _svg_shape(row["event_type"], fill, size, dashed=is_dpc)
            icon = folium.DivIcon(
                html=f'<div style="width:{size}px;height:{size}px">{svg}</div>',
                icon_size=(size, size),
                icon_anchor=(size // 2, size // 2),
            )
            folium.Marker(
                location=[row["lat"], row["lon"]],
                icon=icon,
                tooltip=tooltip,
            ).add_to(target)

        # Add all layer groups to map (FDI first so it renders behind markers)
        fg_fdi.add_to(m)
        fg_clean.add_to(m)
        fg_iccat.add_to(m)
        fg_iuu.add_to(m)
        fg_ofac.add_to(m)
        folium.LayerControl(collapsed=True).add_to(m)

        map_data = st_folium(m, width=700, height=500)

        # Dual-encoding legend: shape = behaviour, fill = listing, size = risk band
        def _legend_svg(shape, fill="#888", size=14, dashed=False):
            s = size
            half = s / 2
            stroke = "#ff9900" if dashed else "#222"
            sw = 2.0 if dashed else 1.2
            dash_attr = ' stroke-dasharray="3 2"' if dashed else ""
            if shape == "square":
                body = f'<rect x="1" y="1" width="{s-2}" height="{s-2}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash_attr}/>'
            elif shape == "triangle":
                pts = f"{half},1 {s-1},{s-1} 1,{s-1}"
                body = f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash_attr}/>'
            else:
                body = f'<circle cx="{half}" cy="{half}" r="{half-1}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash_attr}/>'
            return (
                f'<span style="display:inline-block;vertical-align:middle;margin-right:4px">'
                f'<svg width="{s}" height="{s}">{body}</svg></span>'
            )

        from config import RISK_BAND_COLORS as _RBC
        legend_md = (
            '<b>Behaviour</b> (shape):&ensp;'
            f'{_legend_svg("circle")} AIS Gap&ensp;'
            f'{_legend_svg("square")} Loitering&ensp;'
            f'{_legend_svg("triangle")} Encounter&emsp;'
            '<b>Listing</b> (fill):&ensp;'
            f'{_legend_svg("circle", fill=_RBC["Low"])} Clean&ensp;'
            f'{_legend_svg("circle", fill="#1f77b4")} ICCAT&ensp;'
            f'{_legend_svg("circle", fill="#000000")} IUU&ensp;'
            f'{_legend_svg("circle", fill="#8B0000")} OFAC<br/>'
            '<b>Risk band</b> (size + clean fill):&ensp;'
            f'{_legend_svg("circle", fill=_RBC["Low"], size=14)} Low&ensp;'
            f'{_legend_svg("circle", fill=_RBC["Emerging"], size=17)} Emerging&ensp;'
            f'{_legend_svg("circle", fill=_RBC["Elevated"], size=20)} Elevated&ensp;'
            f'{_legend_svg("circle", fill=_RBC["Severe"], size=24)} Severe&ensp;'
            f'{_legend_svg("circle", fill=_RBC["Critical"], size=28)} Critical<br/>'
            '<b>Behavioural flag</b>:&ensp;'
            f'{_legend_svg("square", fill=_RBC["Low"], size=17, dashed=True)} dashed amber outline = dark port call candidate (loitering within 10 km of shore, AIS-inferred, not satellite-verified)&emsp;'
            '<b>FDI effort</b>:&ensp;'
            '<span style="display:inline-block;width:11px;height:11px;background:#ffffb2;border:1px solid #ccc;margin-right:3px"></span><small>&lt;50d</small>&ensp;'
            '<span style="display:inline-block;width:11px;height:11px;background:#fecc5c;border:1px solid #ccc;margin-right:3px"></span><small>50-500d</small>&ensp;'
            '<span style="display:inline-block;width:11px;height:11px;background:#fd8d3c;border:1px solid #ccc;margin-right:3px"></span><small>500-2kd</small>&ensp;'
            '<span style="display:inline-block;width:11px;height:11px;background:#e31a1c;border:1px solid #ccc;margin-right:3px"></span><small>&gt;2kd</small>'
        )
        st.markdown(f'<div style="font-size:13px;line-height:2.0">{legend_md}</div>', unsafe_allow_html=True)

        st.caption(
            "Click a marker for event details. The clicked vessel is also set "
            "as the default in the **Vessel Investigation** tab."
        )

        # Event detail card on click
        clicked = map_data.get("last_object_clicked") if map_data else None
        if clicked:
            clat, clng = clicked.get("lat"), clicked.get("lng")
            if clat is not None and clng is not None:
                dist = ((df_filtered["lat"] - clat)**2 + (df_filtered["lon"] - clng)**2)
                nearest_idx = dist.idxmin()
                if dist[nearest_idx] < 0.01:
                    ev = df_filtered.loc[nearest_idx]
                    # Sync clicked vessel to the Vessel Investigation selector.
                    # We write to a dedicated key (not the selectbox's own key)
                    # to avoid Streamlit's "can't modify widget state" rule;
                    # the selectbox reads it on next render.
                    clicked_vname = ev.get("vessel_name")
                    if pd.notna(clicked_vname) and clicked_vname:
                        st.session_state["map_clicked_vessel"] = clicked_vname
                    is_ofac_ev = ev.get("ofac_sanctioned", False)
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

                    if is_ofac_ev:
                        st.error(
                            f"**OFAC SANCTIONED** | Name: {ev.get('ofac_vessel_name', 'N/A')} | "
                            f"Program: {ev.get('ofac_sanctions_program', 'N/A')} | "
                            f"Listed: {ev.get('ofac_listing_date', 'N/A')} | "
                            f"Match: {ev.get('ofac_match_type', '')} ({ev.get('ofac_match_confidence', '')}) | "
                            f"Multiplier: {ev.get('ofac_multiplier', 1.0):.1f}x"
                        )

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

                    # Multi-list combination warnings
                    if is_ofac_ev and is_iuu_ev and is_iccat_ev:
                        st.error("**TRIPLE FLAG: OFAC-sanctioned + IUU-listed + ICCAT-authorized**")
                    elif is_ofac_ev and is_iuu_ev:
                        st.error("**DUAL FLAG: OFAC-sanctioned + IUU-listed**")
                    elif is_ofac_ev and is_iccat_ev:
                        st.warning("**DUAL FLAG: OFAC-sanctioned + ICCAT-authorized**")
                    elif is_iuu_ev and is_iccat_ev:
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

                    # External vessel lookup links
                    imo_val = str(ev.get("imo", "")).strip()
                    if imo_val and imo_val not in ("", "0", "nan", "None"):
                        mt_url = f"https://www.marinetraffic.com/en/ais/details/ships/imo:{imo_val}"
                        vf_url = f"https://www.vesselfinder.com/vessels?name={imo_val}"
                        st.markdown(
                            f"External lookups: "
                            f"[MarineTraffic]({mt_url}) | "
                            f"[VesselFinder]({vf_url})"
                        )
    else:
        st.info("No events match the selected filters.")

with col2:
    st.metric("Mediterranean Behavioral Risk Index", f"{total_risk:.0f}")
    if not df_filtered.empty:
        st.metric("Events", len(df_filtered))
        st.metric("Unique Vessels", df_filtered["mmsi"].nunique())
        st.metric("Flags", df_filtered["flag"].nunique())
        if "iuu_matched" in df_filtered.columns:
            iuu_count = int(df_filtered["iuu_matched"].sum())
            if iuu_count > 0:
                st.metric("IUU-Listed Vessels", iuu_count)
        if "ofac_sanctioned" in df_filtered.columns:
            ofac_count = int(df_filtered["ofac_sanctioned"].sum())
            if ofac_count > 0:
                st.metric("OFAC Sanctioned", ofac_count)
        # Kpler-aligned behavioural flags (display-only, do not affect risk_score)
        if "multi_behaviour_flag" in df_filtered.columns:
            multi_vessels = int(
                df_filtered[df_filtered["multi_behaviour_flag"]]["mmsi"].nunique()
            )
            if multi_vessels > 0:
                st.metric(
                    "Multi-behaviour Vessels", multi_vessels,
                    help="Vessels showing two or more distinct GFW event types "
                         "(gap, encounter, loitering). Compound behavioural indicator.",
                )
        if "dark_port_call_candidate" in df_filtered.columns:
            dpc_events = int(df_filtered["dark_port_call_candidate"].sum())
            if dpc_events > 0:
                st.metric(
                    "Dark Port Call Candidates", dpc_events,
                    help="Loitering events within 10 km of shore. AIS-inferred, "
                         "not satellite-verified (hence 'candidate').",
                )
        if "repeat_offender_90d" in df_filtered.columns:
            repeat_vessels = int(
                df_filtered[df_filtered["repeat_offender_90d"]]["mmsi"].nunique()
            )
            if repeat_vessels > 0:
                st.metric(
                    "Repeat Offenders (90d)", repeat_vessels,
                    help="Vessels with two or more events within any 90-day window. "
                         "Captures exposure drift over time.",
                )

# OFAC Alert Box (full width, below map — highest priority)
if not df_filtered.empty and "ofac_sanctioned" in df_filtered.columns:
    ofac_events = df_filtered[df_filtered["ofac_sanctioned"] == True]
    if not ofac_events.empty:
        st.error(f"**OFAC SANCTIONS ALERT:** {len(ofac_events)} event(s) involve OFAC-sanctioned vessels")
        with st.expander("OFAC Sanctions Details", expanded=True):
            display_cols = [
                "vessel_name", "mmsi", "imo", "flag", "event_type", "duration_h",
                "risk_score", "ofac_vessel_name", "ofac_sanctions_program",
                "ofac_listing_date", "ofac_match_type", "ofac_match_confidence",
                "ofac_multiplier",
            ]
            display_cols = [c for c in display_cols if c in ofac_events.columns]
            st.dataframe(
                ofac_events[display_cols].sort_values("risk_score", ascending=False),
                use_container_width=True,
            )

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
# Four top-level tabs ordered drill -> zoom out -> explain -> ask.
# Vessel Watch groups Vessel Summary + Vessel Investigation (drill flow).
# Fleet Overview groups Map & Overview + Fisheries Context (aggregate
# fleet views). The remaining two are generic / interactive.
tab_watch, tab_overview, tab_reference, tab_ai = st.tabs([
    "Vessel Watch",
    "Fleet Overview",
    "Reference & Methodology",
    "AI Analyst",
])

with tab_watch:
    sub_summary, sub_investigation = st.tabs([
        "Vessel Summary", "Vessel Investigation",
    ])

    with sub_summary:
        with st.expander("Tab guide", expanded=False):
            st.markdown("""\
**What it shows:** One row per vessel, sorted by compounded risk score (highest first). \
The table aggregates all behavioural events per vessel and cross-references each against \
the IUU vessel list, ICCAT authorized vessel record, and OFAC sanctions list.

**Data:** GFW behavioural events (AIS gaps, encounters, loitering) scored with the risk \
formula, then aggregated per vessel (MMSI). IUU / ICCAT / OFAC cross-reference results merged in.

**Key columns:** risk_band (colour-coded), compound_multiplier (structural vs behavioural), \
vessel_class, type_mismatch, four behavioural flags (industrial, multi-behaviour, dark port call, repeat offender).

**Interactions:** Click a row to filter the map and pre-select the vessel for investigation. \
Use the slider to control how many vessels appear.

**Collapsed expanders below:** Risk band distribution -- Base vs structural-amplifier decomposition \
-- Top vessels segmented -- Type mismatch by vessel class -- Repeat offenders -- Encounter analysis -- AIS gap behaviour.""")

        # ---- Pill filters (multi-select, None = show all) ----
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            event_types_in_data = sorted(df_filtered["event_type"].dropna().unique())
            pill_events = st.pills(
                "Event type", event_types_in_data,
                selection_mode="multi", default=None, key="pill_event_type",
            )
        with fc2:
            band_order = ["Critical", "Severe", "Elevated", "Emerging", "Low"]
            bands_in_data = [b for b in band_order if b in df_filtered["risk_band"].values]
            pill_bands = st.pills(
                "Risk band", bands_in_data,
                selection_mode="multi", default=None, key="pill_risk_band",
            )
        with fc3:
            flags_in_data = sorted(df_filtered["flag"].dropna().unique())
            pill_flags = st.pills(
                "Flag state", flags_in_data,
                selection_mode="multi", default=None, key="pill_flag",
            )
        with fc4:
            classes_in_data = sorted(
                df_filtered["vessel_class"].dropna().unique()
            ) if "vessel_class" in df_filtered.columns else []
            pill_class = st.pills(
                "Vessel class", classes_in_data,
                selection_mode="multi", default=None, key="pill_vessel_class",
            ) if classes_in_data else []

        df_tab = df_filtered.copy()
        if pill_events:
            df_tab = df_tab[df_tab["event_type"].isin(pill_events)]
        if pill_bands:
            df_tab = df_tab[df_tab["risk_band"].isin(pill_bands)]
        if pill_flags:
            df_tab = df_tab[df_tab["flag"].isin(pill_flags)]
        if pill_class:
            df_tab = df_tab[df_tab["vessel_class"].isin(pill_class)]

        if len(df_tab) < len(df_filtered):
            st.caption(
                f"Showing {len(df_tab)} of {len(df_filtered)} events "
                f"({df_tab['mmsi'].nunique()} vessels). Clear pills to reset."
            )

        render_vessel_summary(df_tab)

        with st.expander("Risk band distribution", expanded=False):
            render_risk_band_distribution(df_tab)

        with st.expander("Base vs structural-amplifier decomposition", expanded=False):
            render_base_vs_compound_decomposition(df_tab)

        with st.expander("Top vessels: base vs structural amplifier", expanded=False):
            render_top_vessels_segmented(df_tab, top_n=10)

        with st.expander("Type mismatch by vessel class", expanded=False):
            render_type_mismatch_by_class(df_tab)

        with st.expander("Repeat offenders -- IUU and ICCAT detail"):
            render_repeat_offenders(df_tab)

        with st.expander("Encounter analysis -- carrier alerts"):
            render_encounter_analysis(df_tab)

        with st.expander("AIS gap behaviour"):
            render_gap_behaviour(df_tab)

    with sub_investigation:
        with st.expander("Tab guide", expanded=False):
            st.markdown("""\
**What it shows:** A per-vessel structured investigation report that walks the risk-tree framework \
from identity through behaviour, spatial context, structural lookups, to a final threat assessment.

**Data:** Scored GFW events for the selected vessel + IUU vessel list + ICCAT authorized vessels \
+ OFAC SDN list + FDI fishing effort and landings (spatial join by c-square) + fishing-in-MPA events.

**Report sections:** Identity confirmation -- IUU / ICCAT / OFAC listing status -- Fisheries \
context (FDI overlay) -- Fishing activity inside MPAs -- Behavioural pattern and flags -- Risk \
score decomposition -- Hypotheses -- External lookup links -- Threat assessment.

**Interactions:** Select a vessel from the dropdown, or click a row in Vessel Summary / a marker \
on the map to pre-select it. The risk-tree trace at the bottom shows which branches fired \
and at what severity (expandable by branch).""")
        render_vessel_investigation(
            df_filtered, iuu_vessels, iccat_vessels, ofac_vessels,
            fdi_effort, fdi_landings, fishing_df=fishing_df,
        )
        st.caption("See **Reference & Methodology** tab for the generic framework and multiplier tables.")

with tab_overview:
    sub_map, sub_fisheries = st.tabs(["Map & Overview", "Fisheries Context"])

    with sub_map:
        with st.expander("Tab guide", expanded=False):
            st.markdown("""\
**What it shows:** Fleet-level aggregate views across all filtered vessels and events.

**Data:** GFW behavioural events scored per event (the same df_filtered used across all tabs).

**Key charts (always visible):** Risk heatmap (flag state vs event type, coloured by total risk) \
-- Daily behavioural risk trend with IUU-event dates marked as dashed verticals -- Monthly event \
counts by event type.

**Collapsed expanders below:** Risk exposure by MPA tier (donut) -- Fleet composition by vessel \
class (donut) -- Flag breakdown (bars + IUU/ICCAT/OFAC tables) -- Event type distribution \
(pie + summary table) -- Event duration distribution (histogram + scatter).""")
        render_risk_heatmap(df_filtered)
        render_daily_trend(df_filtered)

        with st.expander("Risk exposure by MPA tier", expanded=False):
            render_mpa_tier_exposure(df_filtered)

        with st.expander("Fleet composition by vessel class", expanded=False):
            render_vessel_class_composition(df_filtered)

        with st.expander("Flag breakdown"):
            render_flag_breakdown(df_filtered)

        with st.expander("Event type distribution"):
            render_event_types(df_filtered)

        with st.expander("Event duration distribution"):
            render_duration_analysis(df_filtered)

    with sub_fisheries:
        with st.expander("Tab guide", expanded=False):
            st.markdown("""\
**What it shows:** GFW behavioural events overlaid with the EU JRC Fisheries Dependent Information \
(FDI) baseline -- fishing effort (days) and species landings aggregated to 0.5-degree c-squares.

**Data:** GFW events (spatially joined via c-square) + FDI effort (data/fdi_effort_med.csv, \
~83K rows, 2017-2024) + FDI landings (data/fdi_landings_med.csv, ~212K rows).

**Key insight:** Events that fall in low-effort c-squares are the suspicious ones -- they happen \
in waters where legitimate fishing rarely occurs.

**Sections:** FDI effort vs GFW events scatter map -- Event context table (fishing days, top \
species, landings value) -- Seasonal patterns by Med zone -- Species context (top species by value).

**Collapsed expanders below:** Fishing activity inside MPAs (scatter map) -- Geographic risk \
breakdown (sub-zone bars, port-distance scatter).""")
        render_fisheries_context(df_filtered, fdi_effort, fdi_landings)

        with st.expander("Fishing activity inside MPAs", expanded=False):
            render_fishing_in_mpa_map(df_filtered, fishing_df)

        with st.expander("Geographic risk breakdown"):
            render_geographic_risk(df_filtered)

with tab_reference:
    with st.expander("Tab guide", expanded=False):
        st.markdown("""\
**What it shows:** The scoring framework, multiplier tables, and methodology that underpin \
every number in the dashboard.

**Data:** Constants from config.py + reference_content.yaml + risk_tree_framework.yaml. \
No event data is used here -- this tab is pure methodology.

**Contents:** Risk-tree framework diagram (interactive Graphviz) -- Scoring formula with \
annotated terms -- End-to-end scoring pipeline diagram -- Risk band definitions -- All \
multiplier tables (flag risk, IUU, ICCAT, OFAC, MPA) -- ICCAT framing note -- MPA calibration \
note -- Fishing-in-MPA framing note -- Sanctions authority note -- Data source provenance -- \
Epistemological separation -- Methodology references -- Scope and limitations.

**When to use:** Point stakeholders here when they ask "where do these numbers come from?".""")
    render_reference()
    st.caption("See **Vessel Watch -> Vessel Investigation** for an applied per-vessel example.")

with tab_ai:
    with st.expander("Tab guide", expanded=False):
        st.markdown("""\
**What it shows:** An AI-powered analyst (Gemini 2.5 Flash) with sandboxed code execution \
that can query, filter, aggregate, and plot the dashboard data on demand.

**Data available to the analyst:** Copies of the full scored event dataframe, FDI effort and \
landings, IUU / ICCAT / OFAC vessel lists, and fishing-in-MPA events. The model operates on \
copies -- it cannot modify the live data or make network calls.

**How to use:** Pick an example question from the dropdown or type your own. The analyst \
generates pandas / plotly code, executes it in a sandbox, and renders the output (chart, \
table, or metric) inline. The system prompt includes the full knowledge base, column schemas, \
and scoring methodology so it knows what every column means.

**Requires:** A Gemini API key (entered in the sidebar or via .streamlit/secrets.toml).""")
    render_ai_analyst(
        df_filtered, fdi_effort, fdi_landings, knowledge_base, "",
        iuu_vessels, iccat_vessels, ofac_vessels, fishing_df=fishing_df,
    )

# ========================= SIDEBAR METHODOLOGY =========================
with st.sidebar.expander("Methodology & About"):
    st.markdown("""
**GFW-Aligned Risk Scoring**

Risk model replicates Global Fishing Watch transshipment detection
methodology (Miller et al. 2018).

`risk = duration^0.75 x event_weight x flag_mult x shore_factor x event_factors x iuu_mult x iccat_mult x ofac_mult`

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

**OFAC SDN Cross-Reference:**
- Source: US Treasury OFAC Specially Designated Nationals List
- Sanctioned vessel: 2.5x risk multiplier
- Matching: MMSI (exact) > IMO (exact) > vessel name (exact)
- Programs: IRAN, SYRIA, UKRAINE, DPRK, etc.

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
