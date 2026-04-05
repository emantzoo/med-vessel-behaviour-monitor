"""
Pre-process ICCAT Record of Vessels for Med Vessel Behaviour Monitor.
Run once. Output goes to data/ folder and is committed to repo.

Input:  CSV export from https://www.iccat.int/en/vesselsrecord.asp
Output: data/iccat_med_vessels.csv

Usage:
    python data/prepare_iccat.py --raw "path/to/20260405_111056_active.csv"
"""

import argparse
import os
import pandas as pd


# Med-relevant authorization columns and their human-readable labels
MED_AUTH_COLS = {
    "SWOm_ddIF": "SWO-Med",
    "ALBm_ddIF": "ALB-Med",
    "BFEc_ddIF": "BFT-Catching",
    "BFEo_ddIF": "BFT-Other",
    "Carr_ddIF": "Carrier",
}

# Risk tier priority (highest risk first)
TIER_PRIORITY = [
    ("Carr_ddIF", "carrier"),
    ("BFEc_ddIF", "bft_catching"),
    ("BFEo_ddIF", "bft_other"),
    ("SWOm_ddIF", "swo_med"),
    ("ALBm_ddIF", "alb_med"),
]

KEEP_COLS = [
    "ICCATSerialNo", "VesselName", "IntRegNo", "IRNoTypeCode", "IRCS",
    "FlagRepCode", "IsscfvCode", "IsscfgCode", "LOAm", "Tonnage",
    "SWOm_ddIF", "ALBm_ddIF", "BFEc_ddIF", "BFEo_ddIF", "Carr_ddIF",
    "OpName", "OwName",
]


def build_med_authorizations(row):
    """Build comma-separated list of Med authorization labels."""
    auths = []
    for col, label in MED_AUTH_COLS.items():
        if pd.notna(row.get(col)):
            auths.append(label)
    return ", ".join(auths)


def build_risk_tier(row):
    """Return highest-risk authorization tier for the vessel."""
    for col, tier in TIER_PRIORITY:
        if pd.notna(row.get(col)):
            return tier
    return ""


def main():
    parser = argparse.ArgumentParser(description="Pre-process ICCAT vessel list")
    parser.add_argument("--raw", required=True, help="Path to raw ICCAT CSV file")
    args = parser.parse_args()

    print(f"Reading {args.raw} ...")
    raw = pd.read_csv(args.raw)
    print(f"  Raw shape: {raw.shape}")

    # Filter to Med-relevant authorizations
    med_mask = raw[list(MED_AUTH_COLS.keys())].notna().any(axis=1)
    df = raw[med_mask].copy()
    print(f"  Med-relevant vessels: {len(df)}")

    # Keep only relevant columns
    df = df[[c for c in KEEP_COLS if c in df.columns]].copy()

    # Build derived columns
    df["med_authorizations"] = raw[med_mask].apply(build_med_authorizations, axis=1)
    df["iccat_risk_tier"] = raw[med_mask].apply(build_risk_tier, axis=1)

    # Uppercase vessel names for matching
    df["VesselName"] = df["VesselName"].fillna("").astype(str).str.strip().str.upper()

    # Save
    out_path = os.path.join(os.path.dirname(__file__), "iccat_med_vessels.csv")
    df.to_csv(out_path, index=False)

    # Summary
    print(f"\nWrote {len(df)} vessels to {out_path}")
    print(f"\nAuthorization breakdown:")
    for col, label in MED_AUTH_COLS.items():
        count = df[col].notna().sum() if col in df.columns else 0
        print(f"  {label}: {count}")
    print(f"\nRisk tier breakdown:")
    print(df["iccat_risk_tier"].value_counts().to_string())
    print(f"\nTop flags:")
    print(df["FlagRepCode"].value_counts().head(15).to_string())
    print(f"\nSample vessel names (first 10):")
    for n in df["VesselName"].head(10):
        print(f"  {n}")


if __name__ == "__main__":
    main()
