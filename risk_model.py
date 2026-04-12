"""GFW-aligned behavioral risk scoring and FDI context lookups."""

import pandas as pd

from config import (
    TRANSSHIPMENT_VESSEL_TYPES, SPECIES_NAMES,
    IUU_MULTIPLIERS, ICCAT_MULTIPLIERS, OFAC_MULTIPLIER,
    MPA_MULTIPLIERS,
    derive_vessel_class,
)


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

    # MPA intersection factor (spatial rule-zone signal). Applied to the
    # BASE behavioural score, not the compound multiplier chain, because
    # MPA intersection answers a "where" question (behavioural/spatial)
    # rather than a "who" question (list lookup). Uses GFW regions.mpa
    # pre-computed via WDPA. Tier classification happens in data_loading.
    mpa_tier = row.get("mpa_tier") if pd.notna(row.get("mpa_tier")) else ""
    mpa_factor = MPA_MULTIPLIERS.get(str(mpa_tier), 1.0) if mpa_tier else 1.0

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

        return base * ew * fm * shore_factor * mpa_factor * proximity_factor * speed_factor * vessel_factor

    elif row["event_type"] == "LOITERING":
        vtype = str(row.get("vessel_type", "")).upper()
        vessel_factor = 1.6 if vtype in TRANSSHIPMENT_VESSEL_TYPES else 1.0

        speed = row.get("loitering_avg_speed_knots")
        speed_factor = 1.4 if pd.notna(speed) and speed < 2.0 else 1.0

        return base * ew * fm * shore_factor * mpa_factor * vessel_factor * speed_factor

    elif row["event_type"] == "GAP":
        spd_before = row.get("speed_before_gap")
        spd_after = row.get("speed_after_gap")
        if pd.notna(spd_before) and pd.notna(spd_after):
            speed_change = abs(spd_before - spd_after)
            evasion_factor = 1.5 if speed_change > 5 else (1.2 if speed_change > 2 else 1.0)
        else:
            evasion_factor = 1.0

        return base * ew * fm * shore_factor * mpa_factor * evasion_factor

    else:
        return base * ew * fm * shore_factor * mpa_factor


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


