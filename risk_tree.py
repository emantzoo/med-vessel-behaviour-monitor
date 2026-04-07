"""Render the Med IUU Risk Tree framework as a graphviz diagram."""

import yaml
import graphviz
import os


def load_framework(path=None):
    """Load the risk tree framework YAML."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "data", "risk_tree_framework.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["framework"]


def render_framework_tree():
    """Render the static framework as a graphviz diagram."""
    framework = load_framework()

    dot = graphviz.Digraph(
        "iuu_risk_tree",
        graph_attr={
            "rankdir": "TB",
            "fontname": "Helvetica",
            "fontsize": "12",
            "bgcolor": "white",
            "splines": "ortho",
            "nodesep": "0.4",
            "ranksep": "0.6",
        },
        node_attr={
            "fontname": "Helvetica",
            "fontsize": "10",
            "shape": "box",
            "style": "rounded,filled",
        },
        edge_attr={
            "fontname": "Helvetica",
            "fontsize": "9",
        },
    )

    # Root node
    dot.node(
        "root",
        f"{framework['name']}\nVessel under assessment",
        fillcolor="#1f77b4",
        fontcolor="white",
        fontsize="14",
    )

    # Branch nodes
    for branch in framework["branches"]:
        branch_id = branch["id"]
        if branch["type"] == "gate":
            branch_color = "#FF6B6B"
        elif branch["type"] == "contextual":
            branch_color = "#9B59B6"
        else:
            branch_color = "#4ECDC4"

        dot.node(
            branch_id,
            f"{branch['name']}\n[{branch['type'].upper()}]",
            fillcolor=branch_color,
            fontcolor="white",
        )
        dot.edge("root", branch_id)

        # Question sub-nodes
        for q in branch.get("questions", []):
            q_id = f"{branch_id}_{q['id']}"
            q_text = q["text"]
            # Wrap long text
            if len(q_text) > 50:
                q_text = q_text[:50] + "..."

            dot.node(
                q_id,
                q_text,
                fillcolor="#F0F0F0",
                fontcolor="black",
                fontsize="9",
            )
            dot.edge(branch_id, q_id)

    # Tier outcome nodes (rendered as a separate cluster at the bottom)
    with dot.subgraph(name="cluster_tiers") as tiers:
        tiers.attr(label="Tier Outcomes", style="dashed", color="gray")
        for tier in framework["tier_outcomes"]:
            tiers.node(
                f"tier_{tier['tier'].lower()}",
                tier["tier"],
                fillcolor=tier["color"],
                fontcolor="white",
                shape="ellipse",
                fontsize="11",
            )

    return dot
