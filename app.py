"""Med Vessel Behaviour Monitor — orchestrator."""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

from config import (
    EVENT_COLORS, DEFAULT_EVENT_WEIGHTS, FLAG_RISKS,
    SPECIES_NAMES, assign_csquare, assign_csquares_vec, classify_risk_band,
)
from data_loading import (
    load_knowledge_base, load_static_data, load_live_data,
    load_fdi_effort, load_fdi_landings, load_iuu_vessels, load_iccat_vessels,
    load_ofac_vessels, load_closed_area_mpas, lookup_vessel_metadata, load_vessel_metadata_cache,
    load_fishing_events_static, load_fishing_events_live, aggregate_fishing_in_mpa,
    snapshot_exists, snapshot_info, download_api_snapshot,
    load_snapshot_events, load_snapshot_fishing,
    insights_snapshot_exists, insights_snapshot_info,
    download_insights_snapshot, load_snapshot_insights,
)
from risk_model import compute_risk_score, compute_risk_scores_vec, get_fdi_context, match_iuu_vessels, match_iccat_vessels, match_ofac_vessels, compute_vessel_flags
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


# ========================= CACHED HELPERS =========================

@st.cache_data(show_spinner=False)
def _build_fdi_rectangles(fdi_effort_df):
    """Pre-compute FDI rectangle specs (built once, reused across reruns)."""
    latest_year = fdi_effort_df["year"].max()
    fdi_agg = (
        fdi_effort_df[fdi_effort_df["year"] == latest_year]
        .groupby(["rectangle_lon", "rectangle_lat"])["totfishdays"]
        .sum()
        .reset_index()
    )
    rects = []
    for _, cell in fdi_agg.iterrows():
        days = cell["totfishdays"]
        if days >= 2000:
            color, opacity = "#08306b", 0.35
        elif days >= 500:
            color, opacity = "#2171b5", 0.30
        elif days >= 50:
            color, opacity = "#6baed6", 0.25
        else:
            color, opacity = "#c6dbef", 0.15
        rects.append((cell["rectangle_lat"], cell["rectangle_lon"], days, color, opacity))
    return rects


@st.cache_data(show_spinner=False)
def _build_fdi_cache(csquares_tuples, fdi_effort_df, fdi_landings_df):
    """Pre-compute FDI context for each unique c-square (cached across reruns)."""
    cache = {}
    for csq_lon_v, csq_lat_v in csquares_tuples:
        cache[(csq_lon_v, csq_lat_v)] = get_fdi_context(
            csq_lon_v, csq_lat_v, fdi_effort_df, fdi_landings_df
        )
    return cache




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

# Data source: Static demo | API snapshot | Live API
_source_options = ["Static demo"]
if snapshot_exists():
    _source_options.insert(0, "API snapshot")
_source_options.append("Live GFW API")

data_source = st.sidebar.radio(
    "Data source",
    _source_options,
    index=0,
    help="Static demo: bundled sample. API snapshot: previously downloaded real data. Live: fetch from GFW now.",
)
use_live = data_source == "Live GFW API"
use_snapshot = data_source == "API snapshot"

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

# Download API snapshot button
include_fishing = st.sidebar.toggle(
    "Include fishing events", value=False,
    help="Load GFW fishing events for fishing-in-MPA detection. Slower with large datasets.",
)

fisheries_only = st.sidebar.toggle(
    "Fisheries context only", value=False,
    help="Show only vessels connected to fisheries: fishing/carrier class, "
         "IUU-listed, ICCAT-authorized, GFCM-registered, or GFW-classified fishing activity.",
)

include_insights = st.sidebar.toggle(
    "Include vessel insights (GFW)", value=False,
    help="Optional: queries GFW Insights API per vessel for AIS coverage % and "
         "live IUU list cross-check. Supplementary only — all fishing, MPA, "
         "flag-RFMO, and ICCAT analysis works without this. Slow (~5-10 min).",
)

