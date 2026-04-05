"""
Pre-process FDI spatial data for Med Vessel Behaviour Monitor.
Run once. Outputs go to data/ folder and are committed to repo.

Input:  Raw FDI CSVs from JRC ZIP download
        - spatial_effort_tableau_pts_EU27_2012-2024.csv
        - spatial_landings_tableau_pts_{year}_EU27.csv  (2017-2024)

Output: data/fdi_effort_med.csv, data/fdi_landings_med.csv

Usage:
    python data/prepare_fdi.py --raw-dir "C:/Users/emant/Downloads/2025_FDI_spatial_data/EU27"
"""

import argparse
import os
import sys
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Med zone classifier (same as app.py)
# ---------------------------------------------------------------------------
def classify_med_zone(lon, lat):
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


def process_effort(raw_dir, out_dir):
    """Filter and preprocess the effort CSV."""
    path = os.path.join(raw_dir, "spatial_effort_tableau_pts_EU27_2012-2024.csv")
    print(f"Loading effort: {path}")
    df = pd.read_csv(path, dtype={"specon_tech": str, "deep": str})
    print(f"  Raw rows: {len(df):,}")

    # Filter: Mediterranean & Black Sea supra-region
    df = df[df["supra_region"] == "MBS"]
    print(f"  After MBS filter: {len(df):,}")

    # Filter: 2017-2024 only (Med spatial data reliable from 2017)
    df = df[df["year"] >= 2017]
    print(f"  After year >= 2017: {len(df):,}")

    # Filter: 0.5x0.5 dd c-squares only
    df = df[df["rectangle_type"] == "05*05"]
    print(f"  After 05*05 filter: {len(df):,}")

    # Filter: Med lat/lon bounds (exclude Black Sea outliers)
    # Med approx: lon -6 to 36.5, lat 30 to 46
    df = df[(df["rectangle_lon"] >= -6.5) & (df["rectangle_lon"] <= 37) &
            (df["rectangle_lat"] >= 29.5) & (df["rectangle_lat"] <= 46.5)]
    print(f"  After Med bounds filter: {len(df):,}")

    # Compute cell centres
    df["centre_lon"] = df["rectangle_lon"] + 0.25
    df["centre_lat"] = df["rectangle_lat"] + 0.25

    # Assign med zone
    df["med_zone"] = df.apply(
        lambda r: classify_med_zone(r["centre_lon"], r["centre_lat"]), axis=1
    )

    # Aggregate: by c-square + year + quarter + gear_type
    # Drops vessel_length, fishing_tech, sub_region to reduce size (~5 MB)
    df = df.groupby(["year", "quarter", "gear_type", "rectangle_lon",
                     "rectangle_lat", "centre_lon", "centre_lat",
                     "med_zone"]).agg(
        totfishdays=("totfishdays", "sum"),
    ).reset_index()

    out_path = os.path.join(out_dir, "fdi_effort_med.csv")
    df.to_csv(out_path, index=False)
    print(f"\n  Saved: {out_path}")
    print(f"  Rows: {len(df):,}")
    print(f"  Years: {df['year'].min()}-{df['year'].max()}")
    print(f"  Unique c-squares: {df[['rectangle_lon','rectangle_lat']].drop_duplicates().shape[0]:,}")
    print(f"  Top gear types:\n{df['gear_type'].value_counts().head(8).to_string()}")
    print(f"  Med zones:\n{df['med_zone'].value_counts().to_string()}")
    return df


def process_landings(raw_dir, out_dir):
    """Filter and preprocess landings CSVs (one per year, 2017-2024)."""
    frames = []
    for year in range(2017, 2025):
        path = os.path.join(raw_dir, f"spatial_landings_tableau_pts_{year}_EU27.csv")
        if not os.path.exists(path):
            print(f"  Skipping missing: {path}")
            continue
        print(f"  Loading landings {year}...")
        df = pd.read_csv(path, dtype={"specon_tech": str, "deep": str})
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    print(f"\n  Raw landings rows (2017-2024): {len(df):,}")

    # Filter: MBS
    df = df[df["supra_region"] == "MBS"]
    print(f"  After MBS filter: {len(df):,}")

    # Filter: 0.5x0.5 dd
    df = df[df["rectangle_type"] == "05*05"]
    print(f"  After 05*05 filter: {len(df):,}")

    # Filter: Med bounds
    df = df[(df["rectangle_lon"] >= -6.5) & (df["rectangle_lon"] <= 37) &
            (df["rectangle_lat"] >= 29.5) & (df["rectangle_lat"] <= 46.5)]
    print(f"  After Med bounds filter: {len(df):,}")

    # Cell centres + med zone
    df["centre_lon"] = df["rectangle_lon"] + 0.25
    df["centre_lat"] = df["rectangle_lat"] + 0.25
    df["med_zone"] = df.apply(
        lambda r: classify_med_zone(r["centre_lon"], r["centre_lat"]), axis=1
    )

    # Aggregate: by c-square + year + species (drop quarter/gear/vessel_length)
    # Reduces from ~3M rows to ~200K (~17 MB)
    df = df.groupby(["year", "rectangle_lon", "rectangle_lat", "centre_lon",
                     "centre_lat", "species", "med_zone"]).agg(
        totwghtlandg=("totwghtlandg", "sum"),
        totvallandg=("totvallandg", "sum"),
    ).reset_index()

    out_path = os.path.join(out_dir, "fdi_landings_med.csv")
    df.to_csv(out_path, index=False)
    print(f"\n  Saved: {out_path}")
    print(f"  Rows: {len(df):,}")
    print(f"  Years: {df['year'].min()}-{df['year'].max()}")
    print(f"  Unique c-squares: {df[['rectangle_lon','rectangle_lat']].drop_duplicates().shape[0]:,}")
    print(f"  Top species:\n{df.groupby('species')['totwghtlandg'].sum().sort_values(ascending=False).head(10).to_string()}")
    return df


def main():
    parser = argparse.ArgumentParser(description="Preprocess FDI data for Med")
    parser.add_argument("--raw-dir", required=True, help="Path to raw FDI CSV folder")
    args = parser.parse_args()

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 60)
    print("FDI PREPROCESSING — Med Vessel Behaviour Monitor")
    print("=" * 60)

    print("\n--- EFFORT ---")
    process_effort(args.raw_dir, out_dir)

    print("\n--- LANDINGS ---")
    process_landings(args.raw_dir, out_dir)

    print("\n" + "=" * 60)
    print("Done. Commit fdi_effort_med.csv and fdi_landings_med.csv to repo.")
    print("=" * 60)


if __name__ == "__main__":
    main()
