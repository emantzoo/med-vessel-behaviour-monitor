"""Deterministic vessel investigation — rule-based analysis without LLM."""

# ===== Risk tree stub audit (2026-04-13) =====
# Wired (data on disk):
#   encounter_iuu_vessel        — partner name matched against iuu_df
#   encounter_sanctioned_vessel — partner name matched against ofac_df
#   encounter_weak_cooperation_partner — partner flag in {LBY, SYR}
#   encounter_distant_water_partner    — partner flag not EU / not Med coastal
#   authorization_mismatch      — hardcoded flag check (IRN/RUS/PRK/SYR)
#
# Future work (data not loaded):
#   mmsi_consistent       — needs longitudinal MMSI history (GFW Vessels API multi-SSVID)
#   name_history          — needs vessel registry change history
#   eu_sanctioned         — needs EU sanctions list (not loaded; only OFAC available)
#   flag_recent_change    — needs historical flag data
#   gfcm_authorized       — needs GFCM Authorized Vessel List
#   shared_ownership      — needs vessel ownership data (Maritime 2.0 / Equasis)

import pandas as pd
from config import (
    FLAG_RISKS, get_flag_risk, IUU_MULTIPLIERS, ICCAT_MULTIPLIERS, OFAC_MULTIPLIER,
    EU_FLAGS, MED_COASTAL_COOPERATIVE_FLAGS, MED_COASTAL_WEAK_COOPERATION_FLAGS,
)


