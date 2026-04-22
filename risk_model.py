"""GFW-aligned behavioral risk scoring and FDI context lookups."""

import os
import numpy as np
import pandas as pd

from config import (
    TRANSSHIPMENT_VESSEL_TYPES, SPECIES_NAMES,
    IUU_MULTIPLIERS, ICCAT_MULTIPLIERS, OFAC_MULTIPLIER,
    MPA_MULTIPLIERS,
    derive_vessel_class,
    EU_FLAGS, assign_csquare,
    RECOGNISED_FLAG_VALUES_INVALID, GFCM_PARTY_FLAGS,
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
        implied_speed = row.get("gap_implied_speed_knots")
        intentional = row.get("gap_intentional_disabling")
        if intentional is True:
            evasion_factor = 1.5
        elif pd.notna(implied_speed):
            implied_speed = float(implied_speed)
            evasion_factor = 1.4 if implied_speed > 8 else (1.2 if implied_speed > 4 else 1.0)
        else:
            evasion_factor = 1.0

        return base * ew * fm * shore_factor * mpa_factor * evasion_factor

    else:
        return base * ew * fm * shore_factor * mpa_factor


def compute_risk_scores_vec(df, event_weights, flag_risks):
    """Vectorized risk scoring — replaces per-row .apply(compute_risk_score).

    Same formula as the scalar version but uses numpy/pandas vector ops
    for ~50-100x speedup on large DataFrames.
    """
    n = len(df)
    if n == 0:
        return pd.Series(dtype=float)

    # Base: duration_h ^ 0.75
    dur = pd.to_numeric(df["duration_h"], errors="coerce").fillna(0).values
    base = np.power(dur, 0.75)

    # Event weight
    ew = df["event_type"].map(event_weights).fillna(1.0).values

    # Flag multiplier
    fm = df["flag"].map(flag_risks).fillna(1.0).values

    # Shore factor
    if "distance_from_shore_km" in df.columns:
        shore_km = pd.to_numeric(df["distance_from_shore_km"], errors="coerce").values
        shore_factor = np.where(np.isnan(shore_km), 1.0,
                       np.where(shore_km > 37, 1.5,
                       np.where(shore_km > 10, 1.2, 0.8)))
    else:
        shore_factor = np.ones(n)

    # MPA factor
    if "mpa_tier" in df.columns:
        mpa_tier = df["mpa_tier"].fillna("").astype(str)
        mpa_factor = mpa_tier.map(lambda t: MPA_MULTIPLIERS.get(t, 1.0) if t else 1.0).values
    else:
        mpa_factor = np.ones(n)

    # Start with common product
    score = base * ew * fm * shore_factor * mpa_factor

    # --- ENCOUNTER extras ---
    is_enc = (df["event_type"] == "ENCOUNTER").values

    if is_enc.any():
        # Proximity factor
        if "encounter_median_distance_km" in df.columns:
            dist = pd.to_numeric(df["encounter_median_distance_km"], errors="coerce").values
            prox = np.where(np.isnan(dist), 1.0,
                   np.where(dist < 0.5, 1.8,
                   np.where(dist < 1.0, 1.3, 1.0)))
        else:
            prox = np.ones(n)

        # Speed factor
        if "encounter_median_speed_knots" in df.columns:
            espd = pd.to_numeric(df["encounter_median_speed_knots"], errors="coerce").values
            espd_f = np.where(np.isnan(espd), 1.0, np.where(espd < 2.0, 1.5, 1.0))
        else:
            espd_f = np.ones(n)

        # Vessel type factor
        vtype = df.get("vessel_type", pd.Series("", index=df.index)).fillna("").str.upper().values
        vt_f = np.where(np.isin(vtype, list(TRANSSHIPMENT_VESSEL_TYPES)), 1.4, 1.0)

        score = np.where(is_enc, score * prox * espd_f * vt_f, score)

    # --- LOITERING extras ---
    is_loit = (df["event_type"] == "LOITERING").values

    if is_loit.any():
        vtype_l = df.get("vessel_type", pd.Series("", index=df.index)).fillna("").str.upper().values
        vt_l = np.where(np.isin(vtype_l, list(TRANSSHIPMENT_VESSEL_TYPES)), 1.6, 1.0)

        if "loitering_avg_speed_knots" in df.columns:
            lspd = pd.to_numeric(df["loitering_avg_speed_knots"], errors="coerce").values
            lspd_f = np.where(np.isnan(lspd), 1.0, np.where(lspd < 2.0, 1.4, 1.0))
        else:
            lspd_f = np.ones(n)

        score = np.where(is_loit, score * vt_l * lspd_f, score)

    # --- GAP extras ---
    is_gap = (df["event_type"] == "GAP").values

    if is_gap.any():
        intentional = df.get("gap_intentional_disabling", pd.Series(False, index=df.index))
        is_intentional = (intentional == True).values  # noqa: E712
        implied_spd = pd.to_numeric(df.get("gap_implied_speed_knots", pd.Series(dtype=float)), errors="coerce").values
        evasion = np.where(is_intentional, 1.5,
                 np.where(np.isnan(implied_spd), 1.0,
                 np.where(implied_spd > 8, 1.4,
                 np.where(implied_spd > 4, 1.2, 1.0))))

        score = np.where(is_gap, score * evasion, score)

    return pd.Series(np.round(score, 1), index=df.index)


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

        # Fuzzy match: token-overlap + similarity ratio
        # Requires ≥80% character similarity AND all query tokens present
        # in at least one of the pipe-delimited known names.
        if len(name_upper) >= 4:
            from difflib import SequenceMatcher
            query_tokens = set(name_upper.split())
            best_row = None
            best_ratio = 0.0
            for idx, row in working.iterrows():
                known_names = [n.strip().upper() for n in str(row["all_names"]).split("|")]
                for kn in known_names:
                    kn_tokens = set(kn.split())
                    if not query_tokens.issubset(kn_tokens):
                        continue
                    ratio = SequenceMatcher(None, name_upper, kn).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_row = row
            if best_row is not None and best_ratio >= 0.80:
                confidence = "medium" if best_ratio >= 0.90 else "low"
                return _build_match_result(best_row, "name_fuzzy", confidence)

    return dict(_NO_MATCH)


def match_iuu_vessels(df, iuu_df, include_delisted=False):
    """Match all vessels in df against IUU list.

    Adds iuu_* columns and applies multiplier to risk_score.
    Called from app.py after compute_risk_score.
    Optimised: matches per unique vessel, then broadcasts to all events.
    """
    if iuu_df.empty or df.empty:
        for col, val in _NO_MATCH.items():
            df[col] = val
        return df

    # Deduplicate: match once per unique vessel (mmsi)
    vessel_keys = df.groupby("mmsi").first()[["vessel_name", "imo"]].reset_index()
    vessel_matches = vessel_keys.apply(
        lambda row: check_iuu_match(
            row["mmsi"], row.get("vessel_name"), iuu_df, include_delisted,
            imo=row.get("imo"),
        ),
        axis=1,
    )
    vessel_result = pd.DataFrame(vessel_matches.tolist(), index=vessel_keys.index)
    vessel_result["mmsi"] = vessel_keys["mmsi"].values

    # Broadcast to all events
    lookup = vessel_result.set_index("mmsi")
    for col in _NO_MATCH:
        mapped = df["mmsi"].map(lookup[col])
        default = _NO_MATCH[col]
        df[col] = mapped if default is None else mapped.fillna(default)

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
    Optimised: matches per unique vessel, then broadcasts to all events.
    """
    if iccat_df.empty or df.empty:
        for col, val in _NO_ICCAT_MATCH.items():
            df[col] = val
        return df

    vessel_keys = df.groupby("mmsi").first()[["vessel_name", "imo"]].reset_index()
    vessel_matches = vessel_keys.apply(
        lambda row: check_iccat_match(
            row.get("vessel_name"), iccat_df, imo=row.get("imo"),
        ),
        axis=1,
    )
    vessel_result = pd.DataFrame(vessel_matches.tolist(), index=vessel_keys.index)
    vessel_result["mmsi"] = vessel_keys["mmsi"].values

    lookup = vessel_result.set_index("mmsi")
    for col in _NO_ICCAT_MATCH:
        mapped = df["mmsi"].map(lookup[col])
        default = _NO_ICCAT_MATCH[col]
        df[col] = mapped if default is None else mapped.fillna(default)

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
    Optimised: matches per unique vessel, then broadcasts to all events.
    """
    if ofac_df.empty or df.empty:
        for col, val in _NO_OFAC_MATCH.items():
            df[col] = val
        return df

    vessel_keys = df.groupby("mmsi").first()[["vessel_name", "imo"]].reset_index()
    vessel_matches = vessel_keys.apply(
        lambda row: check_ofac_match(
            row["mmsi"], row.get("vessel_name"), ofac_df,
            imo=row.get("imo"),
        ),
        axis=1,
    )
    vessel_result = pd.DataFrame(vessel_matches.tolist(), index=vessel_keys.index)
    vessel_result["mmsi"] = vessel_keys["mmsi"].values

    lookup = vessel_result.set_index("mmsi")
    for col in _NO_OFAC_MATCH:
        mapped = df["mmsi"].map(lookup[col])
        default = _NO_OFAC_MATCH[col]
        df[col] = mapped if default is None else mapped.fillna(default)

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
    # Vectorized: sort once, compute diff per vessel group, check <=90
    time_col = "start_time" if "start_time" in df.columns else ("date" if "date" in df.columns else None)
    if time_col is not None:
        _ts = pd.to_datetime(df[time_col], errors="coerce")
        _tmp = df[["mmsi"]].copy()
        _tmp["_ts"] = _ts
        _tmp = _tmp.dropna(subset=["_ts"]).sort_values(["mmsi", "_ts"])
        _tmp["_diff_days"] = _tmp.groupby("mmsi")["_ts"].diff().dt.days
        _repeat = _tmp[_tmp["_diff_days"] <= 90]["mmsi"].unique()
        df["repeat_offender_90d"] = df["mmsi"].isin(_repeat)
    else:
        df["repeat_offender_90d"] = False

    # 5. Vessel class -- descriptive label derived from registry shiptypes.
    # Falls back to event-level vessel_type when shiptypes is empty so the
    # column is still useful in static demo mode and for vessels that don't
    # resolve in the GFW Vessels API. Class-level, not size-level: a small
    # trawler is artisanal_fishing here but is_industrial=False on the size
    # axis -- both axes can disagree and that is by design.
    shiptypes_series = df["shiptypes"] if "shiptypes" in df.columns else pd.Series("", index=df.index)
    vessel_type_series = df["vessel_type"] if "vessel_type" in df.columns else pd.Series("", index=df.index)
    # Deduplicate: derive once per unique value, then map back
    _st_uniq = shiptypes_series.unique()
    _st_map = {v: derive_vessel_class(v) for v in _st_uniq}
    shiptypes_class = shiptypes_series.map(_st_map)
    _vt_uniq = vessel_type_series.unique()
    _vt_map = {v: derive_vessel_class(v) for v in _vt_uniq}
    vessel_type_class = vessel_type_series.map(_vt_map)
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


def detect_gap_then_fishing_sequence(
    vessel_events,
    vessel_fishing,
    window_hours=72,
    min_gap_duration_h=4,
):
    """Detect cases where a vessel went AIS-dark then resumed fishing.

    For each GAP event ending at time T_end, check whether any FISHING event
    occurs within `window_hours` after T_end for the same MMSI.

    Args:
        vessel_events: DataFrame of behavioural events for one vessel
            (must contain event_type, start_time, end_time)
        vessel_fishing: DataFrame of fishing events for the same vessel
            (must contain date, lat, lon, fishing_hours)
        window_hours: max hours between gap end and fishing event start
        min_gap_duration_h: minimum gap duration to consider

    Returns:
        List of dicts: {gap_end, fishing_start, gap_duration_h, hours_between}
    """
    matches = []
    if vessel_events is None or vessel_events.empty:
        return matches
    if vessel_fishing is None or vessel_fishing.empty:
        return matches

    gaps = vessel_events[vessel_events["event_type"] == "GAP"].copy()
    if gaps.empty:
        return matches

    # Events use "date" as start timestamp; end = date + duration_h
    gaps["_start"] = pd.to_datetime(gaps["date"], errors="coerce")
    dur_h = pd.to_numeric(gaps.get("duration_h", pd.Series(dtype=float)), errors="coerce").fillna(0)
    gaps["_end"] = gaps["_start"] + pd.to_timedelta(dur_h, unit="h")
    gaps["_dur_h"] = dur_h
    gaps = gaps.dropna(subset=["_start", "_end"])
    gaps = gaps[gaps["_dur_h"] >= min_gap_duration_h]
    if gaps.empty:
        return matches

    fishing = vessel_fishing.copy()
    fishing["_fdate"] = pd.to_datetime(fishing["date"], errors="coerce")
    fishing = fishing.dropna(subset=["_fdate"])
    if fishing.empty:
        return matches

    window = pd.Timedelta(hours=window_hours)

    for _, gap in gaps.iterrows():
        gap_end = gap["_end"]
        candidate_fishing = fishing[
            (fishing["_fdate"] > gap_end) & (fishing["_fdate"] <= gap_end + window)
        ]
        if not candidate_fishing.empty:
            first_fishing = candidate_fishing.iloc[0]
            hours_between = (
                (first_fishing["_fdate"] - gap_end).total_seconds() / 3600.0
            )
            matches.append({
                "gap_end": gap_end,
                "gap_duration_h": gap["_dur_h"],
                "fishing_start": first_fishing["_fdate"],
                "hours_between": hours_between,
            })

    return matches


def get_low_effort_csquares(fdi_effort, percentile=5):
    """Return the set of c-square (lon, lat) tuples in the bottom percentile of FDI effort.

    Uses rectangle_lon / rectangle_lat as c-square keys and totfishdays as the
    effort column. Only cells with positive effort are considered (zero-effort
    cells are unknown, not low-effort).

    Args:
        fdi_effort: FDI effort DataFrame with rectangle_lon, rectangle_lat, totfishdays.
        percentile: bottom percentile threshold (default 5 = bottom 5%).

    Returns:
        set of (rectangle_lon, rectangle_lat) tuples below the threshold,
        or empty set if data is unavailable.
    """
    if fdi_effort is None or fdi_effort.empty:
        return set()
    required = {"rectangle_lon", "rectangle_lat", "totfishdays"}
    if not required.issubset(fdi_effort.columns):
        return set()

    cell_effort = (
        fdi_effort.groupby(["rectangle_lon", "rectangle_lat"])["totfishdays"]
        .sum()
        .reset_index()
    )
    cell_effort = cell_effort[cell_effort["totfishdays"] > 0]
    if cell_effort.empty:
        return set()

    threshold = np.percentile(cell_effort["totfishdays"], percentile)
    low = cell_effort[cell_effort["totfishdays"] <= threshold]
    return set(zip(low["rectangle_lon"], low["rectangle_lat"]))


# ---------------------------------------------------------------------------
# Leaf attribution for fishing events (visualisation helper)
# ---------------------------------------------------------------------------

def attribute_leaves_to_fishing_events(fishing_df, df_filtered,
                                       closed_area_csv_path=None):
    """For each fishing event, determine which fishing-related leaves fired.

    Returns a copy of *fishing_df* with extra boolean columns for each leaf,
    a ``primary_leaf`` column (highest-severity fired leaf), and vessel-level
    overlay flags joined from *df_filtered*.

    New columns added:
        leaf_fishing_in_mpa, leaf_fishing_in_closed_area,
        leaf_fishing_in_low_effort_cell, leaf_gfw_no_rfmo_authorization,
        primary_leaf, primary_severity,
        vessel_iuu_crosscheck, vessel_stateless, vessel_unregulated_flag.
    """
    if fishing_df is None or fishing_df.empty:
        return fishing_df

    out = fishing_df.copy()

    # -- Leaf 1: fishing_in_mpa (any WDPA MPA) ----------------------------
    out["leaf_fishing_in_mpa"] = (
        out["in_mpa"].fillna(False).astype(bool)
        if "in_mpa" in out.columns
        else False
    )

    # -- Leaf 2: fishing_in_closed_area (no-take OR curated CSV) ----------
    no_take = (
        out["in_no_take_mpa"].fillna(False).astype(bool)
        if "in_no_take_mpa" in out.columns
        else pd.Series(False, index=out.index)
    )
    curated_closed = pd.Series(False, index=out.index)
    if closed_area_csv_path and os.path.exists(closed_area_csv_path):
        try:
            closed_csv = pd.read_csv(closed_area_csv_path)
            closed_names = set(
                closed_csv["mpa_name"].dropna().str.strip().str.upper()
            )
            if "mpa" in out.columns:
                event_mpas = out["mpa"].fillna("").astype(str).str.upper()
                curated_closed = event_mpas.apply(
                    lambda m: any(c in m for c in closed_names) if m else False
                )
        except Exception:
            pass
    out["leaf_fishing_in_closed_area"] = no_take | curated_closed

    # -- Leaf 3: fishing_in_low_effort_cell (pre-computed flag) -----------
    out["leaf_fishing_in_low_effort_cell"] = (
        out["in_low_effort_cell"].fillna(False).astype(bool)
        if "in_low_effort_cell" in out.columns
        else False
    )

    # -- Leaf 4: gfw_no_rfmo_authorization (vessel-level from Insights) ---
    out["leaf_gfw_no_rfmo_authorization"] = False
    if (df_filtered is not None and not df_filtered.empty
            and "fishing_without_rfmo_auth_events" in df_filtered.columns
            and "mmsi" in df_filtered.columns):
        vessel_no_auth = (
            df_filtered.drop_duplicates("mmsi")
            .set_index(df_filtered.drop_duplicates("mmsi")["mmsi"].astype(str))
            ["fishing_without_rfmo_auth_events"]
            .fillna(0)
        )
        out["leaf_gfw_no_rfmo_authorization"] = (
            out["mmsi"].astype(str).map(
                (vessel_no_auth.astype(float) > 0)
            ).fillna(False).astype(bool)
        )

    # -- Vessel-level overlay flags (from df_filtered) --------------------
    for col in ("vessel_iuu_crosscheck", "vessel_stateless",
                "vessel_unregulated_flag"):
        out[col] = False

    if df_filtered is not None and not df_filtered.empty and "mmsi" in df_filtered.columns:
        df_dedup = df_filtered.drop_duplicates("mmsi")
        mmsi_idx = df_dedup["mmsi"].astype(str)

        # IUU crosscheck
        if "iuu_listed" in df_dedup.columns:
            raw_iuu = df_dedup["iuu_listed"].fillna(False)
            # Guard against NaN being truthy
            vessel_iuu = pd.Series(
                [bool(v) if not (isinstance(v, float) and pd.isna(v)) else False
                 for v in raw_iuu],
                index=mmsi_idx,
            )
            out["vessel_iuu_crosscheck"] = (
                out["mmsi"].astype(str).map(vessel_iuu).fillna(False).astype(bool)
            )

        # Stateless + unregulated flag
        if "flag" in df_dedup.columns:
            vessel_flags = df_dedup.set_index(mmsi_idx)["flag"].fillna("").str.upper().str.strip()
            out["vessel_stateless"] = (
                out["mmsi"].astype(str).map(
                    vessel_flags.isin(RECOGNISED_FLAG_VALUES_INVALID)
                ).fillna(False).astype(bool)
            )
            out["vessel_unregulated_flag"] = (
                out["mmsi"].astype(str).map(
                    ~vessel_flags.isin(RECOGNISED_FLAG_VALUES_INVALID)
                    & ~vessel_flags.isin(GFCM_PARTY_FLAGS)
                    & ~vessel_flags.isin(EU_FLAGS)
                ).fillna(False).astype(bool)
            )

    # -- Primary leaf (highest severity fired) ----------------------------
    def _primary(row):
        if row.get("leaf_fishing_in_closed_area"):
            return "fishing_in_closed_area", "high"
        if row.get("leaf_gfw_no_rfmo_authorization"):
            return "gfw_no_rfmo_authorization", "medium"
        if row.get("leaf_fishing_in_low_effort_cell"):
            return "fishing_in_low_effort_cell", "medium"
        if row.get("leaf_fishing_in_mpa"):
            return "fishing_in_mpa", "high"
        return "none", "none"

    pairs = out.apply(_primary, axis=1)
    out["primary_leaf"] = [p[0] for p in pairs]
    out["primary_severity"] = [p[1] for p in pairs]

    return out
