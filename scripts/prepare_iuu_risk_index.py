"""
Prepare flag-level multipliers from the Poseidon IUU Fishing Risk Index.

Input: raw Index dataset (CSV or Excel) with 40 indicators per country per year.
Output: CSV mapping ISO-3 country code to flag-level multiplier.

Methodology:
- Filter to the latest year available (2025 if present)
- Filter to Resp == "Flag" — 10 indicators per country
- Compute arithmetic mean of the 10 Flag-responsibility scores per country
- Map mean score (1.0-5.0) to multiplier via linear function:
  multiplier = 1.0 + (mean_score - 1.0) * 0.3
  Yields: score 1 -> 1.0x, score 3 -> 1.6x, score 5 -> 2.2x
- Map country names to ISO-3 codes using a lookup table

Source: https://iuufishingindex.net/
"""

import pandas as pd
from pathlib import Path

# Country name -> ISO-3 mapping (all 152 countries in the Index).
COUNTRY_TO_ISO3 = {
    "Albania": "ALB",
    "Algeria": "DZA",
    "Angola": "AGO",
    "Antigua & Barbuda": "ATG",
    "Argentina": "ARG",
    "Australia": "AUS",
    "Bahamas": "BHS",
    "Bahrain": "BHR",
    "Bangladesh": "BGD",
    "Barbados": "BRB",
    "Belgium": "BEL",
    "Belize": "BLZ",
    "Benin": "BEN",
    "Bosnia & Herzegovina": "BIH",
    "Brazil": "BRA",
    "Brunei Darussalam": "BRN",
    "Bulgaria": "BGR",
    "Cambodia": "KHM",
    "Cameroon": "CMR",
    "Canada": "CAN",
    "Cape Verde": "CPV",
    "Chile": "CHL",
    "China": "CHN",
    "Colombia": "COL",
    "Comoros Isl.": "COM",
    "Congo (DRC)": "COD",
    "Congo, R. of": "COG",
    "Cook Islands": "COK",
    "Costa Rica": "CRI",
    "Cote d'Ivoire": "CIV",
    "Croatia": "HRV",
    "Cuba": "CUB",
    "Cyprus": "CYP",
    "Denmark": "DNK",
    "Djibouti": "DJI",
    "Dominica": "DMA",
    "Dominican Republic": "DOM",
    "Ecuador": "ECU",
    "Egypt": "EGY",
    "El Salvador": "SLV",
    "Equatorial Guinea": "GNQ",
    "Eritrea": "ERI",
    "Estonia": "EST",
    "Fiji": "FJI",
    "Finland": "FIN",
    "France": "FRA",
    "Gabon": "GAB",
    "Gambia": "GMB",
    "Georgia": "GEO",
    "Germany": "DEU",
    "Ghana": "GHA",
    "Greece": "GRC",
    "Grenada": "GRD",
    "Guatemala": "GTM",
    "Guinea": "GIN",
    "Guinea-Bissau": "GNB",
    "Guyana": "GUY",
    "Haiti": "HTI",
    "Honduras": "HND",
    "Iceland": "ISL",
    "India": "IND",
    "Indonesia": "IDN",
    "Iran": "IRN",
    "Iraq": "IRQ",
    "Ireland": "IRL",
    "Israel": "ISR",
    "Italy": "ITA",
    "Jamaica": "JAM",
    "Japan": "JPN",
    "Jordan": "JOR",
    "Kenya": "KEN",
    "Kiribati": "KIR",
    "Korea (North)": "PRK",
    "Korea (Rep. South)": "KOR",
    "Kuwait": "KWT",
    "Latvia": "LVA",
    "Lebanon": "LBN",
    "Liberia": "LBR",
    "Libya": "LBY",
    "Lithuania": "LTU",
    "Madagascar": "MDG",
    "Malaysia": "MYS",
    "Maldives": "MDV",
    "Malta": "MLT",
    "Marshall Isl.": "MHL",
    "Mauritania": "MRT",
    "Mauritius": "MUS",
    "Mexico": "MEX",
    "Micronesia (FS of)": "FSM",
    "Monaco": "MCO",
    "Montenegro": "MNE",
    "Morocco": "MAR",
    "Mozambique": "MOZ",
    "Myanmar": "MMR",
    "Namibia": "NAM",
    "Nauru": "NRU",
    "Netherlands": "NLD",
    "New Zealand": "NZL",
    "Nicaragua": "NIC",
    "Nigeria": "NGA",
    "Norway": "NOR",
    "Oman": "OMN",
    "Pakistan": "PAK",
    "Palau": "PLW",
    "Panama": "PAN",
    "Papua New Guinea": "PNG",
    "Peru": "PER",
    "Philippines": "PHL",
    "Poland": "POL",
    "Portugal": "PRT",
    "Qatar": "QAT",
    "Romania": "ROU",
    "Russia": "RUS",
    "Saint Kitts & Nevis": "KNA",
    "Saint Lucia": "LCA",
    "Saint Vincent & the Grenadines": "VCT",
    "Samoa": "WSM",
    "Sao Tome & Principe": "STP",
    "Saudi Arabia": "SAU",
    "Senegal": "SEN",
    "Seychelles": "SYC",
    "Sierra Leone": "SLE",
    "Singapore": "SGP",
    "Slovenia": "SVN",
    "Solomon Isl.": "SLB",
    "Somalia": "SOM",
    "South Africa": "ZAF",
    "Spain": "ESP",
    "Sri Lanka": "LKA",
    "Sudan": "SDN",
    "Suriname": "SUR",
    "Sweden": "SWE",
    "Syria": "SYR",
    "Taiwan": "TWN",
    "Tanzania": "TZA",
    "Thailand": "THA",
    "Timor Leste": "TLS",
    "Togo": "TGO",
    "Tonga": "TON",
    "Trinidad & Tobago": "TTO",
    "Tunisia": "TUN",
    "Turkey": "TUR",
    "Tuvalu": "TUV",
    "USA": "USA",
    "Ukraine": "UKR",
    "United Arab Emirates": "ARE",
    "United Kingdom": "GBR",
    "Uruguay": "URY",
    "Vanuatu": "VUT",
    "Venezuela": "VEN",
    "Viet Nam": "VNM",
    "Yemen": "YEM",
}