def investigate_vessel(vessel_identifier, df, iuu_df, iccat_df, ofac_df, fdi_effort, fdi_landings, fishing_df=None):
    """
    Run a structured 10-step investigation on a vessel.

    vessel_identifier: vessel_name (str) or mmsi (str/int)
    fishing_df: optional dataframe of GFW fishing events (separate dataset
        from the behavioural events). When provided, the report will
        include a fishing_in_mpa section and the risk tree will fire a
        fishing_activity branch when the vessel has GFW-classified
        fishing events inside any MPA.
    Returns: dict with all investigation steps as structured data.
    """
    # Find vessel in df (by name or mmsi). Use EXACT match -- fuzzy matching
    # conflates distinct MMSIs that happen to share a name.
    if str(vessel_identifier).isdigit():
        vessel_events = df[df["mmsi"].astype(str) == str(vessel_identifier)]
    else:
        probe = str(vessel_identifier).upper()
        vessel_events = df[df["vessel_name"].astype(str).str.upper() == probe]

    if vessel_events.empty:
        return {"error": f"Vessel '{vessel_identifier}' not found in current dataset."}

    # If the name happens to map to more than one MMSI (should not happen after
    # the 1:1 rename in the static CSV, but defensively guard anyway), pick the
    # MMSI with the most events so the report is self-consistent.
    if vessel_events["mmsi"].nunique() > 1:
        top_mmsi = vessel_events.groupby("mmsi").size().idxmax()
        vessel_events = vessel_events[vessel_events["mmsi"] == top_mmsi]

    primary = vessel_events.iloc[0]
    report = {}
    trace = []

    # ===== Step 1: Identity =====
    imo_val = str(primary.get("imo", "")).replace(".0", "")
    has_imo = imo_val not in ("", "nan", "None", "0")
    mmsi_val = str(primary.get("mmsi", "")).replace(".0", "")
    flag = primary.get("flag", "")
    vessel_name_val = primary.get("vessel_name", "Unknown")

    report["identity"] = {
        "vessel_name": vessel_name_val,
        "mmsi": mmsi_val,
        "imo": imo_val,
        "flag": flag,
        "vessel_type": primary.get("vessel_type", ""),
        "shiptypes": primary.get("shiptypes", ""),
        "vessel_class": primary.get("vessel_class", ""),
        "vessel_type_mismatch": bool(primary.get("vessel_type_mismatch", False)),
        "events_in_dataset": len(vessel_events),
        "date_range": (vessel_events["date"].min(), vessel_events["date"].max()),
    }

    # Identity trace entries
    trace.append({
        "branch_id": "identity", "question_id": "imo_present",
        "answer": "yes" if has_imo else "no",
        "severity": "none" if has_imo else "high",
        "rule_fired": not has_imo,
        "note": f"IMO: {imo_val}" if has_imo else "No valid IMO -- identity unverifiable",
    })
    # MMSI consistency (future_work: needs longitudinal MMSI history)
    trace.append({
        "branch_id": "identity", "question_id": "mmsi_consistent",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Requires longitudinal AIS history per MMSI over multiple years (GFW Vessels API multi-SSVID time-series pipeline)",
        "status": "future_work",
    })
    # Name history (future_work: needs vessel registry change history)
    trace.append({
        "branch_id": "identity", "question_id": "name_history",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Requires historical vessel name registry with timestamped changes (Equasis / WDPA partial coverage)",
        "status": "future_work",
    })

    # Identity misrepresentation: vessel_type (event-level) vs shiptypes
    # (registry) class disagreement. Class-level comparison so spelling
    # variants ("TRAWLER" vs "FISHING") do not trigger the flag.
    type_mismatch = bool(primary.get("vessel_type_mismatch", False))
    if type_mismatch:
        evt_type = str(primary.get("vessel_type", "")).strip() or "(empty)"
        reg_type = str(primary.get("shiptypes", "")).strip() or "(empty)"
        vc = str(primary.get("vessel_class", "")).strip() or "(unknown)"
        mis_note = (
            f"Event-level vessel_type ({evt_type}) and registry shiptypes "
            f"({reg_type}) map to different canonical classes "
            f"(registry says: {vc}). Irregular vessel information signal "
            f"-- Kpler Grey Fleet equivalent."
        )
    else:
        mis_note = "vessel_type and shiptypes agree (or one is missing)"
    trace.append({
        "branch_id": "identity", "question_id": "identity_misrepresentation",
        "answer": "yes" if type_mismatch else "no",
        "severity": "medium" if type_mismatch else "none",
        "rule_fired": type_mismatch,
        "note": mis_note,
    })

    # ===== Step 2: IUU =====
    iuu_matched = bool(primary.get("iuu_matched", False))
    iuu_is_gfcm = bool(primary.get("iuu_is_gfcm", False)) if iuu_matched else False
    report["iuu"] = {
        "matched": iuu_matched,
        "vessel_name": primary.get("iuu_vessel_name", "") if iuu_matched else None,
        "rfmos": primary.get("iuu_listing_rfmos", "") if iuu_matched else None,
        "is_gfcm": iuu_is_gfcm,
        "match_type": primary.get("iuu_match_type", "") if iuu_matched else None,
        "match_confidence": primary.get("iuu_match_confidence", "") if iuu_matched else None,
        "multiplier": float(primary.get("iuu_multiplier", 1.0)),
        "listing_reason": primary.get("iuu_listing_reason", "") if iuu_matched else None,
    }

    # ===== Step 3: ICCAT =====
    iccat_authorized = bool(primary.get("iccat_authorized", False))
    report["iccat"] = {
        "authorized": iccat_authorized,
        "authorizations": primary.get("iccat_authorizations", "") if iccat_authorized else None,
        "risk_tier": primary.get("iccat_risk_tier", "") if iccat_authorized else None,
        "multiplier": float(primary.get("iccat_multiplier", 1.0)),
        "vessel_name": primary.get("iccat_vessel_name", "") if iccat_authorized else None,
    }

    # ===== Step 4: OFAC =====
    ofac_sanctioned = bool(primary.get("ofac_sanctioned", False))
    report["ofac"] = {
        "sanctioned": ofac_sanctioned,
        "program": primary.get("ofac_sanctions_program", "") if ofac_sanctioned else None,
        "vessel_name": primary.get("ofac_vessel_name", "") if ofac_sanctioned else None,
        "multiplier": float(primary.get("ofac_multiplier", 1.0)),
    }

    # Regulatory trace entries (IUU listed, OFAC, EU sanctions)
    trace.append({
        "branch_id": "regulatory_status", "question_id": "iuu_listed",
        "answer": "yes" if iuu_matched else "no",
        "severity": "high" if (iuu_matched and iuu_is_gfcm) else ("medium" if iuu_matched else "none"),
        "rule_fired": iuu_matched,
        "note": f"IUU-listed by {report['iuu']['rfmos']}" if iuu_matched else "Not on any RFMO IUU list",
    })
    trace.append({
        "branch_id": "regulatory_status", "question_id": "ofac_sanctioned",
        "answer": "yes" if ofac_sanctioned else "no",
        "severity": "critical" if ofac_sanctioned else "none",
        "rule_fired": ofac_sanctioned,
        "note": f"OFAC-sanctioned ({report['ofac']['program']})" if ofac_sanctioned else "Not OFAC-sanctioned",
    })
    trace.append({
        "branch_id": "regulatory_status", "question_id": "eu_sanctioned",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Requires EU Consolidated Financial Sanctions List (vessels track); data prep analogous to OFAC SDN",
        "status": "future_work",
    })

    # Flag risk trace entries
    is_iuu_flag = flag in ("IRN", "PRK", "KHM")
    trace.append({
        "branch_id": "flag_risk", "question_id": "flag_iuu_country",
        "answer": "yes" if is_iuu_flag else "no",
        "severity": "high" if is_iuu_flag else "none",
        "rule_fired": is_iuu_flag,
        "note": f"Flag {flag} is high-risk IUU country" if is_iuu_flag else f"Flag {flag} is not on IUU high-risk list",
    })
    foc_flags = {"PAN", "LBR", "MHL", "BHS", "VCT", "KNA", "BLZ", "HND", "BOL", "MMR", "KHM", "COM", "TGO", "GNQ"}
    is_foc = flag in foc_flags
    trace.append({
        "branch_id": "flag_risk", "question_id": "flag_of_convenience",
        "answer": "yes" if is_foc else "no",
        "severity": "low" if is_foc else "none",
        "rule_fired": False,
        "note": f"Flag {flag} is ITF-recognised FOC" if is_foc else f"Flag {flag} is not an FOC",
    })
    trace.append({
        "branch_id": "flag_risk", "question_id": "flag_recent_change",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Requires longitudinal flag-state history per vessel (same pipeline gap as mmsi_consistent)",
        "status": "future_work",
    })
    psc_blacklist = {"KHM", "COM", "TGO", "TZA", "SLE"}
    is_psc_bl = flag in psc_blacklist
    trace.append({
        "branch_id": "flag_risk", "question_id": "flag_psc_blacklist",
        "answer": "yes" if is_psc_bl else "no",
        "severity": "medium" if is_psc_bl else "none",
        "rule_fired": is_psc_bl,
        "note": f"Flag {flag} is on PSC black list" if is_psc_bl else f"Flag {flag} not on PSC black list",
    })

    # Authorization trace entries
    trace.append({
        "branch_id": "authorization", "question_id": "iccat_authorized",
        "answer": "yes" if iccat_authorized else "no",
        "severity": "none",
        "rule_fired": False,
        "note": f"ICCAT-authorized: {report['iccat']['authorizations']}" if iccat_authorized else "Not ICCAT-authorized",
    })
    trace.append({
        "branch_id": "authorization", "question_id": "gfcm_authorized",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Requires GFCM Record of Authorised Vessels (partial public availability); data prep analogous to ICCAT",
        "status": "future_work",
    })
    # Authorization mismatch: check if flag has no fishing rights in Med
    no_fishing_rights = flag in ("IRN", "RUS", "PRK", "SYR")
    trace.append({
        "branch_id": "authorization", "question_id": "authorization_mismatch",
        "answer": "yes" if no_fishing_rights else "no",
        "severity": "high" if no_fishing_rights else "none",
        "rule_fired": no_fishing_rights,
        "note": f"{flag}-flagged vessel has no legitimate fishing rights in EU Med waters" if no_fishing_rights else "Flag has legitimate fishing access",
    })

    # ===== Step 5: Fisheries Context =====
    fisheries_context = []
    for _, event in vessel_events.iterrows():
        if "csq_lon" not in event or pd.isna(event.get("csq_lon")):
            continue
        eff = fdi_effort[
            (fdi_effort["rectangle_lon"] == event["csq_lon"]) &
            (fdi_effort["rectangle_lat"] == event["csq_lat"])
        ] if not fdi_effort.empty else pd.DataFrame()
        land = fdi_landings[
            (fdi_landings["rectangle_lon"] == event["csq_lon"]) &
            (fdi_landings["rectangle_lat"] == event["csq_lat"])
        ] if not fdi_landings.empty else pd.DataFrame()

        ctx = {
            "event_date": event["date"],
            "event_type": event["event_type"],
            "csq": (event["csq_lon"], event["csq_lat"]),
            "fishing_days": eff["totfishdays"].sum() if not eff.empty else 0,
            "is_known_ground": (eff["totfishdays"].sum() if not eff.empty else 0) > 10,
            "top_species": [],
        }
        if not land.empty:
            top = land.groupby("species")["totwghtlandg"].sum().sort_values(ascending=False).head(3)
            ctx["top_species"] = list(top.index)
        fisheries_context.append(ctx)
    report["fisheries"] = fisheries_context

    # ===== Step 6: Behavioural Pattern =====
    report["behaviour"] = {
        "event_types": vessel_events["event_type"].value_counts().to_dict(),
        "avg_duration_h": float(vessel_events["duration_h"].mean()),
        "max_duration_h": float(vessel_events["duration_h"].max()),
        "total_events": len(vessel_events),
        "unique_dates": vessel_events["date"].nunique(),
        "unique_locations": len(vessel_events[["lat", "lon"]].drop_duplicates()),
    }

    # Gap-specific analysis
    gaps = vessel_events[vessel_events["event_type"] == "GAP"]
    gap_count = len(gaps)
    avg_speed_before = None
    avg_speed_after = None
    if not gaps.empty and "speed_before_gap" in gaps.columns:
        avg_speed_before = float(gaps["speed_before_gap"].mean()) if gaps["speed_before_gap"].notna().any() else None
        avg_speed_after = float(gaps["speed_after_gap"].mean()) if gaps["speed_after_gap"].notna().any() else None
        report["behaviour"]["gap_analysis"] = {
            "count": gap_count,
            "avg_speed_before": avg_speed_before,
            "avg_speed_after": avg_speed_after,
        }

    # Behavioural trace entries
    has_encounter = "ENCOUNTER" in report["behaviour"]["event_types"]
    has_gap = "GAP" in report["behaviour"]["event_types"]
    has_loitering = "LOITERING" in report["behaviour"]["event_types"]

    if gap_count == 0:
        gap_sev = "none"
    elif gap_count <= 1:
        gap_sev = "none"
    elif gap_count <= 3:
        gap_sev = "medium"
    else:
        gap_sev = "high"
    trace.append({
        "branch_id": "behavioural_history", "question_id": "ais_gap_count",
        "answer": str(gap_count),
        "severity": gap_sev,
        "rule_fired": gap_count >= 2,
        "note": f"{gap_count} AIS gap(s) >6h in dataset",
    })
    trace.append({
        "branch_id": "behavioural_history", "question_id": "encounter_with_carrier",
        "answer": "yes" if has_encounter else "no",
        "severity": "medium" if has_encounter else "none",
        "rule_fired": has_encounter,
        "note": "Encounter event detected" if has_encounter else "No encounter events",
    })
    trace.append({
        "branch_id": "behavioural_history", "question_id": "loitering_in_fishing_grounds",
        "answer": "yes" if has_loitering else "no",
        "severity": "medium" if has_loitering else "none",
        "rule_fired": has_loitering,
        "note": "Loitering event detected" if has_loitering else "No loitering events",
    })
    speed_drop_fired = False
    if avg_speed_before and avg_speed_after and (avg_speed_before - avg_speed_after) > 3:
        speed_drop_fired = True
    trace.append({
        "branch_id": "behavioural_history", "question_id": "speed_change_at_gap",
        "answer": "yes" if speed_drop_fired else ("no" if has_gap else "n/a"),
        "severity": "high" if speed_drop_fired else "none",
        "rule_fired": speed_drop_fired,
        "note": f"Speed drop {avg_speed_before:.1f} -> {avg_speed_after:.1f} kn" if speed_drop_fired else "No significant speed change at gap",
    })

    # Kpler-aligned compound / temporal flags (display-only, derived from vessel-level columns)
    multi_behaviour = bool(primary.get("multi_behaviour_flag", False))
    trace.append({
        "branch_id": "behavioural_history", "question_id": "multi_behaviour_compound",
        "answer": "yes" if multi_behaviour else "no",
        "severity": "medium" if multi_behaviour else "none",
        "rule_fired": multi_behaviour,
        "note": (
            "Vessel shows multiple distinct event types (compound indicator)"
            if multi_behaviour
            else "Single event type only"
        ),
    })

    dark_port_candidates = 0
    if "dark_port_call_candidate" in vessel_events.columns:
        dark_port_candidates = int(vessel_events["dark_port_call_candidate"].sum())
    trace.append({
        "branch_id": "behavioural_history", "question_id": "dark_port_call_candidate",
        "answer": "yes" if dark_port_candidates > 0 else "no",
        "severity": "medium" if dark_port_candidates > 0 else "none",
        "rule_fired": dark_port_candidates > 0,
        "note": (
            f"{dark_port_candidates} loitering event(s) within 10 km of shore -- dark port call candidate(s)"
            if dark_port_candidates > 0
            else "No loitering events near shore"
        ),
    })

    repeat_offender = bool(primary.get("repeat_offender_90d", False))
    trace.append({
        "branch_id": "behavioural_history", "question_id": "repeat_offender_90d",
        "answer": "yes" if repeat_offender else "no",
        "severity": "medium" if repeat_offender else "none",
        "rule_fired": repeat_offender,
        "note": (
            "Two or more events within a 90-day window (exposure drift)"
            if repeat_offender
            else "No temporal clustering of events"
        ),
    })

    # Industrial vessel profile -- structural Kpler-aligned flag
    is_industrial = bool(primary.get("is_industrial", False))
    length_val = primary.get("length_m")
    tonnage_val = primary.get("tonnage_gt")
    try:
        length_num = float(length_val) if pd.notna(length_val) else None
    except (TypeError, ValueError):
        length_num = None
    try:
        tonnage_num = float(tonnage_val) if pd.notna(tonnage_val) else None
    except (TypeError, ValueError):
        tonnage_num = None
    if is_industrial:
        parts = []
        if length_num:
            parts.append(f"{length_num:.0f}m LOA")
        if tonnage_num:
            parts.append(f"{tonnage_num:.0f} GT")
        size_str = " / ".join(parts) if parts else "industrial profile"
        size_note = f"Industrial-class vessel ({size_str}); above 24m / 100 GT threshold"
    elif length_num or tonnage_num:
        parts = []
        if length_num:
            parts.append(f"{length_num:.0f}m LOA")
        if tonnage_num:
            parts.append(f"{tonnage_num:.0f} GT")
        size_str = " / ".join(parts)
        size_note = f"Artisanal-class vessel ({size_str}); below 24m / 100 GT threshold"
    else:
        size_note = "Vessel size unknown -- length/tonnage not resolved from GFW registry or static profile"
    trace.append({
        "branch_id": "behavioural_history", "question_id": "vessel_size_industrial",
        "answer": "yes" if is_industrial else ("no" if (length_num or tonnage_num) else "unknown"),
        "severity": "medium" if is_industrial else "none",
        "rule_fired": is_industrial,
        "note": size_note,
    })

    # Surface size on the identity report alongside the existing fields so
    # the investigation card can render Profile: 42m / 420 GT.
    report["identity"]["length_m"] = length_num
    report["identity"]["tonnage_gt"] = tonnage_num
    report["identity"]["is_industrial"] = is_industrial

    # Spatial trace entries
    contested_eez_flags = {"LBY", "SYR", "LBN"}
    vessel_flag = flag
    # Check if events are in contested EEZ (approximate: Libyan/Syrian/Lebanese waters)
    in_contested = False
    in_known_ground = any(ctx.get("is_known_ground", False) for ctx in fisheries_context)
    for _, event in vessel_events.iterrows():
        ev_lon, ev_lat = event.get("lon", 0), event.get("lat", 0)
        if (10 < ev_lon < 25 and 30 < ev_lat < 34) or (35 < ev_lon < 36.5 and 34 < ev_lat < 36):
            in_contested = True
            break
    trace.append({
        "branch_id": "spatial_context", "question_id": "contested_eez",
        "answer": "yes" if in_contested else "no",
        "severity": "high" if in_contested else "none",
        "rule_fired": in_contested,
        "note": "Activity in contested/weakly enforced EEZ" if in_contested else "Not in contested EEZ",
    })
    # MPA intersection from GFW regions.mpa (WDPA point-in-polygon)
    if "in_mpa" in vessel_events.columns:
        mpa_events = vessel_events[vessel_events["in_mpa"].fillna(False).astype(bool)]
    else:
        mpa_events = vessel_events.iloc[0:0]
    in_mpa_any = len(mpa_events) > 0
    if in_mpa_any:
        # Pick the highest-severity tier present on the vessel
        tier_priority = {"gfcm_fra": 3, "eu_site": 2, "general": 1, "": 0}
        tiers = mpa_events.get("mpa_tier", pd.Series(dtype=str)).fillna("").astype(str)
        top_tier = max(tiers, key=lambda t: tier_priority.get(t, 0)) if len(tiers) else ""
        mpa_names = [
            str(n) for n in mpa_events.get("mpa", pd.Series(dtype=str)).fillna("").unique()
            if str(n).strip()
        ]
        note = (
            f"{len(mpa_events)} event(s) inside an MPA "
            f"(highest tier: {top_tier or 'general'}). "
            f"Names: {'; '.join(mpa_names[:3])}"
        )
    else:
        top_tier = ""
        note = "No events intersect an MPA (GFW regions.mpa)"
    trace.append({
        "branch_id": "spatial_context", "question_id": "closed_fishery",
        "answer": "yes" if in_mpa_any else "no",
        "severity": "high" if in_mpa_any else "none",
        "rule_fired": in_mpa_any,
        "note": note,
    })
    trace.append({
        "branch_id": "spatial_context", "question_id": "high_value_grounds",
        "answer": "yes" if in_known_ground else "no",
        "severity": "medium" if in_known_ground else "none",
        "rule_fired": in_known_ground,
        "note": "Events in known fishing ground" if in_known_ground else "Not in known high-value fishing ground",
    })

    # ===== Fishing activity from GFW fishing-events dataset (separate from behavioural df) =====
    fishing_section = {
        "available": False,
        "event_count": 0,
        "hours": 0.0,
        "top_tier": "",
        "mpa_names": [],
        "events": [],
    }
    if fishing_df is not None and not fishing_df.empty and "mmsi" in fishing_df.columns:
        fishing_section["available"] = True
        fishing_for_vessel = fishing_df[
            fishing_df["mmsi"].astype(str) == str(mmsi_val)
        ].copy()
        if not fishing_for_vessel.empty and "in_mpa" in fishing_for_vessel.columns:
            fishing_in_mpa = fishing_for_vessel[
                fishing_for_vessel["in_mpa"].fillna(False).astype(bool)
            ]
            if not fishing_in_mpa.empty:
                tier_priority = {"gfcm_fra": 3, "eu_site": 2, "general": 1, "": 0}
                tiers_present = fishing_in_mpa.get(
                    "mpa_tier", pd.Series(dtype=str)
                ).fillna("").astype(str).tolist()
                top_tier = max(tiers_present, key=lambda t: tier_priority.get(t, 0)) if tiers_present else ""
                mpa_names = [
                    str(n) for n in fishing_in_mpa.get("mpa", pd.Series(dtype=str)).fillna("").unique()
                    if str(n).strip()
                ]
                fishing_section.update({
                    "event_count": int(len(fishing_in_mpa)),
                    "hours": round(float(fishing_in_mpa["fishing_hours"].sum()), 1) if "fishing_hours" in fishing_in_mpa.columns else 0.0,
                    "top_tier": top_tier,
                    "mpa_names": mpa_names,
                    "events": fishing_in_mpa.to_dict("records"),
                })
    report["fishing_in_mpa"] = fishing_section

    fishing_in_mpa_fired = fishing_section["event_count"] > 0
    if fishing_in_mpa_fired:
        fim_note = (
            f"{fishing_section['event_count']} GFW-classified fishing event(s) "
            f"inside an MPA (highest tier: {fishing_section['top_tier'] or 'general'}, "
            f"{fishing_section['hours']:.1f} h total). "
            f"Names: {'; '.join(fishing_section['mpa_names'][:3])}"
        )
    elif fishing_section["available"]:
        fim_note = "No GFW fishing events inside an MPA for this vessel"
    else:
        fim_note = "Fishing events dataset not available in current run"
    trace.append({
        "branch_id": "fishing_activity", "question_id": "fishing_in_mpa",
        "answer": "yes" if fishing_in_mpa_fired else ("no" if fishing_section["available"] else "unknown"),
        "severity": "high" if fishing_in_mpa_fired else "none",
        "rule_fired": fishing_in_mpa_fired,
        "note": fim_note,
    })

    # ===== Network Exposure (associative risk layer) =====
    # Four encounter-partner leaves: two name-based (IUU/OFAC list match),
    # two flag-based (weak-cooperation Med coastal, distant-water/non-Med FoC).
    encounter_events = vessel_events[vessel_events["event_type"] == "ENCOUNTER"]

    # Leaf 1: Encounter with IUU-listed vessel (name match)
    iuu_partner_hits = []
    if not encounter_events.empty and "encounter_vessel_name" in encounter_events.columns:
        partner_names = encounter_events["encounter_vessel_name"].dropna().str.upper().str.strip()
        iuu_names = (
            set(iuu_df["vessel_name"].dropna().str.upper().str.strip())
            if iuu_df is not None and not iuu_df.empty else set()
        )
        iuu_partner_hits = [n for n in partner_names if n in iuu_names]
    trace.append({
        "branch_id": "network_exposure", "question_id": "encounter_iuu_vessel",
        "answer": "yes" if iuu_partner_hits else "no",
        "severity": "high" if iuu_partner_hits else "none",
        "rule_fired": bool(iuu_partner_hits),
        "note": (
            f"Encounter with {len(iuu_partner_hits)} IUU-listed vessel(s): "
            f"{', '.join(sorted(set(iuu_partner_hits))[:3])}"
            if iuu_partner_hits
            else "No encounters with IUU-listed vessels"
        ),
    })

    # Leaf 2: Encounter with OFAC-sanctioned vessel (name match)
    ofac_partner_hits = []
    if not encounter_events.empty and "encounter_vessel_name" in encounter_events.columns:
        partner_names = encounter_events["encounter_vessel_name"].dropna().str.upper().str.strip()
        ofac_names = (
            set(ofac_df["vessel_name"].dropna().str.upper().str.strip())
            if ofac_df is not None and not ofac_df.empty else set()
        )
        ofac_partner_hits = [n for n in partner_names if n in ofac_names]
    trace.append({
        "branch_id": "network_exposure", "question_id": "encounter_sanctioned_vessel",
        "answer": "yes" if ofac_partner_hits else "no",
        "severity": "critical" if ofac_partner_hits else "none",
        "rule_fired": bool(ofac_partner_hits),
        "note": (
            f"Encounter with {len(ofac_partner_hits)} OFAC-sanctioned vessel(s): "
            f"{', '.join(sorted(set(ofac_partner_hits))[:3])}"
            if ofac_partner_hits
            else "No encounters with OFAC-sanctioned vessels"
        ),
    })

    # Leaf 3: Encounter with weak-cooperation Med coastal flag (LBY, SYR)
    weak_coop_partners = []
    if not encounter_events.empty and "encounter_vessel_flag" in encounter_events.columns:
        partner_flags = encounter_events["encounter_vessel_flag"].dropna().str.upper().str.strip()
        weak_coop_partners = [f for f in partner_flags if f in MED_COASTAL_WEAK_COOPERATION_FLAGS]
    trace.append({
        "branch_id": "network_exposure", "question_id": "encounter_weak_cooperation_partner",
        "answer": "yes" if weak_coop_partners else "no",
        "severity": "medium" if weak_coop_partners else "none",
        "rule_fired": bool(weak_coop_partners),
        "note": (
            f"Encounter(s) with partner flagged {', '.join(sorted(set(weak_coop_partners)))}: "
            f"GFCM non-compliance concerns"
            if weak_coop_partners
            else "No encounters with weak-cooperation Med coastal flags"
        ),
    })

    # Leaf 4: Encounter with distant-water or non-Med FoC flag
    med_coastal_all = MED_COASTAL_COOPERATIVE_FLAGS | MED_COASTAL_WEAK_COOPERATION_FLAGS
    dwf_partners = []
    if not encounter_events.empty and "encounter_vessel_flag" in encounter_events.columns:
        partner_flags = encounter_events["encounter_vessel_flag"].dropna().str.upper().str.strip()
        dwf_partners = [f for f in partner_flags if f and f not in EU_FLAGS and f not in med_coastal_all]
    trace.append({
        "branch_id": "network_exposure", "question_id": "encounter_distant_water_partner",
        "answer": "yes" if dwf_partners else "no",
        "severity": "medium" if dwf_partners else "none",
        "rule_fired": bool(dwf_partners),
        "note": (
            f"Encounter(s) with distant-water / non-Med FoC partner flag(s): "
            f"{', '.join(sorted(set(dwf_partners))[:5])}. Catch-laundering pattern."
            if dwf_partners
            else "No encounters with distant-water or non-Med FoC partners"
        ),
    })

    # Shared ownership (future work -- requires vessel ownership data)
    trace.append({
        "branch_id": "network_exposure", "question_id": "shared_ownership",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Requires beneficial ownership graph (Kpler Maritime 2.0 or Equasis); open-data coverage too sparse for fishing vessels",
        "status": "future_work",
    })

    # ===== Step 7: Risk Decomposition =====
    flag_mult = get_flag_risk(primary.get("flag", ""))
    report["risk"] = {
        "total_risk_score": float(vessel_events["risk_score"].sum()),
        "max_single_event": float(vessel_events["risk_score"].max()),
        "avg_event_risk": float(vessel_events["risk_score"].mean()),
        "flag_multiplier": flag_mult,
        "iuu_multiplier": float(primary.get("iuu_multiplier", 1.0)),
        "iccat_multiplier": float(primary.get("iccat_multiplier", 1.0)),
        "ofac_multiplier": float(primary.get("ofac_multiplier", 1.0)),
        "compounded_multiplier": flag_mult * float(primary.get("iuu_multiplier", 1.0))
                                  * float(primary.get("iccat_multiplier", 1.0))
                                  * float(primary.get("ofac_multiplier", 1.0)),
    }

    # ===== Step 8: Hypothesis Generation (rule-based) =====
    hypotheses = []

    # Highest priority signals
    if ofac_sanctioned and iuu_matched:
        hypotheses.append({
            "level": "critical",
            "text": "OFAC-sanctioned AND IUU-listed vessel — sanctions evasion using fisheries cover. Highest priority for investigation and enforcement.",
        })
    elif ofac_sanctioned:
        hypotheses.append({
            "level": "critical",
            "text": f"OFAC-sanctioned vessel under {report['ofac']['program']} program. Any commercial counterparty faces secondary sanctions exposure.",
        })
    elif iuu_matched and iccat_authorized:
        hypotheses.append({
            "level": "high",
            "text": "IUU-listed vessel that is also ICCAT-authorized — vessel with legitimate access that has been confirmed to engage in IUU fishing. Highest-priority fisheries signal.",
        })
    elif iuu_matched and report["iuu"]["is_gfcm"]:
        hypotheses.append({
            "level": "high",
            "text": "GFCM-listed vessel operating in Mediterranean — confirmed IUU history in this exact area. Likely repeat offender.",
        })

    # Behavioural hypotheses (has_encounter, has_gap, has_loitering set above)
    if iccat_authorized and report["iccat"]["risk_tier"] == "carrier" and has_encounter:
        hypotheses.append({
            "level": "high",
            "text": "ICCAT-authorized carrier in encounter event — core transshipment scenario. Verify Regional Observer Programme coverage under Rec. 24-05.",
        })

    if has_gap and report["behaviour"].get("gap_analysis", {}).get("avg_speed_before"):
        avg_before = report["behaviour"]["gap_analysis"]["avg_speed_before"]
        avg_after = report["behaviour"]["gap_analysis"].get("avg_speed_after", 0)
        if avg_before and avg_after and (avg_before - avg_after) > 3:
            hypotheses.append({
                "level": "medium",
                "text": "AIS gap pattern shows significant speed drop (>3kn) — consistent with mid-sea operation, either unauthorized fishing or transshipment.",
            })

    if has_loitering and primary.get("vessel_type", "").upper() in ("CARRIER", "TANKER", "REEFER"):
        hypotheses.append({
            "level": "medium",
            "text": "Carrier/tanker vessel loitering — consistent with staging for ship-to-ship transfer. Look for nearby fishing vessel encounters in the same timeframe.",
        })

    if not hypotheses:
        hypotheses.append({
            "level": "low",
            "text": "No high-confidence hypothesis generated. Vessel shows behavioural signals but no compounding regulatory flags.",
        })

    report["hypotheses"] = hypotheses

    # ===== Step 9: External Lookups =====
    imo = report["identity"]["imo"]
    if imo and str(imo).strip() not in ("", "nan", "None", "0"):
        report["external_links"] = {
            "marinetraffic": f"https://www.marinetraffic.com/en/ais/details/ships/imo:{imo}",
            "vesselfinder": f"https://www.vesselfinder.com/vessels/details/{imo}",
            "equasis": f"https://www.equasis.org/EquasisWeb/restricted/ShipInfo?fs=ShipList&P_IMO={imo}",
        }
    else:
        report["external_links"] = {}

    # ===== Step 10: Threat Assessment =====
    if ofac_sanctioned or (iuu_matched and report["iuu"]["is_gfcm"] and iccat_authorized):
        threat_level = "Critical"
    elif iuu_matched or (iccat_authorized and has_encounter):
        threat_level = "High"
    elif has_gap or has_encounter or has_loitering:
        threat_level = "Moderate"
    else:
        threat_level = "Low"

    key_evidence = []
    if iuu_matched:
        key_evidence.append(f"IUU-listed by {report['iuu']['rfmos']}")
    if iccat_authorized:
        key_evidence.append(f"ICCAT-authorized: {report['iccat']['authorizations']}")
    if ofac_sanctioned:
        key_evidence.append(f"OFAC-sanctioned ({report['ofac']['program']})")
    if flag_mult > 2.0:
        key_evidence.append(f"High-risk flag: {primary.get('flag')}")
    if report["behaviour"]["total_events"] >= 3:
        key_evidence.append(f"{report['behaviour']['total_events']} events in dataset")

    report["assessment"] = {
        "threat_level": threat_level,
        "key_evidence": key_evidence,
        "recommended_action": _recommend_action(threat_level, ofac_sanctioned, iuu_matched, iccat_authorized),
    }

    # Evaluation trace for risk tree visualization
    report["trace"] = trace

    return report


