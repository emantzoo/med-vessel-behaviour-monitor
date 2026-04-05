import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import asyncio
import glob
import re
import os

# ========================= RAG KNOWLEDGE BASE =========================
def load_knowledge_base():
    """Load all markdown files from knowledge/ folder."""
    docs = []
    knowledge_dir = os.path.join(os.path.dirname(__file__), "knowledge")
    if os.path.exists(knowledge_dir):
        for filepath in sorted(glob.glob(os.path.join(knowledge_dir, "*.md"))):
            with open(filepath, "r", encoding="utf-8") as f:
                docs.append(f"## {os.path.basename(filepath)}\n\n{f.read()}")
    return "\n\n---\n\n".join(docs)

KNOWLEDGE_BASE = load_knowledge_base()


def build_system_prompt(df):
    """Build system prompt with dataframe context and domain knowledge."""
    schema = f"""DATAFRAME SCHEMA (variable name: df)
Columns: {list(df.columns)}
Dtypes:
{df.dtypes.to_string()}

Shape: {df.shape[0]} rows x {df.shape[1]} columns

Sample rows (first 5):
{df.head().to_string()}

Value counts for key columns:
- event_type: {df['event_type'].value_counts().to_dict()}
- flag: {df['flag'].value_counts().to_dict()}

Basic stats:
- duration_h: mean={df['duration_h'].mean():.1f}, min={df['duration_h'].min()}, max={df['duration_h'].max()}
- risk_score: mean={df['risk_score'].mean():.1f}, total={df['risk_score'].sum():.0f}
- date range: {df['date'].min()} to {df['date'].max()}
"""

    return f"""You are a maritime intelligence analyst assistant embedded in the
Med Vessel Behaviour Monitor dashboard. You help users analyse vessel behaviour
data in the Mediterranean Sea.

You have access to a pandas DataFrame called `df` containing vessel events
(AIS gaps, encounters, loitering) with risk scores.

{schema}

DOMAIN KNOWLEDGE:
{KNOWLEDGE_BASE}

YOUR CAPABILITIES:
1. Answer questions about the data with domain-informed explanations
2. Generate Python code (pandas, plotly) to analyse the data
3. The code will be executed against the real dataframe

RESPONSE FORMAT:
Always respond with TWO clearly separated sections:

ANALYSIS:
[Your narrative explanation -- interpret results with domain knowledge.
 Explain WHY something matters, not just WHAT the numbers are.
 Reference IUU indicators, flag risks, geographic context where relevant.]

CODE:
```python
# Your pandas/plotly code here
# The dataframe is available as `df`
# For charts, assign to `fig` (plotly) -- it will be rendered automatically
# For tables, assign to `result_df` -- it will be displayed automatically
# For single values, assign to `result_value` -- it will be displayed
# Available libraries: pandas (pd), numpy (np), plotly.express (px),
#   plotly.graph_objects (go)
```

RULES:
- Always generate executable code -- no pseudocode
- Use `df` as the dataframe variable (already in scope)
- For charts, always use plotly (px or go) and assign to `fig`
- For tables, assign to `result_df`
- Keep code concise -- under 20 lines
- If the question cannot be answered from the data, say so clearly
- Do not fabricate data or make up vessel names/MMSIs
- When discussing flags, use the domain knowledge to explain risk context
- When discussing locations, reference relevant Med geography

CODE STYLE (critical -- follow exactly):
- ALWAYS work from `df` directly. Do NOT redefine or overwrite `df`.
- For bar charts: group first into a small df, then pass that to px.bar()
- For scatter/map: pass df directly to px.scatter() or px.scatter_geo()
- For spatial plots: use px.scatter(df, x="lon", y="lat", color=..., size=...) -- NOT density_heatmap (too blocky with small data)
- NEVER pass a Series where a DataFrame is expected
- NEVER use chained expressions inside plotly function arguments
- Test mentally that all column names exist in df before using them
- Prefer simple one-step groupby().agg().reset_index() patterns
- Assign intermediate results to variables, do not nest complex expressions

WORKING CODE PATTERNS (use these):
```
# Bar chart pattern
grouped = df.groupby("flag")["risk_score"].sum().reset_index()
fig = px.bar(grouped, x="flag", y="risk_score", title="Risk by Flag")

# Table pattern
result_df = df[df["flag"]=="RUS"][["mmsi","flag","duration_h","risk_score"]]

# Single value pattern
result_value = f"{{df['risk_score'].sum():.0f}} total risk"

# Scatter map pattern
fig = px.scatter(df, x="lon", y="lat", color="event_type", size="risk_score", title="Events")

# Spatial scatter pattern (preferred over density_heatmap)
fig = px.scatter(df, x="lon", y="lat", color="event_type", size="duration_h",
                 hover_data=["flag","mmsi","risk_score"], title="Event Locations")
```
"""


