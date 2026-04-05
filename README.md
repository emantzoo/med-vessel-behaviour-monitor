# Med Vessel Behaviour Monitor

**Behavioral risk intelligence dashboard for the Mediterranean Sea.**

Live app: [med-vessel-behaviour-monitor.streamlit.app](https://med-vessel-behaviour-monitor-ysq4ipavn5jwnuragca3by.streamlit.app/)

## What it does

Ingests AIS gap, encounter and loitering events from the [Global Fishing Watch Events API](https://globalfishingwatch.org/our-apis/) and scores each event using a risk model aligned with GFW's published transshipment detection methodology.

Events are spatially linked to the EU JRC Fisheries Dependent Information (FDI) spatial dataset, providing fisheries context for each event — whether it occurred in a known fishing ground, what species are typically caught there, and what effort levels are normal. This cross-referencing of observed vessel behaviour against officially compiled fisheries data is the core analytical value of the tool.

12 analytical tabs expose patterns from daily risk trends to encounter proximity analysis, gap speed profiling, and fisheries context mapping. An embedded AI Maritime Analyst (Gemini 2.5 Flash) answers natural-language questions with executable code across both GFW and FDI data.

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

Neither source is ground truth. GFW infers fishing activity from vessel movement patterns. FDI provides statistically processed estimates compiled from logbooks, sales notes, and sampling programmes. Discrepancies between the two may indicate unreported fishing, misreported catches, or data gaps in either system.

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
risk = (duration_h ^ 0.75) x event_weight x flag_multiplier x shore_factor x event_factors
```

- **Event weights**: ENCOUNTER=5.0, GAP=3.2, LOITERING=2.0
- **Flag multipliers**: RUS=2.8, IRN=2.4, PRK=3.0, SYR=2.0, FOC flags=1.2-1.3
- **Shore distance**: >20nm=1.5x, >10km=1.2x, <10km=0.8x
- **Encounter factors**: proximity + speed + vessel type
- **Loitering factors**: vessel type + average speed
- **Gap factors**: speed change before/after AIS disabling

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

## Dashboard Tabs

| Tab | Analysis |
|-----|----------|
| Daily Trend | Risk score aggregated by date |
| Flag Breakdown | Total risk per flag state |
| Event Types | Risk contribution by event type |
| Duration Analysis | Duration histogram by event type |
| Geographic Risk | Risk bubble map, Med zone breakdown, EEZ analysis, port proximity |
| Risk Heatmap | Flag state vs event type matrix |
| Repeat Offenders | Vessels with multiple events |
| Gap Behaviour | Speed before/after AIS disabling, gap distance vs duration |
| Encounter Analysis | Proximity vs duration, partner flag analysis |
| Top Vessels | Riskiest vessels, vessel type breakdown |
| Fisheries Context | FDI effort map, event context table, seasonal patterns, species breakdown |
| AI Analyst | Natural-language Q&A with Gemini 2.5 Flash + RAG knowledge base |

## AI Maritime Analyst

The AI tab uses Google Gemini 2.5 Flash with a RAG (Retrieval-Augmented Generation) approach:

- 5 domain knowledge files (IUU context, flag risks, Med geography, methodology, FDI context)
- Live dataframe schema injected into system prompt (GFW events + FDI baseline)
- Sandboxed code execution (pandas/plotly) with safety checks
- Cross-source queries supported (e.g., "show events in c-squares with high hake landings")
- Example questions via dropdown

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

## Live API Field Extraction

When connected to the GFW Events API, the app extracts nested fields from the JSON response for full risk model support:

- `event_info` → encounter median distance/speed, gap distances/speeds, loitering distance/speed
- `distances` → shore distance (km), port distance (km), nearest port name
- `regions` → EEZ and Mediterranean zone classification
- `vessel` → vessel name, type, flag state

## References

- Miller, N.A. et al. (2018). *Identifying Global Patterns of Transshipment Behavior.* Frontiers in Marine Science.
- Global Fishing Watch. (2017). *The Global View of Transshipment: Revised Preliminary Findings.*
- Global Fishing Watch. [Vessel encounter events documentation.](https://globalfishingwatch.org/faqs/what-is-a-vessel-encounter/)
- European Commission, Joint Research Centre (2026). *2025 - Fisheries landings & effort: data by c-square. Data up to 2024.* [doi:10.2905/f847528b-1734-4bb8-8361-f4877ba395ed](https://data.jrc.ec.europa.eu/dataset/f847528b-1734-4bb8-8361-f4877ba395ed)
- Maina, I. et al. (2026). *tools4MCDA: An R-Package to estimate spatial fishing effort.* Ecological Modelling 516, 111541. [doi:10.1016/j.ecolmodel.2026.111541](https://doi.org/10.1016/j.ecolmodel.2026.111541)
