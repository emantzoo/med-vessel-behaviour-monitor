"""
Pure figure-building functions for the Med Vessel Behaviour Monitor.

Each function accepts data and returns a plotly go.Figure — no Streamlit calls.
Used by tabs.py for display and by exports.py for HTML serialisation.
"""

from collections import OrderedDict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import EVENT_COLORS, RISK_BAND_COLORS, SPECIES_NAMES, classify_risk_band


# ── Severity palette shared by the icicle and card views ──────────────
ICICLE_SEV_COLORS = {
    "none": "#81C784",
    "low": "#FFF176",
    "medium": "#FFB74D",
    "high": "#E57373",
    "critical": "#B71C1C",
}
ICICLE_SEV_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
ICICLE_BRANCH_NAMES = {
    "identity": "Identity Verification",
    "flag_risk": "Flag State Risk",
    "regulatory_status": "Regulatory Status",
    "authorization": "Fishing Authorization",
    "behavioural_history": "Behavioural History",
    "spatial_context": "Spatial / Contextual",
    "fishing_activity": "Fishing Activity",
    "network_exposure": "Network Exposure",
}


# ── Event-type colour palette ─────────────────────────────────────────
EVENT_TYPE_COLORS = {
    "GAP": "#4C78A8",
    "ENCOUNTER": "#E45756",
    "LOITERING": "#F58518",
    "FISHING": "#54A24B",
}


# ── 1. Vessel trajectory ─────────────────────────────────────────────

def build_trajectory_fig(
    vessel_events: pd.DataFrame,
    vessel_summary_row: dict | None = None,
) -> go.Figure | None:
    """Cumulative risk trajectory for a single vessel.

    Returns a go.Figure or None if the data is insufficient.
    """
    if vessel_events is None or vessel_events.empty:
        return None

    time_col = "start_time" if "start_time" in vessel_events.columns else "date"
    if time_col not in vessel_events.columns or "risk_score" not in vessel_events.columns:
        return None

    events = vessel_events.copy()
    events["_time"] = pd.to_datetime(events[time_col], errors="coerce")
    events = events.dropna(subset=["_time", "risk_score"]).sort_values("_time")
    if events.empty:
        return None

    events["cumulative_risk"] = events["risk_score"].cumsum()

    fig = go.Figure()

    # Cumulative line
    fig.add_trace(go.Scatter(
        x=events["_time"],
        y=events["cumulative_risk"],
        mode="lines",
        name="Cumulative risk",
        line=dict(color="#2d2d2d", width=2),
        hoverinfo="skip",
    ))

    # Event markers by type
    for event_type, group in events.groupby("event_type"):
        hover_text = []
        for _, row in group.iterrows():
            parts = [
                f"<b>{row['event_type']}</b>",
                f"{row['_time'].strftime('%Y-%m-%d')}",
                f"Risk: {row['risk_score']:.1f}",
                f"Cumulative: {row['cumulative_risk']:.1f}",
            ]
            if "duration_h" in row.index and pd.notna(row.get("duration_h")):
                parts.append(f"Duration: {row['duration_h']:.1f}h")
            if "in_mpa" in row.index and row.get("in_mpa"):
                parts.append("Inside MPA")
            hover_text.append("<br>".join(parts))

        fig.add_trace(go.Scatter(
            x=group["_time"],
            y=group["cumulative_risk"],
            mode="markers",
            name=event_type,
            marker=dict(
                color=EVENT_TYPE_COLORS.get(event_type, "#888"),
                size=10,
                line=dict(color="white", width=1),
            ),
            text=hover_text,
            hovertemplate="%{text}<extra></extra>",
        ))

    # Band threshold reference lines
    band_thresholds = [
        (50, "Emerging", "#4C78A8"),
        (60, "Elevated", "#F58518"),
        (80, "Severe", "#E45756"),
        (100, "Critical", "#8B0000"),
    ]
    y_max = max(events["cumulative_risk"].max(), 100) * 1.05
    for threshold, label, color in band_thresholds:
        if threshold <= y_max:
            fig.add_hline(
                y=threshold, line_dash="dash", line_color=color,
                line_width=1, opacity=0.6,
                annotation_text=label,
                annotation_position="right",
                annotation=dict(font_size=10, font_color=color),
            )

    fig.update_layout(
        height=400,
        xaxis_title="Event date",
        yaxis_title="Cumulative risk score",
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
        margin=dict(l=40, r=80, t=40, b=40),
    )
    return fig


# ── 2. Risk tree icicle ──────────────────────────────────────────────