FORBIDDEN_CODE = [
    "import os", "import sys", "subprocess", "eval(", "open(",
    "__import__", "exec(", "shutil", "pathlib", "requests",
    "urllib", "socket",
]


def is_safe_code(code):
    """Basic check that generated code doesn't do anything dangerous."""
    code_lower = code.lower()
    for forbidden in FORBIDDEN_CODE:
        if forbidden.lower() in code_lower:
            return False
    return True


# ========================= HELPERS =========================
def classify_med_zone(lon, lat):
    """Classify a point into a Mediterranean sub-region."""
    if lon < 0:
        return "Strait of Gibraltar"
    elif lon < 5:
        return "Alboran Sea"
    elif lon < 12:
        return "Western Med"
    elif lon < 16:
        return "Tyrrhenian / Central"
    elif lon < 22:
        return "Ionian / Adriatic"
    elif lon < 28:
        return "Aegean"
    elif lon < 32:
        return "Levantine"
    else:
        return "Eastern Med / Near East"


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
    token = st.sidebar.text_input("GFW API Token (free)", type="password", help="Register at globalfishingwatch.org -> Our APIs")

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

min_duration = st.sidebar.slider("Minimum event duration (hours)", 2, 48, 2,
                                 help="GFW encounter threshold is 2h")

# Advanced: editable risk weights
with st.sidebar.expander("Advanced -- Risk Weights (optional)"):
    gap_weight = st.number_input("Gap weight", value=3.2, min_value=0.1, step=0.1)
    loitering_weight = st.number_input("Loitering weight", value=2.0, min_value=0.1, step=0.1)
    encounter_weight = st.number_input("Encounter weight", value=5.0, min_value=0.1, step=0.1)

