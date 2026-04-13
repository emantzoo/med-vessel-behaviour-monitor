"""Data loading: static fallback, GFW live API, FDI spatial data, RAG knowledge base."""

import os
import glob
import asyncio
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config import classify_med_zone, classify_mpa_tier, resolve_eez_name

# WDPA ID → name lookup (for resolving numeric MPA IDs from fishing events API)
_WDPA_LOOKUP_PATH = os.path.join(os.path.dirname(__file__), "data", "wdpa_mpa_lookup.csv")
_WDPA_NAMES = {}
if os.path.exists(_WDPA_LOOKUP_PATH):
    _wdpa_df = pd.read_csv(_WDPA_LOOKUP_PATH, dtype={"wdpa_id": str})
    _WDPA_NAMES = dict(zip(_wdpa_df["wdpa_id"], _wdpa_df["name"]))
    del _wdpa_df


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
        df = pd.read_csv(csv_path, parse_dates=["date"], dtype={"imo": str})
        df["imo"] = df["imo"].fillna("")
        # Ensure MPA columns exist even for pre-MPA demo rows
        if "mpa" not in df.columns:
            df["mpa"] = ""
        if "mpa_tier" not in df.columns:
            df["mpa_tier"] = ""
        if "in_mpa" not in df.columns:
            df["in_mpa"] = df["mpa"].fillna("").astype(str).str.len() > 0
        df["mpa"] = df["mpa"].fillna("")
        df["mpa_tier"] = df["mpa_tier"].fillna("")
        df["in_mpa"] = df["in_mpa"].fillna(False).astype(bool)
        return df

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
    df.loc[gap_mask, "gap_implied_speed_knots"] = np.round(rng.uniform(0.5, 14, gap_n), 1)
    df.loc[gap_mask, "gap_intentional_disabling"] = rng.choice([True, False], gap_n, p=[0.2, 0.8])

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

    df["imo"] = ""
    df["med_zone"] = df.apply(lambda r: classify_med_zone(r["lon"], r["lat"]), axis=1)
    return df


# ========================= API SNAPSHOT (download once, keep as CSV) =========

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_SNAPSHOT_EVENTS = os.path.join(_DATA_DIR, "api_events_snapshot.csv")
_SNAPSHOT_FISHING = os.path.join(_DATA_DIR, "api_fishing_snapshot.csv")


def snapshot_exists():
    """True if a cached API snapshot CSV is present."""
    return os.path.exists(_SNAPSHOT_EVENTS)


def snapshot_info():
    """Return (event_count, fishing_count, file_date) or None."""
    if not snapshot_exists():
        return None
    mtime = datetime.fromtimestamp(os.path.getmtime(_SNAPSHOT_EVENTS))
    ev_count = sum(1 for _ in open(_SNAPSHOT_EVENTS, encoding="utf-8")) - 1
    fish_count = 0
    if os.path.exists(_SNAPSHOT_FISHING):
        fish_count = sum(1 for _ in open(_SNAPSHOT_FISHING, encoding="utf-8")) - 1
    return ev_count, fish_count, mtime