def build_icicle_fig(
    trace: list,
    vessel_name: str = "Vessel",
    threat_level: str = "Unknown",
) -> go.Figure | None:
    """Interactive icicle chart of the risk tree evaluation.

    Returns a go.Figure or None if the trace is empty.
    """
    if not trace:
        return None

    root_id = "__root__"
    root_label = f"{vessel_name} ({threat_level})"
    ids = [root_id]
    labels = [root_label]
    parents = [""]
    values = [0]
    colors = ["#CFD8DC"]
    hovers = [f"Final tier: {threat_level}"]

    branches = OrderedDict()
    for entry in trace:
        bid = entry["branch_id"]
        branches.setdefault(bid, []).append(entry)

    for bid, entries in branches.items():
        branch_name = ICICLE_BRANCH_NAMES.get(bid, bid)
        fired_count = sum(1 for e in entries if e.get("rule_fired"))
        total = len(entries)
        worst_sev = max(
            (e.get("severity", "none") for e in entries),
            key=lambda s: ICICLE_SEV_RANK.get(s, 0),
            default="none",
        )
        branch_id = f"branch::{bid}"
        branch_display = f"{branch_name} ({fired_count}/{total})"
        ids.append(branch_id)
        labels.append(branch_display)
        parents.append(root_id)
        values.append(0)
        colors.append(ICICLE_SEV_COLORS.get(worst_sev, "#CFD8DC"))
        hovers.append(f"{branch_name}<br>{fired_count}/{total} rules fired")

        for idx, e in enumerate(entries):
            leaf_display = e.get("question_id", "?").replace("_", " ").title()
            leaf_id = f"leaf::{bid}::{idx}::{e.get('question_id', '?')}"
            sev = e.get("severity", "none")
            fired = e.get("rule_fired", False)
            ids.append(leaf_id)
            labels.append(leaf_display)
            parents.append(branch_id)
            values.append(1)
            colors.append(ICICLE_SEV_COLORS.get(sev, "#CFD8DC"))
            note = str(e.get("note", "")).replace("<", "&lt;").replace(">", "&gt;")
            ans = str(e.get("answer", "?")).upper()
            fired_tag = " | RULE FIRED" if fired else ""
            hovers.append(
                f"<b>{leaf_display}</b><br>"
                f"Answer: {ans}<br>"
                f"Severity: {sev.title()}{fired_tag}<br>"
                f"{note}"
            )

    fig = go.Figure(go.Icicle(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="remainder",
        marker=dict(colors=colors, line=dict(color="white", width=1)),
        customdata=hovers,
        hovertemplate="%{customdata}<extra></extra>",
        tiling=dict(orientation="h"),
        root=dict(color="#FAFAFA"),
        textfont=dict(size=17, family="Helvetica, Arial, sans-serif"),
        insidetextfont=dict(size=17, family="Helvetica, Arial, sans-serif"),
        outsidetextfont=dict(size=17, family="Helvetica, Arial, sans-serif"),
        pathbar=dict(textfont=dict(size=16)),
    ))
    fig.update_layout(
        height=750,
        margin=dict(l=0, r=0, t=40, b=0),
        uniformtext=dict(minsize=14, mode="hide"),
        title=dict(
            text="Click a branch to zoom in; click the breadcrumb at the top to zoom out.",
            font=dict(size=14, color="#555"),
        ),
    )
    return fig


# ── 3. Risk band distribution ────────────────────────────────────────