if token:
    with st.sidebar.expander("Download API snapshot"):
        snap_info = snapshot_info()
        if snap_info:
            ev_n, fish_n, snap_date = snap_info
            ins_info = insights_snapshot_info()
            ins_text = f" + {ins_info[0]} insights" if ins_info else ""
            st.caption(
                f"Existing: {ev_n} events + {fish_n} fishing{ins_text}, "
                f"saved {snap_date:%Y-%m-%d %H:%M}"
            )
        if st.button("Download 30 days from API", key="dl_snapshot"):
            from datetime import timedelta
            end_dt = datetime.today()
            start_dt = end_dt - timedelta(days=30)
            bar = st.progress(0, text="Starting download...")
            try:
                ev_df, fish_df = download_api_snapshot(
                    token, start_dt, end_dt,
                    include_fishing=include_fishing,
                    progress=lambda pct, msg: bar.progress(
                        min(pct, 0.80 if include_insights else 1.0), text=msg),
                )
                # Insights: score → filter Elevated+ → use event vessel_id → batch query
                if include_insights and ev_df is not None and not ev_df.empty:
                    bar.progress(0.82, text="Scoring events for insights filter...")
                    from config import FLAG_RISKS
                    _tmp_scores = compute_risk_scores_vec(ev_df, event_weights, FLAG_RISKS)
                    ev_df["_tmp_score"] = _tmp_scores
                    elevated_mmsis = (
                        ev_df.loc[ev_df["_tmp_score"] >= 60, "mmsi"]
                        .dropna().unique().tolist()
                    )
                    if elevated_mmsis:
                        # Use vessel_id already captured in event parsing (no extra API call)
                        _elevated = ev_df[ev_df["mmsi"].isin(elevated_mmsis)].drop_duplicates("mmsi")
                        _vid_pairs = [
                            (row["vessel_id"], row["mmsi"])
                            for _, row in _elevated.iterrows()
                            if row.get("vessel_id") and str(row["vessel_id"]).strip()
                        ]
                        if _vid_pairs:
                            bar.progress(0.90, text=f"Fetching insights for {len(_vid_pairs)} vessels...")
                            download_insights_snapshot(
                                token, start_dt, end_dt, _vid_pairs,
                                concurrency=5,
                                progress=lambda cur, tot: bar.progress(
                                    0.90 + 0.09 * cur / max(tot, 1),
                                    text=f"Insights: {cur}/{tot} vessels..."),
                            )
                    ev_df.drop(columns=["_tmp_score"], inplace=True)
                bar.empty()
                st.success("Snapshot saved. Switch data source to 'API snapshot'.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                bar.empty()
                import traceback
                st.error(f"Download failed: {e}")
                st.code(traceback.format_exc(), language="text")

# ========================= DATA LOADING =========================
_empty_fishing = pd.DataFrame(columns=[
    "date", "vessel_name", "mmsi", "lat", "lon",
    "fishing_hours", "mpa", "mpa_tier", "in_mpa",
])

if use_live and token:
    df = load_live_data(token, date_range[0], date_range[1], min_duration)
    fishing_df = load_fishing_events_live(token, date_range[0], date_range[1]) if include_fishing else _empty_fishing
elif use_snapshot:
    df = load_snapshot_events()
    fishing_df = load_snapshot_fishing() if include_fishing else _empty_fishing
else:
    df = load_static_data()
    fishing_df = load_fishing_events_static() if include_fishing else _empty_fishing

fdi_effort = load_fdi_effort()
fdi_landings = load_fdi_landings()
iuu_vessels = load_iuu_vessels()
iccat_vessels = load_iccat_vessels()
ofac_vessels = load_ofac_vessels()
closed_area_mpas = load_closed_area_mpas()
knowledge_base = load_knowledge_base()

# Per-vessel fishing-in-MPA aggregation (display-only, no risk multiplier)
fishing_mpa_agg = aggregate_fishing_in_mpa(fishing_df)

# Set of MMSIs that appear in fishing_df (used by "Fisheries context only" toggle)
_fishing_mmsis = set(fishing_df["mmsi"].astype(str).unique()) if not fishing_df.empty else set()

# ========================= FILTER & SCORE =========================
# Cache the enriched df_filtered in session state so pill-only reruns skip
# the entire scoring + matching pipeline. The fingerprint covers every
# sidebar control that affects the pipeline output.
_pipeline_fingerprint = (
    "live" if use_live else ("snapshot" if use_snapshot else "static"),
    tuple(date_range) if isinstance(date_range, (list, tuple)) else date_range,
    min_duration,
    include_delisted,
    resolve_imos,
    include_fishing,
    fisheries_only,
    include_insights if "include_insights" in dir() else False,
    len(df),
)
_pipeline_cached = (
    st.session_state.get("_pipeline_fp") == _pipeline_fingerprint
    and "_df_filtered_cache" in st.session_state
)

if _pipeline_cached:
    df_filtered = st.session_state["_df_filtered_cache"]
# --- BEGIN pipeline (skipped when _pipeline_cached) ---
if not _pipeline_cached:
    # Clip events to selected date range (± 3 day buffer for long-running events)
    if "date" in df.columns and len(date_range) == 2:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True).dt.tz_localize(None)
        buffer_start = pd.Timestamp(date_range[0]) - pd.Timedelta(days=3)
        buffer_end = pd.Timestamp(date_range[1]) + pd.Timedelta(days=3)
        df = df[df["date"].between(buffer_start, buffer_end) | df["date"].isna()]

    df = df.dropna(subset=["lat", "lon"])
    df_filtered = df[df["duration_h"] >= min_duration].copy()
    df_filtered["risk_score"] = compute_risk_scores_vec(df_filtered, event_weights, FLAG_RISKS)

    # Assign c-square cells for FDI joins
    if not df_filtered.empty:
        csq_lon, csq_lat = assign_csquares_vec(df_filtered["lat"], df_filtered["lon"])
        df_filtered["csq_lon"] = csq_lon
        df_filtered["csq_lat"] = csq_lat

    # Vessel metadata enrichment via GFW Vessels API
    if (use_live or use_snapshot) and resolve_imos and not df_filtered.empty:
        unique_mmsis = df_filtered["mmsi"].dropna().unique().tolist()
        meta_map = load_vessel_metadata_cache()
        _cached_mmsis = set(meta_map.keys())
        _needed = [m for m in unique_mmsis if str(m) not in _cached_mmsis]
        if _needed and token:
            progress_bar = st.progress(0, text="Resolving vessel metadata via GFW API...")
            def _update_progress(current, total):
                progress_bar.progress(current / total, text=f"Resolving vessel metadata... {current}/{total}")
            fresh = lookup_vessel_metadata(_needed, token, progress_callback=_update_progress)
            meta_map.update(fresh)
            progress_bar.empty()
        if meta_map:
            mmsi_str = df_filtered["mmsi"].astype(str)
            df_filtered["imo"] = mmsi_str.map(lambda m: (meta_map.get(m) or {}).get("imo") or "")
            df_filtered["length_m"] = mmsi_str.map(lambda m: (meta_map.get(m) or {}).get("length_m"))
            df_filtered["tonnage_gt"] = mmsi_str.map(lambda m: (meta_map.get(m) or {}).get("tonnage_gt"))
            df_filtered["shiptypes"] = mmsi_str.map(lambda m: (meta_map.get(m) or {}).get("shiptypes") or "")
            _vid_map = mmsi_str.map(lambda m: (meta_map.get(m) or {}).get("vessel_id") or "")
            df_filtered["vessel_id"] = _vid_map.where(_vid_map.astype(bool), df_filtered.get("vessel_id", ""))

    # Ensure metadata columns exist
    if "imo" not in df_filtered.columns:
        df_filtered["imo"] = ""
    if "vessel_id" not in df_filtered.columns:
        df_filtered["vessel_id"] = ""
    for _meta_col, _meta_default in [("length_m", None), ("tonnage_gt", None), ("shiptypes", "")]:
        if _meta_col not in df_filtered.columns:
            df_filtered[_meta_col] = _meta_default

    df_filtered["base_risk_score"] = df_filtered["risk_score"].copy()

    # IUU / ICCAT / OFAC cross-reference
    if not df_filtered.empty and not iuu_vessels.empty:
        df_filtered = match_iuu_vessels(df_filtered, iuu_vessels, include_delisted)
    if not df_filtered.empty and not iccat_vessels.empty:
        df_filtered = match_iccat_vessels(df_filtered, iccat_vessels)
    if not df_filtered.empty and not ofac_vessels.empty:
        df_filtered = match_ofac_vessels(df_filtered, ofac_vessels)

    # Risk bands
    if not df_filtered.empty:
        import numpy as _np
        _s = df_filtered["risk_score"].values
        df_filtered["risk_band"] = _np.select(
            [_s < 50, _s < 60, _s < 80, _s < 100],
            ["Low", "Emerging", "Elevated", "Severe"],
            default="Critical",
        )

    # Vessel flags
    df_filtered = compute_vessel_flags(df_filtered)

    # Fishing-in-MPA join
    if not df_filtered.empty and not fishing_mpa_agg.empty:
        df_filtered["mmsi"] = df_filtered["mmsi"].astype(str)
        fishing_mpa_agg["mmsi"] = fishing_mpa_agg["mmsi"].astype(str)
        df_filtered = df_filtered.merge(fishing_mpa_agg, on="mmsi", how="left")
    for _col, _default in [("fishing_in_mpa_events", 0), ("fishing_in_mpa_hours", 0.0), ("fishing_in_mpa_top_tier", "")]:
        if _col not in df_filtered.columns:
            df_filtered[_col] = _default
    df_filtered["fishing_in_mpa_events"] = df_filtered["fishing_in_mpa_events"].fillna(0).astype(int)
    df_filtered["fishing_in_mpa_hours"] = df_filtered["fishing_in_mpa_hours"].fillna(0.0)
    df_filtered["fishing_in_mpa_top_tier"] = df_filtered["fishing_in_mpa_top_tier"].fillna("")

    # GFW Insights join
    _insights_df = load_snapshot_insights() if (use_snapshot or use_live) else pd.DataFrame()
    if not df_filtered.empty and not _insights_df.empty and "mmsi" in _insights_df.columns:
        _ins_cols = ["mmsi", "vessel_id", "ais_coverage_pct", "fishing_events",
                     "fishing_without_rfmo_auth_events", "fishing_in_no_take_mpa_events",
                     "iuu_listed", "iuu_times_listed", "gap_events"]
        _ins_cols = [c for c in _ins_cols if c in _insights_df.columns]
        df_filtered["mmsi"] = df_filtered["mmsi"].astype(str)
        _insights_df["mmsi"] = _insights_df["mmsi"].astype(str)
        df_filtered = df_filtered.merge(
            _insights_df[_ins_cols].drop_duplicates("mmsi"),
            on="mmsi", how="left", suffixes=("", "_gfw"),
        )
    for _col, _default in [("ais_coverage_pct", None), ("fishing_without_rfmo_auth_events", 0),
                            ("fishing_in_no_take_mpa_events", 0), ("iuu_listed", False), ("iuu_times_listed", 0)]:
        if _col not in df_filtered.columns:
            df_filtered[_col] = _default

    # Fisheries context filter
    if fisheries_only and not df_filtered.empty:
        _fisheries_classes = {"industrial_fishing", "artisanal_fishing", "carrier"}
        _is_fisheries_class = df_filtered["vessel_class"].isin(_fisheries_classes) if "vessel_class" in df_filtered.columns else False
        _is_iuu = df_filtered["iuu_matched"].fillna(False).astype(bool) if "iuu_matched" in df_filtered.columns else False
        _is_iccat = df_filtered["iccat_authorized"].fillna(False).astype(bool) if "iccat_authorized" in df_filtered.columns else False
        _is_gfcm = df_filtered["gfcm_registered"].fillna(False).astype(bool) if "gfcm_registered" in df_filtered.columns else False
        _in_fishing = df_filtered["mmsi"].astype(str).isin(_fishing_mmsis)
        df_filtered = df_filtered[_is_fisheries_class | _is_iuu | _is_iccat | _is_gfcm | _in_fishing]

    # Save to session state cache
    st.session_state["_df_filtered_cache"] = df_filtered
    st.session_state["_pipeline_fp"] = _pipeline_fingerprint
