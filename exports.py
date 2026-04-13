"""
Export helpers for the Med Vessel Behaviour Monitor.

Three export patterns:
- Per-vessel case file (Markdown) for analyst case archives
- Fleet-level summary (CSV + Markdown cover) for client reports
- HTML reports with embedded interactive Plotly charts
"""

from collections import OrderedDict
from datetime import datetime
from io import StringIO
import html as _html

import pandas as pd


def _severity_marker(severity: str) -> str:
    """Readable text marker for severity levels."""
    return {
        "critical": "[CRITICAL]",
        "high": "[HIGH]",
        "medium": "[MEDIUM]",
        "low": "[LOW]",
        "none": "[-]",
    }.get(str(severity).lower(), "[-]")


def generate_vessel_case_file(
    mmsi: str,
    vessel_summary_row: dict,
    vessel_events: pd.DataFrame,
    trace: list,
    investigation_narrative: str = "",
) -> str:
    """Produce a Markdown case file for a single vessel.

    Args:
        mmsi: vessel MMSI
        vessel_summary_row: dict from the vessel summary table
        vessel_events: DataFrame of events for this vessel
        trace: risk tree trace list from investigate_vessel()
        investigation_narrative: optional AI-generated text
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    name = vessel_summary_row.get("vessel_name", mmsi)
    flag = vessel_summary_row.get("flag", "Unknown")
    imo = vessel_summary_row.get("imo", "Unknown")
    vessel_class = vessel_summary_row.get("vessel_class", "Unknown")

    risk_band = vessel_summary_row.get("risk_band", "Unknown")
    risk_total = vessel_summary_row.get("risk_score_total", 0)
    base_total = vessel_summary_row.get("base_score_total", 0)
    compound = vessel_summary_row.get("compound_multiplier", 1.0)

    lines = []
    lines.append(f"# Vessel Case File: {name}")
    lines.append("")
    lines.append(f"**Generated:** {now}")
    lines.append("**Tool:** Med Vessel Behaviour Monitor")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. Identity
    lines.append("## 1. Vessel Identity")
    lines.append("")
    lines.append(f"- MMSI: {mmsi}")
    lines.append(f"- IMO: {imo}")
    lines.append(f"- Name: {name}")
    lines.append(f"- Flag: {flag}")
    lines.append(f"- Vessel class: {vessel_class}")
    lines.append("")

    # 2. Risk summary
    lines.append("## 2. Risk Summary")
    lines.append("")
    lines.append(f"- **Risk band:** {risk_band}")
    lines.append(f"- **Total risk score:** {risk_total:.1f}")
    lines.append(f"- **Base behavioural score:** {base_total:.1f}")
    lines.append(f"- **Compound multiplier:** {compound:.2f}x")
    lines.append("")
    lines.append(
        "The compound multiplier reflects how much risk is driven by registry "
        "lookups (IUU / ICCAT / OFAC) versus pure behavioural observation. "
        "Values close to 1.0x are mostly behavioural; above 2x, structural "
        "lookups dominate."
    )
    lines.append("")

    # 3. Structural evidence
    lines.append("## 3. Structural Evidence")
    lines.append("")
    iuu = vessel_summary_row.get("iuu_matched", False)
    iccat = vessel_summary_row.get("iccat_authorized", False)
    ofac = vessel_summary_row.get("ofac_sanctioned", False)
    lines.append(
        f"- IUU list (TMT Combined, 13 RFMOs): "
        f"{'MATCHED' if iuu else 'Not listed'}"
    )
    lines.append(
        f"- ICCAT authorised vessel record: "
        f"{'AUTHORISED' if iccat else 'Not authorised'}"
    )
    lines.append(
        f"- OFAC SDN list: "
        f"{'SANCTIONED' if ofac else 'Not sanctioned'}"
    )
    lines.append("")

    # Behavioural flags
    lines.append("### Behavioural flags")
    lines.append("")
    bf = [
        ("Industrial profile", vessel_summary_row.get("is_industrial", False)),
        ("Multi-behaviour", vessel_summary_row.get("multi_behaviour", vessel_summary_row.get("multi_behaviour_flag", False))),
        ("Dark port call candidate", vessel_summary_row.get("dark_port_candidates", vessel_summary_row.get("dark_port_call_candidate", False))),
        ("Repeat offender (90d)", vessel_summary_row.get("repeat_offender", vessel_summary_row.get("repeat_offender_90d", False))),
        ("Vessel type mismatch", vessel_summary_row.get("type_mismatch", vessel_summary_row.get("vessel_type_mismatch", False))),
    ]
    for label, val in bf:
        lines.append(f"- {label}: {'YES' if val else 'no'}")
    lines.append("")

    # 4. Events
    lines.append("## 4. Behavioural Events")
    lines.append("")
    if vessel_events is not None and not vessel_events.empty:
        et_counts = (
            vessel_events["event_type"].value_counts().to_dict()
            if "event_type" in vessel_events.columns else {}
        )
        lines.append(f"- **Total events observed:** {len(vessel_events)}")
        for etype, cnt in et_counts.items():
            lines.append(f"  - {etype}: {cnt}")
        lines.append("")

        lines.append("### Event detail")
        lines.append("")
        cols = [
            c for c in [
                "date", "start_time", "event_type", "risk_score",
                "base_risk_score", "duration_h",
                "distance_from_shore_km", "in_mpa", "mpa_tier",
            ]
            if c in vessel_events.columns
        ]
        if cols:
            tbl = vessel_events[cols].copy()
            for tc in ("date", "start_time"):
                if tc in tbl.columns:
                    tbl[tc] = tbl[tc].astype(str)
            lines.append(tbl.to_markdown(index=False))
            lines.append("")
    else:
        lines.append("No events in current filter window.")
        lines.append("")

    # 5. Risk tree
    lines.append("## 5. Risk Tree Evaluation")
    lines.append("")
    if trace:
        branches = OrderedDict()
        for entry in trace:
            bid = entry.get("branch_id", "unknown")
            branches.setdefault(bid, []).append(entry)

        for bid, entries in branches.items():
            fired = [e for e in entries if e.get("rule_fired")]
            lines.append(f"### Branch: {bid}")
            lines.append(f"*{len(fired)}/{len(entries)} rules fired*")
            lines.append("")
            for e in entries:
                marker = _severity_marker(e.get("severity", "none"))
                status = "FIRED" if e.get("rule_fired") else "not fired"
                qid = e.get("question_id", "?")
                note = e.get("note", "")
                lines.append(f"- {marker} **{qid}** ({status}): {note}")
            lines.append("")
    else:
        lines.append("Risk tree evaluation unavailable.")
        lines.append("")

    # 6. AI narrative
    if investigation_narrative:
        lines.append("## 6. AI Analyst Narrative")
        lines.append("")
        lines.append(investigation_narrative)
        lines.append("")

    # Footer
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Scores derived from Global Fishing Watch event data scored against "
        "behavioural and structural signals. Flag multipliers calibrated from "
        "the Poseidon IUU Fishing Risk Index. Full methodology: "
        "`knowledge/methodology.md`. Scoring is methodology-driven; empirical "
        "calibration against enforcement outcomes is named as future work."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Case file generated {now} from Med Vessel Behaviour Monitor*")

    return "\n".join(lines)


def generate_fleet_summary(
    vessel_summary_df: pd.DataFrame,
    filters_active: dict = None,
    max_rows: int = None,
) -> tuple:
    """Produce a fleet summary CSV plus a Markdown cover sheet.

    Returns (csv_bytes, cover_markdown).

    Args:
        vessel_summary_df: vessel-level ranked DataFrame
        filters_active: dict of active filter selections
        max_rows: optional row cap
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    df_out = vessel_summary_df.copy()
    if max_rows:
        df_out = df_out.head(max_rows)

    # CSV
    buf = StringIO()
    df_out.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode("utf-8")

    # Cover markdown
    lines = []
    lines.append("# Mediterranean Fleet Risk Summary")
    lines.append("")
    lines.append(f"**Generated:** {now}")
    lines.append("**Tool:** Med Vessel Behaviour Monitor")
    lines.append("")
    lines.append("## Scope")
    lines.append("")

    if filters_active:
        lines.append("**Filters applied:**")
        for k, v in filters_active.items():
            if v:
                lines.append(f"- {k}: {v}")
    else:
        lines.append("No filters applied; full dataset.")
    lines.append("")

    lines.append(f"**Vessels in report:** {len(df_out)}")
    if "risk_band" in df_out.columns:
        lines.append("")
        lines.append("**Band distribution:**")
        band_counts = df_out["risk_band"].value_counts().to_dict()
        for band in ["Critical", "Severe", "Elevated", "Emerging", "Low"]:
            if band in band_counts:
                lines.append(f"- {band}: {band_counts[band]}")
    lines.append("")

    lines.append("## Top vessels")
    lines.append("")
    show_cols = [
        c for c in [
            "mmsi", "vessel_name", "flag", "risk_band",
            "risk_score_total", "base_score_total", "compound_multiplier",
            "event_count", "iuu_matched", "iccat_authorized", "ofac_sanctioned",
        ]
        if c in df_out.columns
    ]
    if show_cols:
        lines.append(df_out[show_cols].head(10).to_markdown(index=False))
    lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Scores derived from Global Fishing Watch event data scored against "
        "behavioural signals (event type, duration, location, shore distance, "
        "MPA tier, flag state) and structural signals (IUU listing, ICCAT "
        "authorisation, OFAC sanctions). Flag multipliers calibrated from "
        "the Poseidon IUU Fishing Risk Index. Risk bands: "
        "Low (<50), Emerging (50-60), Elevated (60-80), Severe (80-100), "
        "Critical (>=100)."
    )
    lines.append("")
    lines.append(
        "The full per-vessel data is in the attached CSV. For deeper "
        "analysis on specific vessels, see the Vessel Investigation tab."
    )
    lines.append("")

    return csv_bytes, "\n".join(lines)