# ========================= DATA LOADING =========================
@st.cache_data
def load_static_data():
    """Rich static fallback dataset (80 realistic Med events with extended fields)."""
    csv_path = os.path.join(os.path.dirname(__file__), "data", "med_events_static.csv")
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path, parse_dates=["date"])

    rng = np.random.default_rng(42)

    n = 80
    event_types = ["GAP"] * 25 + ["LOITERING"] * 30 + ["ENCOUNTER"] * 25
    flags = (["RUS"] * 12 + ["IRN"] * 8 + ["PAN"] * 15 + ["LBR"] * 15
             + ["GRC"] * 10 + ["TUR"] * 8 + ["ITA"] * 7 + ["MLT"] * 5)

    # Duration ranges by event type (hours)
    dur_map = {"GAP": (6, 72), "LOITERING": (4, 48), "ENCOUNTER": (2, 24)}
    durations = [round(rng.uniform(*dur_map[et]), 1) for et in event_types]

    # Sea-only coordinate clusters
    sea_zones = [
        (35.5, 36.5, -1.0, 2.0),
        (38.5, 39.5, 5.0, 7.5),
        (37.5, 39.0, 11.0, 13.0),
        (33.0, 34.5, 13.0, 15.5),
        (35.5, 36.5, 17.5, 19.5),
        (34.0, 35.0, 23.0, 26.5),
        (32.5, 33.5, 30.0, 33.0),
    ]
    zone_idx = rng.integers(0, len(sea_zones), size=n)
    lats = np.array([rng.uniform(sea_zones[z][0], sea_zones[z][1]) for z in zone_idx]).round(2)
    lons = np.array([rng.uniform(sea_zones[z][2], sea_zones[z][3]) for z in zone_idx]).round(2)

    base = datetime(2026, 3, 1)
    dates = [(base + timedelta(days=int(d))).strftime("%Y-%m-%d")
             for d in rng.integers(0, 30, size=n)]

    mmsis = rng.integers(200000000, 800000000, size=n)

    # Vessel names
    cargo_names = ["ATLANTIC SPIRIT", "COSCO HARMONY", "GOLDEN EAGLE", "SEA PIONEER",
                   "NORDIC STAR", "AEGEAN WIND", "MED CARRIER", "BLACK SEA EXPRESS"]
    tanker_names = ["CRUDE VENTURE", "OIL TRADER", "PETRO STAR", "FUEL MASTER"]
    vessel_names = rng.choice(cargo_names + tanker_names, n)

    # Vessel types
    type_pool = ["CARRIER", "FISHING", "CARGO", "TANKER", "SUPPORT"]
    vessel_types = rng.choice(type_pool, n, p=[0.25, 0.30, 0.20, 0.15, 0.10])

    # Distances
    distance_shore = np.round(rng.uniform(2, 250, n), 1)
    distance_port = np.round(distance_shore * rng.uniform(1.0, 2.5, n), 1)

    # Nearest ports
    ports = ["Piraeus", "Valletta", "Genoa", "Barcelona", "Mersin", "Haifa",
             "Alexandria", "Izmir", "Marseille", "Algeciras"]
    nearest_ports = rng.choice(ports, n)

    # EEZ
    eezs = ["Greece", "Italy", "Turkey", "Spain", "Malta", "Libya", "Tunisia",
            "Egypt", "Cyprus", "International Waters"]
    eez_vals = rng.choice(eezs, n, p=[0.15, 0.15, 0.10, 0.10, 0.05,
                                       0.08, 0.07, 0.05, 0.05, 0.20])

    df = pd.DataFrame({
        "event_type": event_types,
        "mmsi": mmsis,
        "flag": flags,
        "vessel_name": vessel_names,
        "vessel_type": vessel_types,
        "duration_h": durations,
        "lat": lats,
        "lon": lons,
        "date": dates,
        "distance_from_shore_km": distance_shore,
        "distance_from_port_km": distance_port,
        "nearest_port": nearest_ports,
        "eez": eez_vals,
    })

    # Gap-specific fields
    gap_mask = df["event_type"] == "GAP"
    gap_n = gap_mask.sum()
    df.loc[gap_mask, "gap_distance_km"] = np.round(rng.uniform(10, 500, gap_n), 1)
    df.loc[gap_mask, "speed_before_gap"] = np.round(rng.uniform(0.5, 14, gap_n), 1)
    df.loc[gap_mask, "speed_after_gap"] = np.round(rng.uniform(0.5, 14, gap_n), 1)

    # Encounter-specific fields
    enc_mask = df["event_type"] == "ENCOUNTER"
    enc_n = enc_mask.sum()
    enc_names = ["SHADOW CARRIER", "REEFER KING", "COLD STAR", "FISH RUNNER",
                 "NEPTUNE BULK", "CARGO QUEEN"]
    df.loc[enc_mask, "encounter_vessel_name"] = rng.choice(enc_names, enc_n)
    df.loc[enc_mask, "encounter_vessel_flag"] = rng.choice(
        ["PAN", "LBR", "GRC", "MLT", "RUS", "MHL"], enc_n)
    df.loc[enc_mask, "encounter_median_distance_km"] = np.round(rng.uniform(0.05, 2.0, enc_n), 2)
    df.loc[enc_mask, "encounter_median_speed_knots"] = np.round(rng.uniform(0.5, 3.0, enc_n), 1)

    # Loitering-specific fields
    loit_mask = df["event_type"] == "LOITERING"
    loit_n = loit_mask.sum()
    df.loc[loit_mask, "loitering_total_distance_km"] = np.round(rng.uniform(5, 150, loit_n), 1)
    df.loc[loit_mask, "loitering_avg_speed_knots"] = np.round(rng.uniform(0.3, 2.5, loit_n), 1)

    # Med zone classification
    df["med_zone"] = df.apply(lambda r: classify_med_zone(r["lon"], r["lat"]), axis=1)

    return df

def _safe_get(d, *keys, default=None):
    """Safely navigate nested dicts."""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
    return d if d is not None else default


