# Med Vessel Behaviour Monitor

**Behavioral risk intelligence dashboard for the Mediterranean Sea.**

Live app: [med-vessel-behaviour-monitor.streamlit.app](https://med-vessel-behaviour-monitor-ysq4ipavn5jwnuragca3by.streamlit.app/)

## What it does

Ingests AIS gap, encounter and loitering events from the [Global Fishing Watch Events API](https://globalfishingwatch.org/our-apis/) and scores each event using a risk model aligned with GFW's published transshipment detection methodology.

11 analytical tabs expose patterns from daily risk trends to encounter proximity analysis and gap speed profiling. An embedded AI Maritime Analyst (Gemini 2.5 Flash) answers natural-language questions with executable code.

## GFW Methodology Alignment

The risk scoring replicates the criteria from Global Fishing Watch's transshipment detection research (Miller et al. 2018, *The Global View of Transshipment*):

| GFW Criterion | How We Apply It |
|---------------|-----------------|
| Encounter: two vessels < 500m | Proximity factor: < 500m = 1.8x risk weight |
| Duration >= 2 hours | Configurable minimum duration filter (sidebar) |
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
| AI Analyst | Natural-language Q&A with Gemini 2.5 Flash + RAG knowledge base |

## AI Maritime Analyst

The AI tab uses Google Gemini 2.5 Flash with a RAG (Retrieval-Augmented Generation) approach:

- 4 domain knowledge files (IUU context, flag risks, Med geography, methodology)
- Live dataframe schema injected into system prompt
- Sandboxed code execution (pandas/plotly) with safety checks
- Example questions via dropdown

## Data

- **Live**: GFW Events API (gaps, encounters, loitering) filtered to Mediterranean via GeoJSON polygon
- **Static fallback**: 80-event synthetic dataset with 23 columns, seeded for reproducibility
- Rich fields: vessel name/type, distances, gap speed profiles, encounter proximity, EEZ, nearest port

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

## References

- Miller, N.A. et al. (2018). *Identifying Global Patterns of Transshipment Behavior.* Frontiers in Marine Science.
- Global Fishing Watch. (2017). *The Global View of Transshipment: Revised Preliminary Findings.*
- Global Fishing Watch. [Vessel encounter events documentation.](https://globalfishingwatch.org/faqs/what-is-a-vessel-encounter/)