def build_risk_band_fig(df: pd.DataFrame) -> go.Figure | None:
    """Bar chart of vessel counts per risk band.

    Expects a DataFrame with at least 'mmsi' and 'risk_score' columns.
    """
    if df.empty or "risk_score" not in df.columns:
        return None

    vessel_totals = df.groupby("mmsi")["risk_score"].sum()
    if vessel_totals.empty:
        return None

    bands = vessel_totals.apply(classify_risk_band)
    band_order = ["Low", "Emerging", "Elevated", "Severe", "Critical"]
    counts = bands.value_counts().reindex(band_order, fill_value=0)

    fig = go.Figure()
    for band in band_order:
        fig.add_trace(go.Bar(
            x=[band], y=[int(counts[band])],
            marker_color=RISK_BAND_COLORS.get(band, "#888"),
            text=[int(counts[band])], textposition="outside",
            name=band, showlegend=False,
            hovertemplate=f"<b>{band}</b><br>Vessels: %{{y}}<extra></extra>",
        ))
    fig.update_layout(
        height=320,
        xaxis_title="Risk band",
        yaxis_title="Vessel count",
        title="Vessels per risk band",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


# ── 4. Top vessels decomposition (base vs structural) ─────────────────

def build_top_vessels_fig(df: pd.DataFrame, top_n: int = 10) -> go.Figure | None:
    """Horizontal stacked bar: behavioural base vs structural amplifier.

    Expects a DataFrame with 'mmsi', 'vessel_name', 'flag',
    'base_risk_score', 'risk_score' columns.
    """
    if df.empty or "base_risk_score" not in df.columns:
        return None

    g = df.groupby("mmsi").agg(
        vessel_name=("vessel_name", lambda s: next((x for x in s.dropna() if x), "")),
        flag=("flag", lambda s: next((x for x in s.dropna() if x), "")),
        base_total=("base_risk_score", "sum"),
        risk_total=("risk_score", "sum"),
    ).reset_index()
    g["structural_delta"] = (g["risk_total"] - g["base_total"]).clip(lower=0)
    g = g.sort_values("risk_total", ascending=False).head(top_n)
    if g.empty:
        return None

    g["label"] = g.apply(
        lambda r: f"{r['vessel_name'] or r['mmsi']} ({r['flag']})", axis=1
    )
    g = g.iloc[::-1]  # plotly horizontal bars draw bottom-up

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=g["label"], x=g["base_total"], name="Behavioural base",
        orientation="h", marker_color="#4C78A8",
        hovertemplate="<b>%{y}</b><br>Behavioural base: %{x:.1f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=g["label"], x=g["structural_delta"], name="Structural amplifier",
        orientation="h", marker_color="#E45756",
        hovertemplate="<b>%{y}</b><br>Structural amplifier: %{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        barmode="stack",
        height=max(280, 38 * len(g) + 80),
        title=f"Top {len(g)} vessels by compounded risk score",
        xaxis_title="Risk score",
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


# ── 5. Daily risk trend ─────────────────────────────────────────────

def build_daily_risk_line_fig(df: pd.DataFrame) -> go.Figure | None:
    """Daily total risk score line with IUU date markers."""
    if df.empty or "date" not in df.columns or "risk_score" not in df.columns:
        return None
    daily = df.groupby("date")["risk_score"].sum().reset_index()
    fig = px.line(daily, x="date", y="risk_score", markers=True,
                  title="Total risk score by day")
    if "iuu_matched" in df.columns:
        iuu_dates = df[df["iuu_matched"] == True]["date"].unique()  # noqa: E712
        for d in iuu_dates:
            d_str = str(d)
            fig.add_shape(type="line", x0=d_str, x1=d_str, y0=0, y1=1,
                          yref="paper", line=dict(dash="dash", color="black", width=1))
            fig.add_annotation(x=d_str, y=1, yref="paper", text="IUU",
                               showarrow=False, font=dict(color="black", size=10))
    return fig


def build_daily_risk_area_fig(df: pd.DataFrame) -> go.Figure | None:
    """Stacked area of daily risk by event type."""
    if df.empty or "date" not in df.columns:
        return None
    daily_by_type = df.groupby(["date", "event_type"])["risk_score"].sum().reset_index()
    fig = px.area(daily_by_type, x="date", y="risk_score", color="event_type",
                  color_discrete_map=EVENT_COLORS,
                  title="Daily Risk by Event Type")
    return fig


def build_monthly_event_counts_fig(df: pd.DataFrame) -> go.Figure | None:
    """Monthly event counts by behaviour type."""
    if df.empty or "date" not in df.columns:
        return None
    df_m = df.copy()
    df_m["date"] = pd.to_datetime(df_m["date"], errors="coerce")
    df_m = df_m.dropna(subset=["date"])
    if df_m.empty:
        return None
    monthly = (df_m.groupby([pd.Grouper(key="date", freq="MS"), "event_type"])
               .size()
               .reset_index(name="events"))
    fig = px.line(
        monthly, x="date", y="events", color="event_type",
        color_discrete_map=EVENT_COLORS, markers=True,
        title="Monthly Event Counts by Behaviour Type",
        labels={"date": "Month", "events": "Event count", "event_type": "Behaviour"},
    )
    return fig


# ── 6. Flag breakdown ───────────────────────────────────────────────

def build_flag_risk_bar_fig(df: pd.DataFrame) -> go.Figure | None:
    """Risk by flag horizontal bar (sorted)."""
    if df.empty or "flag" not in df.columns:
        return None
    flag_risk = (df.groupby("flag")["risk_score"].sum()
                 .reset_index().sort_values("risk_score", ascending=False))
    fig = px.bar(flag_risk, x="risk_score", y="flag", orientation="h",
                 title="Total risk by flag (sorted)")
    return fig


def build_flag_event_stacked_fig(df: pd.DataFrame) -> go.Figure | None:
    """Risk by flag + event type stacked bar."""
    if df.empty or "flag" not in df.columns:
        return None
    flag_type = (df.groupby(["flag", "event_type"])["risk_score"].sum()
                 .reset_index().sort_values("risk_score", ascending=False))
    fig = px.bar(flag_type, x="risk_score", y="flag", color="event_type",
                 orientation="h", color_discrete_map=EVENT_COLORS,
                 title="Risk by Flag State and Event Type")
    return fig


# ── 7. Event type pie ───────────────────────────────────────────────

def build_event_type_pie_fig(df: pd.DataFrame) -> go.Figure | None:
    """Risk contribution by event type pie."""
    if df.empty or "event_type" not in df.columns:
        return None
    type_risk = df.groupby("event_type")["risk_score"].sum().reset_index()
    fig = px.pie(type_risk, names="event_type", values="risk_score",
                 color="event_type", color_discrete_map=EVENT_COLORS,
                 title="Risk contribution by event type")
    return fig


# ── 8. Duration analysis ────────────────────────────────────────────

def build_duration_histogram_fig(df: pd.DataFrame) -> go.Figure | None:
    """Duration distribution overlay histogram by event type."""
    if df.empty or "duration_h" not in df.columns:
        return None
    fig = px.histogram(
        df, x="duration_h", color="event_type", nbins=25,
        barmode="overlay", opacity=0.7,
        color_discrete_map=EVENT_COLORS,
        labels={"duration_h": "Duration (hours)", "event_type": "Event Type"},
        title="Event Duration Distribution",
    )
    fig.update_layout(bargap=0.05)
    return fig


def build_duration_vs_risk_fig(df: pd.DataFrame) -> go.Figure | None:
    """Duration vs risk scatter by flag."""
    if df.empty or "duration_h" not in df.columns or "risk_score" not in df.columns:
        return None
    hover_cols = ["vessel_name", "event_type", "mmsi"] if "vessel_name" in df.columns else ["event_type", "mmsi"]
    fig = px.scatter(df, x="duration_h", y="risk_score", color="flag",
                     hover_data=hover_cols,
                     title="Duration vs Risk Score by Flag",
                     labels={"duration_h": "Duration (hours)", "risk_score": "Risk Score"})
    return fig


# ── 9. Geographic analysis ──────────────────────────────────────────

def build_geographic_scatter_fig(df: pd.DataFrame) -> go.Figure | None:
    """Risk-weighted scatter map with IUU/ICCAT marker shapes."""
    if df.empty or "lon" not in df.columns or "lat" not in df.columns:
        return None
    df_geo = df.copy()
    df_geo["marker"] = "Regular"
    if "iuu_matched" in df_geo.columns:
        df_geo.loc[df_geo["iuu_matched"] == True, "marker"] = "IUU-Listed"  # noqa: E712
    if "iccat_authorized" in df_geo.columns:
        df_geo.loc[
            (df_geo["iccat_authorized"] == True) & (df_geo["marker"] == "Regular"),  # noqa: E712
            "marker",
        ] = "ICCAT-Authorized"
    hover_cols = ["mmsi", "flag", "duration_h", "risk_score"]
    if "vessel_name" in df_geo.columns:
        hover_cols.append("vessel_name")
    fig = px.scatter(
        df_geo, x="lon", y="lat", size="risk_score", color="event_type",
        symbol="marker",
        symbol_map={"Regular": "circle", "IUU-Listed": "diamond", "ICCAT-Authorized": "square"},
        color_discrete_map=EVENT_COLORS,
        hover_data=hover_cols, size_max=25,
        title="Risk-Weighted Event Map (circle=regular, diamond=IUU, square=ICCAT)",
        labels={"lon": "Longitude", "lat": "Latitude"},
    )
    return fig


def build_med_zone_bar_fig(df: pd.DataFrame) -> go.Figure | None:
    """Risk by Mediterranean sub-region horizontal bar."""
    if df.empty or "med_zone" not in df.columns:
        return None
    zone_risk = (
        df.groupby("med_zone")
        .agg(total_risk=("risk_score", "sum"), events=("mmsi", "count"))
        .reset_index().sort_values("total_risk", ascending=True)
    )
    fig = px.bar(
        zone_risk, x="total_risk", y="med_zone", orientation="h",
        color="events", color_continuous_scale="Blues",
        title="Risk by Mediterranean Sub-Region",
        labels={"total_risk": "Total Risk Score", "med_zone": "Region", "events": "Events"},
    )
    return fig


# ── 10. Risk heatmap ────────────────────────────────────────────────

def build_risk_heatmap_fig(df: pd.DataFrame) -> go.Figure | None:
    """Flag vs event type risk heatmap."""
    if df.empty or "flag" not in df.columns or "event_type" not in df.columns:
        return None
    pivot = df.pivot_table(
        values="risk_score", index="flag", columns="event_type",
        aggfunc="sum", fill_value=0,
    )
    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("total", ascending=True).drop(columns="total")
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale="YlOrRd",
        text=pivot.values.round(1),
        texttemplate="%{text}",
        hovertemplate="Flag: %{y}<br>Event: %{x}<br>Risk: %{z:.1f}<extra></extra>",
    ))
    fig.update_layout(
        title="Risk Heatmap: Flag State vs Event Type",
        xaxis_title="Event Type", yaxis_title="Flag State", height=500,
    )
    return fig


