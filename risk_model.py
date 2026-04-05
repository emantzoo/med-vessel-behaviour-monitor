"""GFW-aligned behavioral risk scoring and FDI context lookups."""

import pandas as pd

from config import TRANSSHIPMENT_VESSEL_TYPES, SPECIES_NAMES, IUU_MULTIPLIERS


def compute_risk_score(row, event_weights, flag_risks):
    """GFW-aligned behavioral risk score.

    Aligned with Global Fishing Watch transshipment detection methodology:
    - Encounters: <500m, >=2h, <2kn, >=10km from shore (Miller et al. 2018)
    - Likely transshipment: reefer + fishing vessel, >20nm from shore
    - Potential transshipment: reefer loiters alone (fishing vessel AIS off)
    """
    base = row["duration_h"] ** 0.75
    ew = event_weights.get(row["event_type"], 1.0)
    fm = flag_risks.get(row["flag"], 1.0)

    # Shore distance factor
    shore_km = row.get("distance_from_shore_km")
    if pd.notna(shore_km):
        if shore_km > 37:
            shore_factor = 1.5
        elif shore_km > 10:
            shore_factor = 1.2
        else:
            shore_factor = 0.8
    else:
        shore_factor = 1.0

    if row["event_type"] == "ENCOUNTER":
        dist = row.get("encounter_median_distance_km")
        if pd.notna(dist):
            if dist < 0.5:
                proximity_factor = 1.8
            elif dist < 1.0:
                proximity_factor = 1.3
            else:
                proximity_factor = 1.0
        else:
            proximity_factor = 1.0

        speed = row.get("encounter_median_speed_knots")
        speed_factor = 1.5 if pd.notna(speed) and speed < 2.0 else 1.0

        vtype = str(row.get("vessel_type", "")).upper()
        vessel_factor = 1.4 if vtype in TRANSSHIPMENT_VESSEL_TYPES else 1.0

        return base * ew * fm * shore_factor * proximity_factor * speed_factor * vessel_factor

    elif row["event_type"] == "LOITERING":
        vtype = str(row.get("vessel_type", "")).upper()
        vessel_factor = 1.6 if vtype in TRANSSHIPMENT_VESSEL_TYPES else 1.0

        speed = row.get("loitering_avg_speed_knots")
        speed_factor = 1.4 if pd.notna(speed) and speed < 2.0 else 1.0

        return base * ew * fm * shore_factor * vessel_factor * speed_factor

    elif row["event_type"] == "GAP":
        spd_before = row.get("speed_before_gap")
        spd_after = row.get("speed_after_gap")
        if pd.notna(spd_before) and pd.notna(spd_after):
            speed_change = abs(spd_before - spd_after)
            evasion_factor = 1.5 if speed_change > 5 else (1.2 if speed_change > 2 else 1.0)
        else:
            evasion_factor = 1.0

        return base * ew * fm * shore_factor * evasion_factor

    else:
        return base * ew * fm * shore_factor


def get_fdi_context(csq_lon, csq_lat, fdi_effort, fdi_landings, year=None):
    """Return FDI baseline summary for a c-square cell."""
    if fdi_effort.empty:
        return None

    eff = fdi_effort[(fdi_effort["rectangle_lon"] == csq_lon) &
                     (fdi_effort["rectangle_lat"] == csq_lat)]
    land = fdi_landings[(fdi_landings["rectangle_lon"] == csq_lon) &
                        (fdi_landings["rectangle_lat"] == csq_lat)] if not fdi_landings.empty else pd.DataFrame()

    if year:
        eff = eff[eff["year"] == year]
        land = land[land["year"] == year] if not land.empty else land

    if eff.empty and land.empty:
        return None

    total_fd = eff["totfishdays"].sum() if not eff.empty else 0
    gear_bk = eff.groupby("gear_type")["totfishdays"].sum().sort_values(ascending=False).head(5).to_dict() if not eff.empty else {}
    quarterly = eff.groupby("quarter")["totfishdays"].sum().to_dict() if not eff.empty else {}

    total_wt = land["totwghtlandg"].sum() if not land.empty else 0
    total_val = land["totvallandg"].sum() if not land.empty else 0
    top_sp = []
    if not land.empty:
        sp_agg = land.groupby("species").agg(
            wt=("totwghtlandg", "sum"), val=("totvallandg", "sum")
        ).sort_values("wt", ascending=False).head(5)
        top_sp = [(idx, row["wt"], row["val"]) for idx, row in sp_agg.iterrows()]

    return {
        "total_fishing_days": total_fd,
        "gear_breakdown": gear_bk,
        "quarterly_effort": quarterly,
        "top_species": top_sp,
        "total_landings_tonnes": total_wt,
        "total_landings_value": total_val,
        "is_known_fishing_ground": total_fd > 10,
    }