@st.cache_data
def load_live_data(token, start_date, end_date, _min_dur):
    """Fetch events from GFW Events API with full nested field extraction."""
    try:
        import gfwapiclient as gfw

        gfw_client = gfw.Client(access_token=token)

        datasets = [
            "public-global-gaps-events:latest",
            "public-global-encounters-events:latest",
            "public-global-loitering-events:latest",
        ]

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

        raw_df = asyncio.run(_fetch())

        if raw_df.empty:
            st.warning("No events returned from API for this period.")
            return load_static_data()

        # Build rich dataframe by extracting nested fields
        rows = []
        for _, r in raw_df.iterrows():
            row_dict = {}

            # Core fields
            row_dict["event_type"] = str(r.get("type", "")).upper()
            row_dict["date"] = r.get("start")

            # Position
            pos = r.get("position") if isinstance(r.get("position"), dict) else {}
            row_dict["lat"] = pos.get("lat")
            row_dict["lon"] = pos.get("lon")

            # Vessel identity
            vessel = r.get("vessel") if isinstance(r.get("vessel"), dict) else {}
            row_dict["mmsi"] = vessel.get("ssvid", "0")
            row_dict["flag"] = vessel.get("flag", "UNK")
            row_dict["vessel_name"] = vessel.get("name", "")
            row_dict["vessel_type"] = vessel.get("type", "")

            # Duration
            if r.get("start") and r.get("end"):
                try:
                    start_dt = pd.to_datetime(r["start"])
                    end_dt = pd.to_datetime(r["end"])
                    row_dict["duration_h"] = round((end_dt - start_dt).total_seconds() / 3600, 1)
                except Exception:
                    row_dict["duration_h"] = 0

            # Distances (from nested distances dict)
            distances = r.get("distances") if isinstance(r.get("distances"), dict) else {}
            row_dict["distance_from_shore_km"] = distances.get("shoreDistanceKm")
            row_dict["distance_from_port_km"] = distances.get("portDistanceKm")
            port = distances.get("port") if isinstance(distances.get("port"), dict) else {}
            row_dict["nearest_port"] = port.get("name")

            # Regions (EEZ, RFMO)
            for region in (r.get("regions") or []):
                if isinstance(region, dict):
                    ds = region.get("dataset", "")
                    if "eez" in ds:
                        row_dict["eez"] = region.get("name")

            # Event-specific nested data
            event_info = r.get("event_info") if isinstance(r.get("event_info"), dict) else {}

            if row_dict["event_type"] == "GAP":
                row_dict["gap_distance_km"] = event_info.get("distanceKm")
                row_dict["speed_before_gap"] = event_info.get("speedBeforeKnots")
                row_dict["speed_after_gap"] = event_info.get("speedAfterKnots")

            elif row_dict["event_type"] == "ENCOUNTER":
                enc_vessel = event_info.get("vessel") if isinstance(event_info.get("vessel"), dict) else {}
                row_dict["encounter_vessel_name"] = enc_vessel.get("name")
                row_dict["encounter_vessel_flag"] = enc_vessel.get("flag")
                row_dict["encounter_median_distance_km"] = event_info.get("medianDistanceKm")
                row_dict["encounter_median_speed_knots"] = event_info.get("medianSpeedKnots")

            elif row_dict["event_type"] == "LOITERING":
                row_dict["loitering_total_distance_km"] = event_info.get("totalDistanceKm")
                row_dict["loitering_avg_speed_knots"] = event_info.get("averageSpeedKnots")

            rows.append(row_dict)

        df = pd.DataFrame(rows)

        # Normalise event type
        type_map = {"GAP": "GAP", "ENCOUNTER": "ENCOUNTER", "LOITERING": "LOITERING"}
        df["event_type"] = df["event_type"].map(type_map).fillna(df["event_type"])

        # Add med_zone
        if "lat" in df.columns and "lon" in df.columns:
            df["med_zone"] = df.apply(
                lambda r: classify_med_zone(r["lon"], r["lat"])
                if pd.notna(r.get("lon")) and pd.notna(r.get("lat")) else "", axis=1)

        return df

    except Exception as e:
        st.error(f"Live API error: {e}. Falling back to static demo data.")
        return load_static_data()

# Load data
if use_live and token:
    df = load_live_data(token, date_range[0], date_range[1], min_duration)
else:
    df = load_static_data()

# ========================= RISK SCORE (GFW-aligned) =========================
# Aligned with Global Fishing Watch transshipment detection methodology:
# - Encounters: <500m, >=2h, <2kn, >=10km from shore (Miller et al. 2018)
# - Likely transshipment: reefer + fishing vessel, >20nm from shore
# - Potential transshipment: reefer loiters alone (fishing vessel AIS off)

event_weights = {
    "GAP": gap_weight,
    "LOITERING": loitering_weight,
    "ENCOUNTER": encounter_weight
}

flag_risks = {
    "RUS": 2.8, "IRN": 2.4, "SYR": 2.0, "PRK": 3.0,
    "LBR": 1.3, "PAN": 1.2, "MHL": 1.2
}

# Vessel types with higher transshipment risk (reefers/carriers)
TRANSSHIPMENT_VESSEL_TYPES = {"CARRIER", "TANKER"}


