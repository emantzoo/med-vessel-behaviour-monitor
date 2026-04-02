# Portfolio Projects Spec

Two weekend projects. Both use free AIS data. Both signal "I understand maritime intelligence" to Kpler.

---

## PROJECT 1: Med Vessel Behaviour Monitor (FIX & FINISH)

### Status: Code exists, needs fixes before deployment

### Critical Fix: GFW Python Client API

Your code imports `from gfw_api_python_client import GFWApiClient` — this is wrong. The actual package is:

```python
# Install
pip install gfw-api-python-client

# Import
import gfwapiclient as gfw

# Initialize
client = gfw.Client(access_token="YOUR_TOKEN")
```

The Events API supports these event types:
- `GAP` (AIS disabling)
- `ENCOUNTER` (vessel-to-vessel)
- `LOITERING` (carrier vessel loitering)
- `PORT_VISIT`
- `FISHING`

You need a free GFW API token: register at globalfishingwatch.org, then generate token at their API portal.

### Fix List

1. **Fix GFW client import and method calls**
   - Replace `from gfw_api_python_client import GFWApiClient` with `import gfwapiclient as gfw`
   - Replace `client = GFWApiClient(token=token)` with `client = gfw.Client(access_token=token)`
   - Check actual method signatures in the docs at globalfishingwatch.github.io/gfw-api-python-client
   - The Events API may not accept a raw GeoJSON polygon — check if it takes EEZ codes or bounding boxes instead

2. **Fix Mediterranean polygon**
   - Current polygon is malformed (coordinates jump from 36.0 to 12.0 creating weird shape)
   - Simple fix — use a clean bounding box: `[[-6.0, 30.0], [36.5, 46.0]]`
   - Or query by GFCM/Med EEZ codes if the API supports region codes

3. **Fix date range crash**
   - Add: `if len(date_range) < 2: st.warning("Select a date range"); st.stop()`

4. **Build proper static fallback dataset**
   - Create `data/med_events_static.csv` with 80-100 rows of realistic data
   - Mix of gap/loitering/encounter events across Med
   - Realistic flag distribution (GRC, TUR, ITA, ESP, RUS, IRN, PAN, LBR, MLT)
   - Realistic durations (gaps: 6-72h, loitering: 4-48h, encounters: 2-12h)
   - Spread across eastern, central, western Med
   - Include realistic dates across a 1-month window

5. **Add missing charts (the tabs section)**
   - Tab 1: Map (exists)
   - Tab 2: Daily risk trend — line chart of total risk score by date
   - Tab 3: Breakdown by flag — horizontal bar chart, sorted by total risk
   - Tab 4: Breakdown by event type — stacked bar or pie
   - Tab 5: Top 10 riskiest vessels (by MMSI) — table with flag, event count, total risk

6. **Add download button**
   ```python
   st.download_button("Download filtered data", df_filtered.to_csv(index=False), "med_events.csv")
   ```

7. **Add About/Methodology tab**
   - Explain the risk score formula in plain language
   - Why encounters are weighted highest (transshipment risk)
   - Why Russian/Iranian flags get multiplied (sanctions context)
   - Data source: Global Fishing Watch Events API
   - Caveats: AIS coverage limitations, not all dark activity is illegal

8. **Clean up cosmetics**
   - Remove all emojis from title and captions
   - Remove dev notes ("Drop this file and rerun!")
   - Professional caption: "Data: Global Fishing Watch Events API | Risk model: custom behavioural scoring"
   - Make risk weights editable in sidebar (advanced toggle)

### Deploy
- Streamlit Cloud (free, connect to GitHub repo)
- Add `requirements.txt`: streamlit, pandas, folium, streamlit-folium, plotly, gfw-api-python-client
- Add `.streamlit/secrets.toml` with gfw_token (or keep the text input fallback)
- Clean README.md for the repo

### Time estimate: 4-6 hours to fix and deploy

---

## PROJECT 2: PortPulse — Port Congestion & Waiting Time Analyzer (NEW)

### Concept
Turn raw AIS position data into port logistics intelligence: which vessels are waiting at anchor, how long, what types, congestion trends. Focus on Piraeus (your backyard, major EU container port).

### Data Source: aisstream.io (free, real-time, global)
- Free WebSocket API, just need to register for API key at aisstream.io
- Real-time global AIS feed with position reports
- Filter by bounding box (Piraeus area) and message type
- Returns: MMSI, lat, lon, speed, course, heading, ship type, timestamp, destination, vessel name

Alternative for historical: collect a few days of data into a CSV by running the websocket script, then use that as your static dataset.

### Architecture

```
aisstream.io WebSocket → collector script (saves to CSV/SQLite)
                              ↓
                        Streamlit app reads CSV/DB
                              ↓
                   Smart logic: classify vessel state
                              ↓
                     Dashboard with map + charts
```

### Step 1: Data Collector Script (standalone, runs separately)