# --- END pipeline ---

# ========================= MAIN MAP & METRICS =========================

# Pill filters — rendered above the map so they're always visible.
# Same session-state keys are reused by Fleet Analytics for df_tab filtering.
_pc1, _pc2, _pc3, _pc4 = st.columns(4)
with _pc1:
    _event_types_in_data = sorted(df_filtered["event_type"].dropna().unique())
    _pill_events = st.pills(
        "Event type", _event_types_in_data,
        selection_mode="multi", default=None, key="pill_event_type",
    )
with _pc2:
    _band_order = ["Critical", "Severe", "Elevated", "Emerging", "Low"]
    _bands_in_data = [b for b in _band_order if b in df_filtered["risk_band"].values]
    _pill_bands = st.pills(
        "Risk band", _bands_in_data,
        selection_mode="multi", default=None, key="pill_risk_band",
    )
with _pc3:
    _flags_in_data = sorted(df_filtered["flag"].dropna().unique())
    _pill_flags = st.pills(
        "Flag state", _flags_in_data,
        selection_mode="multi", default=None, key="pill_flag",
    )
with _pc4:
    _classes_in_data = sorted(
        df_filtered["vessel_class"].dropna().unique()
    ) if "vessel_class" in df_filtered.columns else []
    _pill_class = st.pills(
        "Vessel class", _classes_in_data,
        selection_mode="multi", default=None, key="pill_vessel_class",
    ) if _classes_in_data else []

df_map_base = df_filtered
if _pill_events:
    df_map_base = df_map_base[df_map_base["event_type"].isin(_pill_events)]
if _pill_bands:
    df_map_base = df_map_base[df_map_base["risk_band"].isin(_pill_bands)]
if _pill_flags:
    df_map_base = df_map_base[df_map_base["flag"].isin(_pill_flags)]
if _pill_class and "vessel_class" in df_map_base.columns:
    df_map_base = df_map_base[df_map_base["vessel_class"].isin(_pill_class)]

_pills_active = bool(_pill_events or _pill_bands or _pill_flags or _pill_class)

