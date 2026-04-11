# Med Vessel Behaviour Monitor

![Med Vessel Behaviour Monitor](https://raw.githubusercontent.com/emantzoo/emantzoo.github.io/master/images/med-vessel.jpg)

Mediterranean vessel behaviour risk intelligence dashboard. Ingests AIS events from Global Fishing Watch, cross-references against EU fisheries data, IUU vessel lists, ICCAT authorised vessels, and OFAC SDN sanctions, and produces compounding behavioural risk scores for individual vessels operating in the Mediterranean.

Built as a portfolio demonstration of IUU fishing risk analysis methodology, aligned with Global Fishing Watch transshipment detection (Miller et al. 2018) and Kpler's six-layer Risk & Compliance framework applied to fisheries.

Live app: [med-vessel-behaviour-monitor.streamlit.app](https://med-vessel-behaviour-monitor-ysq4ipavn5jwnuragca3by.streamlit.app/)

---

## What it does

- Pulls AIS gap, encounter, and loitering events from the Global Fishing Watch Events API
- Pulls a separate stream of CNN-classified fishing events from GFW (`public-global-fishing-events`, Kroodsma et al. 2018), kept out of the scored dataframe and surfaced only as a per-vessel fishing-in-MPA flag
- Scores each event with a multiplicative risk formula weighted by duration, event type, flag state, shore distance, **MPA intersection tier** (from GFW `regions.mpa`), and event-specific factors (proximity, speed, vessel type)
- Cross-references vessels against five independent reference sources with distinct epistemological status:
  - GFW Events API (observed AIS behavioural inference) — includes WDPA point-in-polygon (`regions.mpa`) and a separate fishing-events feed (Kroodsma 2018 CNN)
  - EU JRC FDI spatial data (statistical fishing effort estimates by c-square)
  - TMT Combined IUU Vessel List (enforcement actions from 13 RFMOs)
  - ICCAT Record of Vessels (Med-authorised vessels)
  - OFAC SDN list (US Treasury sanctions screening)
- Applies compounding multipliers at the event level: IUU listing, ICCAT authorisation (as opportunity indicator), OFAC sanctions, flag risk
- Classifies final scores into Kpler-aligned risk bands: Low, Emerging, Elevated, Severe, Critical
- Aggregates events to vessel level with base vs compounded score decomposition
- Computes three display-only Kpler-aligned behavioural flags at the vessel level: multi-behaviour compound indicator, dark port call candidate (loitering within 10 km of shore), and repeat-offender-within-90-days (exposure drift)
- Visualises results across six tabs including a structured vessel investigation report and an LLM-based analyst interface

---

## Risk scoring model

The base behavioural score is computed per event:

```
base = (duration_h ^ 0.75) x event_weight x flag_multiplier x shore_factor
     x mpa_multiplier x event_specific_factors
```

Event-specific factors depend on event type:
- **Encounters**: proximity (median distance), speed, transshipment vessel type
- **Loitering**: transshipment vessel type, average speed
- **Gaps**: speed change across the gap (evasion proxy)

The MPA factor is applied per event using GFW's `regions.mpa` field, which returns a pre-computed point-in-polygon intersection against the World Database on Protected Areas (WDPA). MPA matches are classified into three regulatory tiers — GFCM Fisheries Restricted Area (`gfcm_fra`, 2.0x, legally binding under Council Regulation (EC) 1967/2006), EU-designated marine site (`eu_site`, 1.5x, includes Natura 2000 marine and Pelagos Sanctuary), and general WDPA entry (`general`, 1.2x). Tier classification is by config-driven substring match on the MPA name. Empirical anchoring: Seguin et al. 2025 (*Science*) found industrial fishing in 47% of coastal MPAs, justifying MPA intersection as a high-tier risk factor; Raynor et al. 2025 (*Science*) found 9× fewer fishing vessels in fully protected MPAs, anchoring the GFCM-FRA tier as the strictest enforcement category. McDonald et al. 2024 (*Nature*) bounds the AIS-only approach as a lower-bound indicator: roughly 90% of fishing vessels inside MPAs do not broadcast AIS.

After base scoring, three lookup-based multipliers apply at the event level:

```
final_score = base x iuu_multiplier x iccat_multiplier x ofac_multiplier
```

**Critical design principle**: all lookup multipliers amplify existing behavioural signal; they never substitute for it. A vessel with no suspicious behaviour carries no score regardless of authorisation or listing status. ICCAT authorisation indicates *opportunity* (access to high-value species or transshipment capability), not exoneration, and only modifies risk when behavioural signal is already present.

Final scores are classified into bands aligned with Kpler's R&C vocabulary (*Turning Tides: Maritime Risk and Compliance Insights 2025-2026*, Dec 2025):

| Band | Score range | Meaning |
|---|---|---|
| Low | <50 | Sparse risk signals |
| Emerging | 50-60 | First risk flags |
| Elevated | 60-80 | Multiple risk indicators |
| Severe | 80-100 | Compounding risk |
| Critical | >=100 | Threshold breach |

The `base_risk_score` column preserves the pre-multiplier behavioural score, enabling explicit decomposition of how much of a vessel's risk comes from behaviour versus structural amplifiers.

In addition, three **display-only** behavioural flags are derived at the vessel level and surfaced in the Vessel Summary, Vessel Investigation, and Map & Overview tabs. They mirror three of the six core inputs in Kpler's October 2025 *Deceptive Shipping Practices* predictive model but are **not** multiplied into the risk score, because the underlying signal is already captured at the event level and double-counting would distort the score:

| Flag | Definition | Source concept |
|---|---|---|
| Multi-behaviour | Vessel shows two or more distinct event types (gap, encounter, loitering) | Kpler compound indicator |
| Dark port call candidate | LOITERING event within 10 km of shore (AIS-inferred, not satellite-verified) | Kpler dark port call |
| Repeat offender (90d) | Two or more events within any 90-day rolling window | Kpler exposure drift |

Dark port call candidates are also rendered on the Folium map with a dashed amber outline on top of the existing shape/fill/size encoding, providing a fourth orthogonal visual channel without overloading the existing colour scheme.

Methodology aligned with GFW transshipment detection (Miller et al. 2018): encounters defined as <500m, >=2h, <2kn, >=10km from shore.

---

## Architecture

Eight-module Streamlit application:

| Module | Responsibility |
|---|---|
| `app.py` | Orchestrator. Loads data, applies filters, runs scoring pipeline, renders Folium map, dispatches to six tabs. |
| `config.py` | Constants (event weights, flag risks, IUU/ICCAT/OFAC multipliers, risk bands, species names, sandbox forbidden code list) and pure utility functions (`classify_med_zone`, `assign_csquare`, `classify_risk_band`). |
| `data_loading.py` | All data loaders with `@st.cache_data`: static CSV, GFW Events API (async), FDI effort/landings, IUU vessels, ICCAT vessels, OFAC SDN, GFW Vessels API (IMO lookup). |
| `risk_model.py` | `compute_risk_score()`, `get_fdi_context()`, IUU matching, ICCAT matching, OFAC matching, `compute_vessel_flags()` (Kpler-aligned display-only flags). |
| `tabs.py` | Render functions for each top-level tab and expander section, including `render_vessel_summary` (Kpler-vocabulary aggregation) and `render_daily_trend` (daily + monthly multi-behaviour trend). |
| `ai_analyst.py` | Google Gemini 2.5 Flash integration with RAG knowledge base, sandboxed pandas/plotly code execution, system prompt builder. |
| `investigation.py` | Deterministic rule-based vessel investigation (no LLM) -- structured multi-section report used by the Vessel Investigation tab. |
| `risk_tree.py` | Two Graphviz diagram builders: `render_framework_tree()` for the Med IUU Risk Tree framework loaded from `data/risk_tree_framework.yaml`, and `render_scoring_pipeline_diagram()` for the end-to-end scoring pipeline shown in the Reference tab. |

## Data pipeline

```
1. Load data         load_live_data() or load_static_data()
2. Load reference    load_fdi_*, load_iuu_vessels, load_iccat_vessels, load_ofac_sdn
3. Filter            duration >= min_duration slider
4. Score             compute_risk_score() -> risk_score
5. Preserve base     base_risk_score = risk_score.copy()
6. Spatialise        assign_csquare() -> csq_lon, csq_lat
7. Resolve identity  lookup_vessel_imos() -> imo (live mode only)
8. IUU match         match_iuu_vessels() -> iuu_* columns, risk *= iuu_multiplier
9. ICCAT match       match_iccat_vessels() -> iccat_* columns, risk *= iccat_multiplier
10. OFAC match       match_ofac_vessels() -> ofac_* columns, risk *= ofac_multiplier
11. Classify         risk_band = classify_risk_band(risk_score)
12. Flag             compute_vessel_flags() -> multi_behaviour_flag,
                     dark_port_call_candidate, repeat_offender_90d (display-only)
13. Render           Folium map + 6 tabs (with expanders) + AI analyst
```

## Tab structure

Six top-level tabs, organised for a tight 30-minute demo (tab order as rendered in `app.py`):

1. **Vessel Investigation** -- three-layer deep dive for the selected vessel: structured narrative from `investigation.py`, per-branch expander cards over the risk tree trace, an interactive Plotly icicle (click a branch to drill in), the full Graphviz framework diagram in a collapsed expander, and a dedicated Behavioural Flags step (multi-behaviour, dark port call candidate, repeat offender 90d).
2. **Map & Overview** -- Folium map (dashed amber overlay for dark port call candidates), risk heatmap, daily and monthly event-type trend, and sidebar tiles for the three behavioural flags. Secondary charts (flag breakdown, event types, duration distribution) in collapsed expanders.
3. **Vessel Summary** -- vessel-level aggregation table with risk bands, base vs compounded score decomposition, and the three display-only behavioural flags. Click a row to pre-select that vessel in the Investigation tab. Secondary views (top vessels legacy, repeat offenders, encounter/carrier alerts, AIS gap behaviour) in collapsed expanders.
4. **Fisheries Context** -- FDI overlay, c-square context, species landings. Geographic risk breakdown in an expander.
5. **AI Analyst** -- Google Gemini 2.5 Flash interface with RAG knowledge base and sandboxed pandas/plotly code execution.
6. **Reference & Methodology** -- generic framework documentation: risk tree diagram from `data/risk_tree_framework.yaml`, risk formula, **end-to-end scoring pipeline diagram** (one AIS event to vessel-level risk band, with a dashed side-chain showing the three display-only flags), risk-band table, and per-multiplier tables (flag, IUU, ICCAT, OFAC).

Secondary diagnostic charts live inside collapsed `st.expander` blocks within their parent tabs, keeping the main navigation clean while preserving full analytical depth for follow-up questions.

---

## Data sources

| Source | Content | Scale |
|---|---|---|
| GFW Events API | AIS gap, encounter, loitering events | Med polygon, up to 5000/query |
| GFW `regions.mpa` | WDPA point-in-polygon, returned in event metadata | Global; tiered into `gfcm_fra` / `eu_site` / `general` by config substring match |
| GFW `public-global-fishing-events` | Kroodsma et al. 2018 CNN-classified fishing activity | Same Med polygon, separate dataframe; never merged into scored events. Surfaced display-only as fishing-in-MPA flag |
| EU JRC FDI | Fishing effort (days) and landings by 0.5 deg c-square | 82.8K effort rows, 212K landings rows, 1,008 unique c-squares, 2017-2024 |
| TMT Combined IUU List | 13 RFMOs, IUU-listed vessels | 369 vessels (213 currently listed, 150 GFCM-listed) |
| ICCAT Record of Vessels | Med-authorised vessels | 9,203 vessels, 786 with IMO |
| OFAC SDN | Sanctioned vessels (filtered demo snapshot) | 2 demo vessels (SABITI, ADRIAN DARYA 1); full SDN list supported via matching logic |

**Epistemological separation**: each data source answers a different question and is kept separate at the data layer. GFW provides AIS-inferred behavioural events; FDI provides aggregate statistical estimates from logbooks and sales notes; TMT provides enforcement actions; ICCAT provides authorisation as an opportunity indicator; OFAC provides formal sanctions listings. Sources are synthesised at the scoring layer with provenance preserved in the UI.

---

## Running the app

Requires Python 3.10+.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Static demo mode (94 pre-generated events across 88 vessels, including 2 IUU-listed, 6 ICCAT-authorised and 2 OFAC-sanctioned demo vessels, enriched so all three behavioural flags fire visibly) runs without any API credentials. Live mode requires a GFW API JWT token, which can be placed in `.streamlit/secrets.toml` or entered via the sidebar.

### Optional credentials

```toml
# .streamlit/secrets.toml
gfw_token = "your GFW JWT"
gemini_key = "your Google Gemini API key (for AI Analyst tab)"
```

Both have sidebar text-input fallbacks if the secrets file is missing.

---

## Key numerical values

- 7 multiplicative factors in the base risk formula
- 4 lookup-based amplifiers applied post-scoring (IUU, ICCAT, OFAC, flag)
- 5 risk bands (Low, Emerging, Elevated, Severe, Critical)
- 6 top-level tabs
- 369 IUU vessels, 9,203 ICCAT Med-authorised vessels, 1,008 FDI c-squares
- 94 static demo events across 88 unique MMSI, including 2 IUU-listed, 6 ICCAT-authorised and 2 OFAC-sanctioned demo vessels
- 3 Kpler-aligned display-only behavioural flags (multi-behaviour, dark port call candidate, repeat offender 90d)
- Med polygon: `[[-6, 30], [36.5, 30], [36.5, 46], [-6, 46]]`
- FDI c-square grid: 0.5 deg x 0.5 deg

---

## Methodology references

- Miller, N.A. et al. (2018). *Identifying Global Patterns of Transshipment Behavior.* Frontiers in Marine Science.
- Kroodsma, D.A. et al. (2018). *Tracking the global footprint of fisheries.* Science 359(6378), 904–908. [doi:10.1126/science.aao5646](https://doi.org/10.1126/science.aao5646) -- CNN-based fishing classification underlying GFW's `public-global-fishing-events` feed and the fishing-in-MPA flag.
- Seguin, R. et al. (2025). *Global patterns and drivers of untracked industrial fishing in coastal marine protected areas.* Science 389, 396–401. [doi:10.1126/science.ado9468](https://doi.org/10.1126/science.ado9468) -- 47% of coastal MPAs show industrial fishing; methodological backbone for MPA intersection.
- Raynor, J. et al. (2025). *Little-to-no industrial fishing occurs in fully and highly protected marine areas.* Science 389, 392–395. [doi:10.1126/science.adt9009](https://doi.org/10.1126/science.adt9009) -- 9× fewer fishing vessels in fully protected MPAs; anchors GFCM-FRA tier as the strictest enforcement category.
- McDonald, G.G. et al. (2024). *Satellite mapping reveals extensive industrial activity at sea.* Nature 625, 85–91. [doi:10.1038/s41586-023-06825-8](https://doi.org/10.1038/s41586-023-06825-8) -- ~75% of fishing vessels at sea and ~90% inside MPAs do not broadcast AIS; bounds AIS-based MPA intersection as a lower-bound indicator.
- Council Regulation (EC) No 1967/2006 -- Mediterranean management measures. Legal basis for GFCM Fisheries Restricted Area enforcement, underpinning the 2.0x `gfcm_fra` regulatory tier.
- Global Fishing Watch. (2017). *The Global View of Transshipment: Revised Preliminary Findings.*
- Kpler. (October 2025). *Deceptive Shipping Practices* -- compounding behavioural risk scoring.
- Kpler. (December 2025). *The Turning Tides: Maritime Risk and Compliance Insights 2025-2026* -- predictive risk bands and vessel-level aggregation.
- Kpler. (April 2026). *How to build a risk tree to assess shadow fleet exposure* -- risk tree framework.
- European Commission, Joint Research Centre (2026). *2025 - Fisheries landings & effort: data by c-square. Data up to 2024.* [doi:10.2905/f847528b-1734-4bb8-8361-f4877ba395ed](https://data.jrc.ec.europa.eu/dataset/f847528b-1734-4bb8-8361-f4877ba395ed)
- Combined IUU Vessel List. TMT. [iuu-vessels.org](https://iuu-vessels.org/)
- ICCAT Record of Vessels. [iccat.int/en/vesselsrecord.asp](https://www.iccat.int/en/vesselsrecord.asp)
- ICCAT Recommendation 24-05 on bluefin tuna in the eastern Atlantic and Mediterranean.

Conceptual alignment: the Med Vessel Monitor implements four of Kpler's six risk layers (formal listing, behavioural signals, geographic exposure, cargo-equivalent species weighting) in a fisheries context. The two layers not implemented -- associative risk and ownership opacity -- are future work that would require fleet-network and beneficial ownership data beyond the current open-source stack.

---

## Status

Portfolio demonstration project. Risk scores are methodology-driven, not empirically calibrated against IUU enforcement outcomes. Validation against RFMO listings or port state denials as proxy outcomes is named as future work.

Static demo renders without API credentials; live mode requires GFW API access.

---

## Author

Irene Mantzouni -- Fisheries Ecology PhD (Copenhagen), STECF expert, data analyst at QUANTOS S.A.
