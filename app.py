import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import plotly.express as px
from datetime import datetime, timedelta
import asyncio
import os

# ========================= CONFIG & SETUP =========================
st.set_page_config(
    page_title="Med Vessel Behaviour Monitor",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Med Vessel Behaviour Monitor")
st.markdown("**Behavioral risk intelligence for the Mediterranean Sea** — AIS gaps, encounters and loitering events")

st.sidebar.header("Filters & Controls")

# Token input
try:
    token = st.secrets["gfw_token"]
except (FileNotFoundError, KeyError):
    token = st.sidebar.text_input("GFW API Token (free)", type="password", help="Register at globalfishingwatch.org → Our APIs")

use_live = st.sidebar.toggle("Use Live GFW API", value=False, help="Requires valid token. Static demo data is always available.")

date_range = st.sidebar.date_input(
    "Date range",
    value=(datetime(2026, 3, 1), datetime(2026, 3, 31)),
    min_value=datetime(2024, 1, 1),
    max_value=datetime.today()
)

if len(date_range) < 2:
    st.warning("Please select both start and end dates.")
    st.stop()

min_duration = st.sidebar.slider("Minimum event duration (hours)", 2, 48, 12)

# Advanced: editable risk weights
with st.sidebar.expander("Advanced — Risk Weights (optional)"):
    gap_weight = st.number_input("Gap weight", value=3.2, min_value=0.1, step=0.1)
    loitering_weight = st.number_input("Loitering weight", value=2.0, min_value=0.1, step=0.1)
    encounter_weight = st.number_input("Encounter weight", value=5.0, min_value=0.1, step=0.1)

# ========================= DATA LOADING =========================
@st.cache_data
def load_static_data():
    """Proper static fallback dataset (80 realistic Med events)."""
    csv_path = os.path.join(os.path.dirname(__file__), "data", "med_events_static.csv")
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path, parse_dates=["date"])

    rng = np.random.default_rng(42)

    n = 80
    event_types = (["GAP"] * 25 + ["LOITERING"] * 30 + ["ENCOUNTER"] * 25)
    flags = (["RUS"] * 12 + ["IRN"] * 8 + ["PAN"] * 15 + ["LBR"] * 15
             + ["GRC"] * 10 + ["TUR"] * 8 + ["ITA"] * 7 + ["MLT"] * 5)

    # Duration ranges by event type (hours)
    dur_map = {"GAP": (6, 72), "LOITERING": (4, 48), "ENCOUNTER": (2, 12)}
    durations = [round(rng.uniform(*dur_map[et]), 1) for et in event_types]

    # Sea-only coordinate clusters — tightly bounded to open water
    sea_zones = [
        # (lat_min, lat_max, lon_min, lon_max)
        (35.5, 37.0, -1.0, 3.0),    # Alboran Sea
        (38.0, 39.5, 5.0, 8.0),     # west of Sardinia
        (36.0, 38.0, 9.0, 13.0),    # Tyrrhenian Sea
        (33.5, 35.5, 12.0, 16.0),   # central Med / off Libya
        (35.0, 36.5, 17.0, 20.0),   # Ionian Sea
        (34.5, 35.5, 22.0, 27.0),   # south of Crete (open water)
        (33.0, 34.5, 30.0, 34.0),   # Levantine basin (off Egypt)
    ]
    zone_idx = rng.integers(0, len(sea_zones), size=n)
    lats = np.array([rng.uniform(sea_zones[z][0], sea_zones[z][1]) for z in zone_idx]).round(2)
    lons = np.array([rng.uniform(sea_zones[z][2], sea_zones[z][3]) for z in zone_idx]).round(2)

    # Dates spread across a 30-day window
    base = datetime(2026, 3, 1)
    dates = [(base + timedelta(days=int(d))).strftime("%Y-%m-%d")
             for d in rng.integers(0, 30, size=n)]

    # Unique MMSIs (9-digit, realistic range)
    mmsis = rng.integers(200000000, 800000000, size=n)

    df = pd.DataFrame({
        "event_type": event_types,
        "mmsi": mmsis,
        "flag": flags,
        "duration_h": durations,
        "lat": lats,
        "lon": lons,
        "date": dates,
    })
    return df