col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Behavioral Risk Map")
    if not df_filtered.empty:
        df_map = df_map_base
        if _pills_active:
            st.caption(
                f"Map showing {len(df_map)} of {len(df_filtered)} events "
                f"(pill filters active). Clear pills above to reset."
            )

        # Pre-compute FDI context per unique c-square (cached across reruns)
        fdi_cache = {}
        if not fdi_effort.empty and "csq_lon" in df_filtered.columns:
            csq_pairs = tuple(
                map(tuple, df_filtered[["csq_lon", "csq_lat"]].drop_duplicates().values)
            )
            fdi_cache = _build_fdi_cache(csq_pairs, fdi_effort, fdi_landings)

        # ---- PyDeck map (GPU-accelerated, no iframe rerenders) ----
        import pydeck as pdk

        _event_rgb = {"GAP": [231, 76, 60], "LOITERING": [243, 156, 18], "ENCOUNTER": [155, 89, 182]}
        _band_radius = {"Low": 3000, "Emerging": 4500, "Elevated": 6000, "Severe": 8000, "Critical": 11000}

        # Prepare map dataframe with colour & radius columns
        _df_deck = df_map.copy()
        _df_deck = _df_deck.dropna(subset=["lat", "lon"])
        # Exclude Low-band unless flagged
        _is_flagged_deck = (
            _df_deck.get("ofac_sanctioned", pd.Series(False, index=_df_deck.index)).fillna(False).astype(bool)
            | _df_deck.get("iuu_matched", pd.Series(False, index=_df_deck.index)).fillna(False).astype(bool)
        )
        _df_deck = _df_deck[_is_flagged_deck | (_df_deck.get("risk_band", "Low") != "Low")]

        def _get_color(row):
            if row.get("ofac_sanctioned"):
                return [139, 0, 0, 220]
            if row.get("iuu_matched"):
                return [0, 0, 0, 220]
            return _event_rgb.get(row.get("event_type", ""), [136, 136, 136]) + [180]

        _df_deck["_color"] = _df_deck.apply(_get_color, axis=1)
        _df_deck["_radius"] = _df_deck.get("risk_band", "Low").map(_band_radius).fillna(3000).astype(int)
        _df_deck["_label"] = (
            _df_deck.get("vessel_name", "").fillna("(unknown)").astype(str)
            + " | " + _df_deck["event_type"].astype(str)
            + " | " + _df_deck["flag"].astype(str)
            + " | risk " + _df_deck["risk_score"].round(1).astype(str)
        )

        _layers = [
            pdk.Layer(
                "ScatterplotLayer",
                id="events",
                data=_df_deck,
                get_position=["lon", "lat"],
                get_color="_color",
                get_radius="_radius",
                pickable=True,
                auto_highlight=True,
                radius_min_pixels=4,
                radius_max_pixels=18,
            ),
        ]

        # FDI effort choropleth (0.5x0.5 degree filled rectangles)
        if show_fdi_layer and not fdi_effort.empty:
            _fdi_rects = _build_fdi_rectangles(fdi_effort)
            if _fdi_rects:
                _fdi_data = []
                for sw_lat, sw_lon, days, color, opacity in _fdi_rects:
                    _hex = color.lstrip("#")
                    _r, _g, _b = int(_hex[:2], 16), int(_hex[2:4], 16), int(_hex[4:6], 16)
                    _fdi_data.append({
                        "_polygon": [
                            [sw_lon, sw_lat],
                            [sw_lon + 0.5, sw_lat],
                            [sw_lon + 0.5, sw_lat + 0.5],
                            [sw_lon, sw_lat + 0.5],
                        ],
                        "_color": [_r, _g, _b, int(opacity * 255)],
                        "_label": f"FDI effort: {days:,.0f} fishing days",
                    })
                _fdi_df = pd.DataFrame(_fdi_data)
                _layers.insert(0,
                    pdk.Layer(
                        "PolygonLayer",
                        id="fdi",
                        data=_fdi_df,
                        get_polygon="_polygon",
                        get_fill_color="_color",
                        get_line_color=[0, 0, 0, 0],
                        pickable=False,
                        stroked=False,
                        filled=True,
                    )
                )

        _view = pdk.ViewState(latitude=37.0, longitude=18.0, zoom=4.5, pitch=0)
        _deck = pdk.Deck(
            layers=_layers,
            initial_view_state=_view,
            map_style="light",
            tooltip={"text": "{_label}"},
        )

        event = st.pydeck_chart(
            _deck, height=500,
            on_select="rerun",
            selection_mode="single-object",
            key="main_map",
        )

        # Click → set investigate vessel
        if event and hasattr(event, "selection") and event.selection:
            _sel_objs = event.selection.get("objects", {})
            # objects is dict keyed by layer index or "ScatterplotLayer"
            _picked_list = []
            for _layer_objs in _sel_objs.values():
                _picked_list.extend(_layer_objs)
            if _picked_list:
                _picked_obj = _picked_list[0]
                _vname = _picked_obj.get("vessel_name")
                if _vname and pd.notna(_vname) and str(_vname).strip():
                    st.session_state["investigate_vessel"] = str(_vname)
                    st.toast(f"Selected **{_vname}** for investigation")

        # Legend
        _leg = (
            '<b>Event type</b>:&ensp;'
            '<span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:#e74c3c;margin-right:3px"></span>AIS Gap&ensp;'
            '<span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:#f39c12;margin-right:3px"></span>Loitering&ensp;'
            '<span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:#9b59b6;margin-right:3px"></span>Encounter&emsp;'
            '<b>Flagged</b>:&ensp;'
            '<span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:#000;margin-right:3px"></span>IUU&ensp;'
            '<span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:#8B0000;margin-right:3px"></span>OFAC&emsp;'
            '<b>Size</b> = risk band'
        )
        st.markdown(f'<div style="font-size:13px;line-height:2.0">{_leg}</div>', unsafe_allow_html=True)
    else:
        st.info("No events match the selected filters.")

