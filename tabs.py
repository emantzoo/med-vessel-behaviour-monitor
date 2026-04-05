"""Render functions for all analytical tabs (1-11). Tab 12 (AI Analyst) is in ai_analyst.py."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import EVENT_COLORS, SPECIES_NAMES
from risk_model import get_fdi_context


def render_daily_trend(df):
    st.subheader("Daily Behavioral Risk Trend")
    if df.empty:
        st.info("No data.")
        return
    daily = df.groupby("date")["risk_score"].sum().reset_index()
    fig = px.line(daily, x="date", y="risk_score", markers=True,
                  title="Total risk score by day")
    st.plotly_chart(fig)


def render_flag_breakdown(df):
    st.subheader("Breakdown by Flag State")
    if df.empty:
        st.info("No data.")
        return
    flag_risk = (df.groupby("flag")["risk_score"].sum()
                 .reset_index().sort_values("risk_score", ascending=False))
    fig = px.bar(flag_risk, x="risk_score", y="flag", orientation="h",
                 title="Total risk by flag (sorted)")
    st.plotly_chart(fig)


def render_event_types(df):
    st.subheader("Breakdown by Event Type")
    if df.empty:
        st.info("No data.")
        return
    type_risk = df.groupby("event_type")["risk_score"].sum().reset_index()
    fig = px.pie(type_risk, names="event_type", values="risk_score",
                 color="event_type", color_discrete_map=EVENT_COLORS,
                 title="Risk contribution by event type")
    st.plotly_chart(fig)


def render_duration_analysis(df):
    st.subheader("Event Duration Distribution")
    if df.empty:
        st.info("No data.")
        return
    fig = px.histogram(
        df, x="duration_h", color="event_type", nbins=25,
        barmode="overlay", opacity=0.7,
        color_discrete_map=EVENT_COLORS,
        labels={"duration_h": "Duration (hours)", "event_type": "Event Type"},
        title="Event Duration Distribution",
    )
    fig.update_layout(bargap=0.05)
    st.plotly_chart(fig)
    st.markdown("**Why it matters:** Long gaps (>24h) suggest deliberate AIS disabling. "
                "Encounters over 8h point to transshipment. Short loitering may be staging.")


def render_geographic_risk(df):
    st.subheader("Geographic Risk Analysis")
    if df.empty:
        st.info("No data.")
        return

    fig = px.scatter(
        df, x="lon", y="lat", size="risk_score", color="event_type",
        color_discrete_map=EVENT_COLORS,
        hover_data=["mmsi", "flag", "duration_h", "risk_score",
                    "vessel_name"] if "vessel_name" in df.columns else ["mmsi", "flag"],
        size_max=25,
        title="Risk-Weighted Event Map (bubble size = risk score)",
        labels={"lon": "Longitude", "lat": "Latitude"},
    )
    st.plotly_chart(fig)

    if "med_zone" in df.columns:
        st.subheader("Risk by Mediterranean Sub-Region")
        zone_risk = (
            df.groupby("med_zone")
            .agg(total_risk=("risk_score", "sum"), events=("mmsi", "count"))
            .reset_index().sort_values("total_risk", ascending=True)
        )
        fig2 = px.bar(
            zone_risk, x="total_risk", y="med_zone", orientation="h",
            color="events", color_continuous_scale="Blues",
            title="Risk by Mediterranean Sub-Region",
            labels={"total_risk": "Total Risk Score", "med_zone": "Region", "events": "Events"},
        )
        st.plotly_chart(fig2)

    if "eez" in df.columns and df["eez"].notna().any():
        st.subheader("Risk by Exclusive Economic Zone")
        eez_risk = (
            df.groupby("eez")
            .agg(total_risk=("risk_score", "sum"), events=("mmsi", "count"))
            .reset_index().sort_values("total_risk", ascending=False)
        )
        fig3 = px.bar(eez_risk, x="total_risk", y="eez", orientation="h",
                      title="Risk by EEZ",
                      labels={"eez": "EEZ", "total_risk": "Total Risk"})
        st.plotly_chart(fig3)

    if "nearest_port" in df.columns and df["nearest_port"].notna().any():
        st.subheader("Risk by Nearest Port")
        port_events = (
            df.groupby("nearest_port")
            .agg(total_risk=("risk_score", "sum"), events=("mmsi", "count"),
                 avg_distance=("distance_from_port_km", "mean"))
            .reset_index().sort_values("total_risk", ascending=False)
        )
        fig4 = px.scatter(
            port_events, x="avg_distance", y="total_risk", size="events",
            text="nearest_port",
            title="Risk by Nearest Port -- Farther from Port = More Suspicious",
            labels={"avg_distance": "Avg Distance from Port (km)", "total_risk": "Total Risk Score"},
        )
        fig4.update_traces(textposition="top center")
        st.plotly_chart(fig4)


def render_risk_heatmap(df):
    st.subheader("Risk Heatmap: Flag State vs Event Type")
    if df.empty:
        st.info("No data.")
        return
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
    st.plotly_chart(fig)
    st.markdown("**Interpretation:** bright cells = high risk combinations. "
                "Look for Russian/Iranian flags with high GAP or ENCOUNTER scores.")


def render_repeat_offenders(df):
    st.subheader("Repeat Offenders -- Vessels with Multiple Events")
    if df.empty:
        st.info("No data.")
        return
    vessel_counts = (
        df.groupby(["mmsi", "flag"])
        .agg(
            event_count=("event_type", "count"),
            total_risk=("risk_score", "sum"),
            event_types=("event_type", lambda x: ", ".join(sorted(set(x)))),
            avg_duration=("duration_h", "mean"),
        )
        .reset_index().sort_values("event_count", ascending=False)
    )
    if "vessel_name" in df.columns:
        name_map = df.dropna(subset=["vessel_name"]).drop_duplicates("mmsi").set_index("mmsi")["vessel_name"]
        vessel_counts["vessel_name"] = vessel_counts["mmsi"].map(name_map).fillna("")

    repeat_vessels = vessel_counts[vessel_counts["event_count"] >= 2]
    if not repeat_vessels.empty:
        fig = px.bar(
            repeat_vessels.head(15), x="mmsi", y="event_count",
            color="total_risk", color_continuous_scale="YlOrRd",
            hover_data=["flag", "event_types", "avg_duration", "total_risk"],
            title="Repeat Offenders -- Vessels with Multiple Events",
            labels={"event_count": "Number of Events", "mmsi": "MMSI"},
        )
        fig.update_xaxes(type="category")
        st.plotly_chart(fig)
        st.dataframe(repeat_vessels.head(15).style.format(
            {"total_risk": "{:.1f}", "avg_duration": "{:.1f}"}))
    else:
        st.info("No vessels with multiple events in filtered data.")

    st.markdown("**Why it matters:** A vessel with 5 events is far more interesting "
                "than 5 vessels with 1 event each. Repeat offenders warrant deeper investigation.")


def render_gap_behaviour(df):
    st.subheader("Gap Behaviour Analysis")
    gap_df = df[df["event_type"] == "GAP"].copy()

    if not gap_df.empty and "speed_before_gap" in gap_df.columns and gap_df["speed_before_gap"].notna().any():
        fig = px.scatter(
            gap_df, x="speed_before_gap", y="speed_after_gap",
            size="duration_h", color="flag",
            hover_data=["mmsi", "duration_h",
                        "gap_distance_km"] + (["vessel_name"] if "vessel_name" in gap_df.columns else []),
            title="Gap Behaviour: Speed Before vs After AIS Disabling",
            labels={"speed_before_gap": "Speed Before Gap (kn)", "speed_after_gap": "Speed After Gap (kn)"},
        )
        fig.add_annotation(x=12, y=1, text="Stopped after gap<br>(possible transfer)",
                           showarrow=False, font=dict(size=10, color="red"))
        fig.add_annotation(x=1, y=12, text="Accelerated after gap<br>(possible evasion)",
                           showarrow=False, font=dict(size=10, color="orange"))
        st.plotly_chart(fig)

        if "gap_distance_km" in gap_df.columns and gap_df["gap_distance_km"].notna().any():
            fig2 = px.scatter(
                gap_df, x="duration_h", y="gap_distance_km", color="flag",
                hover_data=["mmsi"] + (["vessel_name"] if "vessel_name" in gap_df.columns else []),
                title="Gap Duration vs Distance Traveled During Gap",
                labels={"duration_h": "Gap Duration (hours)", "gap_distance_km": "Distance During Gap (km)"},
            )
            st.plotly_chart(fig2)

        st.markdown("**Interpretation:** A vessel going fast, then going dark, then "
                    "reappearing slow suggests a mid-sea transfer. "
                    "Long gaps covering large distances indicate intentional evasion.")
    elif not gap_df.empty:
        st.info("Gap speed data not available. Use live API for detailed gap behaviour.")
        fig = px.histogram(gap_df, x="duration_h", nbins=15, color="flag",
                           title="Gap Duration Distribution",
                           labels={"duration_h": "Duration (hours)"})
        st.plotly_chart(fig)
    else:
        st.info("No gap events in filtered data.")


def render_encounter_analysis(df):
    st.subheader("Encounter Analysis")
    enc_df = df[df["event_type"] == "ENCOUNTER"].copy()

    if not enc_df.empty and "encounter_median_distance_km" in enc_df.columns:
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
        st.plotly_chart(fig)

        if "encounter_vessel_flag" in enc_df.columns and enc_df["encounter_vessel_flag"].notna().any():
            st.subheader("Encounter Partner Flag Analysis")
            partner_flags = (enc_df.groupby(["flag", "encounter_vessel_flag"])
                             .agg(encounters=("mmsi", "count"), total_risk=("risk_score", "sum"))
                             .reset_index().sort_values("total_risk", ascending=False))
            partner_flags.columns = ["Vessel Flag", "Partner Flag", "Encounters", "Total Risk"]
            st.dataframe(partner_flags.style.format({"Total Risk": "{:.1f}"}))

        st.markdown("**Why it matters:** Two vessels within 100m for 8 hours is almost certainly "
                    "a transshipment. Look for high-risk flag combinations (e.g. RUS + PAN).")
    elif not enc_df.empty:
        st.info("Encounter distance data not available. Use live API for detailed encounter analysis.")
        cols = ["mmsi", "flag", "duration_h", "risk_score"]
        if "vessel_name" in enc_df.columns:
            cols = ["vessel_name"] + cols
        st.dataframe(enc_df[cols].sort_values("risk_score", ascending=False))
    else:
        st.info("No encounter events in filtered data.")


def render_top_vessels(df):
    st.subheader("Top 10 Riskiest Vessels")
    if df.empty:
        st.info("No data.")
        return
    group_cols = ["mmsi", "flag"]
    if "vessel_name" in df.columns:
        group_cols.append("vessel_name")
    if "vessel_type" in df.columns:
        group_cols.append("vessel_type")

    vessel_risk = (df.groupby(group_cols)
                   .agg(risk=("risk_score", "sum"), events=("mmsi", "count"))
                   .reset_index().sort_values("risk", ascending=False).head(10))
    st.dataframe(vessel_risk.style.format({"risk": "{:.1f}"}))

    if "vessel_type" in df.columns and df["vessel_type"].notna().any():
        st.subheader("Risk by Vessel Type")
        type_risk = (
            df.groupby("vessel_type")
            .agg(total_risk=("risk_score", "sum"), events=("mmsi", "count"))
            .reset_index().sort_values("total_risk", ascending=False)
        )
        fig = px.bar(type_risk, x="vessel_type", y="total_risk",
                     color="events", color_continuous_scale="Viridis",
                     title="Risk by Vessel Type",
                     labels={"vessel_type": "Vessel Type", "total_risk": "Total Risk"})
        st.plotly_chart(fig)


def render_fisheries_context(df, fdi_effort, fdi_landings):
    st.subheader("Fisheries Context -- EU FDI Baseline")
    st.markdown(
        "Overlaying GFW behavioural events with EU Fisheries Dependent Information (FDI) "
        "spatial data to assess whether events occur in known fishing grounds."
    )

    if fdi_effort.empty:
        st.warning("FDI data not available. Run `python data/prepare_fdi.py` to generate.")
        return
    if df.empty:
        st.info("No GFW events match the selected filters.")
        return

    # Section A: C-Square Effort Comparison Map
    st.subheader("A. Fishing Effort vs GFW Events")
    latest_year = fdi_effort["year"].max()
    eff_agg = (fdi_effort[fdi_effort["year"] == latest_year]
               .groupby(["centre_lon", "centre_lat"])["totfishdays"]
               .sum().reset_index())

    fig_a = go.Figure()
    fig_a.add_trace(go.Scatter(
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
            fig_a.add_trace(go.Scatter(
                x=sub["lon"], y=sub["lat"],
                mode="markers",
                marker=dict(size=10, color=color, line=dict(width=1, color="white")),
                name=etype,
                hovertemplate="Lon: %{x:.2f}<br>Lat: %{y:.2f}<extra>" + etype + "</extra>",
            ))
    fig_a.update_layout(
        title=f"FDI Fishing Effort ({latest_year}) vs GFW Events",
        xaxis_title="Longitude", yaxis_title="Latitude",
        height=550, legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    st.plotly_chart(fig_a)

    # Section B: Event Context Table
    st.subheader("B. Event Context -- Known Fishing Ground?")
    context_rows = []
    for _, row in df.iterrows():
        ctx = get_fdi_context(row["csq_lon"], row["csq_lat"], fdi_effort, fdi_landings)
        if ctx is None:
            flag_label = "No FDI data for cell"
            fd, sp, val = 0, "", 0
        else:
            fd = ctx["total_fishing_days"]
            flag_label = "Known fishing ground" if ctx["is_known_fishing_ground"] else "Outside known fishing ground"
            sp = ", ".join(SPECIES_NAMES.get(s[0], s[0]) for s in ctx["top_species"][:3])
            val = ctx["total_landings_value"]

        context_rows.append({
            "event_type": row["event_type"], "flag": row["flag"],
            "vessel_name": row.get("vessel_name", ""),
            "duration_h": row["duration_h"], "risk_score": row["risk_score"],
            "fishing_days": fd, "top_species": sp,
            "landings_value_eur": val, "context": flag_label,
        })

    ctx_df = pd.DataFrame(context_rows)
    ctx_counts = ctx_df["context"].value_counts()
    cols_b = st.columns(3)
    for i, (label, count) in enumerate(ctx_counts.items()):
        if i < 3:
            cols_b[i].metric(label, count)

    st.dataframe(
        ctx_df.sort_values("risk_score", ascending=False).style.format({
            "risk_score": "{:.1f}", "fishing_days": "{:,.0f}",
            "landings_value_eur": "EUR {:,.0f}", "duration_h": "{:.1f}",
        }),
        use_container_width=True,
    )
    st.markdown(
        "**Interpretation:** Events *outside* known fishing grounds or in cells "
        "with *no FDI data* are potentially more suspicious -- they may indicate "
        "unreported activity or dark fleet operations."
    )

    # Section C: Seasonal Pattern Analysis
    st.subheader("C. Seasonal Patterns -- FDI Effort vs GFW Events")
    if "quarter" in fdi_effort.columns:
        fdi_q = (fdi_effort[fdi_effort["year"] == latest_year]
                 .groupby(["med_zone", "quarter", "gear_type"])["totfishdays"]
                 .sum().reset_index())
        fdi_q_zone = fdi_q.groupby(["med_zone", "quarter"])["totfishdays"].sum().reset_index()

        df_q = df.copy()
        df_q["quarter"] = pd.to_datetime(df_q["date"]).dt.quarter

        zone_sel = st.selectbox(
            "Select Mediterranean zone",
            sorted(df["med_zone"].unique()),
            key="fdi_zone_sel",
        )

        fdi_zone = fdi_q_zone[fdi_q_zone["med_zone"] == zone_sel]
        gfw_zone = df_q[df_q["med_zone"] == zone_sel].groupby("quarter").size().reset_index(name="gfw_events")

        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(
            x=fdi_zone["quarter"], y=fdi_zone["totfishdays"],
            name="FDI Fishing Days", marker_color="steelblue", opacity=0.7,
        ))
        fig_c.add_trace(go.Scatter(
            x=gfw_zone["quarter"], y=gfw_zone["gfw_events"],
            name="GFW Events", mode="lines+markers",
            marker=dict(color="red", size=10), yaxis="y2",
        ))
        fig_c.update_layout(
            title=f"Seasonal Pattern: {zone_sel}",
            xaxis=dict(title="Quarter", dtick=1),
            yaxis=dict(title="FDI Fishing Days", side="left"),
            yaxis2=dict(title="GFW Events", side="right", overlaying="y"),
            height=400,
        )
        st.plotly_chart(fig_c)

    # Section D: Species Context
    st.subheader("D. Species in Event Locations")
    st.markdown(
        "What species are reported in c-squares where GFW events occur? "
        "High-value species (BFT, SWO, HKE) increase transshipment risk."
    )
    if not fdi_landings.empty and "csq_lon" in df.columns:
        event_cells = df[["csq_lon", "csq_lat"]].drop_duplicates()
        event_land = event_cells.merge(
            fdi_landings, left_on=["csq_lon", "csq_lat"],
            right_on=["rectangle_lon", "rectangle_lat"], how="inner",
        )
        if not event_land.empty:
            sp_agg = (event_land.groupby("species")
                      .agg(total_tonnes=("totwghtlandg", "sum"),
                           total_value=("totvallandg", "sum"))
                      .sort_values("total_value", ascending=True).tail(15))
            sp_agg["species_name"] = sp_agg.index.map(
                lambda x: f"{x} ({SPECIES_NAMES.get(x, '?')})"
            )
            fig_d = px.bar(
                sp_agg.reset_index(), x="total_value", y="species_name",
                orientation="h",
                title="Top Species by Landings Value in GFW Event Cells",
                labels={"total_value": "Total Landings Value (EUR)", "species_name": "Species"},
                color="total_tonnes", color_continuous_scale="YlOrRd",
            )
            fig_d.update_layout(coloraxis_colorbar_title="Tonnes")
            st.plotly_chart(fig_d)
        else:
            st.info("No FDI landings data matches GFW event c-squares.")
    else:
        st.info("FDI landings data not available.")
