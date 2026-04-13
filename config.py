"""Constants, lookups, and pure utility functions."""

import numpy as np

# ========================= EVENT & COLOR CONSTANTS =========================

EVENT_COLORS = {"GAP": "#e74c3c", "LOITERING": "#f39c12", "ENCOUNTER": "#8e44ad"}

DEFAULT_EVENT_WEIGHTS = {"GAP": 3.2, "LOITERING": 2.0, "ENCOUNTER": 5.0}

FLAG_RISKS = {
    "RUS": 2.8, "IRN": 2.4, "SYR": 2.0, "PRK": 3.0,
    "LBR": 1.3, "PAN": 1.2, "MHL": 1.2,
}

TRANSSHIPMENT_VESSEL_TYPES = {"CARRIER", "TANKER"}

# ========================= VESSEL TYPE NORMALISATION =========================
# Two vessel-type fields exist on every event row in `df`:
#
#   - vessel_type   event-level metadata from the GFW Events API
#                   (vessel.type on the event payload, often AIS self-reported)
#   - shiptypes     registry-level metadata from the GFW Vessels API
#                   (registry_info / self_reported_info, lowercase, may be
#                    a comma-joined list)
#
# Both fields are mapped through VESSEL_CLASS_PATTERNS into one of the
# canonical descriptive classes below. The result is the `vessel_class`
# column on `df`. Comparing the two derived classes (not the raw strings)
# is what produces the `vessel_type_mismatch` flag -- so a vessel_type of
# "TRAWLER" and a shiptypes of "FISHING" both map to industrial_fishing
# and the mismatch flag does not fire on the spelling difference.
#
# Mismatch fires when both fields are populated AND map to different
# classes. Absence of one field is not a mismatch.
#
# Order matters: first match wins. Put more specific patterns first
# (artisanal before fishing, carrier before cargo, etc.). Patterns are
# substring-matched against the lowercased input.

VESSEL_CLASS_PATTERNS = [
    ("artisanal_fishing", ["artisanal", "small_scale", "small scale"]),
    ("industrial_fishing", ["trawler", "fish_factory", "fish factory",
                            "purse_seine", "purse seiner", "purse_seiner",
                            "longliner", "long_liner", "drifter", "seiner",
                            "gillnetter", "fishing"]),
    ("carrier", ["reefer", "refrigerated_cargo", "refrigerated cargo",
                 "fish_carrier", "fish carrier", "carrier"]),
    ("tanker", ["oil_tanker", "oil tanker", "chemical_tanker", "tanker"]),
    ("cargo", ["bulk_carrier", "general_cargo", "general cargo",
               "container", "cargo"]),
    ("support", ["bunker", "supply", "support", "tug", "service"]),
    ("passenger", ["passenger", "ferry", "cruise"]),
]