def check_iuu_match(mmsi, vessel_name, iuu_df, include_delisted=False, imo=None):
    """Check if a vessel matches any IUU-listed vessel.

    Matching priority: MMSI exact → IMO exact → name exact → name fuzzy (substring).
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

    # Priority 2: IMO exact match (high confidence)
    if imo and pd.notna(imo) and str(imo).strip() not in ("", "0", "nan", "None"):
        imo_str = str(imo).strip()
        if "imo" in working.columns:
            imo_matches = working[working["imo"] == imo_str]
            if not imo_matches.empty:
                return _build_match_result(imo_matches.iloc[0], "IMO", "high")

    # Priority 3 & 4: Name matching
    if vessel_name and pd.notna(vessel_name):
        name_upper = str(vessel_name).strip().upper()
        if not name_upper:
            return dict(_NO_MATCH)

        # Exact match: name is one of the pipe-delimited known names (vectorised)
        name_mask = working["all_names"].str.upper().str.split("|").apply(
            lambda names: name_upper in [n.strip() for n in names]
        )
        exact_matches = working[name_mask]
        if not exact_matches.empty:
            return _build_match_result(exact_matches.iloc[0], "name_exact", "medium")

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
            row["mmsi"], row.get("vessel_name"), iuu_df, include_delisted,
            imo=row.get("imo"),
        ),
        axis=1,
    )
    match_df = pd.DataFrame(matches.tolist(), index=df.index)
    for col in match_df.columns:
        df[col] = match_df[col]

    # Apply risk multiplier
    df["risk_score"] = (df["risk_score"] * df["iuu_multiplier"]).round(1)
    return df


# ========================= ICCAT MATCHING =========================

_NO_ICCAT_MATCH = {
    "iccat_authorized": False,
    "iccat_authorizations": None,
    "iccat_risk_tier": None,
    "iccat_multiplier": 1.0,
    "iccat_vessel_name": None,
}

# Minimum vessel name length to avoid false positives on common short names
_ICCAT_MIN_NAME_LEN = 4


def check_iccat_match(vessel_name, iccat_df, imo=None):
    """Check if a vessel matches any ICCAT Med-authorized vessel.

    Matching priority: IMO exact → vessel name exact.
    Names shorter than 4 characters are skipped to avoid false positives.
    """
    if iccat_df.empty:
        return dict(_NO_ICCAT_MATCH)

    def _build_iccat_result(row):
        tier = row.get("iccat_risk_tier", "")
        multiplier = ICCAT_MULTIPLIERS.get(tier, 1.0)
        return {
            "iccat_authorized": True,
            "iccat_authorizations": row.get("med_authorizations", ""),
            "iccat_risk_tier": tier,
            "iccat_multiplier": multiplier,
            "iccat_vessel_name": row.get("VesselName", ""),
        }

    # Priority 1: IMO exact match
    if imo and pd.notna(imo) and str(imo).strip() not in ("", "0", "nan", "None"):
        imo_str = str(imo).strip()
        if "IntRegNo" in iccat_df.columns and "IRNoTypeCode" in iccat_df.columns:
            imo_matches = iccat_df[
                (iccat_df["IRNoTypeCode"] == "IMO") &
                (iccat_df["IntRegNo"].str.split(".").str[0] == imo_str)
            ]
            if not imo_matches.empty:
                return _build_iccat_result(imo_matches.iloc[0])

    # Priority 2: Vessel name exact match
    if not vessel_name or not pd.notna(vessel_name):
        return dict(_NO_ICCAT_MATCH)

    name_upper = str(vessel_name).strip().upper()
    if len(name_upper) < _ICCAT_MIN_NAME_LEN:
        return dict(_NO_ICCAT_MATCH)

    matches = iccat_df[iccat_df["VesselName"] == name_upper]
    if matches.empty:
        return dict(_NO_ICCAT_MATCH)

    return _build_iccat_result(matches.iloc[0])


def match_iccat_vessels(df, iccat_df):
    """Match all vessels in df against ICCAT Med-authorized list.

    Adds iccat_* columns and applies multiplier to risk_score.
    Called from app.py after match_iuu_vessels.
    """
    if iccat_df.empty or df.empty:
        for col, val in _NO_ICCAT_MATCH.items():
            df[col] = val
        return df

    matches = df.apply(
        lambda row: check_iccat_match(
            row.get("vessel_name"), iccat_df, imo=row.get("imo"),
        ),
        axis=1,
    )
    match_df = pd.DataFrame(matches.tolist(), index=df.index)
    for col in match_df.columns:
        df[col] = match_df[col]

    # Apply risk multiplier
    df["risk_score"] = (df["risk_score"] * df["iccat_multiplier"]).round(1)
    return df


# ========================= OFAC MATCHING =========================

_NO_OFAC_MATCH = {
    "ofac_sanctioned": False,
    "ofac_vessel_name": None,
    "ofac_sanctions_program": None,
    "ofac_listing_date": None,
    "ofac_match_type": None,
    "ofac_match_confidence": None,
    "ofac_multiplier": 1.0,
}


def _build_ofac_result(ofac_row, match_type, confidence):
    """Build match result dict from an OFAC SDN row."""
    return {
        "ofac_sanctioned": True,
        "ofac_vessel_name": ofac_row.get("vessel_name", ""),
        "ofac_sanctions_program": ofac_row.get("sanctions_program", ""),
        "ofac_listing_date": ofac_row.get("listing_date", ""),
        "ofac_match_type": match_type,
        "ofac_match_confidence": confidence,
        "ofac_multiplier": OFAC_MULTIPLIER,
    }


def check_ofac_match(mmsi, vessel_name, ofac_df, imo=None):
    """Check if a vessel matches any OFAC SDN sanctioned vessel.

    Matching priority: MMSI exact -> IMO exact -> vessel name exact.
    No fuzzy matching — OFAC false positives have legal consequences.
    Returns dict with match details or _NO_OFAC_MATCH.
    """
    if ofac_df.empty:
        return dict(_NO_OFAC_MATCH)

    # Priority 1: MMSI exact match (high confidence)
    mmsi_str = str(mmsi).strip()
    if mmsi_str and mmsi_str not in ("0", "nan", ""):
        if "mmsi" in ofac_df.columns:
            mmsi_matches = ofac_df[ofac_df["mmsi"] == mmsi_str]
            if not mmsi_matches.empty:
                return _build_ofac_result(mmsi_matches.iloc[0], "MMSI", "high")

    # Priority 2: IMO exact match (high confidence)
    if imo and pd.notna(imo) and str(imo).strip() not in ("", "0", "nan", "None"):
        imo_str = str(imo).strip()
        if "imo" in ofac_df.columns:
            imo_matches = ofac_df[ofac_df["imo"] == imo_str]
            if not imo_matches.empty:
                return _build_ofac_result(imo_matches.iloc[0], "IMO", "high")

    # Priority 3: Name exact match (medium confidence)
    if vessel_name and pd.notna(vessel_name):
        name_upper = str(vessel_name).strip().upper()
        if not name_upper:
            return dict(_NO_OFAC_MATCH)

        # Exact match against all known names (pipe-delimited)
        if "all_names" in ofac_df.columns:
            name_mask = ofac_df["all_names"].str.upper().str.split("|").apply(
                lambda names: name_upper in [n.strip() for n in names]
            )
            exact_matches = ofac_df[name_mask]
            if not exact_matches.empty:
                return _build_ofac_result(exact_matches.iloc[0], "name_exact", "medium")
        else:
            matches = ofac_df[ofac_df["vessel_name"].str.upper() == name_upper]
            if not matches.empty:
                return _build_ofac_result(matches.iloc[0], "name_exact", "medium")

    return dict(_NO_OFAC_MATCH)


def match_ofac_vessels(df, ofac_df):
    """Match all vessels in df against OFAC SDN sanctioned vessel list.

    Adds ofac_* columns and applies multiplier to risk_score.
    Called from app.py after match_iccat_vessels.
    """
    if ofac_df.empty or df.empty:
        for col, val in _NO_OFAC_MATCH.items():
            df[col] = val
        return df

    matches = df.apply(
        lambda row: check_ofac_match(
            row["mmsi"], row.get("vessel_name"), ofac_df,
            imo=row.get("imo"),
        ),
        axis=1,
    )
    match_df = pd.DataFrame(matches.tolist(), index=df.index)
    for col in match_df.columns:
        df[col] = match_df[col]

    # Apply risk multiplier
    df["risk_score"] = (df["risk_score"] * df["ofac_multiplier"]).round(1)
    return df


# ========================= KPLER-ALIGNED VESSEL FLAGS =========================

def compute_vessel_flags(df):
    """Compute vessel-level flags and descriptive labels.

    Two families of columns are produced here:

    Behavioural display-only flags -- never multiplied into risk_score:

    - is_industrial               vessel is >= 24m LOA or >= 100 GT
                                  (structural; ICCAT industrial / EU 1224/2009 threshold)
    - multi_behaviour_flag        vessel has >= 2 distinct event types
    - dark_port_call_candidate    loitering event within 10 km of shore
    - repeat_offender_90d         vessel has >= 2 events in any 90-day window

    Descriptive vessel-type columns -- never enter the risk score:

    - vessel_class                descriptive label combining shiptypes with
                                  is_industrial. industrial_fishing /
                                  artisanal_fishing / carrier / tanker / cargo
                                  / support / other.
    - vessel_type_mismatch        bool. True iff the event-level vessel_type
                                  field (often AIS self-reported) and the
                                  registry-level shiptypes field (GFW Vessels
                                  API) normalise to different canonical
                                  classes. Misrepresentation signal aligned
                                  with Kpler's "irregular vessel information"
                                  indicator from the Grey Fleet paper.

    Length and tonnage come from the GFW Vessels API registry / self-reported
    metadata in live mode and from the static CSV in demo mode. is_industrial
    fires whenever EITHER size threshold is met. vessel_type_mismatch only
    fires when BOTH fields are populated and disagree -- absence of one field
    is not treated as a mismatch.

    Called from app.py after all scoring and matching is complete.
    """
    if df.empty:
        df["is_industrial"] = False
        df["multi_behaviour_flag"] = False
        df["dark_port_call_candidate"] = False
        df["repeat_offender_90d"] = False
        df["vessel_class"] = ""
        df["vessel_type_mismatch"] = False
        return df

    # 1. Industrial vessel profile -- structural, vessel-level.
    # Threshold: >= 24m LOA OR >= 100 GT. Either one trips it. Missing
    # values do not fire the flag (conservative -- absence of evidence is
    # not evidence of presence).
    if "length_m" in df.columns:
        length = pd.to_numeric(df["length_m"], errors="coerce").fillna(0)
    else:
        length = pd.Series(0.0, index=df.index)
    if "tonnage_gt" in df.columns:
        tonnage = pd.to_numeric(df["tonnage_gt"], errors="coerce").fillna(0)
    else:
        tonnage = pd.Series(0.0, index=df.index)
    df["is_industrial"] = (length >= 24) | (tonnage >= 100)

    # 2. Multi-behaviour flag -- vessel-level, broadcast to each event row
    vessel_event_types = df.groupby("mmsi")["event_type"].nunique()
    multi_behaviour_mmsi = set(vessel_event_types[vessel_event_types >= 2].index)
    df["multi_behaviour_flag"] = df["mmsi"].isin(multi_behaviour_mmsi)

    # 3. Dark port call candidate -- event-level
    if "distance_from_shore_km" in df.columns:
        shore = df["distance_from_shore_km"].fillna(999)
    else:
        shore = pd.Series(999, index=df.index)
    df["dark_port_call_candidate"] = (df["event_type"] == "LOITERING") & (shore < 10)

    # 4. Repeat offender -- vessel-level, any 90-day window containing >= 2 events
    repeat_mmsi = set()
    if "start_time" in df.columns:
        time_col = "start_time"
    elif "date" in df.columns:
        time_col = "date"
    else:
        time_col = None
    if time_col is not None:
        for mmsi, group in df.groupby("mmsi"):
            if len(group) < 2:
                continue
            times = pd.to_datetime(group[time_col], errors="coerce").dropna().sort_values()
            if len(times) < 2:
                continue
            deltas = times.diff().dt.days.dropna()
            if (deltas <= 90).any():
                repeat_mmsi.add(mmsi)
    df["repeat_offender_90d"] = df["mmsi"].isin(repeat_mmsi)

    # 5. Vessel class -- descriptive label derived from registry shiptypes.
    # Falls back to event-level vessel_type when shiptypes is empty so the
    # column is still useful in static demo mode and for vessels that don't
    # resolve in the GFW Vessels API. Class-level, not size-level: a small
    # trawler is artisanal_fishing here but is_industrial=False on the size
    # axis -- both axes can disagree and that is by design.
    shiptypes_series = df["shiptypes"] if "shiptypes" in df.columns else pd.Series("", index=df.index)
    vessel_type_series = df["vessel_type"] if "vessel_type" in df.columns else pd.Series("", index=df.index)
    shiptypes_class = shiptypes_series.apply(derive_vessel_class)
    vessel_type_class = vessel_type_series.apply(derive_vessel_class)
    # Prefer shiptypes (registry, more authoritative) when present
    df["vessel_class"] = shiptypes_class.where(shiptypes_class != "", vessel_type_class)

    # 6. Vessel type mismatch -- registry vs event-level disagreement.
    # Fires only when BOTH fields normalise to a non-empty class AND those
    # classes differ. Class-level comparison (not string-level) so that
    # "TRAWLER" vs "FISHING" does not fire -- both map to industrial_fishing.
    # A "FISHING" event-level vessel that the registry calls "CARGO" is
    # the textbook misrepresentation case from the Kpler Grey Fleet paper.
    both_present = (shiptypes_class != "") & (vessel_type_class != "")
    df["vessel_type_mismatch"] = both_present & (shiptypes_class != vessel_type_class)

    return df
