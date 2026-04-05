"""
Pre-process Combined IUU Vessel List for Med Vessel Behaviour Monitor.
Run once. Output goes to data/ folder and is committed to repo.

Input:  Raw Excel from iuu-vessels.org (user places in data/raw/ or passes via --raw)
Output: data/iuu_vessels.csv

Usage:
    python data/prepare_iuu.py --raw "path/to/IUUList-20260405.xls"
"""

import argparse
import os
import pandas as pd


RFMO_COLUMNS = {
    "IOTC": "Reason",
    "ICCAT": "Reason.1",
    "IATTC": "Reason.2",
    "CCAMLR": "Reason.3",
    "WCPFC": "Reason.4",
    "SEAFO": "Reason.5",
    "NEAFC": "Reason.6",
    "NAFO": "Reason.7",
    "SPRFMO": "Reason.8",
    "CCSBT": "Reason.9",
    "GFCM": "Reason.10",
    "NPFC": "Reason.11",
    "SIOFA": "Reason.12",
}


def build_all_names(name_str):
    """Split Name field on commas, uppercase, strip, pipe-delimit."""
    if pd.isna(name_str) or not str(name_str).strip():
        return ""
    parts = [p.strip().upper() for p in str(name_str).split(",") if p.strip()]
    return "|".join(parts)


def build_listing_rfmos(row):
    """Return comma-separated list of RFMOs that have listed this vessel."""
    rfmos = []
    for rfmo_name in RFMO_COLUMNS:
        if pd.notna(row.get(rfmo_name)) and str(row[rfmo_name]).strip():
            rfmos.append(rfmo_name)
    return ", ".join(rfmos)


def build_listing_reason(row):
    """Return GFCM reason if available, else first available RFMO reason."""
    # Prefer GFCM reason
    gfcm_reason = row.get("Reason.10")
    if pd.notna(gfcm_reason) and str(gfcm_reason).strip():
        return str(gfcm_reason).strip()
    # Fall back to first available
    for reason_col in RFMO_COLUMNS.values():
        val = row.get(reason_col)
        if pd.notna(val) and str(val).strip():
            return str(val).strip()
    return ""


def clean_int_field(series):
    """Convert float/string to clean int-as-string, handling NaN."""
    def _clean(val):
        if pd.isna(val) or str(val).strip() in ("", "nan", "None"):
            return ""
        s = str(val).strip().replace(".0", "")
        try:
            return str(int(float(s)))
        except (ValueError, OverflowError):
            return ""
    return series.apply(_clean)


def main():
    parser = argparse.ArgumentParser(description="Pre-process IUU vessel list")
    parser.add_argument("--raw", required=True, help="Path to raw IUU Excel file")
    args = parser.parse_args()

    print(f"Reading {args.raw} ...")
    raw = pd.read_excel(args.raw, sheet_name="IUUList")
    print(f"  Raw shape: {raw.shape}")

    # Select and rename columns
    keep = {
        "CurrentlyListed": "is_currently_listed",
        "Name": "name_raw",
        "RFMOName": "rfmo_name",
        "IMO": "imo",
        "MMSI": "mmsi",
        "IRCS": "ircs",
        "Flag": "flag",
        "VesselType": "vessel_type",
        "GearType": "gear_type",
        "OwnerName": "owner",
        "OperatorName": "operator",
    }

    df = raw.rename(columns=keep)

    # Build all_names from raw Name field
    df["all_names"] = df["name_raw"].apply(build_all_names)
    # Primary vessel name = first element
    df["vessel_name"] = df["all_names"].apply(
        lambda x: x.split("|")[0] if x else ""
    )

    # RFMO listing info
    df["listing_rfmos"] = raw.apply(build_listing_rfmos, axis=1)
    df["listing_reason"] = raw.apply(build_listing_reason, axis=1)

    # GFCM flag
    df["is_gfcm"] = raw["GFCM"].notna() & (raw["GFCM"].astype(str).str.strip() != "")

    # Clean MMSI and IMO
    df["mmsi"] = clean_int_field(df["mmsi"])
    df["imo"] = clean_int_field(df["imo"])

    # Select final columns
    out_cols = [
        "is_currently_listed", "vessel_name", "all_names", "rfmo_name",
        "imo", "mmsi", "ircs", "flag", "vessel_type", "gear_type",
        "owner", "operator", "is_gfcm", "listing_rfmos", "listing_reason",
    ]
    df = df[out_cols]

    # Save
    out_path = os.path.join(os.path.dirname(__file__), "iuu_vessels.csv")
    df.to_csv(out_path, index=False)

    # Summary
    print(f"\nWrote {len(df)} vessels to {out_path}")
    print(f"  Currently listed: {df['is_currently_listed'].sum()}")
    print(f"  GFCM-listed: {df['is_gfcm'].sum()}")
    print(f"  With MMSI: {(df['mmsi'] != '').sum()}")
    print(f"  With IMO: {(df['imo'] != '').sum()}")
    print(f"  Unique flags: {df['flag'].nunique()}")
    print(f"\nTop flags:")
    print(df["flag"].value_counts().head(10).to_string())
    print(f"\nSample vessel names (first 10):")
    for n in df["vessel_name"].head(10):
        print(f"  {n}")
    print(f"\nSample all_names (first 5):")
    for n in df["all_names"].head(5):
        try:
            print(f"  {n}")
        except UnicodeEncodeError:
            print(f"  {n.encode('ascii', 'replace').decode()}")


if __name__ == "__main__":
    main()
