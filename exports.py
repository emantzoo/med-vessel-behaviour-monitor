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
    gfcm = vessel_summary_row.get("gfcm_registered", False)
    lines.append(
        f"- IUU list (TMT Combined, 13 RFMOs): "
        f"{'MATCHED' if iuu else 'Not listed'}"
    )
    lines.append(
        f"- ICCAT authorised vessel record: "
        f"{'AUTHORISED' if iccat else 'Not authorised'}"
    )
    lines.append(
        f"- GFCM register: "
        f"{'REGISTERED' if gfcm else 'Not matched'}"
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

_HOWTO_DAILY_TREND = """\
<strong>Line chart:</strong> total compounded risk_score summed across all events
on each calendar day. Spikes = many events or one structurally amplified event.<br>
<strong>Black dashed verticals (IUU):</strong> dates with at least one
IUU-listed vessel event.<br>
<strong>Stacked area:</strong> daily totals split by event type (gap / encounter /
loitering) showing composition shifting over time.<br>
<strong>Monthly counts:</strong> event counts by behaviour type per calendar month.
"""

_HOWTO_FLAG_BREAKDOWN = """\
<strong>Top bar:</strong> total compounded risk_score per flag state, sorted
descending. Long bars = headline finding.<br>
<strong>Bottom stacked bar:</strong> same totals broken out by event type --
shows whether a flag's exposure comes from gaps, encounters, or loitering.
"""

_HOWTO_EVENT_TYPES = """\
<strong>Pie:</strong> share of total compounded risk_score contributed by each
event type. Encounters typically dominate (event weight 5.0 vs 3.2 for gaps,
2.0 for loitering).
"""

_HOWTO_DURATION = """\
<strong>Histogram:</strong> distribution of event duration in hours, coloured by
event type. Long-tail bars = suspicious: gaps &gt;24h suggest deliberate AIS
disabling, encounters &gt;8h suggest transshipment.<br>
<strong>Scatter:</strong> each dot is one event, x = duration, y = risk score,
colour = flag. The non-linear relationship comes from duration^0.75 plus
structural multipliers.
"""

_HOWTO_GEOGRAPHIC = """\
<strong>Scatter map:</strong> events at (lon, lat), sized by risk, coloured by
event type, shaped by marker class (circle = regular, diamond = IUU-listed,
square = ICCAT-authorized).<br>
<strong>Sub-region bar:</strong> risk per Med zone (Western / Tyrrhenian /
Ionian / Aegean).
"""

_HOWTO_HEATMAP = """\
<strong>Cells:</strong> total compounded risk_score for (flag, event-type) pairs.
Brighter = more risk. Rows sorted by total risk.<br>
<strong>Read:</strong> look for cells where a high-risk flag intersects with a
high-weight event type -- these are the priority investigation targets.
"""

_HOWTO_REPEAT_OFFENDERS = """\
<strong>Bar chart:</strong> top 15 vessels by event count, colour = total risk.
A vessel with 5 events is far more interesting than 5 vessels with 1 event each.<br>
<strong>Timeline:</strong> top 3 repeat offenders' events on a true time axis --
read the spacing between events to assess operational patterns.
"""

_HOWTO_GAP_BEHAVIOUR = """\
<strong>Speed scatter:</strong> x = speed before gap, y = speed after gap,
size = duration, colour = flag. Vessels going fast then reappearing slow suggest
a mid-sea transfer. Diamonds mark IUU-listed vessels.<br>
<strong>Duration vs distance:</strong> long gaps covering large distances indicate
intentional evasion rather than signal loss.
"""

_HOWTO_ENCOUNTERS = """\
<strong>Proximity scatter:</strong> x = median distance between vessels (km),
y = encounter duration (hours), size = risk score. Close + Long = highest risk
(the classic ship-to-ship transfer signature).<br>
<strong>Flag pairings:</strong> top 10 flag combinations in encounters, coloured
by count. Look for high-risk flag pairings.
"""

_HOWTO_FISHERIES = """\
<strong>FDI effort map:</strong> blue squares = fishing effort from EU JRC FDI
(sized by fishing days), coloured circles = GFW events. Events in low-effort
cells are suspicious.<br>
<strong>Seasonal chart:</strong> FDI fishing days (bars) vs GFW events (line)
by quarter for the most active zone.<br>
<strong>Species bar:</strong> top species by EUR value in event cells. ICCAT-managed
species (BFT, SWO, ALB) increase transshipment risk.
"""

_HOWTO_BASE_COMPOUND = """\
<strong>Blue segment:</strong> sum of base_risk_score -- what was observed
(event duration, shore distance, MPA tier, flag-state risk).<br>
<strong>Coloured segments:</strong> additional risk from each lookup stage:
IUU listing (black), ICCAT authorization (blue), OFAC sanctions (dark red).<br>
<strong>Compound multiplier:</strong> total / base. Close to 1.0x = mostly
behavioural; above 2x = structural lookups dominate.
"""

_HOWTO_BAND_DECOMPOSITION = """\
<strong>Five bars:</strong> one per risk band (Low to Critical), each decomposed
into behavioural base + IUU + ICCAT + OFAC amplifier deltas.<br>
<strong>Annotation:</strong> compound multiplier per band. Critical-band vessels
typically have much higher compound ratios than Emerging -- showing that band
membership is driven by both behavioural severity AND structural amplification.<br>
<strong>Read:</strong> if Critical is mostly non-blue, structural lookups are
the main driver of the most severe vessels.
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
    gfcm = vessel_summary_row.get("gfcm_registered", False)

    structural_rows = (
        f"<tr><td>IUU list (TMT Combined, 13 RFMOs)</td>"
        f"<td>{'<strong>MATCHED</strong>' if iuu else 'Not listed'}</td></tr>"
        f"<tr><td>ICCAT authorised vessel record</td>"
        f"<td>{'<strong>AUTHORISED</strong>' if iccat else 'Not authorised'}</td></tr>"
        f"<tr><td>GFCM register</td>"
        f"<td>{'<strong>REGISTERED</strong>' if gfcm else 'Not matched'}</td></tr>"
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


def _chart_section(fig, howto: str, fallback: str = "Chart not available for current data.") -> str:
    """Render a chart section: howto callout + plotly div, or fallback message."""
    if fig:
        return f"<div class='howto'>{howto}</div>\n{_fig_to_div(fig)}"
    return f"<p class='meta'>{_html.escape(fallback)}</p>"


def generate_fleet_summary_html(
    vessel_summary_df: pd.DataFrame,
    df_events: pd.DataFrame,
    filters_active: dict = None,
    fdi_effort: pd.DataFrame = None,
    fdi_landings: pd.DataFrame = None,
) -> str:
    """Produce a self-contained HTML fleet summary with embedded Plotly charts.

    Includes all fleet-level analytics charts from the Map & Overview,
    Vessel Summary, and Fisheries Context tabs.
    """
    from charts import (
        build_risk_band_fig, build_top_vessels_fig,
        build_daily_risk_line_fig, build_daily_risk_area_fig,
        build_monthly_event_counts_fig,
        build_flag_risk_bar_fig, build_flag_event_stacked_fig,
        build_event_type_pie_fig,
        build_duration_histogram_fig, build_duration_vs_risk_fig,
        build_geographic_scatter_fig, build_med_zone_bar_fig,
        build_risk_heatmap_fig,
        build_repeat_offenders_bar_fig, build_repeat_timeline_fig,
        build_gap_speed_fig, build_gap_duration_distance_fig,
        build_encounter_proximity_fig, build_encounter_flag_pairing_fig,
        build_base_vs_compound_fig, build_band_decomposition_fig,
        build_fdi_effort_map_fig, build_seasonal_pattern_fig,
        build_species_landings_fig,
    )

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    df = df_events

    # ── Scope ────────────────────────────────────────────────────────
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

    # ── Band summary text ────────────────────────────────────────────
    band_text = ""
    if "risk_band" in vessel_summary_df.columns:
        band_counts = vessel_summary_df["risk_band"].value_counts().to_dict()
        band_text = "<ul>"
        for band in ["Critical", "Severe", "Elevated", "Emerging", "Low"]:
            if band in band_counts:
                cls = _RISK_BAND_CLASS.get(band, "")
                label = f'<span class="{cls}">{band}</span>' if cls else band
                band_text += f"<li>{label}: {band_counts[band]}</li>"
        band_text += "</ul>"

    # ── Top vessels table ────────────────────────────────────────────
    show_cols = [
        c for c in [
            "mmsi", "vessel_name", "flag", "risk_band",
            "risk_score_total", "base_score_total", "compound_multiplier",
            "event_count", "iuu_matched", "iccat_authorized", "ofac_sanctioned",
        ]
        if c in vessel_summary_df.columns
    ]
    top_table = _df_to_html_table(vessel_summary_df[show_cols], max_rows=10) if show_cols else ""

    # ── Event type summary table ─────────────────────────────────────
    evt_summary_table = ""
    if not df.empty and "event_type" in df.columns:
        evt_summary = df.groupby("event_type").agg(
            events=("mmsi", "count"),
            avg_duration=("duration_h", "mean"),
            avg_risk=("risk_score", "mean"),
            total_risk=("risk_score", "sum"),
        ).reset_index()
        for col in ["avg_duration", "avg_risk", "total_risk"]:
            evt_summary[col] = evt_summary[col].round(1)
        evt_summary_table = _df_to_html_table(evt_summary)

    # ── Repeat offenders table ───────────────────────────────────────
    repeat_df = None
    if not df.empty:
        vc = (df.groupby(["mmsi", "flag"]).agg(
            event_count=("event_type", "count"),
            total_risk=("risk_score", "sum"),
            event_types=("event_type", lambda x: ", ".join(sorted(set(x)))),
            avg_duration=("duration_h", "mean"),
        ).reset_index().sort_values("event_count", ascending=False))
        if "vessel_name" in df.columns:
            nm = df.dropna(subset=["vessel_name"]).drop_duplicates("mmsi").set_index("mmsi")["vessel_name"]
            vc["vessel_name"] = vc["mmsi"].map(nm).fillna("")
        repeat_df = vc[vc["event_count"] >= 2]

    # ── Build all Plotly figures ─────────────────────────────────────
    # Section 2: Risk band
    s2 = _chart_section(build_risk_band_fig(df), _HOWTO_RISK_BAND)
    # Section 3: Top vessels
    s3 = _chart_section(build_top_vessels_fig(df, top_n=10), _HOWTO_TOP_VESSELS)
    # Section 4a: Base vs compound
    s4a = _chart_section(build_base_vs_compound_fig(df), _HOWTO_BASE_COMPOUND)
    # Section 4b: Band decomposition
    s4b = _chart_section(build_band_decomposition_fig(df), _HOWTO_BAND_DECOMPOSITION)
    # Section 5a: Daily trend (3 charts)
    s5a_line = _chart_section(build_daily_risk_line_fig(df), _HOWTO_DAILY_TREND)
    s5a_area = _fig_to_div(build_daily_risk_area_fig(df)) if build_daily_risk_area_fig(df) else ""
    s5a_monthly = _fig_to_div(build_monthly_event_counts_fig(df)) if build_monthly_event_counts_fig(df) else ""
    # Section 5b: Heatmap
    s5b = _chart_section(build_risk_heatmap_fig(df), _HOWTO_HEATMAP)
    # Section 6a: Flag breakdown
    s6a_bar = _chart_section(build_flag_risk_bar_fig(df), _HOWTO_FLAG_BREAKDOWN)
    flag_stacked_fig = build_flag_event_stacked_fig(df)
    s6a_stacked = _fig_to_div(flag_stacked_fig) if flag_stacked_fig else ""
    # Section 6b: Event type pie
    s6b = _chart_section(build_event_type_pie_fig(df), _HOWTO_EVENT_TYPES)
    # Section 6c: Duration
    s6c_hist = _chart_section(build_duration_histogram_fig(df), _HOWTO_DURATION)
    dur_scatter_fig = build_duration_vs_risk_fig(df)
    s6c_scatter = _fig_to_div(dur_scatter_fig) if dur_scatter_fig else ""
    # Section 7a: Repeat offenders
    s7a_bar = _chart_section(
        build_repeat_offenders_bar_fig(repeat_df) if repeat_df is not None and not repeat_df.empty else None,
        _HOWTO_REPEAT_OFFENDERS,
    )
    top3 = repeat_df.head(3)["mmsi"].tolist() if repeat_df is not None and not repeat_df.empty else []
    s7a_tl = _fig_to_div(build_repeat_timeline_fig(df, top3)) if top3 and build_repeat_timeline_fig(df, top3) else ""
    repeat_table = _df_to_html_table(repeat_df.head(15)) if repeat_df is not None and not repeat_df.empty else ""
    # Section 7b: Encounters
    enc_df = df[df["event_type"] == "ENCOUNTER"].copy() if not df.empty else pd.DataFrame()
    s7b_prox = _chart_section(build_encounter_proximity_fig(enc_df), _HOWTO_ENCOUNTERS)
    pair_fig = build_encounter_flag_pairing_fig(enc_df)
    s7b_pair = _fig_to_div(pair_fig) if pair_fig else ""
    # Section 7c: Gap behaviour
    gap_df = df[df["event_type"] == "GAP"].copy() if not df.empty else pd.DataFrame()
    s7c_speed = _chart_section(build_gap_speed_fig(gap_df), _HOWTO_GAP_BEHAVIOUR)
    dist_fig = build_gap_duration_distance_fig(gap_df)
    s7c_dist = _fig_to_div(dist_fig) if dist_fig else ""
    # Section 8: Geography
    s8a = _chart_section(build_geographic_scatter_fig(df), _HOWTO_GEOGRAPHIC)
    zone_fig = build_med_zone_bar_fig(df)
    s8b = _fig_to_div(zone_fig) if zone_fig else ""
    # Section 9: Fisheries context (conditional)
    has_fdi = fdi_effort is not None and not fdi_effort.empty
    s9a = _chart_section(
        build_fdi_effort_map_fig(df, fdi_effort) if has_fdi else None,
        _HOWTO_FISHERIES,
        "FDI data not available.",
    )
    # Auto-pick busiest zone for seasonal chart
    seasonal_fig = None
    seasonal_note = ""
    if has_fdi and "med_zone" in df.columns and not df.empty:
        busiest_zone = df["med_zone"].value_counts().idxmax()
        seasonal_fig = build_seasonal_pattern_fig(df, fdi_effort, busiest_zone)
        seasonal_note = f"<p class='meta'>Showing zone with most events: {_html.escape(busiest_zone)}. Use interactive app for zone selection.</p>"
    s9b = (_fig_to_div(seasonal_fig) if seasonal_fig else "") + seasonal_note
    species_fig = build_species_landings_fig(df, fdi_landings) if fdi_landings is not None else None
    s9c = _fig_to_div(species_fig) if species_fig else ""

    # ── Assemble HTML ────────────────────────────────────────────────
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mediterranean Fleet Risk Summary</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
{_HTML_CSS}
nav ol {{ columns: 2; column-gap: 2em; }}
nav a {{ color: #4C78A8; text-decoration: none; }}
nav a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>Mediterranean Fleet Risk Summary</h1>
<p class="meta">Generated: {now} | Med Vessel Behaviour Monitor</p>
<hr>

<nav>
<h2>Contents</h2>
<ol>
<li><a href="#s1">Executive Summary</a></li>
<li><a href="#s2">Risk Band Distribution</a></li>
<li><a href="#s3">Top Vessels</a></li>
<li><a href="#s4">Fleet Risk Decomposition</a></li>
<li><a href="#s5">Temporal Analysis</a></li>
<li><a href="#s6">Fleet Composition</a></li>
<li><a href="#s7">Behavioural Deep Dives</a></li>
<li><a href="#s8">Geographic Analysis</a></li>
<li><a href="#s9">Fisheries Context</a></li>
<li><a href="#s10">Methodology</a></li>
</ol>
</nav>
<hr>

<h2 id="s1">1. Executive Summary</h2>
{scope_html}
<p><strong>Vessels in report:</strong> {n_vessels}</p>
{band_text}

<h2 id="s2">2. Risk Band Distribution</h2>
{s2}

<h2 id="s3">3. Top Vessels</h2>
{top_table}
<h3>Base vs Structural Amplifier</h3>
{s3}

<h2 id="s4">4. Fleet Risk Decomposition</h2>
<h3>4a. Base vs Structural Amplifier (Fleet Total)</h3>
{s4a}
<h3>4b. Band-Segmented Decomposition</h3>
{s4b}

<h2 id="s5">5. Temporal Analysis</h2>
<h3>5a. Daily Risk Trend</h3>
{s5a_line}
{s5a_area}
{s5a_monthly}
<h3>5b. Risk Heatmap: Flag x Event Type</h3>
{s5b}

<h2 id="s6">6. Fleet Composition</h2>
<h3>6a. Flag Breakdown</h3>
{s6a_bar}
{s6a_stacked}
<h3>6b. Event Type Distribution</h3>
{s6b}
{evt_summary_table}
<h3>6c. Duration Analysis</h3>
{s6c_hist}
{s6c_scatter}

<h2 id="s7">7. Behavioural Deep Dives</h2>
<h3>7a. Repeat Offenders</h3>
{s7a_bar}
{repeat_table}
{s7a_tl}
<h3>7b. Encounter Analysis</h3>
{s7b_prox}
{s7b_pair}
<h3>7c. AIS Gap Behaviour</h3>
{s7c_speed}
{s7c_dist}

<h2 id="s8">8. Geographic Analysis</h2>
<h3>8a. Risk-Weighted Scatter Map</h3>
{s8a}
<h3>8b. Med Sub-Region Risk</h3>
{s8b if s8b else "<p class='meta'>Med zone data not available.</p>"}

<h2 id="s9">9. Fisheries Context</h2>
<h3>9a. FDI Effort vs Events</h3>
{s9a}
<h3>9b. Seasonal Patterns</h3>
{s9b if s9b else "<p class='meta'>Seasonal data not available.</p>"}
<h3>9c. Species Landings</h3>
{s9c if s9c else "<p class='meta'>Species data not available.</p>"}

<h2 id="s10">10. Methodology</h2>
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