def compute_risk_score(row):
    """GFW-aligned behavioral risk score."""
    base = row["duration_h"] ** 0.75
    ew = event_weights.get(row["event_type"], 1.0)
    fm = flag_risks.get(row["flag"], 1.0)

    # Shore distance factor (GFW: >=10km encounters, >=20nm loitering)
    shore_km = row.get("distance_from_shore_km")
    if pd.notna(shore_km):
        if shore_km > 37:      # >20nm — high suspicion zone
            shore_factor = 1.5
        elif shore_km > 10:    # >10km — GFW encounter threshold
            shore_factor = 1.2
        else:
            shore_factor = 0.8  # near-shore = less suspicious
    else:
        shore_factor = 1.0

    # Event-type-specific GFW-aligned factors
    if row["event_type"] == "ENCOUNTER":
        # Proximity factor (GFW: <500m = 0.5km)
        dist = row.get("encounter_median_distance_km")
        if pd.notna(dist):
            if dist < 0.5:       # within GFW 500m threshold
                proximity_factor = 1.8
            elif dist < 1.0:
                proximity_factor = 1.3
            else:
                proximity_factor = 1.0
        else:
            proximity_factor = 1.0

        # Speed factor (GFW: <2 knots = likely transfer)
        speed = row.get("encounter_median_speed_knots")
        if pd.notna(speed):
            speed_factor = 1.5 if speed < 2.0 else 1.0
        else:
            speed_factor = 1.0

        # Vessel type factor (reefer/carrier encounters are key transshipment indicator)
        vtype = str(row.get("vessel_type", "")).upper()
        vessel_factor = 1.4 if vtype in TRANSSHIPMENT_VESSEL_TYPES else 1.0

        return base * ew * fm * shore_factor * proximity_factor * speed_factor * vessel_factor

    elif row["event_type"] == "LOITERING":
        # Loitering reefer = GFW "potential transshipment" indicator
        vtype = str(row.get("vessel_type", "")).upper()
        vessel_factor = 1.6 if vtype in TRANSSHIPMENT_VESSEL_TYPES else 1.0

        # Low speed = staging behaviour (GFW: avg <2kn)
        speed = row.get("loitering_avg_speed_knots")
        if pd.notna(speed):
            speed_factor = 1.4 if speed < 2.0 else 1.0
        else:
            speed_factor = 1.0

        return base * ew * fm * shore_factor * vessel_factor * speed_factor

    elif row["event_type"] == "GAP":
        # Speed change across gap = evasion indicator
        spd_before = row.get("speed_before_gap")
        spd_after = row.get("speed_after_gap")
        if pd.notna(spd_before) and pd.notna(spd_after):
            speed_change = abs(spd_before - spd_after)
            # Large speed change = likely intentional (was moving, went dark, reappeared slow)
            evasion_factor = 1.5 if speed_change > 5 else (1.2 if speed_change > 2 else 1.0)
        else:
            evasion_factor = 1.0

        return base * ew * fm * shore_factor * evasion_factor

    else:
        return base * ew * fm * shore_factor


df_filtered = df[df["duration_h"] >= min_duration].copy()
df_filtered["risk_score"] = df_filtered.apply(compute_risk_score, axis=1).round(1)
total_risk = df_filtered["risk_score"].sum()

# ========================= COLOR SCHEME =========================
EVENT_COLORS = {"GAP": "#e74c3c", "LOITERING": "#f39c12", "ENCOUNTER": "#8e44ad"}

# ========================= MAIN LAYOUT =========================
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Behavioral Risk Map")
    if not df_filtered.empty:
        m = folium.Map(location=[37.0, 18.0], zoom_start=5, tiles="CartoDB positron")
        color_map = {"GAP": "red", "LOITERING": "orange", "ENCOUNTER": "purple"}

        for _, row in df_filtered.iterrows():
            popup_text = f"""
            <b>Event:</b> {row['event_type']}<br>
            <b>Flag:</b> {row['flag']}<br>
            <b>Duration:</b> {row['duration_h']} h<br>
            <b>Risk Score:</b> {row['risk_score']:.1f}
            """
            if "vessel_name" in row and pd.notna(row.get("vessel_name")):
                popup_text = f"<b>{row['vessel_name']}</b><br>" + popup_text

            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=8,
                color=color_map.get(row["event_type"], "blue"),
                popup=popup_text,
                fill=True
            ).add_to(m)

        st_folium(m, width=700, height=500)
    else:
        st.info("No events match the selected filters.")

with col2:
    st.metric("Mediterranean Behavioral Risk Index", f"{total_risk:.0f}")
    st.caption("Encounters weighted highest . Russian/Iranian flags boosted")

    # Quick stats
    if not df_filtered.empty:
        st.metric("Events", len(df_filtered))
        st.metric("Unique Vessels", df_filtered["mmsi"].nunique())
        st.metric("Flags", df_filtered["flag"].nunique())

# ========================= TABS =========================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
    "Daily Trend",
    "Flag Breakdown",
    "Event Types",
    "Duration Analysis",
    "Geographic Risk",
    "Risk Heatmap",
    "Repeat Offenders",
    "Gap Behaviour",
    "Encounter Analysis",
    "Top Vessels",
    "AI Analyst",
])

# --- Tab 1: Daily Risk Trend ---
with tab1:
    st.subheader("Daily Behavioral Risk Trend")
    if not df_filtered.empty:
        daily = df_filtered.groupby("date")["risk_score"].sum().reset_index()
        fig = px.line(daily, x="date", y="risk_score", markers=True,
                      title="Total risk score by day")
        st.plotly_chart(fig)
    else:
        st.info("No data.")

