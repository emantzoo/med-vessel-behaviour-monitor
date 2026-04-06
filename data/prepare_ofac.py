"""
Pre-process OFAC SDN list for Med Vessel Behaviour Monitor.
Run once. Output goes to data/ folder and is committed to repo.

Input:  SDN CSV from https://www.treasury.gov/ofac/downloads/sdn.csv
        or pre-processed vessels CSV (e.g., from OpenSanctions)
Output: data/ofac_vessels.csv

Usage:
    python data/prepare_ofac.py --raw "path/to/sdn.csv"
    python data/prepare_ofac.py --raw "path/to/opensanctions.csv" --format opensanctions
"""

import argparse
import os
import re

import pandas as pd


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


def extract_vessel_details(remarks_str):
    """Parse OFAC 'Remarks' field for IMO, MMSI, vessel type, flag.

    OFAC format example:
    'IMO 9283760; MMSI 256007000; Vessel Type Crude Oil Tanker; Flag Iran'
    """
    details = {}
    if pd.isna(remarks_str):
        return details

    remarks = str(remarks_str)

    imo_match = re.search(r"IMO\s*[:#]?\s*(\d{7})", remarks, re.IGNORECASE)
    if imo_match:
        details["imo"] = imo_match.group(1)

    mmsi_match = re.search(r"MMSI\s*[:#]?\s*(\d{9})", remarks, re.IGNORECASE)
    if mmsi_match:
        details["mmsi"] = mmsi_match.group(1)

    vtype_match = re.search(r"Vessel\s+Type\s*[:#]?\s*([^;]+)", remarks, re.IGNORECASE)
    if vtype_match:
        details["vessel_type"] = vtype_match.group(1).strip()

    flag_match = re.search(r"(?:Flag|Nationality)\s*[:#]?\s*([^;]+)", remarks, re.IGNORECASE)
    if flag_match:
        details["flag_from_remarks"] = flag_match.group(1).strip()

    return details


def process_ofac_sdn(raw_path):
    """Process raw OFAC SDN CSV."""
    raw = pd.read_csv(raw_path, dtype=str, encoding="latin-1")

    # Filter to vessels only
    vessel_mask = raw["SDN_Type"].fillna("").str.lower().str.contains("vessel")
    vessels = raw[vessel_mask].copy()

    # Extract details from Remarks
    details = vessels["Remarks"].apply(extract_vessel_details)
    details_df = pd.DataFrame(details.tolist(), index=vessels.index)

    # Build output
    df = pd.DataFrame()
    df["vessel_name"] = vessels["SDN_Name"].fillna("").str.strip().str.upper()
    df["all_names"] = df["vessel_name"]
    df["imo"] = details_df.get("imo", pd.Series("", index=vessels.index))
    df["mmsi"] = details_df.get("mmsi", pd.Series("", index=vessels.index))
    df["flag"] = vessels.get("Vess_flag", pd.Series("", index=vessels.index)).fillna("")
    df["vessel_type"] = vessels.get("Vess_type", pd.Series("", index=vessels.index)).fillna("")
    df["sanctions_program"] = vessels["Program"].fillna("")
    df["listing_date"] = ""
    df["sdnentry_id"] = vessels["ent_num"].fillna("")

    df["imo"] = clean_int_field(df["imo"])
    df["mmsi"] = clean_int_field(df["mmsi"])

    return df


def process_opensanctions(raw_path):
    """Process OpenSanctions pre-processed CSV."""
    raw = pd.read_csv(raw_path, dtype=str).fillna("")
    df = pd.DataFrame()
    df["vessel_name"] = raw.get("name", raw.get("caption", pd.Series(""))).str.strip().str.upper()
    df["all_names"] = df["vessel_name"]
    df["imo"] = clean_int_field(raw.get("imo", pd.Series("")))
    df["mmsi"] = clean_int_field(raw.get("mmsi", pd.Series("")))
    df["flag"] = raw.get("flag", "")
    df["vessel_type"] = raw.get("vessel_type", raw.get("type", ""))
    df["sanctions_program"] = raw.get("program", raw.get("dataset", ""))
    df["listing_date"] = raw.get("first_seen", raw.get("listing_date", ""))
    df["sdnentry_id"] = raw.get("id", raw.get("entity_id", ""))
    return df


def main():
    parser = argparse.ArgumentParser(description="Pre-process OFAC SDN vessel list")
    parser.add_argument("--raw", required=True, help="Path to raw SDN CSV file")
    parser.add_argument(
        "--format", default="ofac", choices=["ofac", "opensanctions"],
        help="Input format: 'ofac' for raw SDN CSV, 'opensanctions' for pre-processed",
    )
    args = parser.parse_args()

    print(f"Reading {args.raw} ...")

    if args.format == "ofac":
        df = process_ofac_sdn(args.raw)
    else:
        df = process_opensanctions(args.raw)

    out_path = os.path.join(os.path.dirname(__file__), "ofac_vessels.csv")
    df.to_csv(out_path, index=False)

    print(f"\nWrote {len(df)} vessels to {out_path}")
    print(f"  With IMO: {(df['imo'] != '').sum()}")
    print(f"  With MMSI: {(df['mmsi'] != '').sum()}")
    print(f"  Unique flags: {df['flag'].nunique()}")
    print(f"\n  Sanctions programs:\n{df['sanctions_program'].value_counts().head(10).to_string()}")
    print(f"\n  Sample vessel names (first 10):")
    for n in df["vessel_name"].head(10):
        print(f"    {n}")


if __name__ == "__main__":
    main()
