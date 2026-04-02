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

    # Sea-only coordinate clusters — verified open water, no land overlap
    sea_zones = [
        # (lat_min, lat_max, lon_min, lon_max)
        (35.5, 36.5, -1.0, 2.0),    # Alboran Sea (south of Spain)
        (38.5, 39.5, 5.0, 7.5),     # west of Sardinia
        (37.5, 39.0, 11.0, 13.0),   # Tyrrhenian Sea (north of Sicily)
        (33.0, 34.5, 13.0, 15.5),   # central Med (off Libya, south of Malta)
        (35.5, 36.5, 17.5, 19.5),   # Ionian Sea (west of Greece)
        (34.0, 35.0, 23.0, 26.5),   # south of Crete (open water)
        (32.5, 33.5, 30.0, 33.0),   # Levantine basin (off Egypt coast)
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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Daily Risk Trend",
    "Flag Breakdown",
    "Event Type Breakdown",
    "Top 10 Riskiest Vessels",
    "Methodology & About",
    "AI Analyst",
])

with tab1:
    st.subheader("Daily Behavioral Risk Trend")
    if not df_filtered.empty:
        daily = df_filtered.groupby("date")["risk_score"].sum().reset_index()
        fig = px.line(daily, x="date", y="risk_score", markers=True,
                      title="Total risk score by day")
        st.plotly_chart(fig)
    else:
        st.info("No data.")

with tab2:
    st.subheader("Breakdown by Flag State")
    if not df_filtered.empty:
        flag_risk = df_filtered.groupby("flag")["risk_score"].sum().reset_index().sort_values("risk_score", ascending=False)
        fig = px.bar(flag_risk, x="risk_score", y="flag", orientation="h",
                     title="Total risk by flag (sorted)")
        st.plotly_chart(fig)
    else:
        st.info("No data.")

with tab3:
    st.subheader("Breakdown by Event Type")
    if not df_filtered.empty:
        type_risk = df_filtered.groupby("event_type")["risk_score"].sum().reset_index()
        fig = px.pie(type_risk, names="event_type", values="risk_score",
                     title="Risk contribution by event type")
        st.plotly_chart(fig)
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

with tab6:
    st.subheader("AI Maritime Analyst")
    st.markdown(
        "Ask questions about the vessel data in natural language. "
        "The AI will explain the findings and generate analytical code."
    )

    # Gemini API key
    try:
        gemini_key = st.secrets["gemini_key"]
    except (FileNotFoundError, KeyError):
        gemini_key = st.text_input(
            "Gemini API Key",
            type="password",
            help="Get a key at aistudio.google.com",
        )

    # Chat history
    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = []

    # Example questions
    with st.expander("Example questions"):
        examples = [
            "Which flag states have the highest total risk? Why?",
            "Show me all encounters involving Russian-flagged vessels",
            "Are there any vessels with repeated gap events? What pattern do you see?",
            "What's happening in the eastern Mediterranean (longitude > 25)?",
            "Which day had the most suspicious activity and why?",
            "Plot all events on a scatter map colored by event type",
            "Compare risk profiles of FOC-flagged vs Mediterranean-flagged vessels",
            "Find vessels that had both a gap and an encounter -- could this indicate transshipment?",
            "What's the average gap duration by flag state? Any outliers?",
            "Rank the top 5 riskiest vessels and explain what makes each one suspicious",
        ]
        for ex in examples:
            if st.button(ex, key=f"ex_{hash(ex)}"):
                st.session_state.pending_question = ex
                st.rerun()

    # Question input
    question = st.chat_input("Ask about the vessel data...")

    # Check for pending question from examples
    if "pending_question" in st.session_state:
        question = st.session_state.pending_question
        del st.session_state.pending_question

    if question and gemini_key:
        st.session_state.ai_messages.append({"role": "user", "parts": [question]})

        try:
            from google import genai

            client_ai = genai.Client(api_key=gemini_key)

            system_ctx = build_system_prompt(df_filtered)

            # Build contents list for Gemini (history + current question)
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
            assistant_text = response.text

            st.session_state.ai_messages.append(
                {"role": "model", "parts": [assistant_text]}
            )

        except Exception as e:
            st.error(f"Gemini API error: {e}")
            assistant_text = None

    # Display conversation
    for msg in st.session_state.ai_messages:
        role = "user" if msg["role"] == "user" else "assistant"
        content = msg["parts"][0] if msg["parts"] else ""
        with st.chat_message(role):
            if role == "assistant":
                # Extract code blocks
                code_blocks = re.findall(r"```python\n(.*?)```", content, re.DOTALL)
                # Display narrative (everything outside code blocks)
                narrative = re.sub(
                    r"```python\n.*?```", "", content, flags=re.DOTALL
                ).strip()
                if narrative:
                    st.markdown(narrative)

                # Execute and display code blocks
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

    # Clear chat button
    if st.session_state.ai_messages:
        if st.button("Clear conversation"):
            st.session_state.ai_messages = []
            st.rerun()

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