@st.cache_data
def load_live_data(token, start_date, end_date, _min_dur):
    """Fetch events from GFW Events API (async client, April 2025 package)."""
    try:
        import gfwapiclient as gfw

        gfw_client = gfw.Client(access_token=token)

        datasets = [
            "public-global-gaps-events:latest",
            "public-global-encounters-events:latest",
            "public-global-loitering-events:latest",
        ]

        # Mediterranean bounding box as GeoJSON polygon
        med_geometry = {
            "type": "Polygon",
            "coordinates": [[[-6, 30], [36.5, 30], [36.5, 46], [-6, 46], [-6, 30]]],
        }

        async def _fetch():
            result = await gfw_client.events.get_all_events(
                datasets=datasets,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                geometry=med_geometry,
                limit=5000,
            )
            return result.df()

        df = asyncio.run(_fetch())

        if df.empty:
            st.warning("No events returned from API for this period.")
            return load_static_data()

        # Normalise columns to match our static schema
        df = df.rename(columns={"type": "event_type", "start": "date"})

        # Extract lat/lon from nested position dict
        if "position" in df.columns:
            df["lat"] = df["position"].apply(lambda p: p.get("lat") if isinstance(p, dict) else None)
            df["lon"] = df["position"].apply(lambda p: p.get("lon") if isinstance(p, dict) else None)

        # Extract flag from nested vessel dict
        if "vessel" in df.columns:
            df["flag"] = df["vessel"].apply(lambda v: v.get("flag", "UNK") if isinstance(v, dict) else "UNK")
            df["mmsi"] = df["vessel"].apply(lambda v: v.get("ssvid", "0") if isinstance(v, dict) else "0")

        # Compute duration from start/end
        if "duration_h" not in df.columns and "end" in df.columns and "date" in df.columns:
            df["duration_h"] = (
                (pd.to_datetime(df["end"]) - pd.to_datetime(df["date"]))
                .dt.total_seconds() / 3600
            ).round(1)

        # Normalise event type to uppercase
        type_map = {"gap": "GAP", "encounter": "ENCOUNTER", "loitering": "LOITERING"}
        df["event_type"] = df["event_type"].str.lower().map(type_map).fillna(df["event_type"])

        return df

    except Exception as e:
        st.error(f"Live API error: {e}. Falling back to static demo data.")
        return load_static_data()

# Load data
if use_live and token:
    df = load_live_data(token, date_range[0], date_range[1], min_duration)
else:
    df = load_static_data()

# ========================= RISK SCORE =========================
event_weights = {
    "GAP": gap_weight,
    "LOITERING": loitering_weight,
    "ENCOUNTER": encounter_weight
}

flag_risks = {
    "RUS": 2.8, "IRN": 2.4, "SYR": 2.0, "PRK": 3.0,
    "LBR": 1.3, "PAN": 1.2, "MHL": 1.2
}

def get_offshore_bonus(lat, lon):
    # Simple deep-water proxy for central/eastern Med
    return 1.4 if (lon > 15 and abs(lat - 36) < 8) else 1.0

df_filtered = df[df["duration_h"] >= min_duration].copy()

df_filtered["risk_score"] = df_filtered.apply(
    lambda row: (row["duration_h"] ** 0.75) *
                event_weights.get(row["event_type"], 1.0) *
                flag_risks.get(row["flag"], 1.0) *
                (get_offshore_bonus(row["lat"], row["lon"]) if row["event_type"] == "LOITERING" else 1.0),
    axis=1
)

total_risk = df_filtered["risk_score"].sum()