def _gfw_post(token, datasets, start_date, end_date, page_size=5000, progress=None):
    """Direct REST call to GFW Events API v3 with auto-pagination."""
    import requests as _requests

    url = "https://gateway.api.globalfishingwatch.org/v3/events"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "datasets": datasets,
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-6, 30], [36.5, 30], [36.5, 46], [-6, 46], [-6, 30]]],
        },
    }
    all_entries = []
    offset = 0
    while True:
        resp = _requests.post(
            url, json=body, headers=headers,
            params={"limit": page_size, "offset": offset}, timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("entries", [])
        all_entries.extend(entries)
        total = data.get("total", len(all_entries))
        next_offset = data.get("nextOffset")
        if progress:
            progress(f"Fetched {len(all_entries)}/{total} events...")
        if next_offset is None or next_offset >= total or not entries:
            break
        offset = next_offset
    return all_entries


def download_api_snapshot(token, start_date, end_date, include_fishing=False, progress=None):
    """Fetch events (+ optionally fishing) from GFW API via plain REST and save to CSV.

    Returns (events_df, fishing_df). Both are also persisted to
    data/api_events_snapshot.csv and data/api_fishing_snapshot.csv
    so subsequent runs can use them without an API key.
    """
    if progress:
        progress(0.1, "Fetching behavioural events (gaps, encounters, loitering)...")

    raw_entries = _gfw_post(token, [
        "public-global-gaps-events:latest",
        "public-global-encounters-events:latest",
        "public-global-loitering-events:latest",
    ], start_date, end_date)

    raw_events = pd.DataFrame(raw_entries) if raw_entries else pd.DataFrame()
    events_df = _parse_events_df(raw_events) if not raw_events.empty else pd.DataFrame()

    fishing_df = pd.DataFrame()
    if include_fishing:
        if progress:
            progress(0.5, f"Got {len(events_df)} events. Fetching fishing events...")

        raw_fishing_entries = _gfw_post(token, [
            "public-global-fishing-events:latest",
        ], start_date, end_date)

        raw_fishing = pd.DataFrame(raw_fishing_entries) if raw_fishing_entries else pd.DataFrame()
        fishing_df = _parse_fishing_df(raw_fishing) if not raw_fishing.empty else pd.DataFrame()

    if progress:
        progress(0.8, "Saving to CSV...")

    # Persist
    if not events_df.empty:
        events_df.to_csv(_SNAPSHOT_EVENTS, index=False)
    if not fishing_df.empty:
        fishing_df.to_csv(_SNAPSHOT_FISHING, index=False)

    if progress:
        progress(1.0, "Done.")

    return events_df, fishing_df


@st.cache_data
def load_snapshot_events():
    """Load cached API events snapshot."""
    if not os.path.exists(_SNAPSHOT_EVENTS):
        return load_static_data()
    df = pd.read_csv(_SNAPSHOT_EVENTS, parse_dates=["date"])
    df["imo"] = df["imo"].astype(str).fillna("") if "imo" in df.columns else ""
    if "vessel_id" not in df.columns:
        df["vessel_id"] = ""
    df["vessel_id"] = df["vessel_id"].fillna("")
    for col, default in [("mpa", ""), ("mpa_tier", ""), ("in_mpa", False)]:
        if col not in df.columns:
            df[col] = default
    df["mpa"] = df["mpa"].fillna("")
    df["mpa_tier"] = df["mpa_tier"].fillna("")
    df["in_mpa"] = df["in_mpa"].fillna(False).astype(bool)
    # Resolve numeric EEZ MRGIDs to country names (for old snapshots)
    if "eez" in df.columns:
        df["eez"] = df["eez"].map(resolve_eez_name)
    # Rename legacy gap columns from old snapshots
    _rename = {}
    if "speed_before_gap" in df.columns and "gap_implied_speed_knots" not in df.columns:
        _rename["speed_before_gap"] = "gap_implied_speed_knots"
    if "speed_after_gap" in df.columns and "gap_intentional_disabling" not in df.columns:
        _rename["speed_after_gap"] = "gap_intentional_disabling"
    if _rename:
        df = df.rename(columns=_rename)
    return df


@st.cache_data
def load_snapshot_fishing():
    """Load cached API fishing snapshot."""
    if not os.path.exists(_SNAPSHOT_FISHING):
        return load_fishing_events_static()
    df = pd.read_csv(_SNAPSHOT_FISHING, parse_dates=["date"])
    if "vessel_id" not in df.columns:
        df["vessel_id"] = ""
    df["vessel_id"] = df["vessel_id"].fillna("")
    for col, default in [("mpa", ""), ("mpa_tier", ""), ("in_mpa", False), ("in_no_take_mpa", False)]:
        if col not in df.columns:
            df[col] = default
    df["mpa"] = df["mpa"].fillna("")
    df["mpa_tier"] = df["mpa_tier"].fillna("")
    df["in_mpa"] = df["in_mpa"].fillna(False).astype(bool)
    df["in_no_take_mpa"] = df["in_no_take_mpa"].fillna(False).astype(bool)
    return df


# ========================= GFW INSIGHTS API =========================

_SNAPSHOT_INSIGHTS = os.path.join(_DATA_DIR, "api_insights_snapshot.csv")


def _parse_single_insight(vessel_id, mmsi, raw):
    """Parse a single-vessel Insights API JSON response into a flat dict."""
    row = {"vessel_id": vessel_id, "mmsi": str(mmsi)}

    cov = raw.get("coverage") or {}
    row["ais_coverage_pct"] = cov.get("percentage")

    af = raw.get("apparentFishing") or {}
    counters = af.get("periodSelectedCounters") or {}
    row["fishing_events"] = counters.get("events", 0)
    row["fishing_without_rfmo_auth_events"] = counters.get(
        "eventsInRFMOWithoutKnownAuthorization", 0
    )
    row["fishing_in_no_take_mpa_events"] = counters.get("eventsInNoTakeMPAs", 0)

    vi = raw.get("vesselIdentity") or {}
    iuu = vi.get("iuuVesselList") or {}
    row["iuu_times_listed"] = iuu.get("totalTimesListed", 0)
    row["iuu_listed"] = row["iuu_times_listed"] > 0

    gap = raw.get("gap") or {}
    gap_counters = gap.get("periodSelectedCounters") or {}
    row["gap_events"] = gap_counters.get("events", 0)

    return row


def fetch_vessel_insights(token, vessel_id, start_date, end_date):
    """Single-vessel Insights API call. Returns dict or None on failure.

    Used on the Investigation tab for on-demand enrichment (~1.5s).
    """
    import requests as _requests

    url = "https://gateway.api.globalfishingwatch.org/v3/insights/vessels"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "includes": ["FISHING", "COVERAGE", "VESSEL-IDENTITY-IUU-VESSEL-LIST", "GAP"],
        "startDate": start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date),
        "endDate": end_date.strftime("%Y-%m-%d") if hasattr(end_date, "strftime") else str(end_date),
        "vessels": [
            {"vesselId": vessel_id, "datasetId": "public-global-vessel-identity:latest"}
        ],
    }
    try:
        resp = _requests.post(url, json=body, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def download_insights_snapshot(token, start_date, end_date, vessel_records,
                               concurrency=10, progress=None):
    """Query GFW Insights API for a list of vessels concurrently. Save to CSV.

    Sends one vessel per POST (GFW API does not reliably support multi-vessel
    batches) but runs up to *concurrency* requests in parallel via aiohttp.

    vessel_records: list of (vessel_id, mmsi) tuples.
    Returns DataFrame with one row per vessel.
    """
    import asyncio
    try:
        import aiohttp
    except ImportError:
        return _download_insights_sequential(token, start_date, end_date,
                                             vessel_records, progress)

    url = "https://gateway.api.globalfishingwatch.org/v3/insights/vessels"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    sd = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)
    ed = end_date.strftime("%Y-%m-%d") if hasattr(end_date, "strftime") else str(end_date)

    unique = list({vid: mmsi for vid, mmsi in vessel_records if vid}.items())
    if not unique:
        return pd.DataFrame()

    all_rows = []
    _done = {"n": 0}

    async def fetch_one(session, sem, vid, mmsi):
        async with sem:
            body = {
                "includes": ["FISHING", "COVERAGE", "VESSEL-IDENTITY-IUU-VESSEL-LIST", "GAP"],
                "startDate": sd, "endDate": ed,
                "vessels": [{"vesselId": vid, "datasetId": "public-global-vessel-identity:latest"}],
            }
            try:
                async with session.post(url, json=body, headers=headers) as resp:
                    if resp.status == 201:
                        raw = await resp.json()
                        all_rows.append(_parse_single_insight(vid, mmsi, raw))
            except Exception:
                pass
            finally:
                _done["n"] += 1
                if progress:
                    progress(_done["n"], len(unique))

    async def _run():
        sem = asyncio.Semaphore(concurrency)
        connector = aiohttp.TCPConnector(limit=concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            await asyncio.gather(*[
                fetch_one(session, sem, vid, mmsi) for vid, mmsi in unique
            ])

    try:
        asyncio.run(_run())
    except RuntimeError:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(_run())

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df.to_csv(_SNAPSHOT_INSIGHTS, index=False)
    return df


def _download_insights_sequential(token, start_date, end_date, vessel_records, progress=None):
    """Fallback: sequential single-vessel calls when aiohttp unavailable."""
    unique = list({vid: mmsi for vid, mmsi in vessel_records if vid}.items())
    rows = []
    for i, (vid, mmsi) in enumerate(unique):
        raw = fetch_vessel_insights(token, vid, start_date, end_date)
        if raw:
            rows.append(_parse_single_insight(vid, mmsi, raw))
        if progress:
            progress(i + 1, len(unique))
    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_csv(_SNAPSHOT_INSIGHTS, index=False)
    return df


def insights_snapshot_exists():
    """True if a cached Insights API snapshot CSV is present."""
    return os.path.exists(_SNAPSHOT_INSIGHTS)


def insights_snapshot_info():
    """Return (vessel_count, file_date) or None."""
    if not insights_snapshot_exists():
        return None
    mtime = datetime.fromtimestamp(os.path.getmtime(_SNAPSHOT_INSIGHTS))
    count = sum(1 for _ in open(_SNAPSHOT_INSIGHTS, encoding="utf-8")) - 1
    return count, mtime


@st.cache_data
def load_snapshot_insights():
    """Load cached Insights API snapshot."""
    if not os.path.exists(_SNAPSHOT_INSIGHTS):
        return pd.DataFrame()
    df = pd.read_csv(_SNAPSHOT_INSIGHTS)
    for col in ["vessel_id", "mmsi"]:
        if col in df.columns:
            df[col] = df[col].astype(str).fillna("")
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


def _parse_events_df(raw_df):
    """Parse raw GFW API events dataframe into flat rows."""
    rows = []
    for _, r in raw_df.iterrows():
        row_dict = {}
        row_dict["event_type"] = str(r.get("type", "")).upper()
        row_dict["date"] = r.get("start")

        pos = r.get("position") if isinstance(r.get("position"), dict) else {}
        row_dict["lat"] = pos.get("lat")
        row_dict["lon"] = pos.get("lon")

        vessel = r.get("vessel") if isinstance(r.get("vessel"), dict) else {}
        row_dict["vessel_id"] = vessel.get("id", "")  # GFW UUID for Insights API
        row_dict["mmsi"] = vessel.get("ssvid", "0")
        row_dict["flag"] = vessel.get("flag", "UNK")
        row_dict["vessel_name"] = vessel.get("name", "")
        row_dict["vessel_type"] = vessel.get("type", "")

        row_dict["duration_h"] = 0
        if r.get("start") and r.get("end"):
            try:
                start_dt = pd.to_datetime(r["start"])
                end_dt = pd.to_datetime(r["end"])
                row_dict["duration_h"] = round((end_dt - start_dt).total_seconds() / 3600, 1)
            except Exception:
                pass

        distances = r.get("distances") if isinstance(r.get("distances"), dict) else {}
        row_dict["distance_from_shore_km"] = distances.get("shoreDistanceKm")
        row_dict["distance_from_port_km"] = distances.get("portDistanceKm")
        port = distances.get("port") if isinstance(distances.get("port"), dict) else {}
        row_dict["nearest_port"] = port.get("name")

        # Parse regions — handles both formats:
        # 1. List of dicts: [{"dataset": "public-mpa-all", "name": "..."}]
        # 2. Flat dict:     {"mpa": [id1], "eez": [...], "rfmo": [...]}
        mpa_names, rfmo_names, mpa_ids = [], [], []
        _has_no_take = False
        regions = r.get("regions")
        if isinstance(regions, list):
            # Format 1: list of region dicts
            for region in regions:
                if isinstance(region, dict):
                    ds = str(region.get("dataset", "")).lower()
                    name = region.get("name")
                    rid = region.get("id")
                    if "eez" in ds:
                        row_dict["eez"] = name
                    elif "mpa" in ds and name:
                        mpa_names.append(str(name))
                        if rid:
                            mpa_ids.append(str(rid))
                    elif "rfmo" in ds and name:
                        rfmo_names.append(str(name))
        elif isinstance(regions, dict):
            # Format 2: flat dict with array values
            eez_ids = regions.get("eez")
            if isinstance(eez_ids, list) and eez_ids:
                row_dict["eez"] = resolve_eez_name(eez_ids[0]) or str(eez_ids[0])
            _seen_ids = set()
            for key in ("mpa", "mpaNoTake", "mpaNoTakePartial"):
                ids = regions.get(key)
                if isinstance(ids, list) and ids:
                    for i in ids:
                        sid = str(i)
                        if sid not in _seen_ids:
                            mpa_ids.append(sid)
                            _seen_ids.add(sid)
                    if key in ("mpaNoTake", "mpaNoTakePartial"):
                        _has_no_take = True
            rfmo_ids = regions.get("rfmo")
            if isinstance(rfmo_ids, list):
                rfmo_names.extend(str(i) for i in rfmo_ids)
        # Resolve numeric WDPA IDs to names via lookup table
        if mpa_ids and not mpa_names:
            for mid in mpa_ids:
                resolved = _WDPA_NAMES.get(mid)
                if resolved:
                    mpa_names.append(resolved)
        row_dict["mpa"] = "; ".join(mpa_names) if mpa_names else "; ".join(mpa_ids)
        row_dict["mpa_ids"] = "; ".join(mpa_ids) if mpa_ids else ""
        row_dict["rfmo"] = "; ".join(rfmo_names) if rfmo_names else ""
        row_dict["in_mpa"] = bool(mpa_names or mpa_ids)
        # Persist the no-take signal from GFW's mpaNoTake field
        if not _has_no_take and mpa_names:
            _joined = " | ".join(str(n).lower() for n in mpa_names)
            _has_no_take = any(
                kw in _joined for kw in ("no-take", "no take", "integral reserve", "zone a")
            )
        row_dict["in_no_take_mpa"] = _has_no_take
        if mpa_names:
            row_dict["mpa_tier"] = classify_mpa_tier(mpa_names)
        elif mpa_ids:
            row_dict["mpa_tier"] = "gfcm_fra" if _has_no_take else "general"
        else:
            row_dict["mpa_tier"] = ""

        if row_dict["event_type"] == "GAP":
            gap_info = r.get("gap") if isinstance(r.get("gap"), dict) else {}
            row_dict["gap_distance_km"] = gap_info.get("distanceKm")
            row_dict["gap_implied_speed_knots"] = gap_info.get("impliedSpeedKnots")
            row_dict["gap_intentional_disabling"] = gap_info.get("intentionalDisabling")
        elif row_dict["event_type"] == "ENCOUNTER":
            enc_info = r.get("encounter") if isinstance(r.get("encounter"), dict) else {}
            enc_vessel = enc_info.get("vessel") if isinstance(enc_info.get("vessel"), dict) else {}
            row_dict["encounter_vessel_name"] = enc_vessel.get("name")
            row_dict["encounter_vessel_flag"] = enc_vessel.get("flag")
            row_dict["encounter_median_distance_km"] = enc_info.get("medianDistanceKilometers")
            row_dict["encounter_median_speed_knots"] = enc_info.get("medianSpeedKnots")
        elif row_dict["event_type"] == "LOITERING":
            loit_info = r.get("loitering") if isinstance(r.get("loitering"), dict) else {}
            row_dict["loitering_total_distance_km"] = loit_info.get("totalDistanceKm")
            row_dict["loitering_avg_speed_knots"] = loit_info.get("averageSpeedKnots")

        rows.append(row_dict)

    df = pd.DataFrame(rows)
    type_map = {"GAP": "GAP", "ENCOUNTER": "ENCOUNTER", "LOITERING": "LOITERING"}
    df["event_type"] = df["event_type"].map(type_map).fillna(df["event_type"])

    if "lat" in df.columns and "lon" in df.columns:
        df["med_zone"] = df.apply(
            lambda r: classify_med_zone(r["lon"], r["lat"])
            if pd.notna(r.get("lon")) and pd.notna(r.get("lat")) else "", axis=1)

    df["imo"] = ""
    return df


def _parse_fishing_df(raw_df):
    """Parse raw GFW fishing events into flat rows."""
    rows = []
    for _, r in raw_df.iterrows():
        row = {}
        row["date"] = r.get("start")
        pos = r.get("position") if isinstance(r.get("position"), dict) else {}
        row["lat"] = pos.get("lat")
        row["lon"] = pos.get("lon")

        vessel = r.get("vessel") if isinstance(r.get("vessel"), dict) else {}
        row["vessel_id"] = vessel.get("id", "")  # GFW UUID for Insights API
        row["mmsi"] = vessel.get("ssvid", "0")
        row["flag"] = vessel.get("flag", "UNK")
        row["vessel_name"] = vessel.get("name", "")

        row["fishing_hours"] = 0.0
        if r.get("start") and r.get("end"):
            try:
                start_dt = pd.to_datetime(r["start"])
                end_dt = pd.to_datetime(r["end"])
                row["fishing_hours"] = round((end_dt - start_dt).total_seconds() / 3600, 2)
            except Exception:
                pass

        # Parse regions — handles both formats:
        # 1. List of dicts: [{"dataset": "public-mpa-all", "name": "..."}]
        # 2. Flat dict:     {"mpa": [id1, id2], "mpaNoTake": [...], ...}
        mpa_names, mpa_ids = [], []
        _has_no_take = False
        regions = r.get("regions")
        if isinstance(regions, list):
            # Format 1: list of region dicts (same as behavioural events)
            for region in regions:
                if isinstance(region, dict):
                    ds = str(region.get("dataset", "")).lower()
                    name = region.get("name")
                    if "mpa" in ds and name:
                        mpa_names.append(str(name))
        elif isinstance(regions, dict):
            # Format 2: flat dict with array values (fishing events v3)
            # mpaNoTake/mpaNoTakePartial are subsets of mpa — deduplicate
            _seen_ids = set()
            for key in ("mpa", "mpaNoTake", "mpaNoTakePartial"):
                ids = regions.get(key)
                if isinstance(ids, list) and ids:
                    for i in ids:
                        sid = str(i)
                        if sid not in _seen_ids:
                            mpa_ids.append(sid)
                            _seen_ids.add(sid)
                    if key in ("mpaNoTake", "mpaNoTakePartial"):
                        _has_no_take = True
        # Resolve numeric WDPA IDs to names via lookup table
        if mpa_ids and not mpa_names:
            for mid in mpa_ids:
                resolved = _WDPA_NAMES.get(mid)
                if resolved:
                    mpa_names.append(resolved)
        row["mpa"] = "; ".join(mpa_names) if mpa_names else "; ".join(mpa_ids)
        row["mpa_ids"] = "; ".join(mpa_ids)
        row["in_mpa"] = bool(mpa_names or mpa_ids)
        # Persist the no-take signal from GFW's mpaNoTake field
        if not _has_no_take and mpa_names:
            _joined = " | ".join(str(n).lower() for n in mpa_names)
            _has_no_take = any(
                kw in _joined for kw in ("no-take", "no take", "integral reserve", "zone a")
            )
        row["in_no_take_mpa"] = _has_no_take
        if mpa_names:
            row["mpa_tier"] = classify_mpa_tier(mpa_names)
        elif mpa_ids:
            row["mpa_tier"] = "gfcm_fra" if _has_no_take else "general"
        else:
            row["mpa_tier"] = ""
        rows.append(row)

    return pd.DataFrame(rows)


@st.cache_data
def load_live_data(token, start_date, end_date, _min_dur):
    """Fetch events from GFW Events API v3 via plain REST."""
    try:
        raw_entries = _gfw_post(token, [
            "public-global-gaps-events:latest",
            "public-global-encounters-events:latest",
            "public-global-loitering-events:latest",
        ], start_date, end_date)

        if not raw_entries:
            st.warning("No events returned from API for this period.")
            return load_static_data()

        raw_df = pd.DataFrame(raw_entries)
        return _parse_events_df(raw_df)

    except Exception as e:
        st.error(f"Live API error: {e}. Falling back to static demo data.")
        return load_static_data()


# ========================= FISHING EVENTS =========================

@st.cache_data
def load_fishing_events_static():
    """Static demo dataset of fishing-event-style rows for the three MPA seeds.

    Live mode pulls from GFW's public-global-fishing-events:latest dataset.
    Static mode mirrors the structure with a tiny seeded fixture so the
    Vessel Summary and Investigation tabs render meaningful fishing-in-MPA
    counts without an API key. Schema is the minimum needed for the
    fishing-in-MPA aggregation: vessel_name, mmsi, lat/lon, fishing_hours,
    mpa, mpa_tier, in_mpa.
    """
    csv_path = os.path.join(os.path.dirname(__file__), "data", "med_fishing_static.csv")
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, parse_dates=["date"])
        for col, default in [("mpa", ""), ("mpa_tier", ""), ("in_mpa", False), ("in_no_take_mpa", False)]:
            if col not in df.columns:
                df[col] = default
        df["mpa"] = df["mpa"].fillna("")
        df["mpa_tier"] = df["mpa_tier"].fillna("")
        df["in_mpa"] = df["in_mpa"].fillna(False).astype(bool)
        df["in_no_take_mpa"] = df["in_no_take_mpa"].fillna(False).astype(bool)
        return df
    return pd.DataFrame(columns=[
        "date", "vessel_name", "mmsi", "lat", "lon",
        "fishing_hours", "mpa", "mpa_tier", "in_mpa", "in_no_take_mpa",
    ])


