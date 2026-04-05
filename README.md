# Med Vessel Behaviour Monitor

![Med Vessel Behaviour Monitor](https://raw.githubusercontent.com/emantzoo/emantzoo.github.io/master/images/med-vessel.jpg)


**Behavioral risk intelligence dashboard for the Mediterranean Sea.**

Live app: [med-vessel-behaviour-monitor.streamlit.app](https://med-vessel-behaviour-monitor-ysq4ipavn5jwnuragca3by.streamlit.app/)

## What it does

Ingests AIS gap, encounter and loitering events from the [Global Fishing Watch Events API](https://globalfishingwatch.org/our-apis/) and scores each event using a risk model aligned with GFW's published transshipment detection methodology.

Events are spatially linked to the EU JRC Fisheries Dependent Information (FDI) spatial dataset, providing fisheries context for each event — whether it occurred in a known fishing ground, what species are typically caught there, and what effort levels are normal.

Vessels are cross-referenced against the Combined IUU Vessel List (13 RFMOs), with two-tier alerting for vessels listed by GFCM for Mediterranean IUU activity versus those listed by other RFMOs operating in the Med. ICCAT-authorized vessels (Med swordfish, albacore, bluefin tuna, carriers) are also flagged — authorization provides access, cover, and infrastructure that makes suspicious behaviour more operationally plausible.

This cross-referencing of observed vessel behaviour against officially compiled fisheries data, regulatory IUU records, and ICCAT authorization lists is the core analytical value of the tool — turning raw AIS events into contextualised maritime intelligence.

12 analytical tabs expose patterns from daily risk trends to encounter proximity analysis, gap speed profiling, and fisheries context mapping. An embedded AI Maritime Analyst (Gemini 2.5 Flash) answers natural-language questions with executable code across all data sources.

## Data Sources

### GFW Events API (vessel behaviour)

Near real-time AIS-derived behavioural events filtered to the Mediterranean via GeoJSON polygon:

- **GAP** events — AIS disabling (vessel goes dark)
- **ENCOUNTER** events — vessel-to-vessel meetings (potential transshipment)
- **LOITERING** events — carrier vessels waiting (potential staging)

Rich nested fields extracted: encounter proximity/speed, gap speed profiles, shore/port distances, EEZ, vessel identity.

### EU JRC FDI Spatial Data (fisheries baseline)

Officially compiled fishing effort and landings from EU Member States under the Data Collection Framework (DCF), reviewed by STECF Expert Working Groups:

- **Effort**: fishing days per 0.5x0.5 degree c-square, by quarter, gear type, vessel length, and metier
- **Landings**: weight (tonnes) and value (euros) per c-square, by species
- Coverage: Mediterranean, 2017–2024
- Source: JRC Data Catalogue ([2025 FDI spatial data](https://data.jrc.ec.europa.eu/dataset/f847528b-1734-4bb8-8361-f4877ba395ed))

### Combined IUU Vessel List (regulatory records)

Consolidated list of vessels identified as engaged in IUU fishing, maintained by TMT and merging lists from all 13 Regional Fisheries Management Organisations:

- 369 vessels (213 currently listed, 156 delisted)
- 150 vessels with GFCM listings (Mediterranean-specific IUU activity)
- 64 vessels with MMSI numbers for direct AIS matching
- Fields: vessel name (including previous names), IMO, MMSI, flag, vessel type, owner/operator, listing reason per RFMO
- Source: [Combined IUU Vessel List](https://iuu-vessels.org/) (TMT / iuu-vessels.org)

### ICCAT Record of Vessels (authorization records)

The ICCAT Record of Vessels lists all vessels authorized to fish ICCAT-managed species. Med-relevant authorizations filtered from the full registry:

- 9,203 vessels authorized for Mediterranean fisheries
- Authorization types: SWO-Med (swordfish), ALB-Med (albacore), BFT-Catching (bluefin tuna), BFT-Other (support vessels), Carrier (transshipment)
- 786 vessels with IMO numbers for identity matching
- Source: [ICCAT Record of Vessels](https://www.iccat.int/en/vesselsrecord.asp)

### Data source complementarity

Neither source is ground truth. GFW infers fishing activity from vessel movement patterns. FDI provides statistically processed estimates compiled from logbooks, sales notes, and sampling programmes. The IUU vessel list reflects regulatory enforcement actions. The ICCAT authorization list identifies vessels with legitimate access to high-value fisheries. Discrepancies between these independent sources are where the analytical value lies — they may indicate unreported fishing, misreported catches, identity manipulation, unauthorized fishing, or data gaps.

## GFW Methodology Alignment

The risk scoring replicates the criteria from Global Fishing Watch's transshipment detection research (Miller et al. 2018, *The Global View of Transshipment*):

| GFW Criterion | How We Apply It |
|---------------|-----------------|
| Encounter: two vessels < 500m | Proximity factor: < 500m = 1.8x risk weight |
| Duration >= 2 hours | Default filter at 2h (configurable via sidebar slider) |
| Median speed < 2 knots | Speed factor: < 2kn = 1.5x (encounters), 1.4x (loitering) |
| >= 10km from anchorage | Shore distance factor: > 10km = 1.2x, > 20nm = 1.5x |
| Likely transshipment = reefer + fishing vessel | Vessel type factor: carrier/tanker = 1.4x in encounters |
| Potential transshipment = reefer loiters alone | Carrier/tanker loitering = 1.6x (AIS-off fishing vessel indicator) |
| AIS gaps near encounters | Gap speed-change factor: large delta = evasion indicator |

### Risk Score Formula

```
risk = (duration_h ^ 0.75) x event_weight x flag_multiplier x shore_factor x event_factors x iuu_multiplier x iccat_multiplier
```

- **Event weights**: ENCOUNTER=5.0, GAP=3.2, LOITERING=2.0
- **Flag multipliers**: RUS=2.8, IRN=2.4, PRK=3.0, SYR=2.0, FOC flags=1.2-1.3
- **Shore distance**: >20nm=1.5x, >10km=1.2x, <10km=0.8x
- **Encounter factors**: proximity + speed + vessel type
- **Loitering factors**: vessel type + average speed
- **Gap factors**: speed change before/after AIS disabling
- **IUU multiplier**: GFCM-listed=3.0x, other RFMO-listed=2.0x
- **ICCAT multiplier**: Carrier=1.4x, BFT-Catching/Other=1.3x, SWO-Med/ALB-Med=1.2x

## FDI Integration

Each GFW event is mapped to its 0.5x0.5 degree c-square cell, enabling a spatial join to the FDI baseline. This provides fisheries context for every behavioural event:

| Context Layer | What It Shows |
|---------------|---------------|
| Known fishing ground | Whether the c-square has historically reported fishing effort |
| Effort baseline | Total fishing days by gear type and quarter |
| Species composition | What species are typically landed in that area |
| Economic value | Landings value in euros — high-value areas increase transshipment risk |
| Seasonal patterns | Whether events align with normal fishing seasons |

The FDI data is a historical baseline (latest: 2024), not a real-time feed. It contextualises live events rather than providing direct compliance verification.

## IUU Vessel List Cross-Reference

GFW event vessels are matched against the Combined IUU Vessel List using three methods in priority order:

| Match Method | Reliability | Coverage |
|---|---|---|
| MMSI exact match | High — direct AIS identifier | 64 IUU vessels have MMSI |
| IMO exact match | High — permanent hull identifier | 168 IUU vessels have IMO |
| Vessel name exact match | Medium — names can change | All 369 vessels |
| Vessel name substring match | Lower — risk of false positives | All known previous names |

Two-tier alerting:

- **Tier 1 — GFCM (Med)**: vessel confirmed to have carried out IUU fishing in Mediterranean/Black Sea waters. Risk multiplier: 3.0x
- **Tier 2 — Other RFMO**: vessel IUU-listed by another RFMO (ICCAT, IOTC, etc.) detected operating in Mediterranean waters. Risk multiplier: 2.0x

IUU-matched events are highlighted with distinct markers on the map and surfaced in a prominent alert section.

## ICCAT Authorized Vessel Cross-Reference

GFW event vessels are matched against the ICCAT Record of Vessels authorized for Mediterranean fisheries. Authorization is an **opportunity indicator** — the vessel has means, access, and motive:

| Authorization | Multiplier | Rationale |
|---|---|---|
| Carrier | 1.4x | Authorized transshipment vessel in a suspicious event — core catch laundering scenario |
| BFT-Catching | 1.3x | Highest-value Med species, tightly quota-managed, strong incentive for evasion |
| BFT-Other | 1.3x | Support vessels for BFT operations — towing, transport |
| SWO-Med | 1.2x | Swordfish longliner — seasonal closures create incentive to fish outside authorized periods |
| ALB-Med | 1.2x | Albacore — lower value but still quota-managed |

Matching priority: IMO exact (where available via GFW Vessels API lookup) → vessel name exact (minimum 4 characters).

Key signals:
- ENCOUNTER + Carrier = highest concern (core transshipment scenario, verify Regional Observer Programme coverage under Rec. 24-05)
- GAP + BFT-Catching = high concern (quota evasion)
- A vessel that is BOTH IUU-listed and ICCAT-authorized is the highest-priority signal

ICCAT-authorized events are marked with blue markers on the map.

## Vessel Identity Resolution

In live mode, the app queries the GFW Vessels API to resolve MMSI → IMO numbers for each unique vessel in the event dataset. IMO numbers are permanent hull identifiers that persist across name changes, flag changes, and ownership transfers. This enables stronger matching against both the IUU vessel list (168 vessels with IMO) and ICCAT authorized list (786 vessels with IMO).

In static/demo mode, IMO numbers are pre-populated for known demo vessels. Matching falls back to MMSI and vessel name.

## Dashboard Tabs

| Tab | Analysis |
|-----|----------|
| Daily Trend | Risk score aggregated by date |
| Flag Breakdown | Total risk per flag state |
| Event Types | Risk contribution by event type |
| Duration Analysis | Duration histogram by event type |
| Geographic Risk | Risk bubble map, Med zone breakdown, EEZ analysis, port proximity |
| Risk Heatmap | Flag state vs event type matrix |
| Repeat Offenders | Vessels with multiple events, IUU and ICCAT status |
| Gap Behaviour | Speed before/after AIS disabling, gap distance vs duration |
| Encounter Analysis | Proximity vs duration, partner flag analysis, ICCAT carrier alerts |
| Top Vessels | Riskiest vessels, vessel type breakdown, IUU and ICCAT status |
| AI Analyst | Natural-language Q&A with Gemini 2.5 Flash + RAG knowledge base |
| Fisheries Context | FDI effort map, event context table, seasonal patterns, species breakdown |

## AI Maritime Analyst

The AI tab uses Google Gemini 2.5 Flash with a RAG (Retrieval-Augmented Generation) approach:

- 5 domain knowledge files (IUU context, flag risks, Med geography, methodology, FDI context)
- Live dataframe schema injected into system prompt (GFW events + FDI baseline + IUU vessel list + ICCAT authorized vessels)
- Sandboxed code execution (pandas/plotly) with safety checks
- Cross-source queries supported (e.g., "show IUU-listed vessels in c-squares with high swordfish landings")
- Example questions via dropdown

## Project Structure

```
med_ves_mntr/
├── app.py                  # Orchestrator
├── config.py               # Constants, weights, spatial helpers
├── data_loading.py         # Static, live, FDI, IUU, ICCAT data loaders
├── risk_model.py           # Risk scoring, FDI context, IUU + ICCAT matching
├── tabs.py                 # All 12 tab render functions
├── ai_analyst.py           # RAG, Gemini, sandboxed code execution
├── data/
│   ├── med_events_static.csv       # 86-row static fallback
│   ├── fdi_effort_med.csv          # Med fishing effort by c-square (JRC)
│   ├── fdi_landings_med.csv        # Med landings by c-square/species (JRC)
│   ├── iuu_vessels.csv             # Combined IUU vessel list (TMT)
│   ├── iccat_med_vessels.csv       # ICCAT Med-authorized vessels
│   ├── prepare_fdi.py              # One-time FDI preprocessing
│   ├── prepare_iuu.py              # One-time IUU list preprocessing
│   └── prepare_iccat.py            # One-time ICCAT preprocessing
├── knowledge/
│   ├── flags.md                    # Flag state risk context
│   ├── iuu_context.md              # IUU fishing context + IUU list docs
│   ├── med_geography.md            # Med zones, chokepoints, contested EEZs
│   ├── methodology.md              # GFW-aligned risk score formula
│   └── fdi_context.md              # FDI spatial data context
├── requirements.txt
├── .streamlit/
│   └── config.toml
└── README.md
```

## Stack

Python, Streamlit, Pandas, NumPy, Plotly, Folium, GFW Events API (async), Google Gemini, RAG

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

Add API keys in `.streamlit/secrets.toml`:
```toml
gfw_token = "your_gfw_jwt_token"
gemini_key = "your_gemini_api_key"
```

### FDI Data Setup

The pre-filtered Mediterranean FDI data is bundled in `data/`. To regenerate from raw JRC data:

1. Download the FDI spatial ZIP from [JRC Data Catalogue](https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/FAD/fdi/2025_FDI_spatial_data.zip)
2. Place raw CSVs in `data/raw/`
3. Run `python data/prepare_fdi.py`
4. Outputs: `data/fdi_effort_med.csv`, `data/fdi_landings_med.csv`

### IUU Vessel List Setup

The cleaned IUU vessel list is bundled in `data/`. To regenerate from the latest download:

1. Download the Combined IUU Vessel List from [iuu-vessels.org/Home/Download](https://iuu-vessels.org/Home/Download)
2. Place the Excel file in `data/raw/`
3. Run `python data/prepare_iuu.py`
4. Output: `data/iuu_vessels.csv`

### ICCAT Vessel List Setup

The cleaned ICCAT Med-authorized vessel list is bundled in `data/`. To regenerate from the latest download:

1. Export the active vessel list from [ICCAT Record of Vessels](https://www.iccat.int/en/vesselsrecord.asp)
2. Place the CSV in `data/raw/`
3. Run `python data/prepare_iccat.py --raw data/raw/<filename>.csv`
4. Output: `data/iccat_med_vessels.csv`

## Live API Field Extraction

When connected to the GFW Events API, the app extracts nested fields from the JSON response for full risk model support:

- `event_info` → encounter median distance/speed, gap distances/speeds, loitering distance/speed
- `distances` → shore distance (km), port distance (km), nearest port name
- `regions` → EEZ and Mediterranean zone classification
- `vessel` → vessel name, type, flag state

## Planned Enhancements

- **GFCM stock assessment overlay** — stock status (F/Fmsy) by GSA and species to prioritise events in areas with critically overfished stocks
- **EU sanctions vessel lists** — OFAC/EU sanctions cross-referencing for Russian/Iranian shadow fleet detection
- **Port state control inspection data** — Paris MoU / Med MoU detention history for vessel risk profiling

## References

- Miller, N.A. et al. (2018). *Identifying Global Patterns of Transshipment Behavior.* Frontiers in Marine Science.
- Global Fishing Watch. (2017). *The Global View of Transshipment: Revised Preliminary Findings.*
- Global Fishing Watch. [Vessel encounter events documentation.](https://globalfishingwatch.org/faqs/what-is-a-vessel-encounter/)
- European Commission, Joint Research Centre (2026). *2025 - Fisheries landings & effort: data by c-square. Data up to 2024.* [doi:10.2905/f847528b-1734-4bb8-8361-f4877ba395ed](https://data.jrc.ec.europa.eu/dataset/f847528b-1734-4bb8-8361-f4877ba395ed)
- Maina, I. et al. (2026). *tools4MCDA: An R-Package to estimate spatial fishing effort.* Ecological Modelling 516, 111541. [doi:10.1016/j.ecolmodel.2026.111541](https://doi.org/10.1016/j.ecolmodel.2026.111541)
- Combined IUU Vessel List. TMT. [iuu-vessels.org](https://iuu-vessels.org/)
- EU IUU Regulation: Council Regulation (EC) No 1005/2008.
- GFCM Recommendation GFCM/33/2009/8 on IUU vessel lists.
- ICCAT Record of Vessels. [iccat.int/en/vesselsrecord.asp](https://www.iccat.int/en/vesselsrecord.asp)
- ICCAT Recommendation 24-05 on bluefin tuna in the eastern Atlantic and Mediterranean.