with col2:
    if not df_filtered.empty:
        # When pills are active, show pill-filtered counts with "of N total" context.
        _df_metrics = df_map_base if _pills_active else df_filtered
        _total_label = f" of {len(df_filtered)}" if _pills_active else ""
        _band_counts = _df_metrics["risk_band"].value_counts() if "risk_band" in _df_metrics.columns else pd.Series(dtype=int)
        _n_low = int(_band_counts.get("Low", 0))
        _n_elevated_plus = int(_band_counts.get("Elevated", 0)) + int(_band_counts.get("Severe", 0)) + int(_band_counts.get("Critical", 0))
        _n_map = len(_df_metrics) - _n_low
        _avg_risk = _df_metrics["risk_score"].mean() if not _df_metrics.empty else 0
        _max_risk = _df_metrics["risk_score"].max() if not _df_metrics.empty else 0
        st.metric("Avg Risk Score", f"{_avg_risk:.1f}", help="Mean risk score per event")
        st.metric("Peak Risk Score", f"{_max_risk:.1f}", help="Highest single-event risk score")
        _evt_label = f"{len(_df_metrics)}{_total_label}"
        st.metric("Total Events", _evt_label)
        st.caption(
            f"On map: **{_n_map}** (Emerging+)  \n"
            f"Hidden: {_n_low} Low-band  \n"
            f"Elevated/Severe/Critical: **{_n_elevated_plus}**"
        )
        _n_vessels = _df_metrics["mmsi"].nunique()
        _n_vessels_total = df_filtered["mmsi"].nunique()
        _v_label = f"{_n_vessels} of {_n_vessels_total}" if _pills_active else str(_n_vessels)
        st.metric("Unique Vessels", _v_label)
        _n_flags = _df_metrics["flag"].nunique()
        _n_flags_total = df_filtered["flag"].nunique()
        _f_label = f"{_n_flags} of {_n_flags_total}" if _pills_active else str(_n_flags)
        st.metric("Flags", _f_label)
        if "iuu_matched" in _df_metrics.columns:
            iuu_count = int(_df_metrics["iuu_matched"].sum())
            if iuu_count > 0:
                st.metric("IUU-Listed Vessels", iuu_count)
        if "ofac_sanctioned" in _df_metrics.columns:
            ofac_count = int(_df_metrics["ofac_sanctioned"].sum())
            if ofac_count > 0:
                st.metric("OFAC Sanctioned", ofac_count)
        # Kpler-aligned behavioural flags (display-only, do not affect risk_score)
        if "multi_behaviour_flag" in _df_metrics.columns:
            multi_vessels = int(
                _df_metrics[_df_metrics["multi_behaviour_flag"]]["mmsi"].nunique()
            )
            if multi_vessels > 0:
                st.metric(
                    "Multi-behaviour Vessels", multi_vessels,
                    help="Vessels showing two or more distinct GFW event types "
                         "(gap, encounter, loitering). Compound behavioural indicator.",
                )
        if "dark_port_call_candidate" in _df_metrics.columns:
            dpc_events = int(_df_metrics["dark_port_call_candidate"].sum())
            if dpc_events > 0:
                st.metric(
                    "Dark Port Call Candidates", dpc_events,
                    help="Loitering events within 10 km of shore. AIS-inferred, "
                         "not satellite-verified (hence 'candidate').",
                )
        if "repeat_offender_90d" in _df_metrics.columns:
            repeat_vessels = int(
                _df_metrics[_df_metrics["repeat_offender_90d"]]["mmsi"].nunique()
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
                width="stretch",
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
                width="stretch",
            )

# ========================= TABS =========================
# Four top-level tabs: Investigation first (analyst's primary view),
# Fleet Analytics (aggregate fleet views), Reference, AI Analyst.
tab_investigation, tab_overview, tab_reference, tab_ai = st.tabs([
    "Vessel Investigation",
    "Fleet Analytics",
    "Reference & Methodology",
    "AI Analyst",
])