@st.cache_data
def load_fishing_events_live(token, start_date, end_date):
    """Fetch fishing events from GFW Events API v3 via plain REST."""
    try:
        raw_entries = _gfw_post(token, [
            "public-global-fishing-events:latest",
        ], start_date, end_date)

        if not raw_entries:
            return load_fishing_events_static()

        raw_df = pd.DataFrame(raw_entries)
        return _parse_fishing_df(raw_df)

    except Exception as e:
        st.warning(f"Fishing events API error: {e}. Using static fishing fixture.")
        return load_fishing_events_static()


def aggregate_fishing_in_mpa(fishing_df):
    """Per-vessel aggregation of fishing-in-MPA hours and event counts.

    Returns a dataframe keyed by mmsi with columns:
        fishing_in_mpa_events, fishing_in_mpa_hours, fishing_in_mpa_top_tier
    Vessels with no fishing-in-MPA activity are not included; the caller
    can left-join on mmsi and fill missing values.
    """
    if fishing_df is None or fishing_df.empty or "in_mpa" not in fishing_df.columns:
        return pd.DataFrame(columns=[
            "mmsi", "fishing_in_mpa_events",
            "fishing_in_mpa_hours", "fishing_in_mpa_top_tier",
        ])
    in_mpa = fishing_df[fishing_df["in_mpa"].fillna(False).astype(bool)].copy()
    if in_mpa.empty:
        return pd.DataFrame(columns=[
            "mmsi", "fishing_in_mpa_events",
            "fishing_in_mpa_hours", "fishing_in_mpa_top_tier",
        ])

    tier_priority = {"gfcm_fra": 3, "eu_site": 2, "general": 1, "": 0}

    def _top_tier(s):
        tiers = [str(t) for t in s.fillna("").tolist()]
        return max(tiers, key=lambda t: tier_priority.get(t, 0)) if tiers else ""

    agg = in_mpa.groupby("mmsi").agg(
        fishing_in_mpa_events=("in_mpa", "sum"),
        fishing_in_mpa_hours=("fishing_hours", "sum"),
        fishing_in_mpa_top_tier=("mpa_tier", _top_tier),
    ).reset_index()
    agg["fishing_in_mpa_events"] = agg["fishing_in_mpa_events"].astype(int)
    agg["fishing_in_mpa_hours"] = agg["fishing_in_mpa_hours"].round(1)
    return agg