# --- Tab 2: Flag Breakdown ---
with tab2:
    st.subheader("Breakdown by Flag State")
    if not df_filtered.empty:
        flag_risk = (df_filtered.groupby("flag")["risk_score"].sum()
                     .reset_index().sort_values("risk_score", ascending=False))
        fig = px.bar(flag_risk, x="risk_score", y="flag", orientation="h",
                     title="Total risk by flag (sorted)")
        st.plotly_chart(fig)
    else:
        st.info("No data.")

# --- Tab 3: Event Type Breakdown ---
with tab3:
    st.subheader("Breakdown by Event Type")
    if not df_filtered.empty:
        type_risk = df_filtered.groupby("event_type")["risk_score"].sum().reset_index()
        fig = px.pie(type_risk, names="event_type", values="risk_score",
                     color="event_type", color_discrete_map=EVENT_COLORS,
                     title="Risk contribution by event type")
        st.plotly_chart(fig)
    else:
        st.info("No data.")

# --- Tab 4: Duration Analysis ---
with tab4:
    st.subheader("Event Duration Distribution")
    if not df_filtered.empty:
        fig = px.histogram(
            df_filtered, x="duration_h", color="event_type", nbins=25,
            barmode="overlay", opacity=0.7,
            color_discrete_map=EVENT_COLORS,
            labels={"duration_h": "Duration (hours)", "event_type": "Event Type"},
            title="Event Duration Distribution",
        )
        fig.update_layout(bargap=0.05)
        st.plotly_chart(fig)

        st.markdown("**Why it matters:** Long gaps (>24h) suggest deliberate AIS disabling. "
                     "Encounters over 8h point to transshipment. Short loitering may be staging.")
    else:
        st.info("No data.")

# --- Tab 5: Geographic Risk ---
with tab5:
    st.subheader("Geographic Risk Analysis")
    if not df_filtered.empty:
        # Risk bubble scatter
        fig = px.scatter(
            df_filtered, x="lon", y="lat", size="risk_score", color="event_type",
            color_discrete_map=EVENT_COLORS,
            hover_data=["mmsi", "flag", "duration_h", "risk_score",
                        "vessel_name"] if "vessel_name" in df_filtered.columns else ["mmsi", "flag"],
            size_max=25,
            title="Risk-Weighted Event Map (bubble size = risk score)",
            labels={"lon": "Longitude", "lat": "Latitude"},
        )
        st.plotly_chart(fig)

        # Med zone breakdown
        if "med_zone" in df_filtered.columns:
            st.subheader("Risk by Mediterranean Sub-Region")
            zone_risk = (
                df_filtered.groupby("med_zone")
                .agg(total_risk=("risk_score", "sum"), events=("mmsi", "count"))
                .reset_index()
                .sort_values("total_risk", ascending=True)
            )
            fig2 = px.bar(
                zone_risk, x="total_risk", y="med_zone", orientation="h",
                color="events", color_continuous_scale="Blues",
                title="Risk by Mediterranean Sub-Region",
                labels={"total_risk": "Total Risk Score", "med_zone": "Region", "events": "Events"},
            )
            st.plotly_chart(fig2)

        # EEZ breakdown
        if "eez" in df_filtered.columns and df_filtered["eez"].notna().any():
            st.subheader("Risk by Exclusive Economic Zone")
            eez_risk = (
                df_filtered.groupby("eez")
                .agg(total_risk=("risk_score", "sum"), events=("mmsi", "count"))
                .reset_index()
                .sort_values("total_risk", ascending=False)
            )
            fig3 = px.bar(
                eez_risk, x="total_risk", y="eez", orientation="h",
                title="Risk by EEZ",
                labels={"eez": "EEZ", "total_risk": "Total Risk"},
            )
            st.plotly_chart(fig3)

        # Port proximity
        if "nearest_port" in df_filtered.columns and df_filtered["nearest_port"].notna().any():
            st.subheader("Risk by Nearest Port")
            port_events = (
                df_filtered.groupby("nearest_port")
                .agg(
                    total_risk=("risk_score", "sum"),
                    events=("mmsi", "count"),
                    avg_distance=("distance_from_port_km", "mean"),
                )
                .reset_index()
                .sort_values("total_risk", ascending=False)
            )
            fig4 = px.scatter(
                port_events, x="avg_distance", y="total_risk", size="events",
                text="nearest_port",
                title="Risk by Nearest Port -- Farther from Port = More Suspicious",
                labels={"avg_distance": "Avg Distance from Port (km)", "total_risk": "Total Risk Score"},
            )
            fig4.update_traces(textposition="top center")
            st.plotly_chart(fig4)
    else:
        st.info("No data.")

# --- Tab 6: Risk Heatmap ---
with tab6:
    st.subheader("Risk Heatmap: Flag State vs Event Type")
    if not df_filtered.empty:
        pivot = df_filtered.pivot_table(
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
            xaxis_title="Event Type", yaxis_title="Flag State",
            height=500,
        )
        st.plotly_chart(fig)

        st.markdown("**Interpretation:** bright cells = high risk combinations. "
                     "Look for Russian/Iranian flags with high GAP or ENCOUNTER scores.")
    else:
        st.info("No data.")