# ── HTML export helpers ─────────────────────────────────────────────────

_HTML_CSS = """\
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
  Helvetica, Arial, sans-serif; max-width: 1000px; margin: 0 auto;
  padding: 24px; color: #222; line-height: 1.5; }
h1 { border-bottom: 2px solid #2d2d2d; padding-bottom: 8px; }
h2 { margin-top: 2em; color: #333; border-bottom: 1px solid #ddd;
  padding-bottom: 4px; }
h3 { color: #444; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left;
  font-size: 13px; }
th { background: #f5f5f5; font-weight: 600; }
tr:nth-child(even) td { background: #fafafa; }
.meta { color: #666; font-size: 13px; }
.howto { background: #f8f9fa; border-left: 3px solid #4C78A8; padding: 12px 16px;
  margin: 12px 0; font-size: 13px; color: #444; }
.howto strong { color: #222; }
.risk-critical { color: #8B0000; font-weight: 700; }
.risk-severe { color: #E45756; font-weight: 700; }
.risk-elevated { color: #F58518; font-weight: 700; }
.risk-emerging { color: #4C78A8; font-weight: 700; }
hr { border: none; border-top: 1px solid #ddd; margin: 24px 0; }
@media print { .plotly-graph-div { break-inside: avoid; } }
"""