# ========================= VESSEL IMO LOOKUP =========================

def lookup_vessel_metadata(mmsi_list, token, progress_callback=None):
    """Query GFW Vessels API to retrieve registry metadata for unique MMSIs.

    Returns dict of {mmsi_str: {"imo", "length_m", "tonnage_gt", "shiptypes"}}.
    Each field is independently optional -- a vessel may resolve IMO from
    registry_info while length comes from self_reported_info, etc. Walks
    both lists and takes the first non-null per field.

    Skips invalid MMSIs and handles errors per vessel gracefully.
    progress_callback(current, total) is called after each MMSI lookup.
    """
    try:
        import gfwapiclient as gfw
    except ImportError:
        return {}

    unique_mmsis = list({
        str(m).strip() for m in mmsi_list
        if str(m).strip() not in ("", "0", "nan", "None")
    })
    if not unique_mmsis:
        return {}

    client = gfw.Client(access_token=token)
    result = {}
    total = len(unique_mmsis)

    def _coerce_float(val):
        try:
            f = float(val)
            return f if f > 0 else None
        except (TypeError, ValueError):
            return None

    def _harvest(entries, meta):
        """Update meta dict in-place with first non-null fields from a list of dicts."""
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if meta.get("imo") in (None, "") and entry.get("imo"):
                imo_str = str(entry["imo"])
                if imo_str not in ("0", "None", "nan", ""):
                    meta["imo"] = imo_str
            if meta.get("length_m") is None:
                length = _coerce_float(entry.get("lengthM") or entry.get("length_m"))
                if length:
                    meta["length_m"] = length
            if meta.get("tonnage_gt") is None:
                tonnage = _coerce_float(entry.get("tonnageGt") or entry.get("tonnage_gt"))
                if tonnage:
                    meta["tonnage_gt"] = tonnage
            if not meta.get("shiptypes"):
                st_val = entry.get("shiptypes") or entry.get("shiptype")
                if isinstance(st_val, list) and st_val:
                    meta["shiptypes"] = ",".join(str(s) for s in st_val if s)
                elif isinstance(st_val, str) and st_val.strip():
                    meta["shiptypes"] = st_val.strip()

    _progress_counter = {"done": 0}

    async def _lookup_one(mmsi, sem):
        """Resolve a single MMSI under concurrency limiter."""
        async with sem:
            try:
                resp = await client.vessels.search_vessels(
                    where=f"ssvid = '{mmsi}'"
                )
                vessels = resp.df() if hasattr(resp, 'df') else pd.DataFrame()
                if vessels.empty:
                    return

                meta = {"imo": None, "length_m": None, "tonnage_gt": None,
                        "shiptypes": None, "vessel_id": None}
                for _, v in vessels.iterrows():
                    _harvest(v.get("registry_info") or v.get("registryInfo"), meta)
                for _, v in vessels.iterrows():
                    _harvest(v.get("self_reported_info") or v.get("selfReportedInfo"), meta)

                if not meta.get("vessel_id"):
                    for _, v in vessels.iterrows():
                        for src_key in ("combined_sources_info", "combinedSourcesInfo",
                                        "self_reported_info", "selfReportedInfo"):
                            entries = v.get(src_key)
                            if isinstance(entries, list):
                                for entry in entries:
                                    if isinstance(entry, dict):
                                        vid = entry.get("vessel_id") or entry.get("vesselId") or entry.get("id")
                                        if vid and str(vid).strip():
                                            meta["vessel_id"] = str(vid).strip()
                                            break
                            if meta.get("vessel_id"):
                                break
                        if meta.get("vessel_id"):
                            break

                if any(meta.get(k) for k in ("imo", "length_m", "tonnage_gt", "shiptypes", "vessel_id")):
                    result[mmsi] = meta

            except Exception:
                pass  # Skip vessel, don't fail batch
            finally:
                _progress_counter["done"] += 1
                if progress_callback:
                    progress_callback(_progress_counter["done"], total)

    async def _lookup_all():
        sem = asyncio.Semaphore(10)  # Up to 10 concurrent API calls
        tasks = [_lookup_one(mmsi, sem) for mmsi in unique_mmsis]
        await asyncio.gather(*tasks)

    try:
        asyncio.run(_lookup_all())
    except RuntimeError:
        # Event loop already running (e.g. Jupyter/Streamlit)
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(_lookup_all())
    except Exception:
        pass  # Fall back silently -- name matching still works

    return result


