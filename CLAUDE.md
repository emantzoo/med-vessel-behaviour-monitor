# CLAUDE.md — Med Vessel Behaviour Monitor

## Project Overview

Mediterranean vessel behaviour risk intelligence dashboard. Ingests AIS events from GFW, cross-references against FDI fisheries data, IUU vessel lists, and ICCAT authorized vessels. Streamlit web app with 12 analytical tabs and an AI analyst.

## Architecture

6-module Streamlit app:

- `app.py` — orchestrator (~150 lines). Loads data, applies filters, runs risk scoring and vessel matching, renders map and dispatches to tabs.
- `config.py` — constants (event weights, flag risks, IUU/ICCAT multipliers, species names, forbidden code list) and pure utility functions (`classify_med_zone`, `assign_csquare`).
- `data_loading.py` — all data loaders with `@st.cache_data`: static CSV, GFW Events API (async), FDI effort/landings, IUU vessels, ICCAT vessels, GFW Vessels API (IMO lookup).
- `risk_model.py` — `compute_risk_score()`, `get_fdi_context()`, IUU matching (`check_iuu_match`, `match_iuu_vessels`), ICCAT matching (`check_iccat_match`, `match_iccat_vessels`).
- `tabs.py` — 12 render functions, one per tab. Each receives `df_filtered` and supplementary data as params. All Plotly/Streamlit rendering.
- `ai_analyst.py` — Gemini 2.5 Flash integration with RAG knowledge base, sandboxed code execution, system prompt builder.

## Data Flow

```
GFW Events API (live) or static CSV
    → filter by date range + min duration
    → compute_risk_score() per row
    → assign_csquare() for FDI spatial join
    → lookup_vessel_imos() via GFW Vessels API (live mode only)
    → match_iuu_vessels() — MMSI → IMO → name exact → name fuzzy
    → match_iccat_vessels() — IMO → name exact
    → df_filtered with risk_score + FDI context + IUU/ICCAT flags
    → Folium map + 12 Plotly tabs + AI analyst
```

## Data Sources (4)

1. **GFW Events API** — AIS gap, encounter, loitering events. Auth: JWT token in `.streamlit/secrets.toml` or sidebar input. Async via `gfwapiclient`. Med polygon filter: `[[-6,30],[36.5,30],[36.5,46],[-6,46]]`. Limit 5000 per query.
2. **EU JRC FDI spatial data** — fishing effort (days) and landings (weight/value) by 0.5x0.5 dd c-square, quarter, gear, species. Pre-filtered to Med (supra_region MBS, 2017-2024). Files: `data/fdi_effort_med.csv`, `data/fdi_landings_med.csv`.
3. **Combined IUU Vessel List** — 369 vessels from 13 RFMOs. 64 with MMSI, 168 with IMO. Two-tier alerting: GFCM-listed (3.0x) vs other RFMO (2.0x). File: `data/iuu_vessels.csv`.
4. **ICCAT Record of Vessels** — 9,203 Med-authorized vessels. Authorization types: SWO-Med, ALB-Med, BFT-Catching, BFT-Other, Carrier. 786 with IMO. Risk multipliers: Carrier=1.4x, BFT=1.3x, SWO/ALB=1.2x. File: `data/iccat_med_vessels.csv`.

## Risk Score Formula

```
risk = (duration_h ^ 0.75) x event_weight x flag_multiplier x shore_factor x event_factors x iuu_multiplier x iccat_multiplier
```

All multipliers compound. IUU matching runs before ICCAT matching. A vessel can be both IUU-listed and ICCAT-authorized (highest priority signal).

## Vessel Identity Matching

Priority chain for both IUU and ICCAT:
1. **MMSI exact** (IUU only — ICCAT has no MMSI) — confidence: high
2. **IMO exact** — confidence: high. IMO resolved via GFW Vessels API in live mode, pre-populated in static mode.
3. **Name exact** — confidence: medium. Uppercase comparison, min 4 chars for ICCAT.
4. **Name fuzzy/substring** (IUU only) — confidence: low for short names.

ICCAT IntRegNo has trailing `.0` (e.g., "9063665.0") — must strip before IMO comparison.

