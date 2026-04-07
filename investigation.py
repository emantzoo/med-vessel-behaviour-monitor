"""Deterministic vessel investigation — rule-based analysis without LLM."""

import pandas as pd
from config import FLAG_RISKS, IUU_MULTIPLIERS, ICCAT_MULTIPLIERS, OFAC_MULTIPLIER


def investigate_vessel(vessel_identifier, df, iuu_df, iccat_df, ofac_df, fdi_effort, fdi_landings):
    """
    Run a structured 10-step investigation on a vessel.

    vessel_identifier: vessel_name (str) or mmsi (str/int)
    Returns: dict with all 10 investigation steps as structured data.
    """
    # Find vessel in df (by name or mmsi)
    if str(vessel_identifier).isdigit():
        vessel_events = df[df["mmsi"].astype(str) == str(vessel_identifier)]
    else:
        vessel_events = df[
            df["vessel_name"].str.upper().str.contains(
                str(vessel_identifier).upper(), na=False
            )
        ]

    if vessel_events.empty:
        return {"error": f"Vessel '{vessel_identifier}' not found in current dataset."}

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
    # MMSI consistency: we can only check if MMSI exists, not history
    trace.append({
        "branch_id": "identity", "question_id": "mmsi_consistent",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "MMSI consistency requires historical data (not available in current dataset)",
    })
    # Name history: unknown without historical data
    trace.append({
        "branch_id": "identity", "question_id": "name_history",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Name change history requires historical data (not available in current dataset)",
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
        "note": "EU sanctions data not available in current dataset",
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
        "note": "Flag change history requires historical data",
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
        "note": "GFCM Authorized Vessel List not available in current dataset",
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
    trace.append({
        "branch_id": "spatial_context", "question_id": "closed_fishery",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Closed fishery data not available in current dataset",
    })
    trace.append({
        "branch_id": "spatial_context", "question_id": "high_value_grounds",
        "answer": "yes" if in_known_ground else "no",
        "severity": "medium" if in_known_ground else "none",
        "rule_fired": in_known_ground,
        "note": "Events in known fishing ground" if in_known_ground else "Not in known high-value fishing ground",
    })

    # Network exposure trace entries
    trace.append({
        "branch_id": "network_exposure", "question_id": "encounter_iuu_vessel",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Encounter partner IUU status not checked in current implementation",
    })
    trace.append({
        "branch_id": "network_exposure", "question_id": "encounter_sanctioned_vessel",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Encounter partner sanctions status not checked in current implementation",
    })
    trace.append({
        "branch_id": "network_exposure", "question_id": "shared_ownership",
        "answer": "unknown", "severity": "none", "rule_fired": False,
        "note": "Ownership data not available",
    })

    # ===== Step 7: Risk Decomposition =====
    flag_mult = FLAG_RISKS.get(primary.get("flag", ""), 1.0)
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