# ── 11. Repeat offenders ────────────────────────────────────────────

def build_repeat_offenders_bar_fig(
    repeat_df: pd.DataFrame, top_n: int = 15,
) -> go.Figure | None:
    """Top repeat-offender vessels by event count."""
    if repeat_df is None or repeat_df.empty:
        return None
    top = repeat_df.head(top_n)
    fig = px.bar(
        top, x="mmsi", y="event_count",
        color="total_risk", color_continuous_scale="YlOrRd",
        hover_data=["flag", "event_types", "avg_duration", "total_risk"],
        title="Repeat Offenders -- Vessels with Multiple Events",
        labels={"event_count": "Number of Events", "mmsi": "MMSI"},
    )
    fig.update_xaxes(type="category")
    return fig


def build_repeat_timeline_fig(
    df: pd.DataFrame, top3_mmsis: list,
) -> go.Figure | None:
    """Timeline scatter for top repeat offenders."""
    if df.empty or not top3_mmsis:
        return None
    timeline_df = df[df["mmsi"].isin(top3_mmsis)].copy()
    if timeline_df.empty:
        return None
    hover_cols = ["flag", "duration_h"]
    if "vessel_name" in timeline_df.columns:
        hover_cols.append("vessel_name")
    fig = px.scatter(
        timeline_df, x="date", y="mmsi", color="event_type",
        size="risk_score", color_discrete_map=EVENT_COLORS,
        hover_data=hover_cols,
        title="When did the top repeat offenders act?",
        labels={"mmsi": "Vessel MMSI", "date": "Date"},
    )
    fig.update_yaxes(type="category")
    return fig