def lookup_vessel_imos(mmsi_list, token, progress_callback=None):
    """Backwards-compatible shim returning {mmsi: imo_str} only.

    Prefer lookup_vessel_metadata() for new callers -- this wrapper exists
    so any external script that imported the original symbol keeps working.
    """
    meta = lookup_vessel_metadata(mmsi_list, token, progress_callback=progress_callback)
    return {k: v["imo"] for k, v in meta.items() if v.get("imo")}


# ========================= FDI DATA =========================

@st.cache_data
def load_fdi_effort():
    path = os.path.join(os.path.dirname(__file__), "data", "fdi_effort_med.csv")
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception as e:
            st.warning(f"Error loading FDI effort data: {e}")
    return pd.DataFrame()


@st.cache_data
def load_fdi_landings():
    path = os.path.join(os.path.dirname(__file__), "data", "fdi_landings_med.csv")
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception as e:
            st.warning(f"Error loading FDI landings data: {e}")
    return pd.DataFrame()


# ========================= IUU VESSEL LIST =========================

@st.cache_data
def load_iuu_vessels():
    """Load preprocessed IUU vessel list."""
    path = os.path.join(os.path.dirname(__file__), "data", "iuu_vessels.csv")
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, dtype={"mmsi": str, "imo": str})
            df["mmsi"] = df["mmsi"].fillna("")
            df["imo"] = df["imo"].fillna("")
            df["all_names"] = df["all_names"].fillna("").astype(str)
            return df
        except Exception as e:
            st.warning(f"Error loading IUU vessel list: {e}")
    return pd.DataFrame()


