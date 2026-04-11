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