# ========================= MAIN LAYOUT =========================
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Behavioral Risk Map")
    if not df_filtered.empty:
        m = folium.Map(location=[37.0, 18.0], zoom_start=5, tiles="CartoDB positron")
        color_map = {"GAP": "red", "LOITERING": "orange", "ENCOUNTER": "purple"}
        
        for _, row in df_filtered.iterrows():
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=8,
                color=color_map.get(row["event_type"], "blue"),
                popup=f"""
                <b>Event:</b> {row['event_type']}<br>
                <b>Flag:</b> {row['flag']}<br>
                <b>Duration:</b> {row['duration_h']} h<br>
                <b>Risk Score:</b> {row['risk_score']:.1f}
                """,
                fill=True
            ).add_to(m)
        
        st_folium(m, width=700, height=500)
    else:
        st.info("No events match the selected filters.")

with col2:
    st.metric("Mediterranean Behavioral Risk Index", f"{total_risk:.0f}")
    st.caption("Encounters weighted highest • Russian/Iranian flags boosted")

# ========================= TABS =========================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Daily Risk Trend",
    "Flag Breakdown",
    "Event Type Breakdown",
    "Top 10 Riskiest Vessels",
    "Methodology & About"
])

with tab1:
    st.subheader("Daily Behavioral Risk Trend")
    if not df_filtered.empty:
        daily = df_filtered.groupby("date")["risk_score"].sum().reset_index()
        fig = px.line(daily, x="date", y="risk_score", markers=True,
                      title="Total risk score by day")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data.")

with tab2:
    st.subheader("Breakdown by Flag State")
    if not df_filtered.empty:
        flag_risk = df_filtered.groupby("flag")["risk_score"].sum().reset_index().sort_values("risk_score", ascending=False)
        fig = px.bar(flag_risk, x="risk_score", y="flag", orientation="h",
                     title="Total risk by flag (sorted)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data.")

with tab3:
    st.subheader("Breakdown by Event Type")
    if not df_filtered.empty:
        type_risk = df_filtered.groupby("event_type")["risk_score"].sum().reset_index()
        fig = px.pie(type_risk, names="event_type", values="risk_score",
                     title="Risk contribution by event type")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data.")

with tab4:
    st.subheader("Top 10 Riskiest Vessels")
    if not df_filtered.empty:
        vessel_risk = (df_filtered.groupby(["mmsi", "flag"])
                       .agg(risk=("risk_score", "sum"), events=("mmsi", "count"))
                       .reset_index()
                       .sort_values("risk", ascending=False)
                       .head(10))
        st.dataframe(vessel_risk.style.format({"risk": "{:.1f}"}))
    else:
        st.info("No data.")

with tab5:
    st.subheader("Methodology & About")
    st.markdown("""
    **Risk Score Formula**  
    `risk = (duration_hours ^ 0.75) × event_weight × flag_multiplier × (offshore_bonus if loitering)`  

    - **Encounters** weighted highest (direct transshipment risk).  
    - **Gaps** (AIS disabling) next (intentional dark activity).  
    - **Loitering** weighted for staging behavior + offshore location bonus.  
    - Russian, Iranian and other high-risk flags receive multipliers based on 2026 sanctions context.  

    **Data Source**  
    Global Fishing Watch Events API (GAP, ENCOUNTER, LOITERING).  
    Static fallback uses a realistic synthetic Med dataset derived from public Welch et al. (2022) patterns.

    **Caveats**  
    Not all dark activity is illegal. AIS coverage has gaps. This tool is for educational/portfolio use only.
    """)

# ========================= DOWNLOAD =========================
if not df_filtered.empty:
    csv = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download filtered events as CSV",
        data=csv,
        file_name="med_vessel_events.csv",
        mime="text/csv"
    )

st.caption("Data: Global Fishing Watch Events API | Risk model: custom behavioural scoring | Built as a weekend portfolio project")