# ── 12. Gap behaviour ───────────────────────────────────────────────

def build_gap_speed_fig(gap_df: pd.DataFrame) -> go.Figure | None:
    """Speed before vs after AIS gap scatter."""
    if gap_df is None or gap_df.empty:
        return None
    if "speed_before_gap" not in gap_df.columns or gap_df["speed_before_gap"].isna().all():
        return None
    symbol_col = None
    df_g = gap_df.copy()
    if "iuu_matched" in df_g.columns:
        df_g["status"] = df_g["iuu_matched"].map({True: "IUU-Listed", False: "Regular"})
        symbol_col = "status"
    fig = px.scatter(
        df_g, x="speed_before_gap", y="speed_after_gap",
        size="duration_h", color="flag",
        symbol=symbol_col,
        hover_data=["mmsi", "duration_h"] + (["vessel_name"] if "vessel_name" in df_g.columns else []),
        title="Gap Behaviour: Speed Before vs After AIS Disabling",
        labels={"speed_before_gap": "Speed Before Gap (kn)", "speed_after_gap": "Speed After Gap (kn)"},
    )
    fig.add_annotation(x=12, y=1, text="Stopped after gap<br>(possible transfer)",
                       showarrow=False, font=dict(size=10, color="red"))
    fig.add_annotation(x=1, y=12, text="Accelerated after gap<br>(possible evasion)",
                       showarrow=False, font=dict(size=10, color="orange"))
    return fig


def build_gap_duration_distance_fig(gap_df: pd.DataFrame) -> go.Figure | None:
    """Gap duration vs distance traveled scatter."""
    if gap_df is None or gap_df.empty:
        return None
    if "gap_distance_km" not in gap_df.columns or gap_df["gap_distance_km"].isna().all():
        return None
    fig = px.scatter(
        gap_df, x="duration_h", y="gap_distance_km", color="flag",
        hover_data=["mmsi"] + (["vessel_name"] if "vessel_name" in gap_df.columns else []),
        title="Gap Duration vs Distance Traveled During Gap",
        labels={"duration_h": "Gap Duration (hours)", "gap_distance_km": "Distance During Gap (km)"},
    )
    return fig


# ── 13. Encounter analysis ──────────────────────────────────────────

def build_encounter_proximity_fig(enc_df: pd.DataFrame) -> go.Figure | None:
    """Encounter proximity vs duration scatter."""
    if enc_df is None or enc_df.empty:
        return None
    if "encounter_median_distance_km" not in enc_df.columns:
        return None
    fig = px.scatter(
        enc_df, x="encounter_median_distance_km", y="duration_h",
        color="flag", size="risk_score",
        hover_data=["mmsi", "encounter_vessel_name", "encounter_vessel_flag"]
                    + (["vessel_name"] if "vessel_name" in enc_df.columns else []),
        title="Encounter Analysis: Proximity vs Duration",
        labels={"encounter_median_distance_km": "Median Distance Between Vessels (km)",
                "duration_h": "Encounter Duration (hours)"},
    )
    fig.add_annotation(x=0.1, y=enc_df["duration_h"].max() * 0.8,
                       text="Close + Long = HIGH RISK",
                       showarrow=False, font=dict(size=11, color="red"))
    return fig