# ========================= IUU MATCHING =========================

def _build_match_result(iuu_row, match_type, confidence):
    """Build match result dict from an IUU list row."""
    is_gfcm = bool(iuu_row.get("is_gfcm", False))
    multiplier = IUU_MULTIPLIERS["GFCM"] if is_gfcm else IUU_MULTIPLIERS["OTHER_RFMO"]
    return {
        "iuu_matched": True,
        "iuu_vessel_name": iuu_row.get("vessel_name", ""),
        "iuu_listing_rfmos": iuu_row.get("listing_rfmos", ""),
        "iuu_listing_reason": iuu_row.get("listing_reason", ""),
        "iuu_match_type": match_type,
        "iuu_match_confidence": confidence,
        "iuu_multiplier": multiplier,
        "iuu_is_gfcm": is_gfcm,
        "iuu_is_currently_listed": bool(iuu_row.get("is_currently_listed", False)),
    }


_NO_MATCH = {
    "iuu_matched": False,
    "iuu_vessel_name": None,
    "iuu_listing_rfmos": None,
    "iuu_listing_reason": None,
    "iuu_match_type": None,
    "iuu_match_confidence": None,
    "iuu_multiplier": 1.0,
    "iuu_is_gfcm": False,
    "iuu_is_currently_listed": False,
}


def check_iuu_match(mmsi, vessel_name, iuu_df, include_delisted=False):
    """Check if a vessel matches any IUU-listed vessel.

    Matching priority: MMSI exact → name exact → name fuzzy (substring).
    Returns dict with match details or _NO_MATCH.
    """
    if iuu_df.empty:
        return dict(_NO_MATCH)

    working = iuu_df if include_delisted else iuu_df[iuu_df["is_currently_listed"] == True]
    if working.empty:
        return dict(_NO_MATCH)

    # Priority 1: MMSI exact match (high confidence)
    mmsi_str = str(mmsi).strip()
    if mmsi_str and mmsi_str not in ("0", "nan", ""):
        mmsi_matches = working[working["mmsi"] == mmsi_str]
        if not mmsi_matches.empty:
            return _build_match_result(mmsi_matches.iloc[0], "MMSI", "high")

    # Priority 2 & 3: Name matching
    if vessel_name and pd.notna(vessel_name):
        name_upper = str(vessel_name).strip().upper()
        if not name_upper:
            return dict(_NO_MATCH)

        # Exact match: name is one of the pipe-delimited known names
        for idx, row in working.iterrows():
            known = [n.strip() for n in str(row["all_names"]).upper().split("|")]
            if name_upper in known:
                return _build_match_result(row, "name_exact", "medium")

        # Fuzzy match: name appears as substring in all_names
        fuzzy = working[
            working["all_names"].str.upper().str.contains(name_upper, na=False, regex=False)
        ]
        if not fuzzy.empty:
            confidence = "medium" if len(name_upper) >= 5 else "low"
            return _build_match_result(fuzzy.iloc[0], "name_fuzzy", confidence)

    return dict(_NO_MATCH)


def match_iuu_vessels(df, iuu_df, include_delisted=False):
    """Match all vessels in df against IUU list.

    Adds iuu_* columns and applies multiplier to risk_score.
    Called from app.py after compute_risk_score.
    """
    if iuu_df.empty or df.empty:
        for col, val in _NO_MATCH.items():
            df[col] = val
        return df

    matches = df.apply(
        lambda row: check_iuu_match(
            row["mmsi"], row.get("vessel_name"), iuu_df, include_delisted
        ),
        axis=1,
    )
    match_df = pd.DataFrame(matches.tolist(), index=df.index)
    for col in match_df.columns:
        df[col] = match_df[col]

    # Apply risk multiplier
    df["risk_score"] = (df["risk_score"] * df["iuu_multiplier"]).round(1)
    return df