# ========================= ICCAT VESSEL LIST =========================

@st.cache_data
def load_iccat_vessels():
    """Load preprocessed ICCAT Med-authorized vessel list."""
    path = os.path.join(os.path.dirname(__file__), "data", "iccat_med_vessels.csv")
    if os.path.exists(path):
        try:
            return pd.read_csv(path, dtype=str).fillna("")
        except Exception as e:
            st.warning(f"Error loading ICCAT vessel list: {e}")
    return pd.DataFrame()


# ========================= OFAC SDN VESSEL LIST =========================

@st.cache_data
def load_ofac_vessels():
    """Load preprocessed OFAC SDN sanctioned vessel list."""
    path = os.path.join(os.path.dirname(__file__), "data", "ofac_vessels.csv")
    if os.path.exists(path):
        try:
            return pd.read_csv(path, dtype=str).fillna("")
        except Exception as e:
            st.warning(f"Error loading OFAC vessel list: {e}")
    return pd.DataFrame()


@st.cache_data
def load_closed_area_mpas():
    """Load curated reference of Mediterranean MPAs prohibiting all fishing.

    Returns a DataFrame with columns: mpa_name, mpa_tier, closure_type,
    prohibits, source_reference, notes. Used by the fishing_in_closed_area
    leaf to refine the existing MPA intersection signal.
    """
    csv_path = os.path.join(os.path.dirname(__file__), "data", "closed_area_mpas.csv")
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        return df
    return pd.DataFrame(columns=[
        "mpa_name", "mpa_tier", "closure_type",
        "prohibits", "source_reference", "notes",
    ])