# --- Tab 7: Repeat Offenders ---
with tab7:
    st.subheader("Repeat Offenders -- Vessels with Multiple Events")
    if not df_filtered.empty:
        vessel_counts = (
            df_filtered.groupby(["mmsi", "flag"])
            .agg(
                event_count=("event_type", "count"),
                total_risk=("risk_score", "sum"),
                event_types=("event_type", lambda x: ", ".join(sorted(set(x)))),
                avg_duration=("duration_h", "mean"),
            )
            .reset_index()
            .sort_values("event_count", ascending=False)
        )

        # Add vessel_name if available
        if "vessel_name" in df_filtered.columns:
            name_map = df_filtered.dropna(subset=["vessel_name"]).drop_duplicates("mmsi").set_index("mmsi")["vessel_name"]
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
    else:
        st.info("No data.")

# --- Tab 8: Gap Behaviour ---
with tab8:
    st.subheader("Gap Behaviour Analysis")
    gap_df = df_filtered[df_filtered["event_type"] == "GAP"].copy()

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

        # Gap distance vs duration
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
        # Fallback: show gap duration distribution
        fig = px.histogram(gap_df, x="duration_h", nbins=15, color="flag",
                           title="Gap Duration Distribution",
                           labels={"duration_h": "Duration (hours)"})
        st.plotly_chart(fig)
    else:
        st.info("No gap events in filtered data.")

# --- Tab 9: Encounter Analysis ---
with tab9:
    st.subheader("Encounter Analysis")
    enc_df = df_filtered[df_filtered["event_type"] == "ENCOUNTER"].copy()

    if not enc_df.empty and "encounter_median_distance_km" in enc_df.columns:
        # Proximity vs duration scatter
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

        # Encounter partner flags
        if "encounter_vessel_flag" in enc_df.columns and enc_df["encounter_vessel_flag"].notna().any():
            st.subheader("Encounter Partner Flag Analysis")
            partner_flags = (enc_df.groupby(["flag", "encounter_vessel_flag"])
                             .agg(encounters=("mmsi", "count"), total_risk=("risk_score", "sum"))
                             .reset_index()
                             .sort_values("total_risk", ascending=False))
            partner_flags.columns = ["Vessel Flag", "Partner Flag", "Encounters", "Total Risk"]
            st.dataframe(partner_flags.style.format({"Total Risk": "{:.1f}"}))

        st.markdown("**Why it matters:** Two vessels within 100m for 8 hours is almost certainly "
                     "a transshipment. Look for high-risk flag combinations (e.g. RUS + PAN).")
    elif not enc_df.empty:
        st.info("Encounter distance data not available. Use live API for detailed encounter analysis.")
        # Fallback: basic encounter table
        cols = ["mmsi", "flag", "duration_h", "risk_score"]
        if "vessel_name" in enc_df.columns:
            cols = ["vessel_name"] + cols
        st.dataframe(enc_df[cols].sort_values("risk_score", ascending=False))
    else:
        st.info("No encounter events in filtered data.")

# --- Tab 10: Top Vessels ---
with tab10:
    st.subheader("Top 10 Riskiest Vessels")
    if not df_filtered.empty:
        group_cols = ["mmsi", "flag"]
        if "vessel_name" in df_filtered.columns:
            group_cols.append("vessel_name")
        if "vessel_type" in df_filtered.columns:
            group_cols.append("vessel_type")

        vessel_risk = (df_filtered.groupby(group_cols)
                       .agg(risk=("risk_score", "sum"), events=("mmsi", "count"))
                       .reset_index()
                       .sort_values("risk", ascending=False)
                       .head(10))
        st.dataframe(vessel_risk.style.format({"risk": "{:.1f}"}))

        # Vessel type breakdown
        if "vessel_type" in df_filtered.columns and df_filtered["vessel_type"].notna().any():
            st.subheader("Risk by Vessel Type")
            type_risk = (
                df_filtered.groupby("vessel_type")
                .agg(total_risk=("risk_score", "sum"), events=("mmsi", "count"))
                .reset_index()
                .sort_values("total_risk", ascending=False)
            )
            fig = px.bar(
                type_risk, x="vessel_type", y="total_risk",
                color="events", color_continuous_scale="Viridis",
                title="Risk by Vessel Type",
                labels={"vessel_type": "Vessel Type", "total_risk": "Total Risk"},
            )
            st.plotly_chart(fig)
    else:
        st.info("No data.")