_RISK_BAND_CLASS = {
    "Critical": "risk-critical",
    "Severe": "risk-severe",
    "Elevated": "risk-elevated",
    "Emerging": "risk-emerging",
}


def _fig_to_div(fig) -> str:
    """Convert a Plotly figure to an embeddable HTML div (no full page)."""
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _df_to_html_table(df, max_rows=None) -> str:
    """Convert a DataFrame to a simple HTML table string."""
    if max_rows:
        df = df.head(max_rows)
    return df.to_html(index=False, border=0, classes="export-table")


# ── How-to-read blocks (same text as the Streamlit expanders) ───────────

_HOWTO_TRAJECTORY = """\
<strong>Line:</strong> cumulative risk_score across all events in chronological
order. Steep jumps mean high-risk events; flat sections mean quiet periods.<br>
<strong>Markers:</strong> individual events, coloured by event type (gap,
encounter, loitering). Hover for event detail.<br>
<strong>Dashed horizontal lines:</strong> risk band thresholds -- 50 (Emerging),
60 (Elevated), 80 (Severe), 100 (Critical).<br>
<strong>Read:</strong> where does the vessel's line cross each threshold, and
which event type dominated that section? That's the behavioural arc.
"""

_HOWTO_ICICLE = """\
<strong>Branches:</strong> the seven risk tree evaluation branches (Identity,
Flag Risk, Regulatory Status, Fishing Authorization, Behavioural History,
Spatial / Contextual, Network Exposure).<br>
<strong>Leaves:</strong> individual rule questions. Click a branch to zoom in
to its leaves; click the breadcrumb bar at the top to zoom back out.<br>
<strong>Colour:</strong> severity -- green (none), yellow (low), orange (medium),
red (high), dark red (critical).<br>
<strong>Label:</strong> each branch shows (fired / total) rule counts.
"""