def build_encounter_flag_pairing_fig(enc_df: pd.DataFrame) -> go.Figure | None:
    """Top flag pairings in encounters bar chart."""
    if enc_df is None or enc_df.empty:
        return None
    if "encounter_vessel_flag" not in enc_df.columns or enc_df["encounter_vessel_flag"].isna().all():
        return None
    pair_df = enc_df.groupby(["flag", "encounter_vessel_flag"]).agg(
        count=("mmsi", "count"),
        total_risk=("risk_score", "sum"),
    ).reset_index().sort_values("total_risk", ascending=False).head(10)
    if pair_df.empty:
        return None
    pair_df["pairing"] = pair_df["flag"] + " <> " + pair_df["encounter_vessel_flag"]
    fig = px.bar(pair_df, x="total_risk", y="pairing", orientation="h",
                 color="count", color_continuous_scale="Reds",
                 title="Top Flag Pairings in Encounters (by risk)",
                 labels={"total_risk": "Total Risk", "pairing": "Flag Pairing"})
    return fig


# ── 14. Fleet decomposition: base vs compound ───────────────────────

def _compute_structural_deltas(df: pd.DataFrame):
    """Compute per-source structural amplifier deltas.

    Returns (base_total, iuu_delta, iccat_delta, ofac_delta, risk_total).
    """
    base_total = float(df["base_risk_score"].sum())
    risk_total = float(df["risk_score"].sum())
    has_iuu = "iuu_matched" in df.columns and "iuu_multiplier" in df.columns
    has_iccat = "iccat_authorized" in df.columns and "iccat_multiplier" in df.columns
    has_ofac = "ofac_sanctioned" in df.columns and "ofac_multiplier" in df.columns
    iuu_delta = iccat_delta = ofac_delta = 0.0
    for _, row in df.iterrows():
        base_r = float(row.get("base_risk_score", 0))
        if base_r <= 0:
            continue
        iuu_m = float(row.get("iuu_multiplier", 1.0)) if has_iuu and row.get("iuu_matched") else 1.0
        after_iuu = base_r * iuu_m
        iuu_delta += after_iuu - base_r
        iccat_m = float(row.get("iccat_multiplier", 1.0)) if has_iccat and row.get("iccat_authorized") else 1.0
        after_iccat = after_iuu * iccat_m
        iccat_delta += after_iccat - after_iuu
        ofac_m = float(row.get("ofac_multiplier", 1.0)) if has_ofac and row.get("ofac_sanctioned") else 1.0
        after_ofac = after_iccat * ofac_m
        ofac_delta += after_ofac - after_iccat
    return base_total, iuu_delta, iccat_delta, ofac_delta, risk_total


