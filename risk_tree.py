"""Render the Med IUU Risk Tree framework as a graphviz diagram."""

import yaml
import graphviz
import os
import textwrap


def _wrap(text, width=38):
    """Wrap a string into multiple lines on word boundaries for Graphviz nodes."""
    if not text:
        return ""
    return "\n".join(textwrap.wrap(str(text), width=width)) or str(text)


def load_framework(path=None):
    """Load the risk tree framework YAML."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "data", "risk_tree_framework.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["framework"]


# Severity-to-colour mapping for per-vessel trace
_SEVERITY_FILL = {
    "none": "#E8F5E9",
    "low": "#FFF9C4",
    "medium": "#FFE0B2",
    "high": "#FFAB91",
    "critical": "#EF5350",
}
_SEVERITY_TEXT = {
    "none": "black",
    "low": "black",
    "medium": "black",
    "high": "white",
    "critical": "white",
}


def render_framework_tree(trace=None, tier=None, vessel_label=None):
    """Render the framework as a graphviz diagram.

    Parameters
    ----------
    trace : list of dict, optional
        Per-vessel evaluation trace from investigate_vessel().
        When provided, nodes are coloured by severity.
    tier : str, optional
        Assigned tier (e.g. "Critical", "High"). Highlights the
        matching tier node and mutes the others.
    vessel_label : str, optional
        Display label for the vessel shown in the root node.
    """
    framework = load_framework()

    # Build trace lookup
    trace_lookup = {}
    if trace:
        for entry in trace:
            trace_lookup[entry["question_id"]] = entry

    # Compact layout: TB (top-down), tight spacing, small nodes
    dot = graphviz.Digraph(
        "iuu_risk_tree",
        graph_attr={
            "rankdir": "TB",
            "fontname": "Helvetica",
            "fontsize": "10",
            "bgcolor": "white",
            "splines": "line",
            "nodesep": "0.15",
            "ranksep": "0.35",
            "margin": "0.2",
        },
        node_attr={
            "fontname": "Helvetica",
            "fontsize": "8",
            "shape": "box",
            "style": "rounded,filled",
            "height": "0.3",
            "margin": "0.08,0.04",
        },
        edge_attr={
            "fontname": "Helvetica",
            "fontsize": "7",
            "arrowsize": "0.5",
        },
    )

    # Root node
    root_label = _wrap(framework["name"], width=24)
    if vessel_label:
        root_label += f"\n{_wrap(vessel_label, width=24)}"

    dot.node(
        "root", root_label,
        fillcolor="#1f77b4", fontcolor="white", fontsize="11",
    )

    # Branch type colours
    _BRANCH_COLORS = {
        "gate":       ("#C62828", "#FF6B6B"),   # (fired, default)
        "contextual": ("#6A1B9A", "#9B59B6"),
        "additive":   ("#00897B", "#4ECDC4"),
    }

    for branch in framework["branches"]:
        branch_id = branch["id"]
        questions = branch.get("questions", [])

        # Did any question in this branch fire?
        branch_fired = False
        if trace:
            for q in questions:
                entry = trace_lookup.get(q["id"])
                if entry and entry.get("rule_fired"):
                    branch_fired = True
                    break

        fired_col, default_col = _BRANCH_COLORS.get(
            branch["type"], ("#00897B", "#4ECDC4"))
        branch_color = fired_col if branch_fired else default_col

        # Branch node: short name + type tag + leaf count
        branch_label = (
            f"{_wrap(branch['name'], width=20)}\n"
            f"[{branch['type'].upper()}] {len(questions)} leaves"
        )
        dot.node(
            branch_id, branch_label,
            fillcolor=branch_color, fontcolor="white", fontsize="9",
        )
        dot.edge("root", branch_id)

        # Question leaf nodes — compact single-line labels
        for q in questions:
            q_id = f"{branch_id}_{q['id']}"
            # Short label: just the question id in readable form
            short_name = q["id"].replace("_", " ")
            weight = q.get("weight", "")
            status = q.get("status", "")

            # Colour from trace
            if trace:
                entry = trace_lookup.get(q["id"])
                if entry:
                    severity = entry.get("severity", "none")
                    fill = _SEVERITY_FILL.get(severity, "#F0F0F0")
                    fontcolor = _SEVERITY_TEXT.get(severity, "black")
                    answer = entry.get("answer", "unknown")
                    leaf_label = f"{short_name}\n[{answer.upper()}]"
                else:
                    fill = "#F0F0F0"
                    fontcolor = "#999"
                    leaf_label = short_name
            else:
                fill = "#F0F0F0"
                fontcolor = "black"
                # Add weight/status badges
                badges = []
                if weight:
                    badges.append(weight.upper())
                if status == "future_work":
                    badges.append("FUTURE")
                    fill = "#FAFAFA"
                    fontcolor = "#BDBDBD"
                suffix = f"  [{', '.join(badges)}]" if badges else ""
                leaf_label = f"{short_name}{suffix}"

            dot.node(
                q_id, leaf_label,
                fillcolor=fill, fontcolor=fontcolor,
            )
            dot.edge(branch_id, q_id)

    # Tier outcome nodes — horizontal row
    with dot.subgraph(name="cluster_tiers") as tiers:
        tiers.attr(
            label="Tier Outcomes", style="dashed", color="gray",
            fontsize="9", rank="same",
        )
        for t in framework["tier_outcomes"]:
            tier_name = t["tier"]
            if tier and tier_name.lower() != tier.lower():
                fillcolor = "#E0E0E0"
                fontcolor = "#9E9E9E"
                penwidth = "1"
            elif tier and tier_name.lower() == tier.lower():
                fillcolor = t["color"]
                fontcolor = "white"
                penwidth = "3"
            else:
                fillcolor = t["color"]
                fontcolor = "white"
                penwidth = "1"

            tiers.node(
                f"tier_{tier_name.lower()}", tier_name,
                fillcolor=fillcolor, fontcolor=fontcolor,
                shape="ellipse", fontsize="9", penwidth=penwidth,
            )

    return dot


def render_scoring_pipeline_diagram():
    """Render the end-to-end scoring pipeline as a graphviz flowchart.

    Three clear lanes, read top-to-bottom:

    1. CENTRE (blue tones): the multiplicative scoring chain.
       AIS event -> base behavioural score (snapshot) -> list-lookup
       multipliers (IUU / ICCAT / OFAC) -> per-event risk_score.
    2. CENTRE-BOTTOM (green tones): vessel-level aggregation.
       Sum per-event scores -> risk_score_total -> risk_band.
       Compound multiplier = risk_score_total / base_score_total.
    3. RIGHT (grey, dashed): four display-only vessel flags.
       Computed separately, never multiplied into the score.
       Feed into the Ranking table as parallel indicators.
    """
    dot = graphviz.Digraph(
        "scoring_pipeline",
        graph_attr={
            "rankdir": "TB",
            "fontname": "Helvetica",
            "fontsize": "13",
            "bgcolor": "white",
            "splines": "line",
            "nodesep": "0.6",
            "ranksep": "0.55",
        },
        node_attr={
            "fontname": "Helvetica",
            "fontsize": "11",
            "shape": "box",
            "style": "rounded,filled",
            "fillcolor": "white",
            "color": "#555",
            "margin": "0.18,0.1",
        },
        edge_attr={
            "fontname": "Helvetica",
            "fontsize": "9",
            "color": "#555",
        },
    )

    # ── LANE 1: Per-event scoring chain ──────────────────────────────
    dot.node(
        "evt",
        "AIS EVENT\\ngap | encounter | loitering",
        fillcolor="#ECEFF1", shape="box",
    )

    dot.node(
        "base_calc",
        "duration^0.75\\n"
        "x event_weight  x  flag_risk\\n"
        "x shore_factor  x  mpa_tier\\n"
        "x event-specific factors",
        fillcolor="#E3F2FD",
    )

    dot.node(
        "base_snap",
        "base_risk_score",
        fillcolor="#BBDEFB", fontcolor="#0D47A1",
    )

    # Lookup multipliers as a single compact node
    dot.node(
        "lookups",
        "LOOKUP MULTIPLIERS\\n"
        "IUU  (GFCM 3.0x / other 2.0x)\\n"
        "ICCAT  (carrier 1.4x / BFT 1.3x / SWO 1.2x)\\n"
        "OFAC  (2.5x)",
        fillcolor="#FFF3E0", color="#E65100",
    )

    dot.node(
        "evt_score",
        "risk_score  (per event)\\n"
        "= base  x  IUU  x  ICCAT  x  OFAC",
        fillcolor="#FFE0B2", color="#E65100",
    )

    dot.edge("evt", "base_calc")
    dot.edge("base_calc", "base_snap")
    dot.edge("base_snap", "lookups")
    dot.edge("lookups", "evt_score")

    # ── LANE 2: Vessel-level aggregation ─────────────────────────────
    dot.node(
        "agg",
        "SUM per vessel",
        fillcolor="#E8F5E9",
    )

    dot.node(
        "totals",
        "risk_score_total          base_score_total\\n"
        "compound_multiplier = total / base",
        fillcolor="#C8E6C9", color="#2E7D32",
    )

    dot.node(
        "band",
        "RISK BAND\\n"
        "Low <50 | Emerging 50-59 | Elevated 60-79\\n"
        "Severe 80-99 | Critical >=100",
        fillcolor="#A5D6A7", color="#1B5E20", fontcolor="#1B5E20",
    )

    dot.edge("evt_score", "agg")
    dot.edge("base_snap", "agg", style="dashed", color="#90A4AE",
             label="  base preserved")
    dot.edge("agg", "totals")
    dot.edge("totals", "band")

    # ── LANE 3: Display-only vessel flags (dashed, right side) ───────
    with dot.subgraph(name="cluster_flags") as flags:
        flags.attr(
            label="DISPLAY-ONLY FLAGS\n(not in score)",
            style="dashed", color="#9E9E9E",
            fontname="Helvetica", fontsize="10", fontcolor="#616161",
        )
        flags.node("f1", "industrial\n>=24m or >=100 GT",
                    fillcolor="#F5F5F5", color="#BDBDBD", fontsize="10")
        flags.node("f2", "multi_behaviour\n>=2 event types",
                    fillcolor="#F5F5F5", color="#BDBDBD", fontsize="10")
        flags.node("f3", "dark_port_call\nloitering <10 km shore",
                    fillcolor="#F5F5F5", color="#BDBDBD", fontsize="10")
        flags.node("f4", "repeat_offender\n>=2 events in 90 days",
                    fillcolor="#F5F5F5", color="#BDBDBD", fontsize="10")

    # Invisible edges to align flags beside the main column
    dot.edge("evt", "f1", style="invis")

    # ── Convergence: Ranking table ───────────────────────────────────
    dot.node(
        "ranking",
        "RANKING TABLE\\n"
        "score triplet + flags + listings + vessel identity",
        fillcolor="#E3F2FD", color="#1565C0", fontcolor="#0D47A1",
        shape="box",
    )

    dot.edge("band", "ranking")
    dot.edge("f4", "ranking", style="dashed", color="#9E9E9E")

    return dot
