"""Render functions for all analytical tabs (1-11). Tab 12 (AI Analyst) is in ai_analyst.py."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from pathlib import Path

from config import (
    EVENT_COLORS,
    FLAG_RISKS,
    ICCAT_MULTIPLIERS,
    IUU_MULTIPLIERS,
    OFAC_MULTIPLIER,
    RISK_BAND_COLORS,
    RISK_BANDS,
    SPECIES_NAMES,
    classify_risk_band,
)
from risk_model import get_fdi_context


def render_daily_trend(df):
    st.subheader("Daily Behavioral Risk Trend")
    if df.empty:
        st.info("No data.")
        return
    daily = df.groupby("date")["risk_score"].sum().reset_index()
    fig = px.line(daily, x="date", y="risk_score", markers=True,
                  title="Total risk score by day")

    # Mark IUU event dates
    if "iuu_matched" in df.columns:
        iuu_dates = df[df["iuu_matched"] == True]["date"].unique()
        for d in iuu_dates:
            d_str = str(d)
            fig.add_shape(type="line", x0=d_str, x1=d_str, y0=0, y1=1,
                          yref="paper", line=dict(dash="dash", color="black", width=1))
            fig.add_annotation(x=d_str, y=1, yref="paper", text="IUU",
                               showarrow=False, font=dict(color="black", size=10))

    st.plotly_chart(fig)

    # Stacked area by event type
    daily_by_type = df.groupby(["date", "event_type"])["risk_score"].sum().reset_index()
    fig2 = px.area(daily_by_type, x="date", y="risk_score", color="event_type",
                   color_discrete_map=EVENT_COLORS,
                   title="Daily Risk by Event Type")
    st.plotly_chart(fig2)

    # Monthly multi-behaviour event counts (Kpler Graph 4 analogue)
    df_m = df.copy()
    df_m["date"] = pd.to_datetime(df_m["date"], errors="coerce")
    df_m = df_m.dropna(subset=["date"])
    if not df_m.empty:
        monthly = (df_m.set_index("date")
                   .groupby("event_type")
                   .resample("MS")
                   .size()
                   .reset_index(name="events"))
        fig3 = px.line(
            monthly, x="date", y="events", color="event_type",
            color_discrete_map=EVENT_COLORS, markers=True,
            title="Monthly Event Counts by Behaviour Type",
            labels={"date": "Month", "events": "Event count", "event_type": "Behaviour"},
        )
        st.plotly_chart(fig3)
        st.caption(
            "Same analytic frame as Kpler's \"Turning Tides\" whitepaper Graph 4 "
            "(monthly deceptive behaviour trends), applied here to Mediterranean GFW "
            "event types over the selected date range."
        )


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

    # Stacked bar by event type
    flag_type = (df.groupby(["flag", "event_type"])["risk_score"].sum()
                 .reset_index().sort_values("risk_score", ascending=False))
    fig2 = px.bar(flag_type, x="risk_score", y="flag", color="event_type",
                  orientation="h", color_discrete_map=EVENT_COLORS,
                  title="Risk by Flag State and Event Type")
    st.plotly_chart(fig2)

    # IUU/ICCAT/OFAC summary by flag
    n_summary_cols = 2 + (1 if "ofac_sanctioned" in df.columns else 0)
    cols = st.columns(n_summary_cols)
    col_idx = 0
    if "iuu_matched" in df.columns:
        iuu_by_flag = df[df["iuu_matched"] == True].groupby("flag")["mmsi"].nunique()
        if not iuu_by_flag.empty:
            with cols[col_idx]:
                st.markdown("**IUU-listed vessels by flag:**")
                st.dataframe(iuu_by_flag.reset_index().rename(
                    columns={"mmsi": "IUU Vessels", "flag": "Flag"}))
        col_idx += 1
    if "iccat_authorized" in df.columns:
        iccat_by_flag = df[df["iccat_authorized"] == True].groupby("flag")["mmsi"].nunique()
        if not iccat_by_flag.empty:
            with cols[col_idx]:
                st.markdown("**ICCAT-authorized vessels by flag:**")
                st.dataframe(iccat_by_flag.reset_index().rename(
                    columns={"mmsi": "ICCAT Vessels", "flag": "Flag"}))
        col_idx += 1
    if "ofac_sanctioned" in df.columns:
        ofac_by_flag = df[df["ofac_sanctioned"] == True].groupby("flag")["mmsi"].nunique()
        if not ofac_by_flag.empty:
            with cols[col_idx]:
                st.markdown("**OFAC-sanctioned vessels by flag:**")
                st.dataframe(ofac_by_flag.reset_index().rename(
                    columns={"mmsi": "OFAC Vessels", "flag": "Flag"}))


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

    # Summary table
    summary = df.groupby("event_type").agg(
        events=("mmsi", "count"),
        avg_duration=("duration_h", "mean"),
        avg_risk=("risk_score", "mean"),
        total_risk=("risk_score", "sum"),
    ).reset_index()
    if "iuu_matched" in df.columns:
        iuu_counts = df[df["iuu_matched"] == True].groupby("event_type")["mmsi"].count()
        summary["iuu_matches"] = summary["event_type"].map(iuu_counts).fillna(0).astype(int)
    if "iccat_authorized" in df.columns:
        iccat_counts = df[df["iccat_authorized"] == True].groupby("event_type")["mmsi"].count()
        summary["iccat_authorized"] = summary["event_type"].map(iccat_counts).fillna(0).astype(int)
    st.dataframe(summary.style.format({
        "avg_duration": "{:.1f}h", "avg_risk": "{:.1f}", "total_risk": "{:.0f}"
    }))

    # Band distribution (Kpler R&C "Turning Tides" vocabulary)
    if "risk_band" in df.columns:
        st.markdown("**Event distribution by risk band:**")
        band_order = ["Low", "Emerging", "Elevated", "Severe", "Critical"]
        band_counts = (df["risk_band"].value_counts()
                       .reindex(band_order, fill_value=0).reset_index())
        band_counts.columns = ["risk_band", "events"]
        band_styled = band_counts.style.map(
            lambda v: f"background-color: {RISK_BAND_COLORS.get(v, '')}; color: white"
            if v in RISK_BAND_COLORS else "",
            subset=["risk_band"],
        )
        st.dataframe(band_styled)


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

    # Duration vs risk scatter by flag
    hover_cols = ["vessel_name", "event_type", "mmsi"] if "vessel_name" in df.columns else ["event_type", "mmsi"]
    fig2 = px.scatter(df, x="duration_h", y="risk_score", color="flag",
                      hover_data=hover_cols,
                      title="Duration vs Risk Score by Flag",
                      labels={"duration_h": "Duration (hours)", "risk_score": "Risk Score"})
    st.plotly_chart(fig2)


def render_geographic_risk(df):
    st.subheader("Geographic Risk Analysis")
    if df.empty:
        st.info("No data.")
        return

    df_geo = df.copy()
    df_geo["marker"] = "Regular"
    if "iuu_matched" in df_geo.columns:
        df_geo.loc[df_geo["iuu_matched"] == True, "marker"] = "IUU-Listed"
    if "iccat_authorized" in df_geo.columns:
        df_geo.loc[(df_geo["iccat_authorized"] == True) & (df_geo["marker"] == "Regular"), "marker"] = "ICCAT-Authorized"

    hover_cols = ["mmsi", "flag", "duration_h", "risk_score"]
    if "vessel_name" in df_geo.columns:
        hover_cols.append("vessel_name")

    fig = px.scatter(
        df_geo, x="lon", y="lat", size="risk_score", color="event_type",
        symbol="marker",
        symbol_map={"Regular": "circle", "IUU-Listed": "diamond", "ICCAT-Authorized": "square"},
        color_discrete_map=EVENT_COLORS,
        hover_data=hover_cols,
        size_max=25,
        title="Risk-Weighted Event Map (shape: circle=regular, diamond=IUU, square=ICCAT)",
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
    # Highest risk combination insight
    if not pivot.empty:
        max_flag = pivot.max(axis=1).idxmax()
        max_type = pivot.loc[max_flag].idxmax()
        max_val = pivot.loc[max_flag, max_type]
        st.markdown(f"**Highest risk combination:** {max_flag} + {max_type} = {max_val:.1f} risk score")

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

    # Add IUU info if available
    if "iuu_matched" in df.columns:
        iuu_map = (df[df["iuu_matched"] == True]
                   .drop_duplicates("mmsi").set_index("mmsi")[["iuu_listing_rfmos", "iuu_match_confidence"]])
        if not iuu_map.empty:
            vessel_counts["IUU Listed"] = vessel_counts["mmsi"].map(
                iuu_map["iuu_listing_rfmos"]).fillna("")
            # Sort IUU-listed vessels to top
            vessel_counts["_iuu_sort"] = vessel_counts["IUU Listed"].apply(lambda x: 0 if x else 1)
            vessel_counts = vessel_counts.sort_values(
                ["_iuu_sort", "event_count"], ascending=[True, False]).drop(columns="_iuu_sort")

    # Add ICCAT info if available
    if "iccat_authorized" in df.columns:
        iccat_map = (df[df["iccat_authorized"] == True]
                     .drop_duplicates("mmsi").set_index("mmsi")["iccat_authorizations"])
        if not iccat_map.empty:
            vessel_counts["ICCAT Authorized"] = vessel_counts["mmsi"].map(iccat_map).fillna("")

    # Add OFAC info if available
    if "ofac_sanctioned" in df.columns:
        ofac_map = (df[df["ofac_sanctioned"] == True]
                    .drop_duplicates("mmsi").set_index("mmsi")["ofac_sanctions_program"])
        if not ofac_map.empty:
            vessel_counts["OFAC Sanctioned"] = vessel_counts["mmsi"].map(ofac_map).fillna("")

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

    # Event timeline for top 3 repeat offenders
    if not repeat_vessels.empty:
        top3 = repeat_vessels.head(3)["mmsi"].tolist()
        timeline_df = df[df["mmsi"].isin(top3)].copy()
        if not timeline_df.empty:
            st.subheader("Event Timeline for Top Repeat Offenders")
            hover_cols = ["flag", "duration_h"]
            if "vessel_name" in timeline_df.columns:
                hover_cols.append("vessel_name")
            fig_tl = px.scatter(
                timeline_df, x="date", y="mmsi", color="event_type",
                size="risk_score", color_discrete_map=EVENT_COLORS,
                hover_data=hover_cols,
                title="When did the top repeat offenders act?",
                labels={"mmsi": "Vessel MMSI", "date": "Date"},
            )
            fig_tl.update_yaxes(type="category")
            st.plotly_chart(fig_tl)

    st.markdown("**Why it matters:** A vessel with 5 events is far more interesting "
                "than 5 vessels with 1 event each. Repeat offenders warrant deeper investigation.")


def render_gap_behaviour(df):
    st.subheader("Gap Behaviour Analysis")
    gap_df = df[df["event_type"] == "GAP"].copy()

    # IUU gap warning
    if not gap_df.empty and "iuu_matched" in gap_df.columns:
        iuu_gaps = gap_df[gap_df["iuu_matched"] == True]
        if not iuu_gaps.empty:
            st.warning(f"**{len(iuu_gaps)} AIS gap(s) involve IUU-listed vessels** -- "
                       "highest-priority evasion signals.")

    if not gap_df.empty and "speed_before_gap" in gap_df.columns and gap_df["speed_before_gap"].notna().any():
        # Add IUU status for marker symbols
        if "iuu_matched" in gap_df.columns:
            gap_df["status"] = gap_df["iuu_matched"].map({True: "IUU-Listed", False: "Regular"})
            symbol_col = "status"
        else:
            symbol_col = None

        fig = px.scatter(
            gap_df, x="speed_before_gap", y="speed_after_gap",
            size="duration_h", color="flag",
            symbol=symbol_col,
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

        # ICCAT carrier encounters — high-priority signal
        if "iccat_authorized" in enc_df.columns:
            iccat_carriers = enc_df[
                (enc_df["iccat_authorized"] == True)
                & (enc_df["iccat_risk_tier"] == "carrier")
            ]
            if not iccat_carriers.empty:
                st.warning(
                    f"**{len(iccat_carriers)} encounter(s) involve ICCAT-authorized carriers.** "
                    "If legitimate, these should be operating under Regional Observer Programme "
                    "coverage (Rec. 24-05). Verify observer coverage."
                )
                carrier_cols = ["vessel_name", "mmsi", "flag", "duration_h", "risk_score",
                                "encounter_vessel_name", "encounter_vessel_flag", "iccat_authorizations"]
                carrier_cols = [c for c in carrier_cols if c in iccat_carriers.columns]
                st.dataframe(iccat_carriers[carrier_cols].sort_values("risk_score", ascending=False))

        # Flag pairing analysis
        if "encounter_vessel_flag" in enc_df.columns and enc_df["encounter_vessel_flag"].notna().any():
            pair_df = enc_df.groupby(["flag", "encounter_vessel_flag"]).agg(
                count=("mmsi", "count"),
                total_risk=("risk_score", "sum")
            ).reset_index().sort_values("total_risk", ascending=False).head(10)
            if not pair_df.empty:
                pair_df["pairing"] = pair_df["flag"] + " <> " + pair_df["encounter_vessel_flag"]
                fig_pair = px.bar(pair_df, x="total_risk", y="pairing", orientation="h",
                                  color="count", color_continuous_scale="Reds",
                                  title="Top Flag Pairings in Encounters (by risk)",
                                  labels={"total_risk": "Total Risk", "pairing": "Flag Pairing"})
                st.plotly_chart(fig_pair)

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

    agg_dict = {"risk": ("risk_score", "sum"), "events": ("mmsi", "count")}
    if "base_risk_score" in df.columns:
        agg_dict["base_risk"] = ("base_risk_score", "sum")
    vessel_risk = (df.groupby(group_cols)
                   .agg(**agg_dict)
                   .reset_index().sort_values("risk", ascending=False).head(10))

    # Score decomposition: base behaviour vs structural amplifiers
    if "base_risk" in vessel_risk.columns:
        vessel_risk["compound_mult"] = (
            vessel_risk["risk"] / vessel_risk["base_risk"].replace(0, pd.NA)
        ).round(2)
        vessel_risk["risk_band"] = vessel_risk["risk"].apply(classify_risk_band)

    # Add IUU info if available
    if "iuu_matched" in df.columns:
        iuu_map = (df[df["iuu_matched"] == True]
                   .drop_duplicates("mmsi").set_index("mmsi")["iuu_listing_rfmos"])
        if not iuu_map.empty:
            vessel_risk["IUU Listed"] = vessel_risk["mmsi"].map(iuu_map).fillna("")

    # Add ICCAT info if available
    if "iccat_authorized" in df.columns:
        iccat_map = (df[df["iccat_authorized"] == True]
                     .drop_duplicates("mmsi").set_index("mmsi")["iccat_authorizations"])
        if not iccat_map.empty:
            vessel_risk["ICCAT Authorized"] = vessel_risk["mmsi"].map(iccat_map).fillna("")

    # Add OFAC info if available
    if "ofac_sanctioned" in df.columns:
        ofac_map = (df[df["ofac_sanctioned"] == True]
                    .drop_duplicates("mmsi").set_index("mmsi")["ofac_sanctions_program"])
        if not ofac_map.empty:
            vessel_risk["OFAC Sanctioned"] = vessel_risk["mmsi"].map(ofac_map).fillna("")

    fmt = {"risk": "{:.1f}"}
    if "base_risk" in vessel_risk.columns:
        fmt["base_risk"] = "{:.1f}"
        fmt["compound_mult"] = "{:.2f}x"
    styled = vessel_risk.style.format(fmt)
    if "risk_band" in vessel_risk.columns:
        def _band_bg(val):
            return f"background-color: {RISK_BAND_COLORS.get(val, '')}; color: white" if val in RISK_BAND_COLORS else ""
        styled = styled.map(_band_bg, subset=["risk_band"])
    st.dataframe(styled)

    # Risk decomposition for #1 vessel
    if not vessel_risk.empty:
        top = vessel_risk.iloc[0]
        top_mmsi = top["mmsi"]
        top_events = df[df["mmsi"] == top_mmsi]
        st.markdown(f"**#1 Riskiest Vessel Breakdown:**")
        st.markdown(
            f"- {top_events.shape[0]} events ({top_events['event_type'].value_counts().to_dict()})\n"
            f"- Flag: {top.get('flag', 'N/A')} (multiplier: {FLAG_RISKS.get(top.get('flag', ''), 1.0)}x)\n"
            f"- Avg duration: {top_events['duration_h'].mean():.1f}h\n"
            f"- IUU listed: {'Yes' if top.get('IUU Listed', '') else 'No'}\n"
            f"- ICCAT authorized: {'Yes' if top.get('ICCAT Authorized', '') else 'No'}\n"
            f"- OFAC sanctioned: {'Yes (' + str(top.get('OFAC Sanctioned', '')) + ')' if top.get('OFAC Sanctioned', '') else 'No'}"
        )

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


def render_vessel_summary(df):
    st.subheader("Vessel Summary")
    st.caption(
        "Vessel-level aggregation mirrors the presentation style in Kpler's "
        "\"Turning Tides\" whitepaper (Dec 2025), where risk is reported per vessel "
        "across multiple behavioural events rather than per individual event."
    )
    if df.empty:
        st.info("No data.")
        return

    top_n = st.slider("Number of vessels to show", min_value=5, max_value=100, value=25, step=5)

    # First non-null helper
    def _first(series):
        s = series.dropna()
        return s.iloc[0] if len(s) else ""

    grouped = df.groupby("mmsi")
    rows = []
    for mmsi, g in grouped:
        base_total = float(g["base_risk_score"].sum()) if "base_risk_score" in g.columns else 0.0
        risk_total = float(g["risk_score"].sum())
        compound = round(risk_total / base_total, 2) if base_total > 0 else 1.0
        rows.append({
            "mmsi": mmsi,
            "vessel_name": _first(g["vessel_name"]) if "vessel_name" in g.columns else "",
            "flag": _first(g["flag"]) if "flag" in g.columns else "",
            "event_count": int(len(g)),
            "event_types": ", ".join(sorted(g["event_type"].dropna().unique())),
            "base_score_total": round(base_total, 1),
            "risk_score_total": round(risk_total, 1),
            "max_event_risk": round(float(g["risk_score"].max()), 1),
            "compound_multiplier": compound,
            "risk_band": classify_risk_band(risk_total),
            "iuu_matched": bool(g["iuu_matched"].any()) if "iuu_matched" in g.columns else False,
            "iccat_authorized": bool(g["iccat_authorized"].any()) if "iccat_authorized" in g.columns else False,
            "ofac_sanctioned": bool(g["ofac_sanctioned"].any()) if "ofac_sanctioned" in g.columns else False,
        })

    vessel_df = (pd.DataFrame(rows)
                 .sort_values("risk_score_total", ascending=False)
                 .head(top_n)
                 .reset_index(drop=True))

    styled = vessel_df.style.format({
        "base_score_total": "{:.1f}",
        "risk_score_total": "{:.1f}",
        "max_event_risk": "{:.1f}",
        "compound_multiplier": "{:.2f}x",
    }).map(
        lambda v: f"background-color: {RISK_BAND_COLORS.get(v, '')}; color: white"
        if v in RISK_BAND_COLORS else "",
        subset=["risk_band"],
    )
    st.dataframe(styled, use_container_width=True)

    # Band summary under the table
    band_order = ["Critical", "Severe", "Elevated", "Emerging", "Low"]
    counts = vessel_df["risk_band"].value_counts().reindex(band_order, fill_value=0)
    st.markdown("**Band distribution across shown vessels:** " + " | ".join(
        f"{b}: {int(counts[b])}" for b in band_order
    ))


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
    st.info(
        "FDI spatial data covers EU Member State fleets only. C-squares in non-EU waters "
        "(Libya, North Africa, eastern Mediterranean) have no coverage -- this is expected, "
        "not a data error."
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

            # ICCAT-managed species note
            iccat_species = {"SWO", "BFT", "ALB"}
            top_species_codes = sp_agg.index.tolist()
            if any(s in iccat_species for s in top_species_codes):
                st.markdown("**Note:** ICCAT-managed species detected in these c-squares. "
                            "Transshipment of BFT/SWO in these areas has elevated regulatory significance.")
        else:
            st.info("No FDI landings data matches GFW event c-squares.")
    else:
        st.info("FDI landings data not available.")


def render_vessel_investigation(df, iuu_df, iccat_df, ofac_df, fdi_effort, fdi_landings):
    """Deterministic vessel investigation tab."""
    from investigation import investigate_vessel
    from risk_tree import render_framework_tree

    st.subheader("Vessel Investigation")
    st.markdown(
        "Structured rule-based investigation of any vessel in the current "
        "dataset. The view opens on the highest-risk vessel; pick another "
        "from the selector to re-run instantly."
    )

    if df.empty:
        st.info("No vessel data available.")
        return

    # Vessel selector — order by per-vessel total risk_score so the default is
    # the highest-risk vessel (the most meaningful opening example).
    vessel_totals = (
        df.dropna(subset=["vessel_name"])
          .groupby("vessel_name")["risk_score"]
          .sum()
          .sort_values(ascending=False)
    )
    vessel_options = vessel_totals.index.tolist()
    if not vessel_options:
        st.info("No vessels with names available.")
        return

    # Two-way binding between the map click and the dropdown:
    # - If the user just clicked a new vessel on the map, that click
    #   (stored under "map_clicked_vessel") overrides any existing
    #   dropdown selection for this render.
    # - Otherwise the dropdown's own prior selection is preserved.
    # - If neither exists, fall back to the highest-risk vessel.
    # The user can always override the map click by picking a different
    # vessel from the dropdown afterwards.
    map_clicked = st.session_state.get("map_clicked_vessel")
    if map_clicked and map_clicked in vessel_options:
        # Seed the selectbox key so it opens on the clicked vessel, then
        # clear the click sentinel so it doesn't keep overriding manual picks.
        st.session_state["investigation_vessel"] = map_clicked
        st.session_state.pop("map_clicked_vessel", None)
        st.caption(
            f"Pre-selected **{map_clicked}** from your last map click. "
            "Pick any vessel from the dropdown to override."
        )
    elif "investigation_vessel" not in st.session_state:
        st.session_state["investigation_vessel"] = vessel_options[0]

    selected = st.selectbox(
        "Select vessel to investigate",
        options=vessel_options,
        help="Vessels are ordered by total risk score (highest first). "
             "Click a marker on the Map & Overview tab to pre-select a vessel here.",
        key="investigation_vessel",
    )

    report = investigate_vessel(selected, df, iuu_df, iccat_df, ofac_df, fdi_effort, fdi_landings)

    if "error" in report:
        st.error(report["error"])
        return

    # Render the report sections
    # Step 10 first as a banner
    threat = report["assessment"]["threat_level"]
    if threat == "Critical":
        st.error(f"**Threat Level: {threat}**")
    elif threat == "High":
        st.warning(f"**Threat Level: {threat}**")
    elif threat == "Moderate":
        st.info(f"**Threat Level: {threat}**")
    else:
        st.success(f"**Threat Level: {threat}**")

    # Step 1: Identity
    st.markdown("### 1. Identity Confirmation")
    cols = st.columns(5)
    cols[0].metric("Vessel", report["identity"]["vessel_name"])
    cols[1].metric("MMSI", report["identity"]["mmsi"])
    cols[2].metric("IMO", report["identity"]["imo"] or "Unknown")
    cols[3].metric("Flag", report["identity"]["flag"])
    cols[4].metric("Events", report["identity"]["events_in_dataset"])

    # Step 2: IUU
    st.markdown("### 2. IUU Listing Status")
    if report["iuu"]["matched"]:
        st.error(
            f"**IUU-LISTED**\n\n"
            f"- Listed by: {report['iuu']['rfmos']}\n"
            f"- Tier: {'GFCM (Mediterranean)' if report['iuu']['is_gfcm'] else 'Other RFMO'}\n"
            f"- Match type: {report['iuu']['match_type']} ({report['iuu']['match_confidence']} confidence)\n"
            f"- Risk multiplier: {report['iuu']['multiplier']}x"
        )
    else:
        st.success("Not on any IUU vessel list.")

    # Step 3: ICCAT
    st.markdown("### 3. ICCAT Authorization Status")
    if report["iccat"]["authorized"]:
        st.warning(
            f"**ICCAT-AUTHORIZED**\n\n"
            f"- Authorizations: {report['iccat']['authorizations']}\n"
            f"- Risk tier: {report['iccat']['risk_tier']}\n"
            f"- Risk multiplier: {report['iccat']['multiplier']}x\n\n"
            f"Authorization is an opportunity indicator — provides access and infrastructure."
        )
    else:
        st.info("Not on ICCAT Mediterranean authorized vessel list.")

    # Step 4: OFAC
    st.markdown("### 4. OFAC Sanctions Status")
    if report["ofac"]["sanctioned"]:
        st.error(
            f"**OFAC-SANCTIONED**\n\n"
            f"- Program: {report['ofac']['program']}\n"
            f"- Risk multiplier: {report['ofac']['multiplier']}x\n\n"
            f"Highest-priority compliance flag. Any commercial counterparty faces secondary sanctions exposure."
        )
    else:
        st.success("Not on OFAC SDN list.")

    # Step 5: Fisheries Context — compact summary table (one row per event)
    st.markdown("### 5. Fisheries Context")
    if report["fisheries"]:
        fisheries_rows = []
        for ctx in report["fisheries"]:
            ev_date = str(ctx.get("event_date", ""))[:10]
            fisheries_rows.append({
                "Date": ev_date,
                "Event": ctx.get("event_type", ""),
                "C-square": ctx.get("csq", ""),
                "Fishing ground": "Yes" if ctx.get("is_known_ground") else "No",
                "Fishing days": f"{ctx.get('fishing_days', 0):,.0f}",
                "Top species": ", ".join(ctx.get("top_species", []) or []) or "-",
            })
        fisheries_df = pd.DataFrame(fisheries_rows)
        st.dataframe(fisheries_df, use_container_width=True, hide_index=True)
        st.caption(
            f"Per-event FDI context across {len(fisheries_rows)} event(s). "
            "Fishing ground = c-square has reported EU fleet activity in the FDI dataset."
        )
    else:
        st.info("No FDI fisheries context available for this vessel's events.")

    # Step 6: Behaviour
    st.markdown("### 6. Behavioural Pattern")
    st.write(f"**Event types:** {report['behaviour']['event_types']}")
    st.write(f"**Total events:** {report['behaviour']['total_events']}")
    st.write(f"**Average duration:** {report['behaviour']['avg_duration_h']:.1f} hours")
    st.write(f"**Date range:** {report['behaviour']['unique_dates']} unique dates")
    if "gap_analysis" in report["behaviour"]:
        ga = report["behaviour"]["gap_analysis"]
        if ga["avg_speed_before"] and ga["avg_speed_after"]:
            speed_drop = ga["avg_speed_before"] - ga["avg_speed_after"]
            st.write(f"**Gap speed analysis:** before={ga['avg_speed_before']:.1f}kn, after={ga['avg_speed_after']:.1f}kn (drop: {speed_drop:.1f}kn)")

    # Step 7: Risk Decomposition
    st.markdown("### 7. Risk Score Decomposition")
    cols = st.columns(4)
    cols[0].metric("Total Risk Score", f"{report['risk']['total_risk_score']:.1f}")
    cols[1].metric("Flag Multiplier", f"{report['risk']['flag_multiplier']:.1f}x")
    cols[2].metric("Compounded Multiplier", f"{report['risk']['compounded_multiplier']:.1f}x")
    cols[3].metric("Max Single Event", f"{report['risk']['max_single_event']:.1f}")

    # Step 8: Hypotheses
    st.markdown("### 8. Hypotheses")
    for h in report["hypotheses"]:
        if h["level"] == "critical":
            st.error(h["text"])
        elif h["level"] == "high":
            st.warning(h["text"])
        else:
            st.info(h["text"])

    # Step 9: External Lookups
    if report["external_links"]:
        st.markdown("### 9. External Lookups")
        st.markdown(
            f"- [MarineTraffic]({report['external_links']['marinetraffic']}) — current position and history\n"
            f"- [VesselFinder]({report['external_links']['vesselfinder']}) — ownership and particulars\n"
            f"- [Equasis]({report['external_links']['equasis']}) — IMO ship database"
        )

    # Step 10: Assessment
    st.markdown("### 10. Threat Assessment")
    st.write("**Key evidence:**")
    for ev in report["assessment"]["key_evidence"]:
        st.write(f"- {ev}")
    st.write(f"**Recommended action:** {report['assessment']['recommended_action']}")

    # Per-vessel risk tree
    if "trace" in report:
        st.markdown("---")
        st.markdown("### Risk Tree -- This Vessel's Path")
        st.markdown(
            "The framework applied to this specific vessel. "
            "Coloured nodes show which questions raised concerns and which "
            "rules fired. The highlighted tier is the final classification."
        )

        vessel_label = (
            f"{report['identity']['vessel_name']}\n"
            f"{report['identity']['flag']} | {report['identity']['vessel_type'] or 'Unknown type'}"
        )
        try:
            dot_vessel = render_framework_tree(
                trace=report["trace"],
                tier=report["assessment"]["threat_level"],
                vessel_label=vessel_label,
            )
            st.graphviz_chart(dot_vessel)
        except Exception as e:
            st.warning(f"Per-vessel tree render error: {e}")

        # Interactive trace table grouped by branch
        _SEV_COLORS = {
            "none": "#E8F5E9", "low": "#FFF9C4", "medium": "#FFE0B2",
            "high": "#FFAB91", "critical": "#EF5350",
        }
        _BRANCH_NAMES = {
            "identity": "Identity Verification",
            "flag_risk": "Flag State Risk",
            "regulatory_status": "Regulatory Status",
            "authorization": "Fishing Authorization",
            "behavioural_history": "Behavioural History",
            "spatial_context": "Spatial / Contextual",
            "network_exposure": "Network Exposure",
        }

        with st.expander("Evaluation trace (details)", expanded=False):
            # Group trace entries by branch
            from collections import OrderedDict
            branches = OrderedDict()
            for entry in report["trace"]:
                bid = entry["branch_id"]
                if bid not in branches:
                    branches[bid] = []
                branches[bid].append(entry)

            for bid, entries in branches.items():
                branch_fired = any(e.get("rule_fired") for e in entries)
                branch_label = _BRANCH_NAMES.get(bid, bid)
                if branch_fired:
                    st.markdown(f"**{branch_label}** -- rules fired")
                else:
                    st.markdown(f"**{branch_label}**")

                trace_df = pd.DataFrame([
                    {
                        "Question": e["question_id"].replace("_", " ").title(),
                        "Answer": e.get("answer", "?").upper(),
                        "Severity": e.get("severity", "none").title(),
                        "Finding": e.get("note", ""),
                    }
                    for e in entries
                ])

                def _color_severity(val):
                    sev = val.lower()
                    bg = _SEV_COLORS.get(sev, "#F0F0F0")
                    fg = "white" if sev in ("high", "critical") else "black"
                    return f"background-color: {bg}; color: {fg}"

                st.dataframe(
                    trace_df.style.applymap(_color_severity, subset=["Severity"]),
                    use_container_width=True,
                    hide_index=True,
                )


# ============================================================================
# Reference & Methodology tab
# ============================================================================

@st.cache_data
def _load_reference_content():
    """Load the prose YAML backing the Reference & Methodology tab."""
    import yaml

    path = Path(__file__).parent / "data" / "reference_content.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_reference():
    """Reference & Methodology tab.

    Pure rendering: prose from data/reference_content.yaml, numerical tables
    from config.py, framework diagram from risk_tree.render_framework_tree.
    """
    from risk_tree import load_framework, render_framework_tree

    content = _load_reference_content()

    st.subheader("Reference & Methodology")

    # 1. Intro
    st.markdown(content["intro"])

    # 2. Framework diagram (collapsible, open by default)
    with st.expander("Mediterranean IUU Risk Tree Framework", expanded=True):
        try:
            framework = load_framework()
            st.markdown(f"**{framework['name']}** -- version {framework['version']}")
            st.markdown(framework["description"])
            st.graphviz_chart(render_framework_tree())
        except Exception as e:
            st.warning(f"Could not render framework diagram: {e}")

    # 3. Risk formula
    st.markdown("### Risk Formula")
    st.markdown(content["risk_formula_explanation"])
    st.code(
        "base = (duration_h ^ 0.75)\n"
        "     x event_weight\n"
        "     x flag_multiplier\n"
        "     x shore_factor\n"
        "     x event_specific_factors\n"
        "\n"
        "final_score = base\n"
        "     x iuu_multiplier\n"
        "     x iccat_multiplier\n"
        "     x ofac_multiplier",
        language="text",
    )

    bands_df = pd.DataFrame(
        [
            {
                "Band": label,
                "Lower bound": low,
                "Upper bound": ("infinity" if high == float("inf") else high),
                "Meaning": desc,
            }
            for low, high, label, desc in RISK_BANDS
        ]
    )
    st.markdown("**Kpler-aligned risk bands (applied to final compounded score)**")
    st.dataframe(bands_df, use_container_width=True, hide_index=True)

    # 4. Multiplier tables (collapsed)
    with st.expander("Multiplier tables (from config.py)", expanded=False):
        st.markdown("**Flag risk multipliers** — applied to every event on the flag")
        flag_df = (
            pd.DataFrame(
                [{"Flag (ISO3)": k, "Multiplier": v} for k, v in FLAG_RISKS.items()]
            )
            .sort_values("Multiplier", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(flag_df, use_container_width=True, hide_index=True)
        st.caption("Flags not listed carry a 1.0x multiplier (neutral).")

        st.markdown("**IUU listing multipliers** — applied on IUU vessel match")
        iuu_df = pd.DataFrame(
            [
                {
                    "Listing tier": "GFCM (Mediterranean)"
                    if k == "GFCM"
                    else "Other RFMO",
                    "Key": k,
                    "Multiplier": v,
                }
                for k, v in IUU_MULTIPLIERS.items()
            ]
        )
        st.dataframe(iuu_df, use_container_width=True, hide_index=True)

        st.markdown(
            "**ICCAT authorisation multipliers** — applied conditionally on "
            "behavioural signal"
        )
        _ICCAT_LABELS = {
            "carrier": "Carrier (transshipment-capable)",
            "bft_catching": "Bluefin tuna — catching vessel",
            "bft_other": "Bluefin tuna — support/other",
            "swo_med": "Mediterranean swordfish",
            "alb_med": "Mediterranean albacore",
        }
        iccat_df = pd.DataFrame(
            [
                {
                    "Authorisation": _ICCAT_LABELS.get(k, k),
                    "Key": k,
                    "Multiplier": v,
                }
                for k, v in ICCAT_MULTIPLIERS.items()
            ]
        ).sort_values("Multiplier", ascending=False).reset_index(drop=True)
        st.dataframe(iccat_df, use_container_width=True, hide_index=True)

        st.markdown("**OFAC sanctions multiplier** — applied on OFAC SDN match")
        ofac_df = pd.DataFrame(
            [
                {
                    "Listing": "OFAC SDN (Specially Designated Nationals)",
                    "Multiplier": OFAC_MULTIPLIER,
                }
            ]
        )
        st.dataframe(ofac_df, use_container_width=True, hide_index=True)

    # 5. ICCAT framing note
    with st.expander("ICCAT framing note", expanded=False):
        st.markdown(content["iccat_framing_note"])

    # 6. Data source provenance
    with st.expander("Data source provenance", expanded=False):
        prov_df = pd.DataFrame(content["data_source_provenance"])
        prov_df.columns = [c.capitalize() for c in prov_df.columns]
        st.dataframe(prov_df, use_container_width=True, hide_index=True)

    # 7. Epistemological separation
    with st.expander("Epistemological separation", expanded=False):
        st.markdown(content["epistemological_separation"])

    # 8. Methodology references
    with st.expander("Methodology references", expanded=False):
        for ref in content["methodology_references"]:
            st.markdown(
                f"- **{ref['title']}** -- {ref['citation']}  \n"
                f"  {ref['relevance']}"
            )

    # 9. Scope and limitations
    with st.expander("Scope and limitations", expanded=False):
        st.markdown(content["scope_and_limitations"])