## Map Markers

- Default colors: GAP=red, LOITERING=orange, ENCOUNTER=purple
- IUU-matched: black marker (overrides default)
- ICCAT-authorized: blue outline
- Both IUU + ICCAT: black marker (IUU takes priority), popup notes both

## Key Files

| File | Rows | Description |
|------|------|-------------|
| `data/med_events_static.csv` | 86 | Static fallback: 80 synthetic + 3 IUU demo + 3 ICCAT demo. Has `imo` column. |
| `data/fdi_effort_med.csv` | ~83K | Med fishing effort by c-square/year/quarter/gear |
| `data/fdi_landings_med.csv` | ~212K | Med landings by c-square/year/quarter/species |
| `data/iuu_vessels.csv` | 369 | Combined IUU list. Columns: CurrentlyListed, Name, IMO, MMSI, Flag, is_gfcm, all_names, listing_rfmos |
| `data/iccat_med_vessels.csv` | ~9,203 | ICCAT Med-authorized. Columns: VesselName, IntRegNo, IRNoTypeCode, FlagRepCode, med_authorizations, iccat_risk_tier |
| `knowledge/*.md` | 5 files | RAG knowledge base: flags, iuu_context, med_geography, methodology, fdi_context |

## Preprocessing Scripts

In `data/` directory. Run once, commit outputs:
- `prepare_fdi.py` — filters raw JRC FDI ZIP to Med
- `prepare_iuu.py` — cleans Combined IUU Vessel List Excel
- `prepare_iccat.py` — filters ICCAT vessel export to Med authorizations

Raw source files go in `data/raw/` (gitignored).

## Secrets

`.streamlit/secrets.toml` (not in repo):
```toml
gfw_token = "GFW JWT token"
gemini_key = "Google Gemini API key"
```

Both have sidebar text input fallbacks if secrets file is missing.

## Dependencies

```
streamlit>=1.30
pandas>=2.0
numpy>=1.24
folium>=0.15
streamlit-folium>=0.18
plotly>=5.18
gfw-api-python-client>=1.0
google-genai>=1.0
```

## Conventions

- No icons or emojis in UI
- All data loading functions use `@st.cache_data`
- Tab render functions follow pattern: `render_<tab_name>(df_filtered, **supplementary_data)`
- Risk multipliers defined in `config.py`, not hardcoded in logic
- Species codes use FAO 3-letter system (HKE, BFT, SWO etc.), mapped via `SPECIES_NAMES` dict
- Geographic classification via `classify_med_zone(lon, lat)` — simple longitude-band partitioning
- C-square assignment via `assign_csquare(lat, lon)` — maps point to 0.5x0.5 dd FDI grid cell
- AI analyst code execution is sandboxed: only pandas, numpy, plotly in exec namespace. `FORBIDDEN_CODE` list blocks filesystem/network access.

## Testing

- Syntax check: `python -c "import py_compile; py_compile.compile('<file>.py', doraise=True)"`
- Static mode works without any API keys — uses bundled CSV with 86 demo events
- Demo data includes 3 IUU vessels (KOOSHA 4, ACROS NO. 2, DEYAR 2) and 3 ICCAT vessels (FRIO NARUTO, LEONARDO PADRE, PEDRO Y BEATRIZ)
- Verify: IUU matches show black markers + alert box, ICCAT matches show blue markers + authorization labels

## Common Tasks

**Add a new data source:** Add loader in `data_loading.py`, matching logic in `risk_model.py`, multiplier constants in `config.py`, orchestration in `app.py`, display in relevant `tabs.py` functions, context in `ai_analyst.py` system prompt, documentation in `knowledge/iuu_context.md`.

**Add a new tab:** Add render function in `tabs.py`, add to `st.tabs()` list in `app.py`.

**Update risk model:** Modify `compute_risk_score()` in `risk_model.py`. All weights/multipliers come from `config.py`.

**Update static demo data:** Edit `data/med_events_static.csv`. Ensure new rows have all required columns including `imo`.

**Refresh external data:** Run the relevant `data/prepare_*.py` script with updated raw files in `data/raw/`.