def build_base_vs_compound_fig(df: pd.DataFrame) -> go.Figure | None:
    """Fleet-level single stacked bar: base + IUU + ICCAT + OFAC."""
    if df.empty or "base_risk_score" not in df.columns:
        return None
    base_total, iuu_delta, iccat_delta, ofac_delta, risk_total = _compute_structural_deltas(df)
    if base_total <= 0:
        return None
    compound_mult = risk_total / base_total

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=["Fleet total"], x=[base_total], name="Behavioural base",
        orientation="h", marker_color="#4C78A8",
        hovertemplate="Behavioural base: %{x:.1f}<extra></extra>",
    ))
    if iuu_delta > 0:
        fig.add_trace(go.Bar(
            y=["Fleet total"], x=[iuu_delta], name="IUU listing",
            orientation="h", marker_color="#2d2d2d",
            hovertemplate="IUU listing: +%{x:.1f}<extra></extra>",
        ))
    if iccat_delta > 0:
        fig.add_trace(go.Bar(
            y=["Fleet total"], x=[iccat_delta], name="ICCAT authorization",
            orientation="h", marker_color="#4169E1",
            hovertemplate="ICCAT authorization: +%{x:.1f}<extra></extra>",
        ))
    if ofac_delta > 0:
        fig.add_trace(go.Bar(
            y=["Fleet total"], x=[ofac_delta], name="OFAC sanctions",
            orientation="h", marker_color="#8B0000",
            hovertemplate="OFAC sanctions: +%{x:.1f}<extra></extra>",
        ))
    structural_delta = max(risk_total - base_total, 0.0)
    explained = iuu_delta + iccat_delta + ofac_delta
    residual = structural_delta - explained
    if residual > 0.5:
        fig.add_trace(go.Bar(
            y=["Fleet total"], x=[residual], name="Other structural",
            orientation="h", marker_color="#E45756",
            hovertemplate="Other structural: +%{x:.1f}<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack", height=200,
        title=f"Total risk = {risk_total:.0f}  ({compound_mult:.2f}x compound multiplier over base {base_total:.0f})",
        xaxis_title="Risk score",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.6, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def build_band_decomposition_fig(df: pd.DataFrame) -> go.Figure | None:
    """Band-segmented stacked bars: base + IUU + ICCAT + OFAC per risk band.

    Five horizontal stacked bars (one per risk band). Shows how the compound
    multiplier concentration shifts as you move up the bands — Critical-band
    vessels typically have much higher compound ratios than Emerging.
    """
    if df.empty or "base_risk_score" not in df.columns:
        return None

    # Assign each event to the vessel's risk band
    vessel_totals = df.groupby("mmsi")["risk_score"].sum()
    vessel_bands = vessel_totals.apply(classify_risk_band)
    band_map = vessel_bands.to_dict()
    df_b = df.copy()
    df_b["_vessel_band"] = df_b["mmsi"].map(band_map)

    band_order = ["Low", "Emerging", "Elevated", "Severe", "Critical"]
    bases, iuus, iccats, ofacs, residuals, annotations = [], [], [], [], [], []

    for band in band_order:
        sub = df_b[df_b["_vessel_band"] == band]
        if sub.empty:
            bases.append(0)
            iuus.append(0)
            iccats.append(0)
            ofacs.append(0)
            residuals.append(0)
            annotations.append("")
            continue
        bt, iu, ic, of, rt = _compute_structural_deltas(sub)
        bases.append(bt)
        iuus.append(iu)
        iccats.append(ic)
        ofacs.append(of)
        structural = max(rt - bt, 0.0)
        residuals.append(max(structural - iu - ic - of, 0))
        cm = rt / bt if bt > 0 else 1.0
        annotations.append(f"{cm:.2f}x")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=band_order, x=bases, name="Behavioural base",
        orientation="h", marker_color="#4C78A8",
        hovertemplate="<b>%{y}</b><br>Behavioural base: %{x:.1f}<extra></extra>",
    ))
    if any(v > 0 for v in iuus):
        fig.add_trace(go.Bar(
            y=band_order, x=iuus, name="IUU listing",
            orientation="h", marker_color="#2d2d2d",
            hovertemplate="<b>%{y}</b><br>IUU listing: +%{x:.1f}<extra></extra>",
        ))
    if any(v > 0 for v in iccats):
        fig.add_trace(go.Bar(
            y=band_order, x=iccats, name="ICCAT authorization",
            orientation="h", marker_color="#4169E1",
            hovertemplate="<b>%{y}</b><br>ICCAT authorization: +%{x:.1f}<extra></extra>",
        ))
    if any(v > 0 for v in ofacs):
        fig.add_trace(go.Bar(
            y=band_order, x=ofacs, name="OFAC sanctions",
            orientation="h", marker_color="#8B0000",
            hovertemplate="<b>%{y}</b><br>OFAC sanctions: +%{x:.1f}<extra></extra>",
        ))
    if any(v > 0.5 for v in residuals):
        fig.add_trace(go.Bar(
            y=band_order, x=residuals, name="Other structural",
            orientation="h", marker_color="#E45756",
            hovertemplate="<b>%{y}</b><br>Other structural: +%{x:.1f}<extra></extra>",
        ))

    # Add compound multiplier annotations
    totals = [b + i + ic + o + r for b, i, ic, o, r in zip(bases, iuus, iccats, ofacs, residuals)]
    for idx, (band, ann, total) in enumerate(zip(band_order, annotations, totals)):
        if ann and total > 0:
            fig.add_annotation(
                x=total, y=band, text=ann,
                showarrow=False, xanchor="left", xshift=6,
                font=dict(size=11, color="#555"),
            )

    fig.update_layout(
        barmode="stack",
        height=350,
        title="Risk composition by band — compound multiplier shifts across severity",
        xaxis_title="Risk score",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
        margin=dict(l=20, r=80, t=50, b=20),
    )
    return fig


# ── 15. FDI effort map ──────────────────────────────────────────────