def format_trace_for_llm(trace: list, vessel_name: str = "") -> str:
    """Format the risk tree trace as LLM-readable structured text.

    Produces a compact, branch-grouped summary intended for inclusion
    in the AI Analyst's system prompt. Non-firing rules are included
    but marked, so the LLM can reason about what did and did not fire.
    """
    if not trace:
        return "No risk tree evaluation available for this vessel."

    from collections import OrderedDict
    branches = OrderedDict()
    for entry in trace:
        bid = entry.get("branch_id", "unknown")
        branches.setdefault(bid, []).append(entry)

    lines = []
    if vessel_name:
        lines.append(f"Risk tree trace for {vessel_name}:")
    else:
        lines.append("Risk tree trace:")
    lines.append("")

    for bid, entries in branches.items():
        fired = [e for e in entries if e.get("rule_fired")]
        lines.append(f"Branch: {bid}  ({len(fired)}/{len(entries)} rules fired)")
        for e in entries:
            mark = "FIRED" if e.get("rule_fired") else "not fired"
            sev = e.get("severity", "none")
            qid = e.get("question_id", "?")
            note = e.get("note", "")
            status = e.get("status", "")
            suffix = f" [future_work]" if status == "future_work" else ""
            lines.append(f"  - {qid}: {mark} | severity={sev} | {note}{suffix}")
        lines.append("")

    return "\n".join(lines)


def _recommend_action(threat_level, is_ofac, is_iuu, is_iccat):
    if threat_level == "Critical":
        if is_ofac:
            return "Immediate escalation to compliance team. Block any commercial transactions. Notify OFAC if US nexus exists."
        return "Escalate to GFCM Secretariat and flag state authorities. Add to high-priority watch list."
    elif threat_level == "High":
        if is_iuu:
            return "Notify GFCM Secretariat. Cross-check with port state control databases. Monitor for repeat events."
        return "Verify ICCAT Regional Observer Programme coverage. Cross-check transshipment authorizations."
    elif threat_level == "Moderate":
        return "Continue monitoring. Cross-reference with additional data sources if available."
    else:
        return "Routine monitoring. No immediate action required."
