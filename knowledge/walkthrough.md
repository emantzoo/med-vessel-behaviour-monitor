# Med Vessel Behaviour Monitor — Tab Walkthrough

A complete guide to every tab, chart, table, and interaction in the dashboard. For the scoring formula and column glossary see [`methodology.md`](methodology.md) and [`vessel_intelligence_layers.md`](vessel_intelligence_layers.md).

---

## Above the tabs: Map, Metrics & Alerts

These elements sit above the four tabs because they carry the highest-priority signals and should never be hidden.

### Behavioral Risk Map (left column)

**What it shows:** An interactive Folium map of all filtered GFW behavioural events in the Mediterranean.

**Data:** `df_filtered` — scored GFW events (AIS gaps, encounters, loitering) + FDI fishing effort choropleth overlay (optional, toggle in sidebar).

**Visual encoding (triple):**
- **Shape** = behaviour type: circle (AIS gap), square (loitering), triangle (encounter)
- **Fill colour** = listing status, priority order: OFAC dark red (#8B0000) > IUU black > ICCAT blue > clean (coloured by risk band). Low-band events excluded from map.
- **Size** = risk band: Low (5 px) → Emerging (6 px) → Elevated (7 px) → Severe (9 px) → Critical (11 px)
- **Dashed amber outline** = dark port call candidate (loitering within 10 km of shore)

**FDI choropleth layer (toggleable):** All Mediterranean 0.5-degree c-squares coloured by fishing days with opacity tiers — pale yellow (<50d, 0.15 opacity), orange (50–500d, 0.25), orange-red (500–2000d, 0.30), dark red (>2000d, 0.35). Coverage is fleet-wide, not limited to event proximity.

**Interactions:**
- Click a marker to see the event detail card (vessel, event type, risk score, flag, duration, date, listing status, FDI context, external lookup links).
- Clicking a marker also pre-selects that vessel for the Vessel Investigation tab and filters the map to that vessel's events.
- Use the layer control (top-right) to toggle IUU-Listed / OFAC Sanctioned / FDI Fishing Effort layers.
- When a vessel is focused (via row click, marker click, or Investigation dropdown), the map auto-zooms to fit that vessel's events. Use the "Clear map filter" button to return to the full fleet view.

**Scope note:** The map responds to both pill filters (event type, risk band, flag, vessel class) and vessel-level focus (marker click, quick-select row click, investigation dropdown). Pill filter state is read from session state before the map renders, so changing a pill in Fleet Analytics updates the map, the metrics column, and the subtabs on the next rerun. When pills are active, fleet metrics show the pill-filtered count as primary with "of N total" context (e.g., "12 of 38"). Alert boxes always show the full sidebar-filtered dataset.

**Performance note:** FDI choropleth rectangles and FDI context lookups are cached across reruns (`@st.cache_data`), so only event markers are rebuilt when pills or vessel focus change. The `st_folium` component uses a stable `key` to avoid full unmount/remount cycles.

### Fleet Metrics (right column)

**What it shows:** Summary metrics for the filtered fleet. When pill filters are active, metrics show the pill-filtered count as primary with "of N total" context (e.g., "12 of 38" events). When no pills are active, metrics show the full sidebar-filtered dataset.

**Metrics displayed:**
- Avg Risk Score (mean risk score per event)
- Peak Risk Score (highest single-event risk score)
- Total Events (count, or "X of Y" when pills active)
- Map coverage caption (Emerging+ on map, Low-band hidden, Elevated/Severe/Critical count)
- Unique Vessels (MMSI count, or "X of Y" when pills active)
- Flags (unique flag count, or "X of Y" when pills active)
- IUU-Listed Vessels (event count where iuu_matched=True, if any)
- OFAC Sanctioned (event count where ofac_sanctioned=True, if any)
- Multi-behaviour Vessels (unique vessel count, if column present)
- Dark Port Call Candidates (event count, if events present)
- Repeat Offenders 90d (unique vessel count, if column present)

### OFAC Sanctions Alert (full width)

Red alert banner if any event involves an OFAC-sanctioned vessel. Expandable table with: vessel name, MMSI, IMO, flag, event type, duration, risk score, OFAC vessel name, sanctions program, listing date, match type, match confidence, multiplier.

### IUU Alert (full width)

Red alert banner if any event involves an IUU-listed vessel. Expandable table with: vessel name, MMSI, flag, event type, duration, risk score, IUU vessel name, listing RFMOs, match type, match confidence, multiplier.

---

## Tab 1: Vessel Investigation

**What it shows:** A per-vessel structured investigation report that walks the risk-tree framework from identity through behaviour, spatial context, structural lookups, to a final threat assessment.

**Data:** Scored GFW events for the selected vessel + IUU vessel list + ICCAT authorized vessels + OFAC SDN list + FDI fishing effort and landings (spatial join by c-square) + fishing-in-MPA events.

**Report sections (15 steps):**

1. **Identity confirmation** — vessel name, MMSI, IMO, flag, event count, profile (length/tonnage), industrial badge.
2. **IUU listing status** — colour-coded alert (red if matched, green if clean), tier (GFCM/Other), match type/confidence.
3. **ICCAT authorization status** — colour-coded alert (amber if authorized, blue if not), authorization types, risk tier.
4. **OFAC sanctions status** — colour-coded alert (red if sanctioned, green if clean), sanctions program, multiplier.
4c. **GFW Insights cross-references** (optional, live/snapshot mode only) — AIS coverage %, fishing without RFMO auth, GFW IUU listed, AIS-off events.
5. **Fisheries context** — event-level table with FDI overlay (fishing days, top species, landings value per c-square).
5b. **Fishing activity inside MPAs** — event count, total hours, highest tier, MPA name list + event detail table (display-only).
6. **Behavioural pattern** — event types, counts, average duration, gap speed analysis (intentional disabling, implied speed).
6b. **Behavioural flags** — multi-behaviour, dark port call candidates, repeat offender (display-only metrics).
7. **Risk score decomposition** — total risk, flag multiplier, compounded multiplier, max single event.
8. **Hypotheses** — prioritised findings (critical/high/info level) generated by the investigation engine.
9. **External lookups** — links to MarineTraffic, VesselFinder, Equasis.
10. **Threat assessment** — key evidence summary + recommended action.
11. **Risk tree trace** — per-vessel evaluation of all branches and leaves (expandable by branch).
12. **Cumulative risk trajectory** — line chart with band threshold lines showing behavioural arc over time.

**Quick-select table:** Expandable compact table with vessel name, flag, events, risk score, risk band, IUU, OFAC. Click a row to switch investigation and filter the map.

**Risk-tree trace** (rendered as steps 11-12 of the investigation report):
- Expandable by branch (Identity, Flag Risk, Regulatory Status, Authorization, Behavioural History, Spatial/Contextual, Network Exposure, Fishing Activity).
- Each branch shows fired/total questions, coloured severity tags, and notes.
- Interactive icicle chart (Plotly) showing the full tree hierarchy.
- Full Graphviz diagram of the tree for this vessel.

**Cumulative risk trajectory** (step 12): line chart of cumulative risk score over time with horizontal band-threshold lines (Low/Emerging/Elevated/Severe/Critical).

**Interactions:** Select a vessel from the dropdown, the quick-select table, or click a marker on the map. The dropdown is pre-populated with the highest-risk vessel.

---

## Tab 2: Fleet Analytics

### Subtab: Ranking

**What it shows:** One row per vessel, sorted by compounded risk score (highest first). Fleet-level vessel table with pill filters.

**Data:** `df_filtered` aggregated per vessel (MMSI). Each row summarises all behavioural events for that vessel and includes cross-reference results from the IUU vessel list (369 vessels from 13 RFMOs), ICCAT authorized vessel record (~9,200 Med vessels), and OFAC SDN sanctions list.

**Key columns:**
- `risk_band` — Kpler Turning Tides classification: Low (<50), Emerging (50-60), Elevated (60-80), Severe (80-100), Critical (>=100). Cell background coloured.
- `base_score_total` / `risk_score_total` / `max_event_risk` — sum of base scores, sum of compounded scores, and highest single-event score.
- `compound_multiplier` — `risk_score_total / base_score_total`. 1.0x = purely behavioural; >2x = structural lookups (IUU, ICCAT, OFAC) dominate.
- `vessel_class` — descriptive category from GFW Vessels API shiptypes (industrial_fishing / artisanal_fishing / carrier / tanker / cargo / support / passenger / other).
- `type_mismatch` — fires when event-level vessel_type and registry shiptypes map to different canonical classes (Kpler Grey Fleet "irregular vessel information" equivalent).
- Four behavioural flags: `is_industrial`, `multi_behaviour`, `dark_port_candidates`, `repeat_offender` (display-only, never scored).
- MPA intersection: `in_mpa`, `mpa_tier`, `fishing_in_mpa_events`, `fishing_in_mpa_hours`.
- Listing booleans: `iuu_matched`, `iccat_authorized`, `ofac_sanctioned`, `gfcm_registered`.

**Pill filters:** Event type, risk band, flag state, vessel class. Sit above the subtabs and cascade to all five Fleet Analytics subtabs.

**Interactions:** Use the slider to control how many vessels appear. Use pill filters to narrow the fleet view. Switch to **Vessel Investigation** tab for per-vessel drill-down.

**Collapsed expanders:**

| Expander | Chart | What it answers |
|----------|-------|-----------------|
| Risk band distribution | Bar chart of vessel count per band | What's the shape of the fleet? |
| Base vs structural-amplifier decomposition | Stacked horizontal bar (fleet total): behavioural base + IUU (black) + ICCAT (blue) + OFAC (dark red) segments | How does the scoring split between behaviour and each lookup source? |
| Top vessels: base vs structural amplifier | Top-10 horizontal bars, each split base + amplifier | Who are the worst actors and why? |

### Subtab: Exploration

**What it shows:** Behavioural deep dives — repeat offenders, encounter patterns, and AIS gap analysis.

**Data:** Same pill-filtered GFW behavioural events as the Ranking subtab.

**Collapsed expanders:**

| Expander | Chart | What it answers |
|----------|-------|-----------------|
| Repeat offenders | Bar of vessels with >=2 events + top-3 timeline | Who keeps coming back? |
| Encounter analysis -- carrier alerts | Scatter (distance vs duration) + carrier alert + flag pairings | Who's transshipping with whom? |
| AIS gap behaviour | Speed scatter or histogram + geographic scatter | Who's going dark, and how? |

---

### Subtab: Trends & Patterns

**What it shows:** Fleet-level aggregate views across all filtered vessels and events.

**Data:** `df_filtered` — scored GFW events per event.

**Always-visible charts:**

- **Risk heatmap (flag state vs event type)** — Plotly heatmap, rows = flag (sorted by total risk), columns = event type, values = summed risk score. Coloured YlOrRd. Read: bright cells = high-risk (flag, event-type) combinations.
- **Daily behavioural risk trend** — line chart of total risk per day, with IUU-event dates marked as black dashed verticals. Below it, a stacked area split by event type. Below that, monthly event counts by event type.

**Collapsed expanders:**

| Expander | Chart | What it answers |
|----------|-------|-----------------|
| Risk exposure by MPA tier | Donut (risk by MPA tier: GFCM-FRA / EU site / Other WDPA / Outside) | Where does MPA risk concentrate? |
| Fleet composition by vessel class | Donut (unique vessels per class) | What kinds of vessels are in the fleet? |
| Type mismatch by vessel class | Horizontal bar of mismatch counts by class + detail table | Whose AIS identity disagrees with their registry? |
| Flag breakdown | Horizontal bars (risk by flag) + stacked bars (by event type) + IUU/ICCAT/OFAC tables | Which flags carry the most risk? |
| Event type distribution | Pie (risk share) + summary table + band distribution table | Which event types drive risk? |
| Event duration distribution | Histogram (duration by event type) + scatter (duration vs risk) | How do event durations relate to risk? |

---

### Subtab: Fisheries Context

**What it shows:** GFW behavioural events overlaid with EU JRC FDI baseline data to assess whether events occur in known fishing grounds.

**Data:**
- `df_filtered` — scored GFW events (spatially joined via c-square)
- `fdi_effort` — `data/fdi_effort_med.csv` (~83K rows): fishing effort in days by 0.5-degree c-square, year, quarter, gear. Mediterranean (MBS supra-region), 2017-2024.
- `fdi_landings` — `data/fdi_landings_med.csv` (~212K rows): landings weight and value by c-square, year, quarter, species.

**Key insight:** Events in low-effort c-squares are the suspicious ones — they happen in waters where legitimate fishing rarely occurs.

**Sections:**
- **FDI effort vs GFW events** — scatter map with FDI effort centres (sized by fishing days) and GFW events (coloured by event type).
- **Event context table** — one row per event with fishing days, top species, landings value, context flag (known/unknown fishing ground).
- **Seasonal patterns** — bar + line chart of FDI fishing days vs GFW event count by quarter, filterable by Med zone.
- **Species context** — top 15 species by value in event c-squares, with ICCAT-managed species (SWO, BFT, ALB) highlighted.

**Collapsed expanders:**

| Expander | Chart | What it answers |
|----------|-------|-----------------|
| Geographic risk breakdown | Sub-zone risk bars + port-distance scatter | Which Mediterranean zones and port distances carry the most risk? |

---


---

### Subtab: Fishing Activity

**What it shows:** GFW-classified fishing events (`public-global-fishing-events` CNN feed) with risk signal attribution. These are actual fishing detections — separate from the behavioural gap/encounter/loitering events.

**Data:** `fishing_df` (loaded separately, never merged into `df_filtered`) cross-referenced against WDPA MPAs, FDI low-effort cells, and GFCM party flag list.

**Toggle filters (cascade to both map and table):**
- **In MPA only** — restrict to events with `in_mpa=True`
- **Non-GFCM flag** — vessels flagged to non-GFCM contracting parties
- **With behavioural** — vessels that also appear in the scored behavioural events
- **Fishing-only** — vessels in `fishing_df` not in `df_filtered` (pure fishing detections, no suspicious AIS behaviour)

**Views:**

| View | What it shows |
|---|---|
| Scatter map | Background grey dots = all fishing inside MPAs; foreground coloured shapes = events that fired risk tree leaves. Shape encodes leaf type (circle = general MPA, triangle = closed area, square = low-effort cell, diamond = no RFMO auth); colour encodes severity. |
| Fishing vessel table (expander) | One row per fishing vessel with event counts, total hours, in-MPA events, non-GFCM flag, whether the vessel also appears in the behavioural ranking. Sorted by in-MPA event count descending. |

**Static-demo caveat:** the bundled fishing dataset has ~5 fishing-in-MPA events. Switch to live GFW mode for the full picture.


## Tab 3: Reference & Methodology

**What it shows:** The scoring framework, multiplier tables, and methodology that underpin every number in the dashboard.

**Data:** Constants from `config.py` + `data/reference_content.yaml` + `data/risk_tree_framework.yaml`. No event data is used — this tab is pure methodology.

**Contents:**
- **Risk-tree framework** — interactive Graphviz diagram of the Mediterranean IUU Risk Tree with all branches and leaves.
- **Risk formula** — prose + code block: `risk = (duration_h ^ 0.75) x event_weight x flag_multiplier x shore_factor x mpa_multiplier x event_factors x iuu_multiplier x iccat_multiplier x ofac_multiplier`.
- **Scoring pipeline diagram** — end-to-end Graphviz showing data flow from GFW API to final risk band.
- **Risk band definitions** — table: band name, lower/upper bounds, meaning.
- **Multiplier tables** — flag risk, IUU listing (GFCM 3.0x / other RFMO 2.0x), ICCAT authorization (carrier 1.4x / BFT 1.3x / SWO-ALB 1.2x), OFAC sanctions (2.5x), MPA tier.
- **Framing notes** — ICCAT, MPA calibration, fishing-in-MPA, sanctions authority.
- **Data source provenance** — table with source, file path, rows, update frequency.
- **Epistemological separation** — what the app measures vs what it does not claim.
- **Methodology references** — academic and institutional citations.
- **Scope and limitations** — what the tool can and cannot do.

**When to use:** Point stakeholders here when they ask "where do these numbers come from?"

---

## Tab 4: AI Analyst

**What it shows:** An AI-powered analyst (Gemini 2.5 Flash) with sandboxed code execution that can query, filter, aggregate, and plot the dashboard data on demand.

**Data available to the analyst:**
- `df` — copy of `df_filtered` (scored GFW events with all cross-reference columns)
- `fdi_effort` — FDI fishing effort dataframe
- `fdi_landings` — FDI landings dataframe
- `iuu_vessels` — Combined IUU Vessel List
- `iccat_vessels` — ICCAT Med-authorized vessels
- `ofac_vessels` — OFAC SDN vessel list
- `fishing_df` — fishing-in-MPA events

The model operates on copies. It cannot modify the live data, read/write files, or make network calls.

**How to use:**
1. Pick an example question from the dropdown (16 pre-programmed investigation queries) or type your own.
2. Click "Ask".
3. The analyst generates pandas/plotly code, executes it in a sandbox, and renders the output (chart, table, or metric) inline.
4. The system prompt includes the full `knowledge/` directory as RAG context, so the model knows column names, multiplier tables, the scoring formula, and all methodology.

**Requires:** A Gemini API key (entered in the sidebar or via `.streamlit/secrets.toml`).

**Example questions:**
- "Which vessels had fishing activity inside a GFCM Fisheries Restricted Area?"
- "Plot the top 5 flag states by total risk."
- "Which vessels have a vessel_type_mismatch?"
- "How many industrial-class vessels had multi-behaviour flags?"

---

## Data sources summary

| Source | File / API | Rows | Used in |
|--------|-----------|------|---------|
| GFW Events API | Live or `data/med_events_static.csv` (95 demo) | Variable | All tabs |
| EU JRC FDI effort | `data/fdi_effort_med.csv` | ~83K | Fisheries Context, Map FDI layer, AI Analyst |
| EU JRC FDI landings | `data/fdi_landings_med.csv` | ~212K | Fisheries Context, AI Analyst |
| Combined IUU Vessel List | `data/iuu_vessels.csv` | 369 | Ranking, Vessel Investigation, Map, Alerts, AI Analyst |
| ICCAT Med-authorized | `data/iccat_med_vessels.csv` | ~9,200 | Ranking, Vessel Investigation, Map, AI Analyst |
| OFAC SDN vessels | `data/ofac_vessels.csv` | ~50 | Ranking, Vessel Investigation, Map, Alerts, AI Analyst |
| GFW Fishing Events | Live or `data/med_fishing_static.csv` (12 demo) | Variable | Fishing Activity, Ranking, Vessel Investigation, AI Analyst |
| WDPA MPA reference | `data/wdpa_mpa_lookup.csv` | Variable | Fishing Activity scatter map |