_HOWTO_RISK_BAND = """\
<strong>Bars:</strong> number of unique vessels whose summed compounded risk
score falls into each band. Aggregation is per MMSI, not per event.<br>
<strong>Colours:</strong> match the vessel-summary table and map markers.<br>
<strong>Cutoffs:</strong> Low &lt;50, Emerging 50-60, Elevated 60-80,
Severe 80-100, Critical &ge;100 (Kpler R&amp;C Turning Tides, Dec 2025).<br>
<strong>Read:</strong> a healthy fleet skews left (Low/Emerging). A
right-skewed distribution is the headline finding.
"""

_HOWTO_TOP_VESSELS = """\
<strong>Blue segment:</strong> base_risk_score summed across that vessel's
events (behavioural + spatial observation).<br>
<strong>Red segment:</strong> the additional risk added by IUU / ICCAT / OFAC
list lookups (the gap between risk_score and base_risk_score).<br>
<strong>Mostly red:</strong> vessel is on a sanctions or IUU list -- the
structural multiplier amplifies whatever it does.<br>
<strong>Mostly blue:</strong> pure behavioural outlier -- it earned its position
from event observation alone, with little or no list-based amplification.<br>
<strong>Hover</strong> for exact base and amplifier values.
"""


def generate_vessel_case_html(
    mmsi: str,
    vessel_summary_row: dict,
    vessel_events: pd.DataFrame,
    trace: list,
    investigation_narrative: str = "",
) -> str:
    """Produce a self-contained HTML case file with embedded Plotly charts.

    Same content as the Markdown case file, plus:
    - Interactive cumulative risk trajectory chart
    - Interactive risk tree icicle chart
    - "How to read" explanatory text for each chart
    """
    from charts import build_trajectory_fig, build_icicle_fig

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    name = _html.escape(str(vessel_summary_row.get("vessel_name", mmsi)))
    flag = _html.escape(str(vessel_summary_row.get("flag", "Unknown")))
    imo = _html.escape(str(vessel_summary_row.get("imo", "Unknown")))
    vessel_class = _html.escape(str(vessel_summary_row.get("vessel_class", "Unknown")))

    risk_band = vessel_summary_row.get("risk_band", "Unknown")
    risk_total = vessel_summary_row.get("risk_score_total", 0)
    base_total = vessel_summary_row.get("base_score_total", 0)
    compound = vessel_summary_row.get("compound_multiplier", 1.0)

    band_cls = _RISK_BAND_CLASS.get(risk_band, "")
    band_span = f'<span class="{band_cls}">{_html.escape(risk_band)}</span>' if band_cls else _html.escape(risk_band)

    # Structural evidence
    iuu = vessel_summary_row.get("iuu_matched", False)
    iccat = vessel_summary_row.get("iccat_authorized", False)
    ofac = vessel_summary_row.get("ofac_sanctioned", False)

    structural_rows = (
        f"<tr><td>IUU list (TMT Combined, 13 RFMOs)</td>"
        f"<td>{'<strong>MATCHED</strong>' if iuu else 'Not listed'}</td></tr>"
        f"<tr><td>ICCAT authorised vessel record</td>"
        f"<td>{'<strong>AUTHORISED</strong>' if iccat else 'Not authorised'}</td></tr>"
        f"<tr><td>OFAC SDN list</td>"
        f"<td>{'<strong>SANCTIONED</strong>' if ofac else 'Not sanctioned'}</td></tr>"
    )

    # Behavioural flags
    bf = [
        ("Industrial profile", vessel_summary_row.get("is_industrial", False)),
        ("Multi-behaviour", vessel_summary_row.get("multi_behaviour", vessel_summary_row.get("multi_behaviour_flag", False))),
        ("Dark port call candidate", vessel_summary_row.get("dark_port_candidates", vessel_summary_row.get("dark_port_call_candidate", False))),
        ("Repeat offender (90d)", vessel_summary_row.get("repeat_offender", vessel_summary_row.get("repeat_offender_90d", False))),
        ("Vessel type mismatch", vessel_summary_row.get("type_mismatch", vessel_summary_row.get("vessel_type_mismatch", False))),
    ]
    flag_rows = "".join(
        f"<tr><td>{_html.escape(label)}</td><td>{'<strong>YES</strong>' if val else 'no'}</td></tr>"
        for label, val in bf
    )

    # Events table
    events_html = ""
    if vessel_events is not None and not vessel_events.empty:
        et_counts = (
            vessel_events["event_type"].value_counts().to_dict()
            if "event_type" in vessel_events.columns else {}
        )
        events_summary = f"<p><strong>Total events observed:</strong> {len(vessel_events)}</p><ul>"
        for etype, cnt in et_counts.items():
            events_summary += f"<li>{_html.escape(str(etype))}: {cnt}</li>"
        events_summary += "</ul>"

        cols = [
            c for c in [
                "date", "start_time", "event_type", "risk_score",
                "base_risk_score", "duration_h",
                "distance_from_shore_km", "in_mpa", "mpa_tier",
            ]
            if c in vessel_events.columns
        ]
        if cols:
            tbl = vessel_events[cols].copy()
            for tc in ("date", "start_time"):
                if tc in tbl.columns:
                    tbl[tc] = tbl[tc].astype(str)
            events_html = events_summary + _df_to_html_table(tbl)
    else:
        events_html = "<p>No events in current filter window.</p>"

    # Risk tree text
    tree_html = ""
    if trace:
        branches = OrderedDict()
        for entry in trace:
            bid = entry.get("branch_id", "unknown")
            branches.setdefault(bid, []).append(entry)
        for bid, entries in branches.items():
            fired = [e for e in entries if e.get("rule_fired")]
            tree_html += f"<h3>Branch: {_html.escape(bid)}</h3>"
            tree_html += f"<p><em>{len(fired)}/{len(entries)} rules fired</em></p><ul>"
            for e in entries:
                marker = _severity_marker(e.get("severity", "none"))
                status = "FIRED" if e.get("rule_fired") else "not fired"
                qid = _html.escape(str(e.get("question_id", "?")))
                note = _html.escape(str(e.get("note", "")))
                tree_html += f"<li>{marker} <strong>{qid}</strong> ({status}): {note}</li>"
            tree_html += "</ul>"
    else:
        tree_html = "<p>Risk tree evaluation unavailable.</p>"

    # Build Plotly figures
    traj_div = ""
    traj_fig = build_trajectory_fig(vessel_events, vessel_summary_row)
    if traj_fig:
        traj_div = _fig_to_div(traj_fig)

    icicle_div = ""
    icicle_fig = build_icicle_fig(trace, vessel_name=str(vessel_summary_row.get("vessel_name", mmsi)), threat_level=risk_band)
    if icicle_fig:
        icicle_div = _fig_to_div(icicle_fig)

    # AI narrative
    narrative_section = ""
    if investigation_narrative:
        narrative_section = (
            f"<h2>6. AI Analyst Narrative</h2>"
            f"<p>{_html.escape(investigation_narrative)}</p>"
        )

    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Case File: {name}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>{_HTML_CSS}</style>