def build_fdi_effort_map_fig(
    df: pd.DataFrame, fdi_effort: pd.DataFrame,
) -> go.Figure | None:
    """FDI fishing effort c-squares overlaid with GFW events."""
    if df.empty or fdi_effort is None or fdi_effort.empty:
        return None
    latest_year = fdi_effort["year"].max()
    eff_agg = (fdi_effort[fdi_effort["year"] == latest_year]
               .groupby(["centre_lon", "centre_lat"])["totfishdays"]
               .sum().reset_index())
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=eff_agg["centre_lon"], y=eff_agg["centre_lat"],
        mode="markers",
        marker=dict(
            size=8, symbol="square",
            color=eff_agg["totfishdays"],
            colorscale="Blues", showscale=True,
            colorbar=dict(title="Fishing Days", x=1.02),
            opacity=0.6,
        ),
        name=f"FDI Effort ({latest_year})",
        hovertemplate="Lon: %{x:.1f}<br>Lat: %{y:.1f}<br>Fishing days: %{marker.color:,.0f}<extra>FDI</extra>",
    ))
    for etype, color in EVENT_COLORS.items():
        sub = df[df["event_type"] == etype]
        if not sub.empty:
            fig.add_trace(go.Scatter(
                x=sub["lon"], y=sub["lat"],
                mode="markers",
                marker=dict(size=10, color=color, line=dict(width=1, color="white")),
                name=etype,
                hovertemplate="Lon: %{x:.2f}<br>Lat: %{y:.2f}<extra>" + etype + "</extra>",
            ))
    fig.update_layout(
        title=f"FDI Fishing Effort ({latest_year}) vs GFW Events",
        xaxis_title="Longitude", yaxis_title="Latitude",
        height=550, legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    return fig


def build_seasonal_pattern_fig(
    df: pd.DataFrame, fdi_effort: pd.DataFrame, zone: str,
) -> go.Figure | None:
    """Dual-axis seasonal chart: FDI fishing days (bars) vs GFW events (line)."""
    if df.empty or fdi_effort is None or fdi_effort.empty or not zone:
        return None
    if "quarter" not in fdi_effort.columns or "med_zone" not in fdi_effort.columns:
        return None
    latest_year = fdi_effort["year"].max()
    fdi_q = (fdi_effort[(fdi_effort["year"] == latest_year)]
             .groupby(["med_zone", "quarter"])["totfishdays"]
             .sum().reset_index())
    fdi_zone = fdi_q[fdi_q["med_zone"] == zone]
    df_q = df.copy()
    df_q["quarter"] = pd.to_datetime(df_q["date"], errors="coerce").dt.quarter
    gfw_zone = df_q[df_q.get("med_zone", pd.Series()) == zone] if "med_zone" in df_q.columns else df_q
    gfw_qtr = gfw_zone.groupby("quarter").size().reset_index(name="gfw_events")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=fdi_zone["quarter"], y=fdi_zone["totfishdays"],
        name="FDI Fishing Days", marker_color="steelblue", opacity=0.7,
    ))
    fig.add_trace(go.Scatter(
        x=gfw_qtr["quarter"], y=gfw_qtr["gfw_events"],
        name="GFW Events", mode="lines+markers",
        marker=dict(color="red", size=10), yaxis="y2",
    ))
    fig.update_layout(
        title=f"Seasonal Pattern: {zone}",
        xaxis=dict(title="Quarter", dtick=1),
        yaxis=dict(title="FDI Fishing Days", side="left"),
        yaxis2=dict(title="GFW Events", side="right", overlaying="y"),
        height=400,
    )
    return fig


def build_species_landings_fig(
    df: pd.DataFrame, fdi_landings: pd.DataFrame,
) -> go.Figure | None:
    """Top species by landings value in GFW event c-squares."""
    if df.empty or fdi_landings is None or fdi_landings.empty:
        return None
    if "csq_lon" not in df.columns:
        return None
    event_cells = df[["csq_lon", "csq_lat"]].drop_duplicates()
    event_land = event_cells.merge(
        fdi_landings, left_on=["csq_lon", "csq_lat"],
        right_on=["rectangle_lon", "rectangle_lat"], how="inner",
    )
    if event_land.empty:
        return None
    sp_agg = (event_land.groupby("species")
              .agg(total_tonnes=("totwghtlandg", "sum"),
                   total_value=("totvallandg", "sum"))
              .sort_values("total_value", ascending=True).tail(15))
    sp_agg["species_name"] = sp_agg.index.map(
        lambda x: f"{x} ({SPECIES_NAMES.get(x, '?')})"
    )
    fig = px.bar(
        sp_agg.reset_index(), x="total_value", y="species_name",
        orientation="h",
        title="Top Species by Landings Value in GFW Event Cells",
        labels={"total_value": "Total Landings Value (EUR)", "species_name": "Species"},
        color="total_tonnes", color_continuous_scale="YlOrRd",
    )
    fig.update_layout(coloraxis_colorbar_title="Tonnes")
    return fig
