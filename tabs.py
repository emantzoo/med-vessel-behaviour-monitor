"""Render functions for all analytical tabs (1-11). Tab 12 (AI Analyst) is in ai_analyst.py."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from pathlib import Path

from config import (
    EVENT_COLORS,
    FLAG_RISKS, FLAG_RISKS_SOURCE_YEAR,
    ICCAT_MULTIPLIERS,
    IUU_MULTIPLIERS,
    OFAC_MULTIPLIER,
    MPA_MULTIPLIERS,
    RISK_BAND_COLORS,
    RISK_BANDS,
    SPECIES_NAMES,
    classify_risk_band,
)
from risk_model import get_fdi_context


def render_daily_trend(df):
    st.subheader("Daily Behavioral Risk Trend")
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- **Top line chart**: total compounded `risk_score` summed across all
  events on each calendar day. Spikes mean either many events on one day
  or one very large structurally amplified event.
- **Black dashed verticals labelled "IUU"**: dates on which at least one
  IUU-listed vessel had an event. These dates are precomputed from the
  IUU-matching pipeline and overlaid here as flags, not added to the
  numeric series.
- **Bottom stacked area**: same daily totals split by event type so you
  can see the composition (gap vs encounter vs loitering) shifting over
  time. This is the Med analogue of Kpler *Turning Tides* Graph 4.
            """
        )
    if df.empty:
        st.info("No data.")
        return
    from charts import build_daily_risk_line_fig, build_daily_risk_area_fig, build_monthly_event_counts_fig

    fig = build_daily_risk_line_fig(df)
    if fig:
        st.plotly_chart(fig)

    fig2 = build_daily_risk_area_fig(df)
    if fig2:
        st.plotly_chart(fig2)

    fig3 = build_monthly_event_counts_fig(df)
    if fig3:
        st.plotly_chart(fig3)
        st.caption(
            "Monthly deceptive behaviour trends across Mediterranean GFW "
            "event types over the selected date range."
        )


def render_flag_breakdown(df):
    st.subheader("Breakdown by Flag State")
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- **Top horizontal bar**: total compounded `risk_score` per flag state,
  sorted descending. Long bars at the top are the headline finding.
- **Bottom stacked bar**: same totals broken out by event type so you
  can see whether a flag's exposure comes from gaps, encounters or
  loitering.
- **Side tables**: per-flag counts of vessels matched to the IUU list,
  ICCAT Med record, and OFAC SDN list. These three tables are the
  structural-amplifier provenance for the bars above.
- High-risk flags often combine: a Russian-flagged vessel may show up
  on the IUU table *and* dominate the encounter bar simultaneously.
            """
        )
    if df.empty:
        st.info("No data.")
        return
    from charts import build_flag_risk_bar_fig, build_flag_event_stacked_fig

    fig = build_flag_risk_bar_fig(df)
    if fig:
        st.plotly_chart(fig)

    fig2 = build_flag_event_stacked_fig(df)
    if fig2:
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
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- **Pie**: share of total compounded `risk_score` contributed by each
  event type. Encounters typically dominate because their event weight
  is the highest (5.0 vs 3.2 for gaps and 2.0 for loitering).
- **Summary table**: per-event-type event count, mean duration, mean
  risk per event, total risk, and structural matches (IUU / ICCAT
  counts).
- **Risk band distribution table**: events binned into the Turning
  Tides bands. This is *event-level* banding -- the band column on the
  Ranking subtab is *vessel-level* banding (sum across events).
            """
        )
    if df.empty:
        st.info("No data.")
        return
    from charts import build_event_type_pie_fig

    fig = build_event_type_pie_fig(df)
    if fig:
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

    # Band distribution (R&C risk-band vocabulary)
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
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- **Top histogram**: distribution of event duration in hours, coloured
  by event type. Long-tail bars on the right are the suspicious cases:
  gaps over 24h suggest deliberate AIS disabling, encounters over 8h
  suggest transshipment, multi-day loitering near a coastline suggests
  staging.
- **Bottom scatter**: each dot is one event, x = duration, y = compounded
  risk score, colour = flag. The non-linear relationship comes from the
  `duration_h ^ 0.75` term in the scoring formula plus the structural
  multipliers.
- The two charts together show why we use a sub-linear duration term:
  doubling the duration of an event roughly multiplies its score by 1.7,
  not by 2.
            """
        )
    if df.empty:
        st.info("No data.")
        return
    from charts import build_duration_histogram_fig, build_duration_vs_risk_fig

    fig = build_duration_histogram_fig(df)
    if fig:
        st.plotly_chart(fig)
    st.markdown("**Why it matters:** Long gaps (>24h) suggest deliberate AIS disabling. "
                "Encounters over 8h point to transshipment. Short loitering may be staging.")

    fig2 = build_duration_vs_risk_fig(df)
    if fig2:
        st.plotly_chart(fig2)


def render_geographic_risk(df):
    st.subheader("Geographic Risk Analysis")
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- Events are placed into Mediterranean sub-zones via
  `classify_med_zone(lon, lat)` (a longitude-band partition: Western
  basin, Tyrrhenian, Ionian/Adriatic, Aegean/Levantine).
- The **bar chart** sums compounded risk per zone, with colour encoding
  the marker class (Regular / IUU-Listed / ICCAT-Authorized / OFAC).
- The **port-distance scatter** shows each event's distance from the
  nearest major port on the x axis vs total risk on the y axis. Events
  far offshore that nonetheless score high are the prime investigation
  targets -- they cannot be explained as port-adjacent loitering.
            """
        )
    if df.empty:
        st.info("No data.")
        return

    from charts import build_geographic_scatter_fig, build_med_zone_bar_fig

    fig = build_geographic_scatter_fig(df)
    if fig:
        st.plotly_chart(fig)

    if "med_zone" in df.columns:
        st.subheader("Risk by Mediterranean Sub-Region")
        fig2 = build_med_zone_bar_fig(df)
        if fig2:
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
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- Each cell = total compounded `risk_score` for that
  (flag, event-type) combination. Brighter cells = more risk.
- Rows are sorted bottom-to-top by total risk so the worst flags
  always sit at the top of the heatmap.
- The "Highest risk combination" line under the chart names the single
  cell with the largest score -- the headline finding.
- Look for cells where a high-risk flag (Russia, Iran, FoCs) intersects
  with a high-weight event type (encounter, gap). These are the
  combinations the analyst should open in the Vessel Investigation tab.
            """
        )
    if df.empty:
        st.info("No data.")
        return
    from charts import build_risk_heatmap_fig

    fig = build_risk_heatmap_fig(df)
    if fig:
        st.plotly_chart(fig)

    # Highest risk combination insight
    pivot = df.pivot_table(
        values="risk_score", index="flag", columns="event_type",
        aggfunc="sum", fill_value=0,
    )
    if not pivot.empty:
        max_flag = pivot.sum(axis=1).idxmax()
        max_type = pivot.loc[max_flag].idxmax()
        max_val = pivot.loc[max_flag, max_type]
        st.markdown(f"**Highest risk combination:** {max_flag} + {max_type} = {max_val:.1f} risk score")

    st.markdown("**Interpretation:** bright cells = high risk combinations. "
                "Look for Russian/Iranian flags with high GAP or ENCOUNTER scores.")


def render_repeat_offenders(df):
    st.subheader("Repeat Offenders -- Vessels with Multiple Events")
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- A vessel is a "repeat offender" here if it has at least **two
  events** in the current filter window (any event type, any spacing).
  This is the loose definition; the strict 90-day version drives the
  `repeat_offender_90d` flag in the Ranking subtab.
- **Bar chart**: top 15 vessels by event count, x = MMSI, y = number of
  events, colour = total compounded risk.
- IUU-listed vessels are pulled to the top of the underlying table
  regardless of event count.
- The **timeline plot** below the bars shows the top-3 repeat offenders'
  events on a true time axis so you can read the spacing.
- Hovering on a bar exposes flag, event types, average duration and
  total risk for that vessel.
            """
        )
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
        from charts import build_repeat_offenders_bar_fig, build_repeat_timeline_fig

        fig = build_repeat_offenders_bar_fig(repeat_vessels)
        if fig:
            st.plotly_chart(fig)
        st.dataframe(repeat_vessels.head(15).style.format(
            {"total_risk": "{:.1f}", "avg_duration": "{:.1f}"}))
    else:
        st.info("No vessels with multiple events in filtered data.")

    # Event timeline for top 3 repeat offenders
    if not repeat_vessels.empty:
        top3 = repeat_vessels.head(3)["mmsi"].tolist()
        st.subheader("Event Timeline for Top Repeat Offenders")
        fig_tl = build_repeat_timeline_fig(df, top3)
        if fig_tl:
            st.plotly_chart(fig_tl)

    st.markdown("**Why it matters:** A vessel with 5 events is far more interesting "
                "than 5 vessels with 1 event each. Repeat offenders warrant deeper investigation.")