</head>
<body>
<h1>Vessel Case File: {name}</h1>
<p class="meta">Generated: {now} | Med Vessel Behaviour Monitor</p>
<hr>

<h2>1. Vessel Identity</h2>
<table>
<tr><td>MMSI</td><td>{_html.escape(str(mmsi))}</td></tr>
<tr><td>IMO</td><td>{imo}</td></tr>
<tr><td>Name</td><td>{name}</td></tr>
<tr><td>Flag</td><td>{flag}</td></tr>
<tr><td>Vessel class</td><td>{vessel_class}</td></tr>
</table>

<h2>2. Risk Summary</h2>
<table>
<tr><td>Risk band</td><td>{band_span}</td></tr>
<tr><td>Total risk score</td><td>{risk_total:.1f}</td></tr>
<tr><td>Base behavioural score</td><td>{base_total:.1f}</td></tr>
<tr><td>Compound multiplier</td><td>{compound:.2f}x</td></tr>
</table>
<p>The compound multiplier reflects how much risk is driven by registry lookups
(IUU / ICCAT / OFAC) versus pure behavioural observation. Values close to 1.0x
are mostly behavioural; above 2x, structural lookups dominate.</p>

<h2>3. Structural Evidence</h2>
<table>{structural_rows}</table>
<h3>Behavioural flags</h3>
<table>{flag_rows}</table>

<h2>4. Behavioural Events</h2>
{events_html}

<h2>5. Risk Trajectory</h2>
{"<div class='howto'>" + _HOWTO_TRAJECTORY + "</div>" if traj_div else ""}
{traj_div if traj_div else "<p>No trajectory data available.</p>"}

<h2>6. Risk Tree Evaluation</h2>
{tree_html}
<h3>Interactive risk tree</h3>
{"<div class='howto'>" + _HOWTO_ICICLE + "</div>" if icicle_div else ""}
{icicle_div if icicle_div else "<p>No icicle data available.</p>"}

