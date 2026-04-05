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


def assign_csquare(lat, lon):
    """Map a point to its 0.5x0.5 dd c-square cell (FDI rectangle corner).
    FDI cells are centred at multiples of 0.5 (0.0, 0.5, 1.0, ...),
    rectangle_lon/lat is the SW corner = centre - 0.25.
    """
    centre_lon = round(round(lon * 2) / 2, 1)
    centre_lat = round(round(lat * 2) / 2, 1)
    return centre_lon - 0.25, centre_lat - 0.25
