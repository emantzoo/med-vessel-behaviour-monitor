"""Data loading: static fallback, GFW live API, FDI spatial data, RAG knowledge base."""

import os
import glob
import asyncio
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config import classify_med_zone


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


# ========================= STATIC DATA =========================

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

    dur_map = {"GAP": (6, 72), "LOITERING": (4, 48), "ENCOUNTER": (2, 24)}
    durations = [round(rng.uniform(*dur_map[et]), 1) for et in event_types]

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

    cargo_names = ["ATLANTIC SPIRIT", "COSCO HARMONY", "GOLDEN EAGLE", "SEA PIONEER",
                   "NORDIC STAR", "AEGEAN WIND", "MED CARRIER", "BLACK SEA EXPRESS"]
    tanker_names = ["CRUDE VENTURE", "OIL TRADER", "PETRO STAR", "FUEL MASTER"]
    vessel_names = rng.choice(cargo_names + tanker_names, n)

    type_pool = ["CARRIER", "FISHING", "CARGO", "TANKER", "SUPPORT"]
    vessel_types = rng.choice(type_pool, n, p=[0.25, 0.30, 0.20, 0.15, 0.10])

    distance_shore = np.round(rng.uniform(2, 250, n), 1)
    distance_port = np.round(distance_shore * rng.uniform(1.0, 2.5, n), 1)

    ports = ["Piraeus", "Valletta", "Genoa", "Barcelona", "Mersin", "Haifa",
             "Alexandria", "Izmir", "Marseille", "Algeciras"]
    nearest_ports = rng.choice(ports, n)

    eezs = ["Greece", "Italy", "Turkey", "Spain", "Malta", "Libya", "Tunisia",
            "Egypt", "Cyprus", "International Waters"]
    eez_vals = rng.choice(eezs, n, p=[0.15, 0.15, 0.10, 0.10, 0.05,
                                       0.08, 0.07, 0.05, 0.05, 0.20])

    df = pd.DataFrame({
        "event_type": event_types, "mmsi": mmsis, "flag": flags,
        "vessel_name": vessel_names, "vessel_type": vessel_types,
        "duration_h": durations, "lat": lats, "lon": lons, "date": dates,
        "distance_from_shore_km": distance_shore,
        "distance_from_port_km": distance_port,
        "nearest_port": nearest_ports, "eez": eez_vals,
    })

    gap_mask = df["event_type"] == "GAP"
    gap_n = gap_mask.sum()
    df.loc[gap_mask, "gap_distance_km"] = np.round(rng.uniform(10, 500, gap_n), 1)
    df.loc[gap_mask, "speed_before_gap"] = np.round(rng.uniform(0.5, 14, gap_n), 1)
    df.loc[gap_mask, "speed_after_gap"] = np.round(rng.uniform(0.5, 14, gap_n), 1)

    enc_mask = df["event_type"] == "ENCOUNTER"
    enc_n = enc_mask.sum()
    enc_names = ["SHADOW CARRIER", "REEFER KING", "COLD STAR", "FISH RUNNER",
                 "NEPTUNE BULK", "CARGO QUEEN"]
    df.loc[enc_mask, "encounter_vessel_name"] = rng.choice(enc_names, enc_n)
    df.loc[enc_mask, "encounter_vessel_flag"] = rng.choice(
        ["PAN", "LBR", "GRC", "MLT", "RUS", "MHL"], enc_n)
    df.loc[enc_mask, "encounter_median_distance_km"] = np.round(rng.uniform(0.05, 2.0, enc_n), 2)
    df.loc[enc_mask, "encounter_median_speed_knots"] = np.round(rng.uniform(0.5, 3.0, enc_n), 1)

    loit_mask = df["event_type"] == "LOITERING"
    loit_n = loit_mask.sum()
    df.loc[loit_mask, "loitering_total_distance_km"] = np.round(rng.uniform(5, 150, loit_n), 1)
    df.loc[loit_mask, "loitering_avg_speed_knots"] = np.round(rng.uniform(0.3, 2.5, loit_n), 1)

    df["med_zone"] = df.apply(lambda r: classify_med_zone(r["lon"], r["lat"]), axis=1)
    return df


# ========================= LIVE GFW API =========================

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

        rows = []
        for _, r in raw_df.iterrows():
            row_dict = {}
            row_dict["event_type"] = str(r.get("type", "")).upper()
            row_dict["date"] = r.get("start")

            pos = r.get("position") if isinstance(r.get("position"), dict) else {}
            row_dict["lat"] = pos.get("lat")
            row_dict["lon"] = pos.get("lon")

            vessel = r.get("vessel") if isinstance(r.get("vessel"), dict) else {}
            row_dict["mmsi"] = vessel.get("ssvid", "0")
            row_dict["flag"] = vessel.get("flag", "UNK")
            row_dict["vessel_name"] = vessel.get("name", "")
            row_dict["vessel_type"] = vessel.get("type", "")

            if r.get("start") and r.get("end"):
                try:
                    start_dt = pd.to_datetime(r["start"])
                    end_dt = pd.to_datetime(r["end"])
                    row_dict["duration_h"] = round((end_dt - start_dt).total_seconds() / 3600, 1)
                except Exception:
                    row_dict["duration_h"] = 0

            distances = r.get("distances") if isinstance(r.get("distances"), dict) else {}
            row_dict["distance_from_shore_km"] = distances.get("shoreDistanceKm")
            row_dict["distance_from_port_km"] = distances.get("portDistanceKm")
            port = distances.get("port") if isinstance(distances.get("port"), dict) else {}
            row_dict["nearest_port"] = port.get("name")

            for region in (r.get("regions") or []):
                if isinstance(region, dict):
                    ds = region.get("dataset", "")
                    if "eez" in ds:
                        row_dict["eez"] = region.get("name")

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
        type_map = {"GAP": "GAP", "ENCOUNTER": "ENCOUNTER", "LOITERING": "LOITERING"}
        df["event_type"] = df["event_type"].map(type_map).fillna(df["event_type"])

        if "lat" in df.columns and "lon" in df.columns:
            df["med_zone"] = df.apply(
                lambda r: classify_med_zone(r["lon"], r["lat"])
                if pd.notna(r.get("lon")) and pd.notna(r.get("lat")) else "", axis=1)

        return df

    except Exception as e:
        st.error(f"Live API error: {e}. Falling back to static demo data.")
        return load_static_data()


# ========================= FDI DATA =========================

@st.cache_data
def load_fdi_effort():
    path = os.path.join(os.path.dirname(__file__), "data", "fdi_effort_med.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


@st.cache_data
def load_fdi_landings():
    path = os.path.join(os.path.dirname(__file__), "data", "fdi_landings_med.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()