{narrative_section}

<h2>Methodology</h2>
<p>Scores derived from Global Fishing Watch event data scored against behavioural
and structural signals. Flag multipliers calibrated from the Poseidon IUU Fishing
Risk Index. Full methodology available in the application's
<code>knowledge/methodology.md</code>. Scoring is methodology-driven; empirical
calibration against enforcement outcomes is named as future work.</p>
<hr>
<p class="meta">Case file generated {now} from Med Vessel Behaviour Monitor</p>
</body>
</html>"""

    return html


def generate_fleet_summary_html(
    vessel_summary_df: pd.DataFrame,
    df_events: pd.DataFrame,
    filters_active: dict = None,
) -> str:
    """Produce a self-contained HTML fleet summary with embedded Plotly charts.

    Includes:
    - Risk band distribution chart
    - Top vessels decomposition chart (base vs structural)
    - "How to read" explanatory text for each chart
    """
    from charts import build_risk_band_fig, build_top_vessels_fig

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Scope section
    scope_html = ""
    if filters_active:
        scope_html = "<p><strong>Filters applied:</strong></p><ul>"
        for k, v in filters_active.items():
            if v:
                scope_html += f"<li>{_html.escape(str(k))}: {_html.escape(str(v))}</li>"
        scope_html += "</ul>"
    else:
        scope_html = "<p>No filters applied; full dataset.</p>"

    n_vessels = len(vessel_summary_df)

    # Band distribution text
    band_html = ""
    if "risk_band" in vessel_summary_df.columns:
        band_counts = vessel_summary_df["risk_band"].value_counts().to_dict()
        band_html = "<ul>"
        for band in ["Critical", "Severe", "Elevated", "Emerging", "Low"]:
            if band in band_counts:
                cls = _RISK_BAND_CLASS.get(band, "")
                label = f'<span class="{cls}">{band}</span>' if cls else band
                band_html += f"<li>{label}: {band_counts[band]}</li>"
        band_html += "</ul>"

    # Top vessels table
    show_cols = [
        c for c in [
            "mmsi", "vessel_name", "flag", "risk_band",
            "risk_score_total", "base_score_total", "compound_multiplier",
            "event_count", "iuu_matched", "iccat_authorized", "ofac_sanctioned",
        ]
        if c in vessel_summary_df.columns
    ]
    top_table = ""
    if show_cols:
        top_table = _df_to_html_table(vessel_summary_df[show_cols], max_rows=10)

    # Build Plotly figures
    band_div = ""
    band_fig = build_risk_band_fig(df_events)
    if band_fig:
        band_div = _fig_to_div(band_fig)

    top_div = ""
    top_fig = build_top_vessels_fig(df_events, top_n=10)
    if top_fig:
        top_div = _fig_to_div(top_fig)

    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mediterranean Fleet Risk Summary</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>{_HTML_CSS}</style>
</head>
<body>
<h1>Mediterranean Fleet Risk Summary</h1>
<p class="meta">Generated: {now} | Med Vessel Behaviour Monitor</p>
<hr>

<h2>Scope</h2>
{scope_html}
<p><strong>Vessels in report:</strong> {n_vessels}</p>

<h2>Risk Band Distribution</h2>
{band_html}
{"<div class='howto'>" + _HOWTO_RISK_BAND + "</div>" if band_div else ""}
{band_div if band_div else "<p>No risk band data available.</p>"}

<h2>Top Vessels</h2>
{top_table}

<h2>Top Vessels: Base vs Structural Amplifier</h2>
{"<div class='howto'>" + _HOWTO_TOP_VESSELS + "</div>" if top_div else ""}
{top_div if top_div else "<p>No decomposition data available.</p>"}

<h2>Methodology</h2>
<p>Scores derived from Global Fishing Watch event data scored against behavioural
signals (event type, duration, location, shore distance, MPA tier, flag state)
and structural signals (IUU listing, ICCAT authorisation, OFAC sanctions).
Flag multipliers calibrated from the Poseidon IUU Fishing Risk Index.
Risk bands: Low (&lt;50), Emerging (50-60), Elevated (60-80),
Severe (80-100), Critical (&ge;100).</p>
<p>The full per-vessel data is in the companion CSV export. For deeper analysis
on specific vessels, see the Vessel Investigation tab in the application.</p>
<hr>
<p class="meta">Fleet summary generated {now} from Med Vessel Behaviour Monitor</p>
</body>
</html>"""

    return html
