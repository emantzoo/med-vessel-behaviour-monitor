# Med Vessel Behaviour Monitor

![Med Vessel Behaviour Monitor](https://raw.githubusercontent.com/emantzoo/emantzoo.github.io/master/images/med-vessel.jpg)

Mediterranean vessel behaviour risk intelligence dashboard. Ingests AIS events from Global Fishing Watch, cross-references against EU fisheries data, IUU vessel lists, ICCAT authorised vessels, and OFAC SDN sanctions, and produces compounding behavioural risk scores for individual vessels operating in the Mediterranean.

Built as a portfolio demonstration of IUU fishing risk analysis methodology, aligned with Global Fishing Watch transshipment detection (Miller et al. 2018) and Kpler's six-layer Risk & Compliance framework applied to fisheries.

Live app: [med-vessel-behaviour-monitor.streamlit.app](https://med-vessel-behaviour-monitor-ysq4ipavn5jwnuragca3by.streamlit.app/)

---

## What it does

- Pulls AIS gap, encounter, and loitering events from the Global Fishing Watch Events API
- Scores each event with a multiplicative risk formula weighted by duration, event type, flag state, shore distance, and event-specific factors (proximity, speed, vessel type)
- Cross-references vessels against five independent reference sources with distinct epistemological status:
  - GFW Events API (observed AIS behavioural inference)
  - EU JRC FDI spatial data (statistical fishing effort estimates by c-square)
  - TMT Combined IUU Vessel List (enforcement actions from 13 RFMOs)
  - ICCAT Record of Vessels (Med-authorised vessels)
  - OFAC SDN list (US Treasury sanctions screening)
- Applies compounding multipliers at the event level: IUU listing, ICCAT authorisation (as opportunity indicator), OFAC sanctions, flag risk
- Classifies final scores into Kpler-aligned risk bands: Low, Emerging, Elevated, Severe, Critical
- Aggregates events to vessel level with base vs compounded score decomposition
- Visualises results across six tabs including a structured vessel investigation report and an LLM-based analyst interface

---

## Risk scoring model

The base behavioural score is computed per event:

```
base = (duration_h ^ 0.75) x event_weight x flag_multiplier x shore_factor
     x event_specific_factors
```

Event-specific factors depend on event type:
- **Encounters**: proximity (median distance), speed, transshipment vessel type
- **Loitering**: transshipment vessel type, average speed
- **Gaps**: speed change across the gap (evasion proxy)

After base scoring, three lookup-based multipliers apply at the event level:

```
final_score = base x iuu_multiplier x iccat_multiplier x ofac_multiplier
```

**Critical design principle**: all lookup multipliers amplify existing behavioural signal; they never substitute for it. A vessel with no suspicious behaviour carries no score regardless of authorisation or listing status. ICCAT authorisation indicates *opportunity* (access to high-value species or transshipment capability), not exoneration, and only modifies risk when behavioural signal is already present.

Final scores are classified into bands aligned with Kpler's R&C vocabulary (*Turning Tides: Maritime Risk and Compliance Insights 2025-2026*, Dec 2025):

| Band | Score range | Meaning |
|---|---|---|
| Low | <50 | Sparse risk signals |
| Emerging | 50-59 | First risk flags |
| Elevated | 60-79 | Multiple risk indicators |
| Severe | 80-99 | Compounding risk |
| Critical | >=100 | Threshold breach |

The `base_risk_score` column preserves the pre-multiplier behavioural score, enabling explicit decomposition of how much of a vessel's risk comes from behaviour versus structural amplifiers.

Methodology aligned with GFW transshipment detection (Miller et al. 2018): encounters defined as <500m, >=2h, <2kn, >=10km from shore.

---

## Architecture

Eight-module Streamlit application:

| Module | Responsibility |
|---|---|
| `app.py` | Orchestrator. Loads data, applies filters, runs scoring pipeline, renders Folium map, dispatches to six tabs. |
| `config.py` | Constants (event weights, flag risks, IUU/ICCAT/OFAC multipliers, risk bands, species names, sandbox forbidden code list) and pure utility functions (`classify_med_zone`, `assign_csquare`, `classify_risk_band`). |
| `data_loading.py` | All data loaders with `@st.cache_data`: static CSV, GFW Events API (async), FDI effort/landings, IUU vessels, ICCAT vessels, OFAC SDN, GFW Vessels API (IMO lookup). |
| `risk_model.py` | `compute_risk_score()`, `get_fdi_context()`, IUU matching, ICCAT matching, OFAC matching. |
| `tabs.py` | Render functions for each top-level tab and expander section, including `render_vessel_summary` (Kpler-vocabulary aggregation) and `render_daily_trend` (daily + monthly multi-behaviour trend). |
| `ai_analyst.py` | Google Gemini 2.5 Flash integration with RAG knowledge base, sandboxed pandas/plotly code execution, system prompt builder. |
| `investigation.py` | Deterministic rule-based vessel investigation (no LLM) -- structured multi-section report used by the Vessel Investigation tab. |
| `risk_tree.py` | Med IUU Risk Tree framework loaded from `data/risk_tree_framework.yaml` and rendered as a Graphviz diagram. |

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
12. Render           Folium map + 6 tabs (with expanders) + AI analyst
```

## Tab structure

Six top-level tabs, organised for a tight 30-minute demo:

1. **Map & Overview** -- Folium map, risk heatmap, daily and monthly event-type trend. Secondary charts (flag breakdown, event types pie, duration distribution) in collapsed expanders.
2. **Vessel Summary** -- vessel-level aggregation table with risk bands and base vs compounded score decomposition. The Kpler-vocabulary tab. Secondary views (top vessels legacy, repeat offenders, encounter/carrier alerts, AIS gap behaviour) in collapsed expanders.
3. **Fisheries Context** -- FDI overlay, c-square context, species landings. Geographic risk breakdown in an expander.
4. **Vessel Investigation** -- three-layer deep dive: framework methodology, structured narrative from `investigation.py`, per-vessel coloured risk tree path.
5. **Risk Tree Framework** -- methodology visualisation from `data/risk_tree_framework.yaml`. Direct conceptual link to Kpler's April 2026 shadow fleet risk tree blog post.
6. **AI Analyst** -- Google Gemini 2.5 Flash interface with RAG knowledge base and sandboxed pandas/plotly code execution.

Secondary diagnostic charts live inside collapsed `st.expander` blocks within their parent tabs, keeping the main navigation clean while preserving full analytical depth for follow-up questions.

---

## Data sources

| Source | Content | Scale |
|---|---|---|
| GFW Events API | AIS gap, encounter, loitering events | Med polygon, up to 5000/query |
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

Static demo mode (88 pre-generated events including IUU, ICCAT and OFAC demo vessels) runs without any API credentials. Live mode requires a GFW API JWT token, which can be placed in `.streamlit/secrets.toml` or entered via the sidebar.

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
- 88 static demo events including 3 IUU, 3 ICCAT and 2 OFAC demo vessels
- Med polygon: `[[-6, 30], [36.5, 30], [36.5, 46], [-6, 46]]`
- FDI c-square grid: 0.5 deg x 0.5 deg

---

## Methodology references

- Miller, N.A. et al. (2018). *Identifying Global Patterns of Transshipment Behavior.* Frontiers in Marine Science.
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