def derive_vessel_class(value):
    """Map a free-form vessel-type string to a canonical descriptive class.

    Returns one of artisanal_fishing / industrial_fishing / carrier /
    tanker / cargo / support / passenger / other, or "" for null inputs.

    Used twice per row in compute_vessel_flags(): once on the event-level
    `vessel_type` and once on the registry-level `shiptypes`. The two
    results are then compared to produce `vessel_type_mismatch`.

    Patterns are config-driven via VESSEL_CLASS_PATTERNS so adjusting the
    taxonomy does not require touching the derivation logic. Substring
    matching means "trawler" and "Industrial Trawler" both classify the
    same way without needing exact-string entries.

    NB: this is a pure descriptor. The is_industrial flag remains size-
    based (>=24m or >=100GT) for EU regulatory alignment. vessel_class
    is orthogonal -- a small artisanal trawler classifies as
    artisanal_fishing here but is_industrial=False on the size axis.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    # shiptypes may be a comma-joined list -- the first part wins
    parts = [p.strip().lower() for p in s.split(",") if p.strip()]
    for part in parts:
        for canonical, patterns in VESSEL_CLASS_PATTERNS:
            if any(p in part for p in patterns):
                return canonical
    return "other"


IUU_MULTIPLIERS = {"GFCM": 3.0, "OTHER_RFMO": 2.0}

ICCAT_MULTIPLIERS = {
    "carrier": 1.4,
    "bft_catching": 1.3,
    "bft_other": 1.3,
    "swo_med": 1.2,
    "alb_med": 1.2,
}

OFAC_MULTIPLIER = 2.5

# ========================= MPA MULTIPLIERS =========================
# Spatial rule-zone factor applied to the base behavioural score (before
# IUU/ICCAT/OFAC compound multipliers). Tiered by regulatory enforcement
# backing rather than empirical outcomes -- calibration is by ordinal
# anchoring against the existing compliance chain, not by ground truth.
#
# Source: GFW Events API `regions.mpa` field, which pre-computes
# point-in-polygon intersection against WDPA (World Database on Protected
# Areas). Classification into tiers is by substring pattern on the MPA
# name returned by GFW.
#
# Calibration rationale (see reference_content.yaml::mpa_framing_note):
#   GFCM FRA    2.0x   parity with "other RFMO IUU listing", Reg 1967/2006
#   EU site     1.5x   Natura 2000 marine, national MPAs, softer enforcement
#   General     1.2x   other WDPA entries, contextual signal only
#
# AIS-only caveat: McDonald et al. 2024 (Nature) found ~75% of SAR-detected
# fishing vessels are AIS-dark, and the gap inside MPAs is closer to 90%.
# An AIS-based MPA intersection is therefore a lower-bound signal on
# broadcasting vessels, complementary to (not a replacement for) the
# existing AIS-gap evasion signal.

MPA_MULTIPLIERS = {
    "gfcm_fra": 2.0,
    "eu_site":  1.5,
    "general":  1.2,
}

# Substring patterns (lowercased) used to classify an MPA name into a tier.
# Order matters: first match wins, so put stricter patterns first.
MPA_TIER_PATTERNS = [
    ("gfcm_fra", ["gfcm", "fisheries restricted area", "fra"]),
    ("eu_site",  ["natura 2000", "natura2000", "site of community importance",
                  "special area of conservation", "sac", "spa",
                  "pelagos sanctuary"]),
]

# ========================= RISK BANDS =========================
# Aligned with Kpler R&C "Turning Tides" (Dec 2025) score-band vocabulary.
# Applied to final compounded risk_score after all multipliers.

RISK_BANDS = [
    (0,    50,             "Low",      "Sparse risk signals"),
    (50,   60,             "Emerging", "First risk flags"),
    (60,   80,             "Elevated", "Multiple risk indicators"),
    (80,   100,            "Severe",   "Compounding risk"),
    (100,  float("inf"),   "Critical", "Threshold breach"),
]

RISK_BAND_COLORS = {
    "Low":      "#2ecc71",
    "Emerging": "#f1c40f",
    "Elevated": "#e67e22",
    "Severe":   "#e74c3c",
    "Critical": "#8e0000",
}

FDI_EFFORT_COLORS = {
    "Very High": "#e31a1c",
    "High": "#fd8d3c",
    "Moderate": "#fecc5c",
    "Low": "#ffffb2",
}

# FAO 3-letter species code lookup (common Med species)
SPECIES_NAMES = {
    "HKE": "Hake", "MUT": "Red mullet", "SWO": "Swordfish",
    "BFT": "Bluefin tuna", "PIL": "Sardine", "ANE": "Anchovy",
    "DPS": "Deep-water rose shrimp", "OCC": "Common octopus",
    "ARS": "Red shrimp", "SAA": "Round sardinella", "ALB": "Albacore",
    "BOG": "Bogue", "SBG": "Gilthead seabream", "MZZ": "Marine fishes nei",
    "HOM": "Horse mackerel", "BSH": "Blue shark", "ARA": "Blue & red shrimp",
    "SQM": "European squid", "VMA": "Violet squid", "RPW": "Red pandora",
}

# ========================= FLAG TIER CONSTANTS (encounter-partner rules) ====
# Used by the network_exposure branch of the risk tree to classify encounter
# partner flags into regulatory tiers. Not used in scoring.

# EU member state flags (ISO 3166-1 alpha-3)
EU_FLAGS = {
    "ITA", "ESP", "GRC", "FRA", "HRV", "MLT", "CYP", "SVN",
    "PRT", "DEU", "NLD", "BEL", "IRL", "DNK", "SWE", "FIN",
    "POL", "EST", "LVA", "LTU", "BGR", "ROU", "HUN", "CZE",
    "SVK", "AUT", "LUX",
}

# Mediterranean coastal non-EU states with active GFCM cooperation
# and/or bilateral EU fisheries agreements. Encounters with these flags
# are routine regional interactions, not associative risk signals.
MED_COASTAL_COOPERATIVE_FLAGS = {
    "MAR",  # Morocco
    "TUN",  # Tunisia
    "TUR",  # Turkey
    "DZA",  # Algeria
    "EGY",  # Egypt
    "LBN",  # Lebanon
    "ISR",  # Israel
    "ALB",  # Albania
    "MNE",  # Montenegro
}

# Mediterranean coastal states with weak or compromised GFCM cooperation.
# Cited in GFCM non-compliance reports; encounters warrant medium-severity flag.
MED_COASTAL_WEAK_COOPERATION_FLAGS = {
    "LBY",  # Libya -- conflict-affected, weak enforcement capacity
    "SYR",  # Syria -- conflict-affected, weak enforcement capacity
}

FORBIDDEN_CODE = [
    "import os", "import sys", "subprocess", "eval(", "open(",
    "__import__", "exec(", "shutil", "pathlib", "requests",
    "urllib", "socket",
]


# ========================= GEOGRAPHIC HELPERS =========================

def classify_med_zone(lon, lat):
    """Classify a point into a Mediterranean sub-region."""
    if lat < 30 or lat > 46:
        return "Outside Mediterranean"
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


def classify_risk_band(score):
    """Return band label for a compounded risk score."""
    if score is None or (hasattr(score, "__float__") and score != score):  # NaN guard
        return "Low"
    for low, high, label, _desc in RISK_BANDS:
        if low <= score < high:
            return label
    return "Critical"


def classify_mpa_tier(mpa_names):
    """Map a list of MPA names to the highest-severity tier they imply.

    Uses substring matching against MPA_TIER_PATTERNS. Falls back to
    'general' if no pattern matches. An empty list returns ''.
    """
    if not mpa_names:
        return ""
    joined = " | ".join(str(n).lower() for n in mpa_names)
    for tier, patterns in MPA_TIER_PATTERNS:
        for pat in patterns:
            if pat in joined:
                return tier
    return "general"


def assign_csquare(lat, lon):
    """Map a point to its 0.5x0.5 dd c-square cell (FDI rectangle corner).
    FDI cells are centred at multiples of 0.5 (0.0, 0.5, 1.0, ...),
    rectangle_lon/lat is the SW corner = centre - 0.25.
    """
    centre_lon = round(round(lon * 2) / 2, 1)
    centre_lat = round(round(lat * 2) / 2, 1)
    return centre_lon - 0.25, centre_lat - 0.25