def render_gap_behaviour(df):
    st.subheader("Gap Behaviour Analysis")
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- **GAP events** are AIS broadcast interruptions of significant
  duration that GFW classifies separately from ordinary signal loss.
- **IUU gap warning box** (if present): the precise list of IUU-matched
  vessels with gap events in the current window. Treat as the highest-
  priority leads in the entire dataset.
- **Distribution histogram**: gap durations in hours. Long-tail bars
  represent multi-day disabling events that cannot be explained by
  signal degradation.
- **Geographic scatter**: gap end-point positions, sized by duration.
  Geographic clustering of long gaps off a coastline often signals a
  ship-to-ship transfer or unreported port call.
            """
        )
    gap_df = df[df["event_type"] == "GAP"].copy()

    # IUU gap warning
    if not gap_df.empty and "iuu_matched" in gap_df.columns:
        iuu_gaps = gap_df[gap_df["iuu_matched"] == True]
        if not iuu_gaps.empty:
            st.warning(f"**{len(iuu_gaps)} AIS gap(s) involve IUU-listed vessels** -- "
                       "highest-priority evasion signals.")

    if not gap_df.empty and "speed_before_gap" in gap_df.columns and gap_df["speed_before_gap"].notna().any():
        from charts import build_gap_speed_fig, build_gap_duration_distance_fig

        fig = build_gap_speed_fig(gap_df)
        if fig:
            st.plotly_chart(fig)

        fig2 = build_gap_duration_distance_fig(gap_df)
        if fig2:
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
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- **ENCOUNTER events** are GFW pairings: two AIS-broadcasting vessels
  within ~500 m for >2h while both are moving at <2 kn. The classic
  signature of a ship-to-ship transfer.
- **Scatter**: x = median distance between the two vessels in km, y =
  encounter duration in hours, dot size = compounded risk score, colour
  = flag.
- **Carrier alert**: ICCAT-authorized BFT carriers (`type=Carrier`)
  flagged separately because they are *the* watchlist for unreported
  bluefin tuna transshipment in the Med.
- The encounter table at the bottom enumerates the partner vessel name
  and flag for every encounter -- this is the most operationally
  actionable column in the entire dashboard.
            """
        )
    enc_df = df[df["event_type"] == "ENCOUNTER"].copy()

    if not enc_df.empty and "encounter_median_distance_km" in enc_df.columns:
        from charts import build_encounter_proximity_fig, build_encounter_flag_pairing_fig

        fig = build_encounter_proximity_fig(enc_df)
        if fig:
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
        fig_pair = build_encounter_flag_pairing_fig(enc_df)
        if fig_pair:
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


