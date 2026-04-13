"""
Pure figure-building functions for the Med Vessel Behaviour Monitor.

Each function accepts data and returns a plotly go.Figure — no Streamlit calls.
Used by tabs.py for display and by exports.py for HTML serialisation.
"""

from collections import OrderedDict

import pandas as pd
import plotly.graph_objects as go

from config import RISK_BAND_COLORS, classify_risk_band


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
