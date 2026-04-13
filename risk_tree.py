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

    dot = graphviz.Digraph(
        "iuu_risk_tree",
        graph_attr={
            "rankdir": "LR",
            "fontname": "Helvetica",
            "fontsize": "12",
            "bgcolor": "white",
            "splines": "polyline",
            "nodesep": "0.3",
            "ranksep": "1.0",
        },
        node_attr={
            "fontname": "Helvetica",
            "fontsize": "9",
            "shape": "box",
            "style": "rounded,filled",
            "width": "3.0",
            "height": "0.6",
            "margin": "0.12,0.08",
        },
        edge_attr={
            "fontname": "Helvetica",
            "fontsize": "8",
        },
    )

    # Build trace lookup
    trace_lookup = {}
    if trace:
        for entry in trace:
            trace_lookup[entry["question_id"]] = entry

    # Root node
    _framework_name_wrapped = _wrap(framework["name"], width=28)
    if vessel_label:
        root_label = f"{_framework_name_wrapped}\n{_wrap(vessel_label, width=28)}"
    else:
        root_label = f"{_framework_name_wrapped}\nVessel under assessment"

    dot.node(
        "root",
        root_label,
        fillcolor="#1f77b4",
        fontcolor="white",
        fontsize="14",
    )

    # Branch nodes
    for branch in framework["branches"]:
        branch_id = branch["id"]

        # Check if any question in this branch fired a rule
        branch_fired = False
        if trace:
            for q in branch.get("questions", []):
                entry = trace_lookup.get(q["id"])
                if entry and entry.get("rule_fired"):
                    branch_fired = True
                    break

        # Branch colour: deepens when a rule fired
        if branch["type"] == "gate":
            branch_color = "#C62828" if branch_fired else "#FF6B6B"
        elif branch["type"] == "contextual":
            branch_color = "#6A1B9A" if branch_fired else "#9B59B6"
        else:
            branch_color = "#00897B" if branch_fired else "#4ECDC4"

        dot.node(
            branch_id,
            f"{_wrap(branch['name'], width=24)}\n[{branch['type'].upper()}]",
            fillcolor=branch_color,
            fontcolor="white",
        )
        dot.edge("root", branch_id)

        # Question sub-nodes
        for q in branch.get("questions", []):
            q_id = f"{branch_id}_{q['id']}"
            # Word-wrap the full question text so nothing is truncated
            q_text = _wrap(q["text"], width=38)

            # Colour from trace if available
            if trace:
                entry = trace_lookup.get(q["id"])
                if entry:
                    severity = entry.get("severity", "none")
                    fill = _SEVERITY_FILL.get(severity, "#F0F0F0")
                    fontcolor = _SEVERITY_TEXT.get(severity, "black")
                    answer = entry.get("answer", "unknown")
                    q_text = f"{q_text}\n[{answer.upper()}]"
                else:
                    fill = "#F0F0F0"
                    fontcolor = "black"
            else:
                fill = "#F0F0F0"
                fontcolor = "black"

            dot.node(
                q_id,
                q_text,
                fillcolor=fill,
                fontcolor=fontcolor,
                fontsize="9",
            )
            dot.edge(branch_id, q_id)

    # Tier outcome nodes
    with dot.subgraph(name="cluster_tiers") as tiers:
        tiers.attr(label="Tier Outcomes", style="dashed", color="gray")
        for t in framework["tier_outcomes"]:
            tier_name = t["tier"]
            # Mute non-assigned tiers when a specific tier is highlighted
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
                f"tier_{tier_name.lower()}",
                tier_name,
                fillcolor=fillcolor,
                fontcolor=fontcolor,
                shape="ellipse",
                fontsize="11",
                penwidth=penwidth,
            )

    return dot