def render_vessel_summary(df, fdi_effort=None, fdi_landings=None):
    st.subheader("Fleet Risk Ranking")
    st.caption(
        "Vessel-level aggregation reports risk per vessel across multiple "
        "behavioural events rather than per individual event."
    )

    with st.expander("How to read this table", expanded=False):
        st.markdown(
            """
**Four behavioural flags** are shown alongside the risk band. They are
**display-only** -- they are *not* multiplied into the risk score
(the underlying signal is already captured at the event level).

| Flag | Definition | Type |
|---|---|---|
| **Industrial** | Vessel >=24 m LOA or >=100 GT (ICCAT industrial / EU 1224/2009 reporting threshold) | Structural |
| **Multi-behaviour** | Vessel shows two or more distinct event types | Compound |
| **Dark port call candidate** | Loitering within 10 km of shore (AIS-inferred, not satellite-verified) | Spatial |
| **Repeat offender** | Two or more events within a 90-day window (exposure drift) | Temporal |

Length and tonnage come from the GFW Vessels API registry / self-reported
metadata in live mode and from the static profile in demo mode.

**Two spatial-context columns** are also shown:

- **MPA intersection** -- sourced from GFW's `regions.mpa` field
  (WDPA point-in-polygon, pre-computed server-side), tiered into
  GFCM-FRA / EU-site / general. *Unlike the behavioural flags, MPA
  intersection **is** multiplied into the base behavioural score.*
- **Fishing-in-MPA** (event count and total hours) -- comes from a
  separate GFW `public-global-fishing-events` query. Display-only:
  legitimate fishing outside MPAs is normal commercial activity, so
  only fishing inside protected zones is the actionable IUU signal.

**Two vessel-identity columns** sit alongside the size profile:

- **Vessel class** -- descriptive label derived from the GFW Vessels
  API `shiptypes` field, falling back to the event-level `vessel_type`
  when shiptypes is empty. One of `industrial_fishing`,
  `artisanal_fishing`, `carrier`, `tanker`, `cargo`, `support`,
  `passenger`, or `other`. *Orthogonal* to `is_industrial`: a small
  trawler is `artisanal_fishing` here but `is_industrial=False` on
  the size axis.
- **Type mismatch** -- True when both the event-level `vessel_type`
  (often AIS self-reported) and the registry-level `shiptypes` (GFW
  Vessels API) are populated and normalise to *different* canonical
  classes. Misrepresentation signal aligned with Kpler's "irregular
  vessel information" indicator. Class-level comparison so trivial
  spelling differences (`TRAWLER` vs `FISHING`) do not fire.
            """
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
        # MPA intersection: any event in an MPA, plus highest-severity tier present
        if "in_mpa" in g.columns:
            in_mpa_mask = g["in_mpa"].fillna(False).astype(bool)
            in_mpa_any = bool(in_mpa_mask.any())
        else:
            in_mpa_mask = pd.Series([False] * len(g), index=g.index)
            in_mpa_any = False
        if in_mpa_any and "mpa_tier" in g.columns:
            tier_priority = {"gfcm_fra": 3, "eu_site": 2, "general": 1, "": 0}
            tiers_present = g.loc[in_mpa_mask, "mpa_tier"].fillna("").astype(str).tolist()
            mpa_tier_top = max(tiers_present, key=lambda t: tier_priority.get(t, 0)) if tiers_present else ""
        else:
            mpa_tier_top = ""
        # Fishing-in-MPA: pre-joined onto every event row in app.py from a
        # separate GFW fishing-events query, so all events for a given mmsi
        # share the same value. Take any non-null max as the per-vessel value.
        fim_events = (
            int(g["fishing_in_mpa_events"].max())
            if "fishing_in_mpa_events" in g.columns and g["fishing_in_mpa_events"].notna().any()
            else 0
        )
        fim_hours = (
            float(g["fishing_in_mpa_hours"].max())
            if "fishing_in_mpa_hours" in g.columns and g["fishing_in_mpa_hours"].notna().any()
            else 0.0
        )
        # Vessel size profile -- length_m and tonnage_gt are vessel-level
        # (broadcast to every event row in app.py), so any non-null value is fine.
        length_m_val = None
        if "length_m" in g.columns:
            l_series = pd.to_numeric(g["length_m"], errors="coerce").dropna()
            if len(l_series):
                length_m_val = float(l_series.iloc[0])
        tonnage_val = None
        if "tonnage_gt" in g.columns:
            t_series = pd.to_numeric(g["tonnage_gt"], errors="coerce").dropna()
            if len(t_series):
                tonnage_val = float(t_series.iloc[0])
        if length_m_val and tonnage_val:
            profile_str = f"{length_m_val:.0f}m / {tonnage_val:.0f} GT"
        elif length_m_val:
            profile_str = f"{length_m_val:.0f}m"
        elif tonnage_val:
            profile_str = f"{tonnage_val:.0f} GT"
        else:
            profile_str = "—"

        # Vessel class -- propagated identically to every event row, take the
        # first non-empty value. Mismatch flag is True if any event row marks it.
        vessel_class_val = ""
        if "vessel_class" in g.columns:
            vc_series = g["vessel_class"].dropna().astype(str)
            vc_series = vc_series[vc_series != ""]
            if len(vc_series):
                vessel_class_val = vc_series.iloc[0]
        type_mismatch = (
            bool(g["vessel_type_mismatch"].any())
            if "vessel_type_mismatch" in g.columns
            else False
        )

        rows.append({
            "mmsi": mmsi,
            "vessel_name": _first(g["vessel_name"]) if "vessel_name" in g.columns else "",
            "flag": _first(g["flag"]) if "flag" in g.columns else "",
            "event_count": int(len(g)),
            "event_types": ", ".join(sorted(g["event_type"].dropna().unique())),
            "vessel_class": vessel_class_val,
            "type_mismatch": type_mismatch,
            "is_industrial": bool(g["is_industrial"].any()) if "is_industrial" in g.columns else False,
            "length_m": length_m_val,
            "profile": profile_str,
            "multi_behaviour": bool(g["multi_behaviour_flag"].any()) if "multi_behaviour_flag" in g.columns else False,
            "dark_port_candidates": int(g["dark_port_call_candidate"].sum()) if "dark_port_call_candidate" in g.columns else 0,
            "repeat_offender": bool(g["repeat_offender_90d"].any()) if "repeat_offender_90d" in g.columns else False,
            "in_mpa": in_mpa_any,
            "mpa_tier": mpa_tier_top,
            "fishing_in_mpa_events": fim_events,
            "fishing_in_mpa_hours": round(fim_hours, 1),
            "base_score_total": round(base_total, 1),
            "risk_score_total": round(risk_total, 1),
            "max_event_risk": round(float(g["risk_score"].max()), 1),
            "compound_multiplier": compound,
            "risk_band": classify_risk_band(risk_total),
            "iuu_matched": bool(g["iuu_matched"].any()) if "iuu_matched" in g.columns else False,
            "iccat_authorized": bool(g["iccat_authorized"].any()) if "iccat_authorized" in g.columns else False,
            "ofac_sanctioned": bool(g["ofac_sanctioned"].any()) if "ofac_sanctioned" in g.columns else False,
            "gfcm_registered": bool(g["gfcm_registered"].any()) if "gfcm_registered" in g.columns else False,
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
    st.dataframe(styled, width="stretch")

    # Band summary under the table
    band_order = ["Critical", "Severe", "Elevated", "Emerging", "Low"]
    counts = vessel_df["risk_band"].value_counts().reindex(band_order, fill_value=0)
    st.markdown("**Band distribution across shown vessels:** " + " | ".join(
        f"{b}: {int(counts[b])}" for b in band_order
    ))

    # --- Fleet summary export ---
    st.markdown("---")
    st.subheader("Export fleet summary")
    st.caption(
        "Download a fleet-level risk summary as CSV, with a Markdown cover "
        "sheet documenting scope and band distribution."
    )

    from exports import generate_fleet_summary
    from datetime import datetime as _dt

    # Infer which filters are active from the data that was passed in
    filters_active = {}
    if "event_type" in df.columns:
        et = sorted(df["event_type"].dropna().unique())
        if et:
            filters_active["Event types"] = ", ".join(et)
    if "flag" in df.columns:
        fl = sorted(df["flag"].dropna().unique())
        if fl:
            filters_active["Flag states"] = f"{len(fl)} flags"
    if "risk_band" in df.columns:
        rb = sorted(df["risk_band"].dropna().unique())
        if rb:
            filters_active["Risk bands"] = ", ".join(rb)

    csv_bytes, cover_md = generate_fleet_summary(
        vessel_summary_df=vessel_df,
        filters_active=filters_active,
    )

    from exports import generate_fleet_summary_html
    fleet_html = generate_fleet_summary_html(
        vessel_summary_df=vessel_df,
        df_events=df,
        filters_active=filters_active,
        fdi_effort=fdi_effort,
        fdi_landings=fdi_landings,
    )

    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        fn_csv = f"fleet_summary_{_dt.utcnow().strftime('%Y%m%d_%H%M')}.csv"
        st.download_button(
            label="Download fleet CSV",
            data=csv_bytes,
            file_name=fn_csv,
            mime="text/csv",
        )
    with col_e2:
        fn_md = f"fleet_summary_cover_{_dt.utcnow().strftime('%Y%m%d_%H%M')}.md"
        st.download_button(
            label="Download cover sheet (Markdown)",
            data=cover_md,
            file_name=fn_md,
            mime="text/markdown",
        )
    with col_e3:
        fn_html = f"fleet_summary_{_dt.utcnow().strftime('%Y%m%d_%H%M')}.html"
        st.download_button(
            label="Download fleet report (HTML)",
            data=fleet_html,
            file_name=fn_html,
            mime="text/html",
        )

    with st.expander("Preview cover sheet"):
        st.markdown(cover_md)


def render_fisheries_context(df, fdi_effort, fdi_landings):
    st.subheader("Fisheries Context -- EU FDI Baseline")
    st.markdown(
        "Overlaying GFW behavioural events with EU Fisheries Dependent Information (FDI) "
        "spatial data to assess whether events occur in known fishing grounds."
    )
    with st.expander("How to read this section", expanded=False):
        st.markdown(
            """
- **FDI** = EU Joint Research Centre's Fisheries Dependent Information.
  Spatially aggregated to **0.5 x 0.5 degree c-squares** by year, gear,
  and species. We use the Mediterranean (MBS) supra-region, 2017-2024.
- **Section A: Effort vs events**: c-square fishing-effort heat overlaid
  with GFW behavioural events. Events that fall in *low-effort*
  c-squares are the suspicious ones -- they happen in waters where
  legitimate fishing rarely occurs.
- **Section B: Species landings**: top species (by weight or value)
  for the c-squares that contain GFW events. Highlights when
  ICCAT-managed species (BFT, SWO, ALB) dominate the landings of the
  same c-squares where GFW events occur -- the basis for transshipment
  hypotheses.
- FDI is *baseline data*, not a risk signal. It tells you whether the
  GFW event sits inside a known fishing ground, which is the difference
  between "vessel transiting" and "vessel operating".
            """
        )

    if fdi_effort.empty:
        st.warning("FDI data not available. Run `python data/prepare_fdi.py` to generate.")
        return
    if df.empty:
        st.info("No GFW events match the selected filters.")
        return

    # Section A: C-Square Effort Comparison Map
    st.subheader("A. Fishing Effort vs GFW Events")
    from charts import build_fdi_effort_map_fig, build_seasonal_pattern_fig, build_species_landings_fig

    fig_a = build_fdi_effort_map_fig(df, fdi_effort)
    if fig_a:
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
        width="stretch",
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
    if "quarter" in fdi_effort.columns and "med_zone" in df.columns:
        zone_sel = st.selectbox(
            "Select Mediterranean zone",
            sorted(df["med_zone"].unique()),
            key="fdi_zone_sel",
        )
        fig_c = build_seasonal_pattern_fig(df, fdi_effort, zone_sel)
        if fig_c:
            st.plotly_chart(fig_c)

    # Section D: Species Context
    st.subheader("D. Species in Event Locations")
    st.markdown(
        "What species are reported in c-squares where GFW events occur? "
        "High-value species (BFT, SWO, HKE) increase transshipment risk."
    )
    fig_d = build_species_landings_fig(df, fdi_landings)
    if fig_d:
        st.plotly_chart(fig_d)
        # ICCAT-managed species note
        if "csq_lon" in df.columns and not fdi_landings.empty:
            event_cells = df[["csq_lon", "csq_lat"]].drop_duplicates()
            event_land = event_cells.merge(
                fdi_landings, left_on=["csq_lon", "csq_lat"],
                right_on=["rectangle_lon", "rectangle_lat"], how="inner",
            )
            if not event_land.empty:
                sp_agg = (event_land.groupby("species")
                          .agg(total_value=("totvallandg", "sum"))
                          .sort_values("total_value", ascending=True).tail(15))
                iccat_species = {"SWO", "BFT", "ALB"}
                if any(s in iccat_species for s in sp_agg.index.tolist()):
                    st.markdown("**Note:** ICCAT-managed species detected in these c-squares. "
                                "Transshipment of BFT/SWO in these areas has elevated regulatory significance.")
    else:
        st.info("FDI landings data not available or no matches.")


def render_base_vs_compound_decomposition(df):
    """Fleet-level base-vs-compound decomposition.

    The single best chart for explaining the scoring methodology visually:
    a horizontal stacked bar where the left segment is the behavioural base
    risk (what we observed) and the right segment is the structural amplifier
    delta (what we looked up about the vessel via IUU/ICCAT/OFAC). Aggregated
    across the entire filtered fleet so it answers "how does scoring work?"
    rather than "who is worst?" (the latter is plot #6).
    """
    st.subheader("Base vs structural-amplifier decomposition")
    st.caption(
        "Fleet-wide split between behavioural risk (event observation) and "
        "structural amplifiers (IUU / ICCAT-Carrier / OFAC list lookups). "
        "Reads the methodology directly off real data."
    )
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- **Blue segment** = sum of `base_risk_score` across every event in the
  current filter window. This is what we *observed*: event duration,
  shore distance, MPA tier, flag-state risk, event-specific factors.
- **Coloured segments** = the additional risk added by each lookup
  stage: IUU listing (black), ICCAT authorization (blue), OFAC sanctions
  (dark red). This is what we *looked up* about the vessels.
- **Compound multiplier** in the title = total / base. A value close to
  1.0x means the fleet's risk is almost entirely behavioural; values
  above 2x mean structural lookups dominate.
- **Why MPA tier lives in the base.** The MPA tier multiplier is
  observation -- it describes where the event happened, not who the
  vessel is. IUU / ICCAT / OFAC sit in the compound segment because
  they are registry lookups about the vessel's identity. This is the
  "base = observation, compound = lookup" split that underpins the
  entire scoring design.
            """
        )
    if df.empty or "base_risk_score" not in df.columns:
        st.info("Base risk score not available in current dataset.")
        return

    from charts import build_base_vs_compound_fig, build_band_decomposition_fig

    fig = build_base_vs_compound_fig(df)
    if fig is None:
        st.info("No risk scored in current filter window.")
        return
    st.plotly_chart(fig, width="stretch")

    base_total = float(df["base_risk_score"].sum())
    risk_total = float(df["risk_score"].sum())
    compound_mult = risk_total / base_total if base_total > 0 else 1.0
    st.markdown(
        f"**Read:** **{base_total:.0f}** behavioural base "
        f"= **{risk_total:.0f}** total "
        f"(**{compound_mult:.2f}x** compound multiplier). "
        "The compound multiplier is the ratio of total to base -- how much "
        "of this fleet's risk is structural vs behavioural."
    )

    # Band-segmented decomposition
    fig_band = build_band_decomposition_fig(df)
    if fig_band:
        st.subheader("Risk composition by band")
        st.caption(
            "Does the compound multiplier shift as you move up the bands? "
            "Critical-band vessels typically have much higher compound ratios "
            "than Emerging -- band membership is driven by behavioural severity "
            "AND structural amplification."
        )
        st.plotly_chart(fig_band, width="stretch")


def render_risk_band_distribution(df):
    """Vessel count per Kpler 'Turning Tides' risk band.

    The single chart Amanda will recognise fastest because it's literally
    the Kpler vocabulary. One bar per band, coloured by band.
    """
    st.subheader("Risk band distribution")
    st.caption(
        "Vessels grouped into the Turning Tides risk vocabulary. "
        "Bands apply to the *compounded* per-vessel risk total."
    )
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- Each bar = number of unique vessels whose **summed compounded risk
  score** falls into that band.
- Aggregation is per `mmsi`, not per event -- a vessel with five small
  loitering events can sit in a higher band than a vessel with one
  large gap event.
- Band colours match the vessel-summary table and the map markers.
- Cutoffs align with Kpler R&C *Turning Tides* (Dec 2025): Low <50,
  Emerging 50-60, Elevated 60-80, Severe 80-100, Critical >=100.
- A healthy fleet skews left (Low/Emerging). A right-skewed distribution
  is the headline finding for the analyst.
            """
        )
    if df.empty:
        st.info("No data.")
        return

    from charts import build_risk_band_fig

    fig = build_risk_band_fig(df)
    if fig is None:
        st.info("No vessel-level risk in current filter window.")
        return

    st.plotly_chart(fig, width="stretch")
    st.markdown(
        "**Bands:** Low <50 | Emerging 50-60 | Elevated 60-80 | Severe 80-100 | Critical >=100. "
        "Cutoffs aligned with Kpler R&C *Turning Tides* (Dec 2025)."
    )


def render_mpa_tier_exposure(df):
    """Donut of total risk_score split by MPA tier of the underlying event."""
    st.subheader("Risk exposure by MPA tier")
    st.caption(
        "Where the risk lives: total compounded risk split by the protected-area "
        "tier of each event's location. MPA tier is the only spatial-regulatory "
        "signal that enters the *base* score."
    )
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- Each donut slice = total compounded `risk_score` summed across every
  event whose location intersects an MPA of that tier.
- **GFCM FRA** (red): Fisheries Restricted Areas under EC 1967/2006.
  Strongest regulatory signal -- 2.0x base multiplier.
- **EU site** (orange): Natura 2000 marine sites and EU member-state MPAs.
  1.5x base multiplier.
- **Other WDPA** (light orange): general protected areas without EU/GFCM
  designation. 1.2x contextual multiplier.
- **Outside MPA** (grey): events on the high seas or in unprotected EEZ.
- Per McDonald 2024 (*Nature*), AIS-broadcast vessels are a lower bound:
  ~90% of fishing vessels detected inside MPAs by satellite radar do not
  broadcast AIS at all.
            """
        )
    if df.empty or "mpa_tier" not in df.columns:
        st.info("MPA tier column not available in current dataset.")
        return

    tier_labels = {
        "gfcm_fra": "GFCM FRA",
        "eu_site": "EU site",
        "general": "Other WDPA",
        "": "Outside MPA",
    }
    tier_colors = {
        "gfcm_fra": "#8B0000",
        "eu_site": "#E45756",
        "general": "#F58518",
        "": "#B0B0B0",
    }

    tier_series = df["mpa_tier"].fillna("").astype(str)
    risk_by_tier = df.assign(_tier=tier_series).groupby("_tier")["risk_score"].sum()
    risk_by_tier = risk_by_tier[risk_by_tier > 0]
    if risk_by_tier.empty:
        st.info("No risk scored in current filter window.")
        return

    labels = [tier_labels.get(t, t or "Outside MPA") for t in risk_by_tier.index]
    colors = [tier_colors.get(t, "#888") for t in risk_by_tier.index]

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=risk_by_tier.values,
        hole=0.55,
        marker=dict(colors=colors),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>Risk: %{value:.1f}<br>Share: %{percent}<extra></extra>",
        sort=False,
    )])
    fig.update_layout(
        height=380,
        title=f"Total risk score by MPA tier (sum: {float(risk_by_tier.sum()):.0f})",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    st.plotly_chart(fig, width="stretch")

    in_mpa_share = float(risk_by_tier.drop("", errors="ignore").sum()) / float(risk_by_tier.sum())
    st.markdown(
        f"**Read:** {in_mpa_share*100:.0f}% of total compounded risk comes from "
        "events that fell inside a WDPA-listed MPA. GFCM FRAs carry a 2.0x base "
        "multiplier, EU sites 1.5x, other WDPA 1.2x. "
        "*AIS-broadcast vessels inside MPAs are a lower bound -- per McDonald 2024 "
        "(Nature), ~90% of fishing vessels detected by satellite radar inside MPAs "
        "do not broadcast AIS at all.*"
    )


def render_top_vessels_segmented(df, top_n=10):
    """Top-N vessels horizontal bar with base + structural-amplifier segmentation.

    Vessel-centric counterpart to render_base_vs_compound_decomposition: same
    visual grammar, different question. Plot #1 shows the principle, this shows
    the worst actors. Both belong in the Ranking subtab because they tell the
    interviewer two things at once -- here is how scoring works, and here is who
    it singles out.
    """
    st.subheader(f"Top {top_n} vessels: base vs structural amplifier")
    st.caption(
        "Each bar splits a vessel's total risk into the behavioural base (left) "
        "and the structural amplifier delta from list lookups (right). Sorted by "
        "compounded risk total."
    )
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- One row per vessel, top to bottom = lowest to highest compounded risk
  in the top-N slice. Sorted by `risk_score_total` descending overall.
- **Blue segment** = `base_risk_score` summed across that vessel's events.
- **Red segment** = the additional risk added by IUU x ICCAT x OFAC list
  lookups (the gap between `risk_score` and `base_risk_score`).
- **A vessel with mostly red** is on a sanctions or IUU list -- the
  behavioural signal alone wouldn't put it on the list, but the structural
  multiplier amplifies whatever it does to the top.
- **A vessel with mostly blue** is a pure behavioural outlier -- it
  earned its position from event observation alone, with little or no
  list-based amplification.
- The hover shows exact base and amplifier values for each row.
            """
        )
    from charts import build_top_vessels_fig

    fig = build_top_vessels_fig(df, top_n)
    if fig is None:
        st.info("Base risk score not available or no vessels in current filter window.")
        return
    st.plotly_chart(fig, width="stretch")
    st.markdown(
        "**Read:** vessels with a long red segment owe most of their score to "
        "structural lookups (IUU listing, ICCAT carrier authorisation, OFAC "
        "sanctions). Vessels with little or no red segment are pure behavioural "
        "outliers."
    )


def render_fishing_in_mpa_map(df, fishing_df):
    """Scatter of GFW fishing events that fall inside an MPA.

    Sized by fishing_hours, coloured by mpa_tier. Gracefully handles small-N
    in static demo mode (5 events at last check) by showing a banner inviting
    the user to switch to live mode for denser data.
    """
    st.subheader("Fishing activity inside MPAs")
    st.caption(
        "GFW classified-fishing events that fell inside a WDPA-listed MPA. "
        "Display-only -- never scored into risk_score, because GFW's fishing "
        "classifier applies globally and would otherwise penalise legitimate EU "
        "fishing. Inside an MPA the same signal becomes the strongest publicly "
        "available IUU indicator."
    )
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- Each dot = one GFW *fishing* event (from the
  `public-global-fishing-events` feed) whose position fell inside a WDPA
  MPA polygon. The fishing classification is the Kroodsma 2018 CNN
  applied per AIS position.
- **Dot size** = duration of the fishing event in hours.
- **Dot colour** = MPA tier of the polygon the event fell into:
  red GFCM FRA, orange-red EU site, orange other WDPA.
- These events are **never** added to `risk_score`. They are shown as
  context because GFW's fishing classifier fires on every commercial
  fishing trip globally -- inside an MPA the same signal flips from
  background noise into the strongest publicly available IUU indicator.
- **Cross-reference**: vessels appearing here should match the
  `fishing_in_mpa_count > 0` column in the Ranking subtab.
- In static demo mode coverage is sparse (a handful of events). Switch
  to live GFW mode for the full picture.
- **AIS-based lower bound.** McDonald et al. 2024 (*Nature*) found
  approximately 90% of fishing vessels detected by satellite radar inside
  MPAs do not broadcast AIS. Vessels shown here broadcast openly inside
  protected areas -- a strong signal precisely because they did not go
  dark. The true number in violation is higher; this chart captures the
  tip of the iceberg.
            """
        )
    if fishing_df is None or fishing_df.empty:
        st.info("No GFW fishing events available in current dataset.")
        return

    in_mpa_col = "in_mpa" if "in_mpa" in fishing_df.columns else None
    mpa_col = "mpa" if "mpa" in fishing_df.columns else (
        "mpa_name" if "mpa_name" in fishing_df.columns else None
    )
    hours_col = "fishing_hours" if "fishing_hours" in fishing_df.columns else (
        "duration_h" if "duration_h" in fishing_df.columns else None
    )

    if in_mpa_col is None:
        st.info("`in_mpa` column not available on fishing_df.")
        return

    fim = fishing_df[fishing_df[in_mpa_col].fillna(False).astype(bool)].copy()
    n_events = len(fim)
    n_vessels = fim["mmsi"].nunique() if "mmsi" in fim.columns else 0

    if n_events == 0:
        st.info("No fishing-in-MPA events in current dataset.")
        return

    if n_events < 8:
        st.warning(
            f"Showing {n_events} fishing-in-MPA event(s) across {n_vessels} vessel(s) "
            "from the static demo dataset. Switch to live GFW mode for denser coverage."
        )

    tier_colors = {
        "gfcm_fra": "#8B0000",
        "eu_site": "#E45756",
        "general": "#F58518",
        "": "#888888",
    }
    if "mpa_tier" in fim.columns:
        fim["_tier"] = fim["mpa_tier"].fillna("").astype(str)
    else:
        fim["_tier"] = ""

    if hours_col and hours_col in fim.columns:
        fim["_hours"] = pd.to_numeric(fim[hours_col], errors="coerce").fillna(0.0)
        size_col = "_hours"
    else:
        fim["_hours"] = 1.0
        size_col = "_hours"

    hover_cols = [c for c in ["vessel_name", "flag", mpa_col, "_hours", "date"] if c and c in fim.columns]

    fig = px.scatter_map(
        fim,
        lat="lat", lon="lon",
        color="_tier",
        color_discrete_map=tier_colors,
        size=size_col, size_max=22,
        hover_data=hover_cols,
        zoom=4, height=500,
    )
    fig.update_layout(
        map_style="open-street-map",
        margin=dict(l=0, r=0, t=10, b=0),
        legend_title_text="MPA tier",
    )
    st.plotly_chart(fig, width="stretch")

    if hours_col and hours_col in fim.columns:
        total_h = float(pd.to_numeric(fim[hours_col], errors="coerce").fillna(0).sum())
        st.markdown(
            f"**Total fishing-in-MPA hours:** {total_h:.1f}h across "
            f"**{n_events} events** from **{n_vessels} vessels**."
        )


def render_vessel_class_composition(df):
    """Donut of unique vessels per descriptive vessel_class.

    The fleet shape at a glance: how many of the vessels in the current
    filter window are industrial fishing, artisanal fishing, carriers,
    tankers, cargo, support, etc. Class is derived from registry shiptypes
    falling back to event-level vessel_type. Empty classes are folded into
    `other`.
    """
    st.subheader("Fleet composition by vessel class")
    st.caption(
        "Distribution of unique vessels by descriptive vessel class. "
        "Class is derived from the GFW Vessels API `shiptypes` field "
        "(falling back to event-level `vessel_type` when shiptypes is empty)."
    )
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- One slice per **vessel_class**: industrial_fishing, artisanal_fishing,
  carrier, tanker, cargo, support, passenger, other.
- Slice value = unique vessel count (deduplicated by `mmsi`).
- This is **descriptive** -- it does not contribute to the risk score.
  It exists to give context: a fleet dominated by carriers tells a
  different story from one dominated by industrial fishing vessels.
- `industrial_fishing` here is *category-based* (gear/type), not
  *size-based*. A small vessel can still classify as industrial fishing
  on this axis while being `is_industrial=False` on the size axis.
            """
        )
    if df.empty or "vessel_class" not in df.columns:
        st.info("Vessel class column not available in current dataset.")
        return

    per_vessel = df.drop_duplicates("mmsi")
    counts = per_vessel["vessel_class"].fillna("").replace("", "other").value_counts()
    if counts.empty:
        st.info("No vessel-class data in current filter window.")
        return

    class_colors = {
        "industrial_fishing": "#1f77b4",
        "artisanal_fishing":  "#aec7e8",
        "carrier":            "#d62728",
        "tanker":             "#ff7f0e",
        "cargo":              "#9467bd",
        "support":            "#8c564b",
        "passenger":          "#e377c2",
        "other":              "#7f7f7f",
    }
    colors = [class_colors.get(c, "#888") for c in counts.index]

    fig = go.Figure(data=[go.Pie(
        labels=counts.index.tolist(),
        values=counts.values,
        hole=0.55,
        marker=dict(colors=colors),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>Vessels: %{value}<br>Share: %{percent}<extra></extra>",
        sort=False,
    )])
    fig.update_layout(
        height=380,
        title=f"Fleet composition ({int(counts.sum())} unique vessels)",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    st.plotly_chart(fig, width="stretch")


def render_type_mismatch_by_class(df):
    """Horizontal bar of vessel_type_mismatch counts grouped by vessel_class.

    Surfaces where misrepresentation concentrates. If all the mismatches sit
    in one class (e.g. cargo vessels misreporting as fishing) that's the
    headline. If they're spread across classes, that's a different and
    weaker pattern. Either way the chart answers the question.
    """
    st.subheader("Vessel type misrepresentation by class")
    st.caption(
        "How many vessels in each class have a mismatch between their "
        "event-level `vessel_type` (often AIS self-reported) and their "
        "registry-level `shiptypes` (GFW Vessels API)."
    )
    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            """
- Each bar = number of unique vessels in that **vessel_class** with
  `vessel_type_mismatch == True`.
- A mismatch fires only when both fields are populated *and* normalise
  to different canonical classes -- spelling differences ("TRAWLER" vs
  "FISHING") do not fire because comparison is class-level, not
  string-level.
- A mismatch is the textbook **misrepresentation signal** from Kpler's
  Grey Fleet paper: a vessel that broadcasts one identity in AIS while
  the registry records another. Common shadow-fleet tactic to evade
  port-state controls.
- In static demo mode you should see exactly two mismatches: one in
  `cargo` (the obvious IUU case) and one in `carrier` (the subtle
  ICCAT-authorised case). In live mode the picture will depend on
  what GFW resolves for each MMSI.
- **Cross-reference**: vessels with mismatch=True should also appear
  with the type-mismatch flag set in the Ranking subtab.
- **Class-level comparison.** Mismatch fires on canonical-class
  disagreement after normalisation -- TRAWLER and FISHING both map to
  `industrial_fishing`, so spelling variants do not trigger the flag.
  Only true category disagreement surfaces, e.g. a vessel broadcasting
  FISHING in its AIS self-reported data while its registry record says
  CARGO. This is the open-data equivalent of Kpler's "irregular vessel
  information" indicator from the *Grey Fleet* paper (March 2025).
            """
        )
    if df.empty or "vessel_type_mismatch" not in df.columns or "vessel_class" not in df.columns:
        st.info("Vessel type-mismatch columns not available in current dataset.")
        return

    per_vessel = df.drop_duplicates("mmsi")
    n_mm = int(per_vessel["vessel_type_mismatch"].fillna(False).astype(bool).sum())
    if n_mm == 0:
        st.info(
            "No vessel-type mismatches in current filter window. "
            "In static demo mode you should normally see two -- if you've "
            "filtered them out via the date range, widen the window."
        )
        return

    mm_by_class = (
        per_vessel[per_vessel["vessel_type_mismatch"].fillna(False).astype(bool)]
        .groupby("vessel_class")
        .size()
        .sort_values(ascending=True)
    )

    fig = go.Figure(data=[go.Bar(
        x=mm_by_class.values,
        y=mm_by_class.index.tolist(),
        orientation="h",
        marker_color="#E45756",
        text=mm_by_class.values,
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Mismatched vessels: %{x}<extra></extra>",
    )])
    fig.update_layout(
        height=max(220, 60 * len(mm_by_class) + 80),
        title=f"Vessel-type mismatches by class ({n_mm} total mismatched vessels)",
        xaxis_title="Mismatched vessel count",
        margin=dict(l=20, r=20, t=50, b=20),
    )
    st.plotly_chart(fig, width="stretch")

    # Show the actual mismatched vessels for context
    detail = per_vessel[per_vessel["vessel_type_mismatch"].fillna(False).astype(bool)][
        [c for c in ["vessel_name", "flag", "vessel_type", "shiptypes", "vessel_class"]
         if c in per_vessel.columns]
    ].reset_index(drop=True)
    if not detail.empty:
        st.caption("Mismatched vessels in current filter window:")
        st.dataframe(detail, width="stretch")