```python
# collector.py — run this for a few hours/days to build dataset
import asyncio
import websockets
import json
import csv
from datetime import datetime

API_KEY = "YOUR_AISSTREAM_KEY"

# Piraeus anchorage area bounding box
PIRAEUS_BBOX = [[[37.85, 23.50], [37.97, 23.72]]]
# Can also add: Thessaloniki, or broader Saronic Gulf

async def collect():
    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
        subscribe = {
            "APIKey": API_KEY,
            "BoundingBoxes": PIRAEUS_BBOX,
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"]
        }
        await ws.send(json.dumps(subscribe))

        with open("piraeus_ais.csv", "a", newline="") as f:
            writer = csv.writer(f)
            async for msg in ws:
                data = json.loads(msg)
                meta = data.get("MetaData", {})
                pos = data.get("Message", {}).get("PositionReport", {})
                if pos:
                    writer.writerow([
                        datetime.utcnow().isoformat(),
                        meta.get("MMSI"),
                        meta.get("ShipName", ""),
                        meta.get("latitude"),
                        meta.get("longitude"),
                        pos.get("Sog", 0),       # speed over ground
                        pos.get("Cog", 0),        # course
                        pos.get("TrueHeading", 0),
                        pos.get("NavigationalStatus", 0),
                        meta.get("ShipType", 0),
                    ])

asyncio.run(collect())
```

### Step 2: Smart Processing Logic

```python
# In the Streamlit app

import pandas as pd
from shapely.geometry import Point, Polygon

# Define Piraeus anchorage zone (approximate polygon)
ANCHORAGE_ZONE = Polygon([
    (23.55, 37.88), (23.62, 37.88),
    (23.65, 37.93), (23.58, 37.95),
    (23.53, 37.92), (23.55, 37.88)
])

def classify_vessel_state(group):
    """For each vessel (MMSI), classify state from position history"""
    latest = group.sort_values("timestamp").iloc[-1]
    avg_speed = group["sog"].mean()
    in_anchorage = ANCHORAGE_ZONE.contains(Point(latest["lon"], latest["lat"]))

    if avg_speed < 0.5 and in_anchorage:
        return "WAITING_AT_ANCHOR"
    elif avg_speed < 0.5 and not in_anchorage:
        return "BERTHED_OR_MOORED"
    elif avg_speed < 3:
        return "MANEUVERING"
    else:
        return "IN_TRANSIT"

def calculate_wait_time(group):
    """Estimate how long vessel has been waiting"""
    sorted_g = group.sort_values("timestamp")
    slow_positions = sorted_g[sorted_g["sog"] < 0.5]
    if len(slow_positions) < 2:
        return 0
    first_slow = slow_positions.iloc[0]["timestamp"]
    last_slow = slow_positions.iloc[-1]["timestamp"]
    return (last_slow - first_slow).total_seconds() / 3600  # hours

# Ship type mapping (AIS type codes)
SHIP_TYPES = {
    70: "Cargo", 71: "Cargo", 72: "Cargo", 79: "Cargo",
    80: "Tanker", 81: "Tanker", 82: "Tanker", 89: "Tanker",
    60: "Passenger", 69: "Passenger",
    30: "Fishing",
    0: "Unknown"
}
```

### Step 3: Streamlit Dashboard

**Layout:**

- Sidebar: port selector (Piraeus default, can add more later), date filter, ship type filter, min wait threshold
- Row 1: KPI cards — Total vessels in area | Currently waiting | Avg wait time | Congestion index
- Row 2: Map (Folium) — vessels colored by state (red=waiting, green=transit, yellow=maneuvering, blue=berthed)
- Row 3 tabs:
  - Wait times by ship type (bar chart)
  - Congestion over time (line chart — vessels waiting per hour/day)
  - Vessel list table (sortable: name, MMSI, type, state, wait time)
  - Anchorage heatmap (where exactly are ships clustering)

**Congestion Index formula:**
```python
congestion_index = current_waiting_vessels / historical_avg_waiting_vessels * 100
# >100 = more congested than usual, <100 = less
```

### Step 4: Polish

- "Export CSV" button for filtered vessel list
- About tab explaining methodology
- Clean README with screenshots
- Optional: "Live mode" toggle that connects directly to aisstream websocket (advanced — may not work well on Streamlit Cloud due to websocket limitations, so static data is safer)

### Deploy
- Streamlit Cloud (free)
- `requirements.txt`: streamlit, pandas, folium, streamlit-folium, plotly, shapely, geopandas
- Include a pre-collected `piraeus_ais.csv` sample (2-3 days of data) so the demo works without live API

### Time estimate: 8-10 hours total (including data collection time)

---

## Recommended Sequence

**This weekend:**
1. Saturday morning: fix Med Vessel Behaviour Monitor (4-6h) → deploy
2. Saturday evening: register aisstream.io API key, start collector script running overnight for Piraeus
3. Sunday: build PortPulse Streamlit app using collected data (6-8h) → deploy

**Result:** Two deployed portfolio projects by Monday, both demonstrating AIS data skills, maritime intelligence thinking, and Python/Streamlit proficiency. Link both from your GitHub portfolio.

---

## Interview Talking Points

**Med Vessel Behaviour Monitor:** "I built a risk-scoring tool that flags suspicious vessel behaviour in the Mediterranean — AIS gaps, encounters, loitering — weighted by flag state and event type. It uses the Global Fishing Watch API and a custom scoring model that reflects sanctions and dark-fleet patterns."

**PortPulse:** "I built a port congestion analyzer using live AIS data from Piraeus. It automatically classifies vessels as waiting, berthed, or in transit based on speed and position, calculates wait times by ship type, and computes a real-time congestion index. The kind of operational intelligence that shipping companies and port authorities need."