# --- Tab 11: AI Analyst ---
with tab11:
    st.subheader("AI Maritime Analyst")
    st.markdown(
        "Ask questions about the vessel data in natural language. "
        "The AI will explain the findings and generate analytical code."
    )

    try:
        gemini_key = st.secrets["gemini_key"]
    except (FileNotFoundError, KeyError):
        gemini_key = st.text_input(
            "Gemini API Key", type="password",
            help="Get a key at aistudio.google.com",
        )

    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = []

    examples = [
        "",
        "Which flag states have the highest total risk? Why?",
        "Show me all encounters involving Russian-flagged vessels",
        "Are there any vessels with repeated gap events?",
        "What's happening in the eastern Mediterranean (longitude > 25)?",
        "Which day had the most suspicious activity and why?",
        "Plot all events on a scatter map colored by event type",
        "Compare risk profiles of FOC-flagged vs Mediterranean-flagged vessels",
        "What's the average gap duration by flag state? Any outliers?",
        "Rank the top 5 riskiest vessels and explain what makes each one suspicious",
    ]

    picked = st.selectbox(
        "Pick a question or type your own below", examples, index=0,
        format_func=lambda x: "-- Pick an example question --" if x == "" else x,
        key="example_sel",
    )

    typed = st.text_input(
        "Or type your own question", value="", key="typed_q",
        placeholder="Type a question here...",
    )

    ask_clicked = st.button("Ask", type="primary")

    question = None
    if ask_clicked:
        if typed.strip():
            question = typed.strip()
        elif picked:
            question = picked

    if question and gemini_key:
        st.session_state.ai_messages = []
        st.session_state.ai_messages.append({"role": "user", "parts": [question]})

        with st.spinner("Thinking..."):
            try:
                from google import genai

                client_ai = genai.Client(api_key=gemini_key)
                system_ctx = build_system_prompt(df_filtered)

                contents = []
                for msg in st.session_state.ai_messages[-20:]:
                    contents.append(
                        genai.types.Content(
                            role=msg["role"],
                            parts=[genai.types.Part(text=msg["parts"][0])],
                        )
                    )

                response = client_ai.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=system_ctx,
                        max_output_tokens=2000,
                    ),
                )

                st.session_state.ai_messages.append(
                    {"role": "model", "parts": [response.text]}
                )

            except Exception as e:
                st.error(f"Gemini API error: {e}")

    for msg in st.session_state.ai_messages:
        role = "user" if msg["role"] == "user" else "assistant"
        content = msg["parts"][0] if msg["parts"] else ""
        with st.chat_message(role):
            if role == "assistant":
                code_blocks = re.findall(r"```python\n(.*?)```", content, re.DOTALL)
                narrative = re.sub(
                    r"```python\n.*?```", "", content, flags=re.DOTALL
                ).strip()
                if narrative:
                    st.markdown(narrative)

                for code in code_blocks:
                    with st.expander("Generated Code", expanded=True):
                        st.code(code, language="python")

                    if is_safe_code(code):
                        try:
                            exec_ns = {
                                "df": df_filtered.copy(),
                                "pd": pd,
                                "np": np,
                                "px": px,
                                "go": go,
                            }
                            exec(code, exec_ns)

                            if "fig" in exec_ns and exec_ns["fig"] is not None:
                                st.plotly_chart(exec_ns["fig"])
                            if "result_df" in exec_ns and exec_ns["result_df"] is not None:
                                st.dataframe(exec_ns["result_df"])
                            if "result_value" in exec_ns and exec_ns["result_value"] is not None:
                                st.metric("Result", exec_ns["result_value"])
                        except Exception as e:
                            st.error(f"Code execution error: {e}")
                    else:
                        st.warning("Generated code contains restricted operations. Skipping execution.")
            else:
                st.markdown(content)

# ========================= METHODOLOGY (sidebar) =========================
with st.sidebar.expander("Methodology & About"):
    st.markdown("""
**GFW-Aligned Risk Scoring**

Risk model replicates Global Fishing Watch transshipment detection
methodology (Miller et al. 2018).

`risk = duration^0.75 x event_weight x flag_mult x shore_factor x event_factors`

**Encounter factors** (GFW criteria):
- Proximity: <500m = 1.8x (GFW threshold)
- Speed: <2kn = 1.5x (likely transfer)
- Vessel type: reefer/carrier = 1.4x

**Loitering factors** (potential transshipment):
- Reefer/carrier loitering = 1.6x
- Avg speed <2kn = 1.4x

**Gap factors** (evasion):
- Speed change >5kn across gap = 1.5x

**Shore distance** (all events):
- >20nm = 1.5x | >10km = 1.2x | <10km = 0.8x

**Data:** GFW Events API (GAP, ENCOUNTER, LOITERING)

*Not all dark activity is illegal. For educational use only.*
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