def render_vessel_trajectory(vessel_events: pd.DataFrame, vessel_summary_row: dict):
    """Cumulative risk trajectory for a single vessel over the observation window.

    Line chart of cumulative risk_score over time, one point per event.
    Reference lines at risk band thresholds. Event markers coloured by
    event type. Shows the behavioural arc -- when the vessel accumulated
    which risk, and when it crossed band boundaries.
    """
    import plotly.graph_objects as go

    st.subheader("Risk trajectory")
    st.caption(
        "Cumulative risk score over time. Each marker is an event; the line "
        "shows running total. Dashed horizontal lines are band thresholds."
    )

    with st.expander("How to read this chart", expanded=False):
        st.markdown(
            "- **Line**: cumulative `risk_score` across all events in chronological "
            "order. Steep jumps mean high-risk events; flat sections mean quiet "
            "periods.\n"
            "- **Markers**: individual events, coloured by event type (gap, "
            "encounter, loitering). Hover for event detail.\n"
            "- **Dashed horizontal lines**: risk band thresholds -- "
            "50 (Emerging), 60 (Elevated), 80 (Severe), 100 (Critical).\n"
            "- **Read**: where does the vessel's line cross each threshold, and "
            "which event type dominated that section? That's the behavioural arc."
        )

    from charts import build_trajectory_fig

    fig = build_trajectory_fig(vessel_events, vessel_summary_row)
    if fig is None:
        st.info("No events for this vessel in the current filter window.")
        return

    st.plotly_chart(fig, width="stretch")

    # Summary caption
    time_col = "start_time" if "start_time" in vessel_events.columns else "date"
    events = vessel_events.copy()
    events["_time"] = pd.to_datetime(events[time_col], errors="coerce")
    events = events.dropna(subset=["_time", "risk_score"]).sort_values("_time")
    if not events.empty:
        final_cum = events["risk_score"].cumsum().iloc[-1]
        event_count = len(events)
        first_date = events["_time"].iloc[0].strftime("%Y-%m-%d")
        last_date = events["_time"].iloc[-1].strftime("%Y-%m-%d")
        st.markdown(
            f"**Trajectory summary:** {event_count} events between {first_date} and "
            f"{last_date}, accumulating to total risk {final_cum:.1f}. "
            "Band crossings readable from where the line intersects the dashed thresholds."
        )