with tab_overview:
    # Pill filters are rendered above the map; read their values here.
    pill_events = _pill_events
    pill_bands = _pill_bands
    pill_flags = _pill_flags
    pill_class = _pill_class

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

    sub_ranking, sub_exploration, sub_map, sub_fisheries, sub_fishing = st.tabs([
        "Ranking", "Exploration", "Trends & Patterns", "Fisheries Context", "Fishing Activity",
    ])

    with sub_ranking:
        with st.expander("Tab guide", expanded=False):
            st.markdown("""\
**What it shows:** The fleet-level risk ranking. One row per vessel, sorted by compounded risk score \
(highest first). Each row aggregates all behavioural events for that vessel and cross-references \
against the IUU vessel list (369 vessels, 13 RFMOs), ICCAT authorized vessel record (~9,200 Med \
vessels), and OFAC SDN sanctions list.

**Data:** GFW behavioural events (AIS gaps, encounters, loitering) scored with the risk formula, \
then aggregated per vessel (MMSI). IUU / ICCAT / OFAC cross-reference results merged in.

**Key columns:**
- **risk_band** -- Kpler Turning Tides classification: Low (<50), Emerging (50-60), Elevated (60-80), Severe (80-100), Critical (>=100). Colour-coded cells.
- **compound_multiplier** -- ratio of final risk to behavioural-only base. 1.0x = purely behavioural; >2x = structural lookups (IUU/ICCAT/OFAC) dominate.
- **vessel_class** -- descriptive category from GFW registry (industrial_fishing, carrier, tanker, etc.).
- **type_mismatch** -- True when AIS self-reported type disagrees with registry. Kpler "irregular vessel information" equivalent.
- **Four behavioural flags** (display-only, never scored): industrial profile, multi-behaviour, dark port call candidate, repeat offender.
- **MPA intersection** -- whether events fall inside Marine Protected Areas, with tier (GFCM-FRA / EU / general).
- **Listing booleans** -- iuu_matched, iccat_authorized, ofac_sanctioned.

**Pill filters** (above the subtabs) narrow all Fleet Analytics subtabs by event type, risk band, \
flag state, or vessel class.

**What to look for:** Vessels with Critical/Severe bands and compound_multiplier > 2x are the \
highest-priority targets. Type mismatches and multi-behaviour flags add investigative context. \
Switch to the **Vessel Investigation** tab for a per-vessel deep dive.

**Collapsed expanders below:** Risk band distribution -- Base vs structural-amplifier decomposition \
-- Top vessels segmented.""")

        render_vessel_summary(df_tab, fdi_effort=fdi_effort, fdi_landings=fdi_landings)

        with st.expander("Risk band distribution", expanded=False):
            render_risk_band_distribution(df_tab)

        with st.expander("Base vs structural-amplifier decomposition", expanded=False):
            render_base_vs_compound_decomposition(df_tab)

        with st.expander("Top vessels: base vs structural amplifier", expanded=False):
            render_top_vessels_segmented(df_tab, top_n=10)

    with sub_exploration:
        with st.expander("Tab guide", expanded=False):
            st.markdown("""\
**What it shows:** Behavioural deep dives -- repeat offenders, encounter patterns, and AIS gap \
analysis. These plots answer "who keeps coming back?", "who is transshipping with whom?", and \
"who is going dark?"

**Data:** Same pill-filtered GFW behavioural events as the Ranking subtab.

**Sections:**
- **Repeat offenders** -- vessels with 2+ events in a 90-day window, with timeline of top \
recidivists. Cross-references IUU and ICCAT matches.
- **Encounter analysis** -- scatter of encounter distance vs duration, with carrier vessel alerts \
for possible transshipment.
- **AIS gap behaviour** -- distribution and geographic scatter of GAP events, highlighting vessels \
that go dark near MPAs or in known transshipment zones.

**What to look for:** Repeat offenders with IUU matches are the highest-confidence targets. \
Short-distance, long-duration encounters near carrier vessels suggest at-sea transshipment. \
AIS gaps clustered near MPAs or away from shipping lanes may indicate intentional concealment.""")

        with st.expander("Repeat offenders -- IUU and ICCAT detail"):
            render_repeat_offenders(df_tab)

        with st.expander("Encounter analysis -- carrier alerts"):
            render_encounter_analysis(df_tab)

        with st.expander("AIS gap behaviour"):
            render_gap_behaviour(df_tab)

    with sub_map:
        with st.expander("Tab guide", expanded=False):
            st.markdown("""\
**What it shows:** Fleet-level temporal and cross-tabulated risk patterns. Answers "which flag-state \
and event-type combinations carry the most risk?" and "how does risk evolve over time?"

**Data:** Scored GFW behavioural events, filtered by the pill selections above.

**Key charts (always visible):**
- **Risk heatmap (flag state vs event type)** -- rows = flags sorted by total risk, columns = event \
types (GAP, LOITERING, ENCOUNTER). Bright cells = high-risk combinations. Read: which flags \
concentrate in which behaviours?
- **Daily behavioural risk trend** -- total risk per day, with IUU-event dates marked as black \
dashed verticals. Below it, a stacked area split by event type showing how GAP / LOITERING / \
ENCOUNTER risk distributes over time.
- **Monthly event counts** -- bar chart of event counts by month and type.

**What to look for:** Bright heatmap cells reveal flag-state specialisation (e.g. a flag that \
only shows GAP events). Spikes in the daily trend near IUU-event dates suggest coordinated \
behaviour. Use the **Ranking** subtab for vessel-level drill-down.

**Collapsed expanders below:** Risk exposure by MPA tier (donut) -- Fleet composition by vessel \
class (donut) -- Type mismatch by vessel class -- Flag breakdown (bars + IUU/ICCAT/OFAC tables) \
-- Event type distribution (pie + summary table) -- Event duration distribution (histogram + scatter).""")
        render_risk_heatmap(df_tab)
        render_daily_trend(df_tab)

        with st.expander("Risk exposure by MPA tier", expanded=False):
            render_mpa_tier_exposure(df_tab)

        with st.expander("Fleet composition by vessel class", expanded=False):
            render_vessel_class_composition(df_tab)

        with st.expander("Type mismatch by vessel class", expanded=False):
            render_type_mismatch_by_class(df_tab)

        with st.expander("Flag breakdown"):
            render_flag_breakdown(df_tab)

        with st.expander("Event type distribution"):
            render_event_types(df_tab)

        with st.expander("Event duration distribution"):
            render_duration_analysis(df_tab)

    with sub_fisheries:
        with st.expander("Tab guide", expanded=False):
            st.markdown("""\
**What it shows:** GFW behavioural events overlaid with the EU JRC Fisheries Dependent Information \
(FDI) baseline. Answers "do these events happen in known fishing grounds or in empty waters?"

**Data:** GFW events (spatially joined via 0.5-degree c-square) + FDI effort \
(data/fdi_effort_med.csv, ~83K rows, 2017-2024) + FDI landings (data/fdi_landings_med.csv, \
~212K rows, weight and value by species).

**Key insight:** Events in **low-effort c-squares** are the suspicious ones -- they happen in \
waters where legitimate fishing rarely occurs. Events in high-effort squares are more likely \
to be normal commercial activity.

**Sections:**
- **FDI effort vs GFW events** -- scatter map showing FDI effort centres (sized by fishing days) \
alongside GFW events (coloured by event type).
- **Event context table** -- one row per event with fishing days, top species, landings value, \
and a context flag (known/unknown fishing ground).
- **Seasonal patterns** -- bar + line chart of FDI fishing days vs GFW event count by quarter, \
filterable by Mediterranean zone.
- **Species context** -- top 15 species by value in event c-squares, with ICCAT-managed species \
(SWO, BFT, ALB) highlighted.

**What to look for:** Events with zero or near-zero fishing days in their c-square, combined \
with ICCAT-managed species in adjacent squares, suggest transshipment or IUU targeting of \
high-value stocks. See also the **Vessel Investigation** tab for per-vessel FDI context.

**Collapsed expanders below:** Fishing activity inside MPAs (scatter map of fishing-in-MPA events) \
-- Geographic risk breakdown (sub-zone bars, port-distance scatter).""")
        st.markdown(
            "Two views of fishing in the Mediterranean: the FDI baseline showing "
            "where legitimate effort concentrates, and GFW fishing events inside "
            "MPAs showing where that activity crosses into protected areas. "
            "Low-effort c-squares with suspicious behavioural events are the "
            "enforcement priority -- fishing happening where legitimate fishing "
            "rarely occurs."
        )
        render_fisheries_context(df_tab, fdi_effort, fdi_landings)

        with st.expander("Geographic risk breakdown"):
            render_geographic_risk(df_tab)

    with sub_fishing:
        with st.expander("Tab guide", expanded=False):
            st.markdown("""\
**What it shows:** GFW-classified fishing events (CNN model) with risk signal attribution. \
Separate from behavioural events (gaps, encounters, loitering) — these are actual fishing detections.

**Data:** GFW `public-global-fishing-events` feed, cross-referenced against WDPA marine protected \
areas, FDI low-effort cells, and flag-RFMO authorization status.

**Two views:**
- **Scatter map** -- background (grey dots) = all fishing inside MPAs; foreground (coloured shapes) = \
events that fire risk tree leaves (closed area, low-effort cell, non-GFCM flag).
- **Vessel table** -- one row per fishing vessel with event counts, MPA fishing, and flag status. \
Includes fishing-only vessels not visible in the behavioural Ranking tab.""")

        if fishing_df is not None and not fishing_df.empty:
            from config import GFCM_PARTY_FLAGS

            # Shared pill filters for both map and table
            _fc1, _fc2, _fc3 = st.columns(3)
            _pill_mpa = _fc1.toggle(
                "In MPA only", key="fa_mpa",
                help="Show only fishing events inside Marine Protected Areas (GFCM-FRA, EU Natura 2000, etc.).",
            )
            _pill_nongfcm = _fc2.toggle(
                "Non-GFCM flag", key="fa_nongfcm",
                help="Show only vessels flying flags of non-GFCM member states (potentially unregulated in the Med).",
            )
            _vessel_filter = _fc3.radio(
                "Vessel filter", ["All", "With behavioural", "Fishing-only"],
                horizontal=True, key="fa_vessel_filter", label_visibility="collapsed",
                help="All: every fishing vessel. "
                     "With behavioural: only vessels that also triggered AIS gap/encounter/loitering events. "
                     "Fishing-only: vessels with fishing activity but NO behavioural events (invisible to the main risk map).",
            )
            _pill_beh = _vessel_filter == "With behavioural"
            _pill_fishonly = _vessel_filter == "Fishing-only"

            _beh_mmsi = set(df_tab["mmsi"].astype(str).unique()) if not df_tab.empty else set()
            _fish_filt = fishing_df.copy()
            _fish_filt["_has_beh"] = _fish_filt["mmsi"].astype(str).isin(_beh_mmsi)
            _fish_filt["_non_gfcm"] = ~_fish_filt["flag"].fillna("").str.upper().str.strip().isin(GFCM_PARTY_FLAGS)

            if _pill_mpa:
                _fish_filt = _fish_filt[_fish_filt["in_mpa"].fillna(False).astype(bool)]
            if _pill_nongfcm:
                _fish_filt = _fish_filt[_fish_filt["_non_gfcm"]]
            if _pill_beh:
                _fish_filt = _fish_filt[_fish_filt["_has_beh"]]
            if _pill_fishonly:
                _fish_filt = _fish_filt[~_fish_filt["_has_beh"]]

            st.caption(
                f"{len(_fish_filt):,} / {len(fishing_df):,} fishing events "
                f"({_fish_filt['mmsi'].nunique():,} vessels)."
            )

            # Scatter map (filtered)
            render_fishing_in_mpa_map(df_tab, _fish_filt)

            # Vessel table (aggregated from filtered events)
            # Highlight row if a map marker was clicked
            _clicked_mmsi = st.session_state.get("fishing_map_clicked_mmsi")
            with st.expander("Fishing vessel table", expanded=True):
                _fv = _fish_filt.groupby(["mmsi", "vessel_name", "flag"]).agg(
                    events=("date", "size"),
                    total_hours=("fishing_hours", "sum"),
                    in_mpa_events=("in_mpa", "sum"),
                ).reset_index()
                _fv["total_hours"] = _fv["total_hours"].round(1)
                _fv["in_mpa_events"] = _fv["in_mpa_events"].astype(int)
                _fv["non_gfcm_flag"] = ~_fv["flag"].fillna("").str.upper().str.strip().isin(GFCM_PARTY_FLAGS)
                _fv["has_behavioural"] = _fv["mmsi"].astype(str).isin(_beh_mmsi)
                _fv = _fv.sort_values("in_mpa_events", ascending=False).reset_index(drop=True)

                # Move clicked vessel to top and show event detail card
                if _clicked_mmsi:
                    _hit = _fv[_fv["mmsi"].astype(str) == _clicked_mmsi]
                    _rest = _fv[_fv["mmsi"].astype(str) != _clicked_mmsi]
                    _fv = pd.concat([_hit, _rest], ignore_index=True)
                    if not _hit.empty:
                        _r = _hit.iloc[0]
                        st.info(
                            f"Selected: **{_r['vessel_name']}** ({_r['flag']}) — "
                            f"{int(_r['in_mpa_events'])} in-MPA events, "
                            f"{_r['total_hours']:.1f} h total fishing. "
                            f"{'Has behavioural events.' if _r['has_behavioural'] else 'Fishing-only vessel.'}"
                        )

                _fv_display = _fv.rename(columns={
                    "mmsi": "MMSI", "vessel_name": "Vessel", "flag": "Flag",
                    "events": "Fishing events", "total_hours": "Total hours",
                    "in_mpa_events": "In MPA", "non_gfcm_flag": "Non-GFCM",
                    "has_behavioural": "Behavioural",
                })

                def _highlight_clicked(row):
                    if _clicked_mmsi and str(row["MMSI"]) == _clicked_mmsi:
                        return ["background-color: #fff3cd"] * len(row)
                    return [""] * len(row)

                st.dataframe(
                    _fv_display.style.apply(_highlight_clicked, axis=1),
                    use_container_width=True, hide_index=True,
                )
                if _clicked_mmsi:
                    if st.button("Clear selection", key="fa_clear_sel"):
                        st.session_state.pop("fishing_map_clicked_mmsi", None)
                        st.rerun()
        else:
            st.info("No fishing events available. Enable 'Include fishing events' and download.")