def render_scoring_pipeline_diagram():
    """Render the end-to-end scoring pipeline as a graphviz flowchart.

    Mirrors the mental model a reviewer needs to audit the risk score:
    one AIS event -> base behavioural score -> compounding multipliers ->
    per-event score -> vessel-level aggregation -> risk band. A separate
    dashed side-chain shows the four vessel-level Kpler-aligned flags
    (industrial profile, multi-behaviour, dark port call candidate,
    repeat offender) which are computed independently and fed to the
    Vessel Summary as display-only signals (never multiplied into the
    score). Industrial profile is the only structural flag of the four;
    the other three are temporal/compound.
    """
    dot = graphviz.Digraph(
        "scoring_pipeline",
        graph_attr={
            "rankdir": "TB",
            "fontname": "Helvetica",
            "fontsize": "13",
            "bgcolor": "white",
            "splines": "ortho",
            "nodesep": "0.4",
            "ranksep": "0.5",
        },
        node_attr={
            "fontname": "Helvetica",
            "fontsize": "11",
            "shape": "box",
            "style": "rounded,filled",
            "fillcolor": "white",
            "color": "#555",
            "margin": "0.15,0.1",
        },
        edge_attr={
            "fontname": "Helvetica",
            "fontsize": "9",
            "color": "#555",
        },
    )

    # --- Main pipeline (per-event scoring) ---
    dot.node(
        "A",
        "AIS Event\\n(gap / encounter / loitering)",
        fillcolor="#ECEFF1",
    )
    dot.node(
        "B",
        "Base Behavioural Score\\n"
        "duration^0.75 x event_weight\\n"
        "x flag x shore x mpa_tier x event_factors",
        fillcolor="#E8F4F8",
    )
    dot.node(
        "C",
        "base_risk_score\\n(snapshot)",
        fillcolor="#FFFFFF",
    )
    dot.node(
        "D",
        "x IUU multiplier\\nGFCM 3.0x / other 2.0x",
        fillcolor="#FFF4E6",
    )
    dot.node(
        "E",
        "x ICCAT multiplier\\ncarrier 1.4x / BFT 1.3x / SWO-ALB 1.2x",
        fillcolor="#FFF4E6",
    )
    dot.node(
        "F",
        "x OFAC multiplier\\n2.5x",
        fillcolor="#FFF4E6",
    )
    dot.node(
        "G",
        "risk_score\\n(per event)",
        fillcolor="#FFF4E6",
    )

    dot.edge("A", "B")
    dot.edge("B", "C", label="snapshot")
    dot.edge("B", "D")
    dot.edge("D", "E")
    dot.edge("E", "F")
    dot.edge("F", "G")

    # --- Vessel-level aggregation ---
    dot.node(
        "H",
        "Sum events per vessel",
        fillcolor="#FFFFFF",
    )
    dot.node(
        "I",
        "Sum base per vessel",
        fillcolor="#FFFFFF",
    )
    dot.node(
        "J",
        "risk_score_total",
        fillcolor="#E8F8E8",
    )
    dot.node(
        "K",
        "base_score_total",
        fillcolor="#E8F8E8",
    )
    dot.node(
        "L",
        "compound_multiplier\\n= risk_score_total / base_score_total",
        fillcolor="#E8F8E8",
    )
    dot.node(
        "M",
        "risk_band\\nLow / Emerging / Elevated / Severe / Critical",
        fillcolor="#F8E8E8",
    )

    dot.edge("G", "H")
    dot.edge("C", "I")
    dot.edge("H", "J")
    dot.edge("I", "K")
    dot.edge("J", "L")
    dot.edge("K", "L")
    dot.edge("J", "M")

    # --- Vessel-level flags (computed separately, dashed to show they
    # do not multiply into the risk score) ---
    dot.node(
        "N",
        "Vessel-level flags\\n(computed separately)",
        fillcolor="#F0F0F0",
    )
    dot.node("N1", "is_industrial\\n(>=24m or >=100GT)", fillcolor="#FAFAFA")
    dot.node("O", "multi_behaviour_flag", fillcolor="#FAFAFA")
    dot.node("P", "dark_port_call_candidate", fillcolor="#FAFAFA")
    dot.node("Q", "repeat_offender_90d", fillcolor="#FAFAFA")
    dot.node(
        "R",
        "Display-only:\\nVessel Summary + Investigation badges\\n+ risk tree rules",
        fillcolor="#F0F0F0",
    )

    dot.edge("N", "N1", style="dashed")
    dot.edge("N", "O", style="dashed")
    dot.edge("N", "P", style="dashed")
    dot.edge("N", "Q", style="dashed")
    dot.edge("N1", "R", style="dashed")
    dot.edge("O", "R", style="dashed")
    dot.edge("P", "R", style="dashed")
    dot.edge("Q", "R", style="dashed")

    # --- Final convergence into the Vessel Summary subtab ---
    dot.node(
        "S",
        "Vessel Summary subtab",
        fillcolor="#E3F2FD",
        fontsize="12",
    )
    dot.edge("M", "S")
    dot.edge("L", "S")
    dot.edge("R", "S")

    return dot
