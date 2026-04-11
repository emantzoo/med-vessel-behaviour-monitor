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