with tab_investigation:
    with st.expander("Tab guide", expanded=False):
        st.markdown("""\
**What it shows:** A per-vessel structured investigation report. Walks the risk-tree framework \
from identity through behaviour, spatial context, structural lookups, to a final threat assessment. \
This is the analyst's primary working view -- the equivalent of Kpler's AQUARIS deep dive applied \
to fisheries.

**Data:** All scored GFW events for the selected vessel, cross-referenced against IUU vessel list \
(369 vessels, 13 RFMOs), ICCAT authorized vessel record (~9,200 Med vessels), OFAC SDN sanctions \
list, FDI fishing effort and landings (spatial join by c-square), and fishing-in-MPA events.

**Report sections (10 steps):**
1. Identity confirmation (name, MMSI, IMO, flag, profile)
2. IUU listing status (red if matched, green if clean)
3. ICCAT authorization status (amber if authorized, blue if not)
4. OFAC sanctions status (red if sanctioned, green if clean)
5. Fisheries context with FDI overlay (fishing days, species, landings per c-square)
5b. Fishing activity inside MPAs (event count, hours, MPA names)
6. Behavioural pattern (event types, durations, gap speed analysis)
6b. Behavioural flags (multi-behaviour, dark port call, repeat offender)
7. Risk score decomposition (total, flag multiplier, compound multiplier, max single event)
8. Hypotheses (colour-coded cards from the investigation engine)
9. External lookups (MarineTraffic, VesselFinder, Equasis links)
10. Threat assessment (key evidence + recommended action)

**Risk-tree trace (bottom):** Expandable by branch -- shows which of the 8 branches fired, at \
what severity, with notes. Interactive icicle chart for visual exploration. Full Graphviz \
diagram in a collapsed expander.

**Interactions:** Select a vessel from the dropdown, use the quick-select table (expandable), or \
click a marker on the map. The dropdown defaults to the highest-risk vessel.""")
    render_vessel_investigation(
        df_filtered, iuu_vessels, iccat_vessels, ofac_vessels,
        fdi_effort, fdi_landings, fishing_df=fishing_df,
        closed_area_mpas=closed_area_mpas,
    )
    st.caption("See **Reference & Methodology** tab for the generic framework and multiplier tables.")