def render_vessel_investigation(df, iuu_df, iccat_df, ofac_df, fdi_effort, fdi_landings, fishing_df=None):
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
    current_inv = st.session_state.get("investigation_vessel")
    if map_clicked and map_clicked in vessel_options and map_clicked != current_inv:
        # Seed the selectbox key so it opens on the map-clicked vessel.
        # Keep map_clicked_vessel in session state so the map (rendered
        # above the tabs) stays filtered to this vessel.
        st.session_state["investigation_vessel"] = map_clicked
    elif "investigation_vessel" not in st.session_state:
        st.session_state["investigation_vessel"] = vessel_options[0]

    selected = st.selectbox(
        "Select vessel to investigate",
        options=vessel_options,
        help="Vessels are ordered by total risk score (highest first). "
             "Click a marker on the map or use the quick-select table below "
             "to pick a vessel.",
        key="investigation_vessel",
    )
    # --- Compact vessel summary table (click a row to switch) ---
    with st.expander("Vessel quick-select table", expanded=False):
        _grouped = df.dropna(subset=["vessel_name"]).groupby("vessel_name")
        _compact_rows = []
        for _vn, _vg in _grouped:
            _risk = float(_vg["risk_score"].sum())
            _compact_rows.append({
                "vessel_name": _vn,
                "flag": _vg["flag"].dropna().iloc[0] if _vg["flag"].notna().any() else "",
                "events": len(_vg),
                "risk_score": round(_risk, 1),
                "risk_band": classify_risk_band(_risk),
                "iuu": bool(_vg["iuu_matched"].any()) if "iuu_matched" in _vg.columns else False,
                "ofac": bool(_vg["ofac_sanctioned"].any()) if "ofac_sanctioned" in _vg.columns else False,
            })
        _compact_df = (
            pd.DataFrame(_compact_rows)
            .sort_values("risk_score", ascending=False)
            .reset_index(drop=True)
        )
        _compact_styled = _compact_df.style.format({"risk_score": "{:.1f}"}).map(
            lambda v: f"background-color: {RISK_BAND_COLORS.get(v, '')}; color: white"
            if v in RISK_BAND_COLORS else "",
            subset=["risk_band"],
        )
        # Highlight currently selected vessel
        if selected:
            def _hl_inv(row):
                if row["vessel_name"] == selected:
                    return ["background-color: #e0f0ff"] * len(row)
                return [""] * len(row)
            _compact_styled = _compact_styled.apply(_hl_inv, axis=1)

        _inv_sel = st.dataframe(
            _compact_styled,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key="investigation_quick_table",
        )
        _sel_rows = (
            _inv_sel.selection.rows
            if _inv_sel is not None and hasattr(_inv_sel, "selection")
            else []
        )
        if _sel_rows:
            _picked = _compact_df.iloc[_sel_rows[0]]["vessel_name"]
            if _picked and _picked != selected:
                # Write to map_clicked_vessel only — the selectbox key
                # cannot be modified after the widget is instantiated.
                # On rerun the map_clicked logic at the top of this
                # function will seed investigation_vessel BEFORE the
                # selectbox renders.
                st.session_state["map_clicked_vessel"] = _picked
                st.rerun()

    report = investigate_vessel(selected, df, iuu_df, iccat_df, ofac_df, fdi_effort, fdi_landings, fishing_df=fishing_df)

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
    cols = st.columns(6)
    cols[0].metric("Vessel", report["identity"]["vessel_name"])
    cols[1].metric("MMSI", report["identity"]["mmsi"])
    # IMO is only mandatory for vessels >=100 GT (IMO Convention SOLAS Ch XI-1
    # Reg 3). Below the threshold, an absent IMO is normal -- not a red flag.
    _imo_val = report["identity"]["imo"]
    _is_artisanal = (
        not report["identity"].get("is_industrial")
        and (report["identity"].get("length_m") or report["identity"].get("tonnage_gt"))
    )
    if _imo_val:
        _imo_display = _imo_val
    elif _is_artisanal:
        _imo_display = "Not required"
    else:
        _imo_display = "Unknown"
    cols[2].metric("IMO", _imo_display)
    cols[3].metric("Flag", report["identity"]["flag"])
    cols[4].metric("Events", report["identity"]["events_in_dataset"])
    # Profile: length / GT, with industrial badge if above the ICCAT threshold
    _length = report["identity"].get("length_m")
    _tonnage = report["identity"].get("tonnage_gt")
    if _length and _tonnage:
        _profile_str = f"{_length:.0f}m / {_tonnage:.0f} GT"
    elif _length:
        _profile_str = f"{_length:.0f}m"
    elif _tonnage:
        _profile_str = f"{_tonnage:.0f} GT"
    else:
        _profile_str = "Unknown"
    _industrial_label = "Industrial" if report["identity"].get("is_industrial") else (
        "Artisanal" if (_length or _tonnage) else ""
    )
    cols[5].metric(
        "Profile",
        _profile_str,
        delta=_industrial_label or None,
        delta_color="off",
    )

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
        st.dataframe(fisheries_df, width="stretch", hide_index=True)
        st.caption(
            f"Per-event FDI context across {len(fisheries_rows)} event(s). "
            "Fishing ground = c-square has reported EU fleet activity in the FDI dataset."
        )
    else:
        st.info("No FDI fisheries context available for this vessel's events.")

    # Step 5b: Fishing activity inside MPAs (display-only signal)
    st.markdown("### 5b. Fishing Activity Inside MPAs")
    st.caption(
        "GFW-classified FISHING events for this vessel, intersected with the WDPA "
        "via GFW's `regions.mpa` field. This is GFW's own neural-network classification "
        "of active fishing (Kroodsma et al. 2018) -- not behavioural inference -- and "
        "is the strongest publicly available signal for IUU fishing inside protected "
        "areas. Display-only: not multiplied into the risk score, because legitimate "
        "fishing outside MPAs is normal and only fishing inside protected zones is the "
        "actionable IUU signal."
    )
    fishing_section = report.get("fishing_in_mpa") or {}
    fim_total_events = int(fishing_section.get("event_count", 0))
    fim_total_hours = float(fishing_section.get("hours", 0.0))
    fim_top_tier = str(fishing_section.get("top_tier", ""))
    if fim_total_events > 0:
        fcol_a, fcol_b, fcol_c = st.columns(3)
        fcol_a.metric("Fishing events in MPA", fim_total_events)
        fcol_b.metric("Total fishing hours", f"{fim_total_hours:.1f}")
        fcol_c.metric("Highest tier", fim_top_tier or "general")
        mpa_names = fishing_section.get("mpa_names", []) or []
        if mpa_names:
            st.write("**MPAs intersected by fishing activity:** " + "; ".join(mpa_names[:5]))
        ev_rows = fishing_section.get("events", []) or []
        if ev_rows:
            ev_df = pd.DataFrame(ev_rows)
            keep_cols = [c for c in ["date", "lat", "lon", "fishing_hours", "mpa", "mpa_tier"] if c in ev_df.columns]
            st.dataframe(ev_df[keep_cols], width="stretch", hide_index=True)
    else:
        st.info("No GFW fishing events recorded inside an MPA for this vessel in the current dataset.")

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

    # Step 6b: behavioural flags (display-only, do not multiply into risk_score)
    st.markdown("### 6b. Behavioural Flags")
    st.caption(
        "Three compound/temporal flags derived directly from GFW event data. "
        "Display-only -- these are not multiplied into the risk score, to avoid "
        "double-counting with signals already captured at the event level."
    )
    # Resolve flags by MMSI from the investigation report (authoritative),
    # not by re-matching on vessel_name. This guarantees the flags shown here
    # correspond to the SAME MMSI the rest of the report is describing.
    investigated_mmsi = str(report["identity"].get("mmsi", ""))
    if investigated_mmsi and "mmsi" in df.columns:
        vessel_rows_for_flags = df[df["mmsi"].astype(str) == investigated_mmsi]
    else:
        vessel_rows_for_flags = df.iloc[0:0]
    multi_behaviour = bool(vessel_rows_for_flags["multi_behaviour_flag"].any()) if "multi_behaviour_flag" in vessel_rows_for_flags.columns else False
    dark_port_candidates = int(vessel_rows_for_flags["dark_port_call_candidate"].sum()) if "dark_port_call_candidate" in vessel_rows_for_flags.columns else 0
    repeat_offender = bool(vessel_rows_for_flags["repeat_offender_90d"].any()) if "repeat_offender_90d" in vessel_rows_for_flags.columns else False
    fcol1, fcol2, fcol3 = st.columns(3)
    fcol1.metric(
        "Multi-behaviour",
        "Yes" if multi_behaviour else "No",
        help="Vessel shows two or more distinct event types (gap, encounter, loitering).",
    )
    fcol2.metric(
        "Dark Port Call Candidates",
        dark_port_candidates,
        help="Count of loitering events within 10 km of shore. AIS-inferred, not satellite-verified.",
    )
    fcol3.metric(
        "Repeat Offender (90d)",
        "Yes" if repeat_offender else "No",
        help="Two or more events within any 90-day window. Exposure drift concept.",
    )

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
            "Expand each branch below to see which questions raised concerns "
            "and which rules fired. The full Graphviz diagram is available "
            "in the expander at the bottom if you prefer the spatial view."
        )

        vessel_label = (
            f"{report['identity']['vessel_name']}\n"
            f"{report['identity']['flag']} | {report['identity']['vessel_type'] or 'Unknown type'}"
        )

        # Interactive trace: one collapsible expander per branch, with a
        # severity summary in the header. Click a branch to reveal the
        # individual questions (leaves) underneath. Each leaf is rendered
        # as a compact card with a colour strip instead of a raw dataframe
        # row, so the visual scan is cleaner than a wall of tables.
        _SEV_COLORS = {
            "none": "#81C784",     # green
            "low": "#FFF176",      # yellow
            "medium": "#FFB74D",   # orange
            "high": "#E57373",     # red
            "critical": "#B71C1C", # dark red
        }
        _SEV_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        _SEV_ICONS = {
            "none": "OK", "low": "LOW", "medium": "MED", "high": "HIGH", "critical": "CRIT",
        }
        _BRANCH_NAMES = {
            "identity": "Identity Verification",
            "flag_risk": "Flag State Risk",
            "regulatory_status": "Regulatory Status",
            "authorization": "Fishing Authorization",
            "behavioural_history": "Behavioural History",
            "spatial_context": "Spatial / Contextual",
            "fishing_activity": "Fishing Activity",
            "network_exposure": "Network Exposure",
        }

        st.markdown("#### Evaluation trace")
        st.caption(
            "One expander per risk tree branch. The header shows the worst "
            "severity found in that branch and how many rules fired. "
            "Click a branch to drill into the individual questions (leaves) "
            "that were evaluated for this vessel."
        )

        # Group trace entries by branch, preserving the original order.
        from collections import OrderedDict
        branches = OrderedDict()
        for entry in report["trace"]:
            bid = entry["branch_id"]
            if bid not in branches:
                branches[bid] = []
            branches[bid].append(entry)

        for bid, entries in branches.items():
            branch_label = _BRANCH_NAMES.get(bid, bid)
            fired_count = sum(1 for e in entries if e.get("rule_fired"))
            total = len(entries)
            worst_sev = max(
                (e.get("severity", "none") for e in entries),
                key=lambda s: _SEV_RANK.get(s, 0),
                default="none",
            )
            sev_tag = _SEV_ICONS.get(worst_sev, "OK")
            # Emoji-free, monospace-friendly header
            header = f"[{sev_tag}] {branch_label}  ·  {fired_count}/{total} rules fired"
            # Auto-expand only if something fired in this branch
            with st.expander(header, expanded=(fired_count > 0)):
                for e in entries:
                    sev = e.get("severity", "none")
                    bg = _SEV_COLORS.get(sev, "#EEEEEE")
                    fg = "white" if sev in ("high", "critical") else "#222"
                    q = e.get("question_id", "?").replace("_", " ").title()
                    a = str(e.get("answer", "?")).upper()
                    note = e.get("note", "")
                    fired = e.get("rule_fired", False)
                    # Card: left colour strip + question/answer/note block
                    card = (
                        f"<div style='display:flex;align-items:stretch;"
                        f"margin:6px 0;border-radius:4px;overflow:hidden;"
                        f"border:1px solid #ddd;'>"
                        f"<div style='width:6px;background:{bg};'></div>"
                        f"<div style='padding:8px 12px;flex:1;background:#FAFAFA;'>"
                        f"<div style='font-weight:600;color:#222;'>{q}</div>"
                        f"<div style='font-size:12px;color:#555;margin-top:2px;'>"
                        f"Answer: <span style='background:{bg};color:{fg};"
                        f"padding:1px 6px;border-radius:3px;font-weight:600;'>{a}</span>"
                        f"{'  ·  <span style=\"color:#B71C1C;font-weight:600;\">rule fired</span>' if fired else ''}"
                        f"</div>"
                        f"<div style='font-size:12px;color:#444;margin-top:4px;'>{note}</div>"
                        f"</div></div>"
                    )
                    st.markdown(card, unsafe_allow_html=True)

        # Interactive Plotly icicle. Two-level hierarchy: branch -> leaf.
        # Click any branch to zoom into its leaves; click the centre
        # breadcrumb to zoom back out. Severity is colour-encoded with
        # the same palette as the card view above.
        with st.expander("Show interactive risk tree (click to drill in)", expanded=False):
            try:
                from charts import build_icicle_fig

                fig_icicle = build_icicle_fig(
                    trace=report["trace"],
                    vessel_name=report["identity"]["vessel_name"],
                    threat_level=report["assessment"]["threat_level"],
                )
                if fig_icicle:
                    st.plotly_chart(fig_icicle, width="stretch")
                else:
                    st.info("No risk tree data for this vessel.")
            except Exception as e:
                st.warning(f"Icicle render error: {e}")

        # Full Graphviz diagram, tucked into a collapsed expander so it
        # does not dominate the tab. Kept for users who prefer the
        # spatial view over the per-branch card cards.
        with st.expander("Show full risk tree diagram (Graphviz)", expanded=False):
            try:
                dot_vessel = render_framework_tree(
                    trace=report["trace"],
                    tier=report["assessment"]["threat_level"],
                    vessel_label=vessel_label,
                )
                st.graphviz_chart(dot_vessel)
            except Exception as e:
                st.warning(f"Per-vessel tree render error: {e}")

    # --- Risk trajectory ---
    vessel_events_for_traj = df[df["vessel_name"].astype(str).str.upper() == str(selected).upper()]
    render_vessel_trajectory(vessel_events_for_traj, report.get("identity", {}))

    # --- Case file export ---
    st.markdown("---")
    st.subheader("Export case file")
    st.caption(
        "Download a Markdown case file for this vessel, suitable for "
        "analyst case archives or forwarding to a client."
    )

    from exports import generate_vessel_case_file
    from datetime import datetime as _dt

    identity = report.get("identity", {})
    risk = report.get("risk", {})
    base_total = float(
        vessel_rows_for_flags["base_risk_score"].sum()
    ) if "base_risk_score" in vessel_rows_for_flags.columns else 0.0
    risk_total = risk.get("total_risk_score", 0)
    compound_val = round(risk_total / base_total, 2) if base_total > 0 else 1.0

    case_row = {
        "vessel_name": identity.get("vessel_name", selected),
        "flag": identity.get("flag", ""),
        "imo": identity.get("imo", ""),
        "vessel_class": identity.get("vessel_class", ""),
        "risk_band": report.get("assessment", {}).get("threat_level", "Unknown"),
        "risk_score_total": risk_total,
        "base_score_total": base_total,
        "compound_multiplier": compound_val,
        "iuu_matched": report.get("iuu", {}).get("matched", False),
        "iccat_authorized": report.get("iccat", {}).get("authorized", False),
        "ofac_sanctioned": report.get("ofac", {}).get("sanctioned", False),
        "is_industrial": bool(
            vessel_rows_for_flags["is_industrial"].any()
        ) if "is_industrial" in vessel_rows_for_flags.columns else False,
        "multi_behaviour_flag": multi_behaviour,
        "dark_port_call_candidate": dark_port_candidates,
        "repeat_offender_90d": repeat_offender,
        "vessel_type_mismatch": identity.get("vessel_type_mismatch", False),
    }

    case_md = generate_vessel_case_file(
        mmsi=investigated_mmsi,
        vessel_summary_row=case_row,
        vessel_events=vessel_rows_for_flags,
        trace=report.get("trace", []),
    )

    from exports import generate_vessel_case_html
    case_html = generate_vessel_case_html(
        mmsi=investigated_mmsi,
        vessel_summary_row=case_row,
        vessel_events=vessel_rows_for_flags,
        trace=report.get("trace", []),
    )

    safe_name = str(case_row["vessel_name"]).replace(" ", "_").replace("/", "_")[:50]
    fn_md = f"case_file_{safe_name}_{_dt.utcnow().strftime('%Y%m%d')}.md"
    fn_html = f"case_file_{safe_name}_{_dt.utcnow().strftime('%Y%m%d')}.html"

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.download_button(
            label="Download case file (Markdown)",
            data=case_md,
            file_name=fn_md,
            mime="text/markdown",
        )
    with col_d2:
        st.download_button(
            label="Download case file (HTML)",
            data=case_html,
            file_name=fn_html,
            mime="text/html",
        )

    with st.expander("Preview case file"):
        st.markdown(case_md)


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
    from risk_tree import load_framework, render_framework_tree, render_scoring_pipeline_diagram

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

    # 2b. Network exposure leaves (associative risk layer)
    with st.expander("Network exposure leaves (associative risk)", expanded=False):
        st.markdown(
            "Five encounter-partner leaves in the `network_exposure` branch evaluate "
            "associative risk for each vessel. These fire in the risk tree and appear "
            "in the Vessel Investigation narrative but are **not** multiplied into the "
            "numeric risk score.\n\n"
            "| Leaf | Severity | Signal |\n"
            "|------|----------|--------|\n"
            "| `encounter_iuu_vessel` | high | Partner name on TMT Combined IUU list (13 RFMOs) |\n"
            "| `encounter_sanctioned_vessel` | critical | Partner name on OFAC SDN list |\n"
            "| `encounter_weak_cooperation_partner` | medium | Partner flag LBY or SYR (GFCM non-compliance) |\n"
            "| `encounter_distant_water_partner` | medium | Partner flag not EU and not Med coastal |\n"
            "| `encounter_pattern_recurrence` | medium | Same counterparty 2+ times within 90 days |\n\n"
            "The first four are identity-based (who did the vessel meet); the fifth is "
            "temporal (how often). Fleet-network propagation and ownership graph remain "
            "future work (`shared_ownership` stub)."
        )

    # 3. Risk formula
    st.markdown("### Risk Formula")
    st.markdown(content["risk_formula_explanation"])
    st.code(
        "base = (duration_h ^ 0.75)\n"
        "     x event_weight\n"
        "     x flag_multiplier\n"
        "     x shore_factor\n"
        "     x mpa_tier_multiplier\n"
        "     x event_specific_factors\n"
        "\n"
        "final_score = base\n"
        "     x iuu_multiplier\n"
        "     x iccat_multiplier\n"
        "     x ofac_multiplier",
        language="text",
    )

    # End-to-end scoring pipeline diagram: AIS event -> base -> compounding
    # multipliers -> per-event score -> vessel aggregation -> risk band,
    # with a dashed side-chain for the three display-only vessel flags.
    with st.expander("End-to-end scoring pipeline (diagram)", expanded=True):
        st.caption(
            "How one AIS event becomes a per-vessel risk band. The main "
            "column is the multiplicative chain that produces the risk "
            "score; the dashed side-chain shows the four vessel-level "
            "behavioural flags (industrial profile, multi-behaviour, dark "
            "port call candidate, repeat offender), which are displayed "
            "alongside the score but are **not** multiplied into it."
        )
        try:
            st.graphviz_chart(render_scoring_pipeline_diagram())
        except Exception as e:
            st.warning(f"Could not render scoring pipeline diagram: {e}")

    bands_df = pd.DataFrame(
        [
            {
                "Band": label,
                "Lower bound": str(low),
                "Upper bound": ("\u221e" if high == float("inf") else str(high)),
                "Meaning": desc,
            }
            for low, high, label, desc in RISK_BANDS
        ]
    )
    st.markdown("**Risk bands (applied to final compounded score)**")
    st.dataframe(bands_df, width="stretch", hide_index=True)

    # 4. Multiplier tables (collapsed)
    with st.expander("Multiplier tables (from config.py)", expanded=False):
        src_yr = f" (source: IUU Fishing Index {FLAG_RISKS_SOURCE_YEAR})" if FLAG_RISKS_SOURCE_YEAR else ""
        st.markdown(f"**Flag risk multipliers** — applied to every event on the flag{src_yr}")
        flag_df = (
            pd.DataFrame(
                [{"Flag (ISO3)": k, "Multiplier": round(v, 3)} for k, v in FLAG_RISKS.items()]
            )
            .sort_values("Multiplier", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(flag_df, width="stretch", hide_index=True, height=300)
        st.caption("Derived from the Poseidon IUU Fishing Risk Index — 10 Flag-responsibility indicators per country. Flags not in the Index carry a 1.0x multiplier (neutral).")

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
        st.dataframe(iuu_df, width="stretch", hide_index=True)

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
        st.dataframe(iccat_df, width="stretch", hide_index=True)

        st.markdown("**OFAC sanctions multiplier** — applied on OFAC SDN match")
        ofac_df = pd.DataFrame(
            [
                {
                    "Listing": "OFAC SDN (Specially Designated Nationals)",
                    "Multiplier": OFAC_MULTIPLIER,
                }
            ]
        )
        st.dataframe(ofac_df, width="stretch", hide_index=True)

        st.markdown(
            "**MPA intersection multipliers** — applied to the base behavioural "
            "score (spatial rule-zone signal, not a list lookup). Data from "
            "GFW `regions.mpa` (WDPA point-in-polygon, computed server-side)."
        )
        _MPA_LABELS = {
            "gfcm_fra": "GFCM Fisheries Restricted Area (legally binding, Reg 1967/2006)",
            "eu_site":  "EU-designated (Natura 2000, Pelagos Sanctuary, national MPAs)",
            "general":  "Other WDPA entry (contextual signal only)",
        }
        mpa_df = pd.DataFrame(
            [
                {
                    "Tier": _MPA_LABELS.get(k, k),
                    "Key": k,
                    "Multiplier": v,
                }
                for k, v in MPA_MULTIPLIERS.items()
            ]
        ).sort_values("Multiplier", ascending=False).reset_index(drop=True)
        st.dataframe(mpa_df, width="stretch", hide_index=True)

    # 5. ICCAT framing note
    with st.expander("ICCAT framing note", expanded=False):
        st.markdown(content["iccat_framing_note"])

    # 5a. MPA framing note (spatial rule-zone signal, calibration, AIS caveat)
    if "mpa_framing_note" in content:
        with st.expander("MPA intersection and calibration note", expanded=False):
            st.markdown(content["mpa_framing_note"])

    # 5a-bis. Fishing-in-MPA framing note (separate GFW dataset, display-only signal)
    if "fishing_in_mpa_note" in content:
        with st.expander("Fishing-in-MPA framing note", expanded=False):
            st.markdown(content["fishing_in_mpa_note"])

    # 5b. Sanctions authority note (IUU list coverage, EU vs OFAC, authority tagging)
    if "sanctions_authority_note" in content:
        with st.expander("Sanctions and IUU-list authority note", expanded=False):
            st.markdown(content["sanctions_authority_note"])

    # 6. Data source provenance
    with st.expander("Data source provenance", expanded=False):
        prov_df = pd.DataFrame(content["data_source_provenance"])
        prov_df.columns = [c.capitalize() for c in prov_df.columns]
        st.dataframe(prov_df, width="stretch", hide_index=True)

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
