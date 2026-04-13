"""
Export helpers for the Med Vessel Behaviour Monitor.

Two export patterns:
- Per-vessel case file (Markdown) for analyst case archives
- Fleet-level summary (CSV + Markdown cover) for client reports
"""

from collections import OrderedDict
from datetime import datetime
from io import StringIO
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