with tab_reference:
    with st.expander("Tab guide", expanded=False):
        st.markdown("""\
**What it shows:** The scoring framework, multiplier tables, and methodology that underpin \
every number in the dashboard. No event data is used -- this tab is pure methodology.

**Data sources:** Constants from config.py + reference_content.yaml + risk_tree_framework.yaml.

**Contents:**
- **Risk-tree framework** -- interactive Graphviz diagram of the Mediterranean IUU Risk Tree \
(8 branches, 41 leaves, compound logic for tier assignment).
- **Risk formula** -- annotated scoring equation: \
`risk = (duration_h ^ 0.75) x event_weight x flag_multiplier x shore_factor x mpa_multiplier \
x event_factors x iuu_multiplier x iccat_multiplier x ofac_multiplier`.
- **Scoring pipeline diagram** -- end-to-end Graphviz showing data flow from GFW API event \
through spatial join, IUU/ICCAT/OFAC matching, to final risk band.
- **Risk band definitions** -- Low (<50), Emerging (50-60), Elevated (60-80), Severe (80-100), \
Critical (>=100), using Kpler Turning Tides vocabulary.
- **Multiplier tables** -- flag risk (per ISO-3), IUU listing (GFCM 3.0x / other RFMO 2.0x), \
ICCAT authorization (carrier 1.4x / BFT 1.3x / SWO-ALB 1.2x), OFAC sanctions (2.5x), MPA tier.
- **Framing notes** -- ICCAT, MPA calibration, fishing-in-MPA, sanctions authority.
- **Data source provenance** -- table with source, file, rows, update frequency.
- **Epistemological separation** -- what the tool measures vs what it does not claim.
- **Methodology references** and **Scope and limitations**.

**When to use:** Point stakeholders here when they ask "where do these numbers come from?" \
See the **Vessel Investigation** tab for a per-vessel applied example of this framework.""")
    render_reference()
    st.caption("See **Vessel Investigation** tab for an applied per-vessel example.")

with tab_ai:
    with st.expander("Tab guide", expanded=False):
        st.markdown("""\
**What it shows:** An AI-powered analyst (Gemini 2.5 Flash) with sandboxed code execution \
that can query, filter, aggregate, and plot the dashboard data on demand. Ask any question \
about the fleet data and get an instant answer with code, charts, or tables.

**Data available to the analyst:**
- `df` -- full scored event dataframe (all columns including risk_score, risk_band, IUU/ICCAT/OFAC flags)
- `fdi_effort` -- FDI fishing effort by c-square/year/quarter/gear
- `fdi_landings` -- FDI landings by c-square/year/quarter/species
- `iuu_vessels` -- Combined IUU Vessel List (369 vessels)
- `iccat_vessels` -- ICCAT Med-authorized vessels (~9,200)
- `ofac_vessels` -- OFAC SDN vessel list
- `fishing_df` -- fishing-in-MPA events

The model operates on copies -- it cannot modify live data, read/write files, or make network calls.

**How to use:** Pick an example question from the dropdown (16 pre-built investigation queries) \
or type your own. The analyst generates pandas/plotly code, executes it in a sandbox, and \
renders the output inline. The system prompt includes the full knowledge base so the model \
knows column names, multiplier tables, the scoring formula, and all methodology.

**Example questions:**
- "Which vessels had fishing activity inside a GFCM Fisheries Restricted Area?"
- "Plot the top 5 flag states by total risk."
- "Which vessels have a vessel_type_mismatch?"
- "Compare base vs compounded risk for OFAC-sanctioned vessels."

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

`risk = duration^0.75 x event_weight x flag_mult x shore_factor x mpa_mult x event_factors x iuu_mult x iccat_mult x ofac_mult`

**Encounter factors** (GFW criteria):
- Proximity: <500m = 1.8x (GFW threshold)
- Speed: <2kn = 1.5x (likely transfer)
- Vessel type: reefer/carrier = 1.4x

**Loitering factors** (potential transshipment):
- Reefer/carrier loitering = 1.6x
- Avg speed <2kn = 1.4x

**Gap factors** (evasion):
- Intentional disabling (GFW flag) = 1.5x
- Implied speed >8kn = 1.4x | >4kn = 1.2x

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