def score_to_multiplier(mean_score: float, slope: float = 0.3) -> float:
    """Map mean Flag score (1.0-5.0) to a risk multiplier.

    Linear mapping centred at 1.0x for score 1 (best).
    Default slope 0.3 gives: 1 -> 1.0, 3 -> 1.6, 5 -> 2.2.
    """
    if pd.isna(mean_score):
        return None
    return round(1.0 + (mean_score - 1.0) * slope, 3)


def main(input_path: str, output_path: str, year: int = 2025):
    print(f"Loading IUU Risk Index dataset from {input_path}")

    in_path = Path(input_path)
    if in_path.suffix in (".xlsx", ".xls"):
        df = pd.read_excel(in_path)
    else:
        df = pd.read_csv(in_path)

    # Normalise column names defensively
    df.columns = [c.strip() for c in df.columns]

    # Filter to the target year
    available_years = sorted(df["Year"].unique())
    if year not in available_years:
        year = max(available_years)
        print(f"Target year not in data. Using latest: {year}")
    df_year = df[df["Year"] == year].copy()
    print(f"Using year: {year}, {df_year['Country'].nunique()} countries")

    # Filter to Flag responsibility indicators only
    flag_df = df_year[df_year["Resp"] == "Flag"].copy()
    print(f"Found {len(flag_df)} Flag-responsibility records")

    # Aggregate per country
    country_scores = (
        flag_df.groupby("Country")
        .agg(
            flag_score_mean=("Score", "mean"),
            n_indicators=("Score", "count"),
        )
        .reset_index()
    )

    # Map country names to ISO-3
    country_scores["iso3"] = country_scores["Country"].map(COUNTRY_TO_ISO3)
    unmapped = country_scores[country_scores["iso3"].isna()]["Country"].tolist()
    if unmapped:
        print(f"WARNING: {len(unmapped)} countries unmapped to ISO-3:")
        for c in unmapped:
            print(f"  - {c}")
        print("Add to COUNTRY_TO_ISO3 dict and re-run.")

    # Compute multiplier
    country_scores["flag_multiplier"] = country_scores["flag_score_mean"].apply(
        score_to_multiplier
    )
    country_scores["source_year"] = year

    # Drop unmapped countries; sort by multiplier descending
    country_scores = country_scores.dropna(subset=["iso3"])
    country_scores = country_scores.sort_values("flag_multiplier", ascending=False)

    # Final columns and export
    output_cols = [
        "iso3", "Country", "flag_score_mean", "flag_multiplier",
        "n_indicators", "source_year",
    ]
    country_scores = country_scores[output_cols].rename(
        columns={"Country": "country"}
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    country_scores.to_csv(out_path, index=False)
    print(f"\nWrote {len(country_scores)} rows to {out_path}")
    print(f"Multiplier range: "
          f"{country_scores['flag_multiplier'].min():.3f} to "
          f"{country_scores['flag_multiplier'].max():.3f}")

    # Sanity check — Med & Black Sea flags
    print("\nMed & Black Sea flags:")
    med_iso3 = {"ITA", "GRC", "ESP", "FRA", "HRV", "MLT", "CYP", "SVN",
                "TUR", "TUN", "MAR", "DZA", "EGY", "LBY", "SYR",
                "LBN", "ISR", "ALB", "MNE", "BGR", "ROU", "GEO", "UKR"}
    for _, row in country_scores.iterrows():
        if row["iso3"] in med_iso3:
            print(f"  {row['iso3']}: {row['country']:20s} = "
                  f"{row['flag_multiplier']:.3f}x "
                  f"(score {row['flag_score_mean']:.2f})")

    print("\nFoC / distant-water / sanctions flags:")
    other_iso3 = {"PAN", "LBR", "MHL", "IRN", "RUS", "PRK",
                  "HND", "BLZ", "KHM", "COM", "CHN", "JPN", "KOR"}
    for _, row in country_scores.iterrows():
        if row["iso3"] in other_iso3:
            print(f"  {row['iso3']}: {row['country']:20s} = "
                  f"{row['flag_multiplier']:.3f}x "
                  f"(score {row['flag_score_mean']:.2f})")


if __name__ == "__main__":
    import sys
    in_path = sys.argv[1] if len(sys.argv) > 1 else \
        "data/raw/iuu_fishing_index_2019-2025_indicator_scores.csv"
    out_path = sys.argv[2] if len(sys.argv) > 2 else \
        "data/iuu_risk_index_flags.csv"
    main(in_path, out_path)
