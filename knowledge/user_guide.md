# Med Vessel Behaviour Monitor — User Guide

A short field guide to the UI tabs, what each chart shows, and how to read it. For the underlying methodology, scoring formula and column glossary see [`methodology.md`](methodology.md) and [`vessel_intelligence_layers.md`](vessel_intelligence_layers.md).

---

## The top-level tabs

The app uses four top-level tabs, ordered **investigate → fleet → explain → ask**:

1. **Vessel Investigation** — per-vessel structured report with coloured risk-tree path and quick-select table
2. **Fleet Analytics** — fleet-level aggregate views. Pill filters (event type, risk band, flag state, vessel class) sit above the subtabs and cascade to all five:
   - Subtab *Ranking*: vessel table + risk band distribution + base-vs-compound decomposition + top vessels
   - Subtab *Exploration*: repeat offenders + encounter analysis + AIS gap behaviour
   - Subtab *Trends & Patterns*: heatmaps, daily trends, MPA tier exposure, type mismatch
   - Subtab *Fisheries Context*: FDI overlay, c-square context, species landings
   - Subtab *Fishing Activity*: GFW-classified fishing events with leaf attribution scatter map + vessel table
3. **Reference & Methodology** — explain: scoring framework, multiplier tables, methodology diagram
4. **AI Analyst** — ask: Gemini 2.5 Flash sandboxed code interface

The Map and the OFAC/IUU alert boxes sit *above* the tabs because they are the highest-priority signals and should never be hidden.

---

## Data modes and sidebar controls

The sidebar offers three data modes:

- **Static demo** — bundled CSV with ~95 events across 8 demo vessels. No API key needed.
- **Live GFW** — real-time query to GFW Events API. Requires JWT token.
- **Snapshot** — download once via API, cache to CSV, reload from disk. Best for reproducible analysis. Snapshot files: `api_events_snapshot.csv`, `api_fishing_snapshot.csv`, optionally `api_insights_snapshot.csv`. Default window: 30 days.

**Sidebar toggles:**

- **Include fishing events** — enables the GFW fishing-events feed (`public-global-fishing-events`). Off by default to speed up initial load.
- **Include vessel insights** — optional: queries GFW Insights API per vessel for AIS coverage % and live IUU list cross-check. Supplementary only — all fishing, MPA, flag-RFMO, and ICCAT analysis works without this. Slow (~5-10 min). Only runs during snapshot download.
- **Min duration** slider — filters events below the threshold.

## Map

The Folium map uses FastMarkerCluster for performance (handles 5K+ events). Flagged vessels (IUU/OFAC-matched) keep individual SVG markers for visibility. Low-band (Low risk) events are excluded from the map to reduce noise.

**Marker priority:** OFAC dark red > IUU black > event type default (GAP=red, LOITERING=orange, ENCOUNTER=purple). ICCAT-authorized vessels are not marked separately — authorization is an opportunity indicator, not a risk signal.

**FDI choropleth layer (toggleable):** All Mediterranean 0.5-degree c-squares coloured by fishing days with opacity tiers: pale yellow (<50d, 0.15 opacity) → orange (50–500d, 0.25) → orange-red (500–2000d, 0.30) → dark red (>2000d, 0.35). Coverage is fleet-wide, not limited to event proximity.

---

## Fleet Analytics → Ranking

The single most important table in the app. One row per vessel, sorted by compounded `risk_score_total` descending.

**Columns to know:**

- **Risk band** — the Kpler *Turning Tides* classification: Low (<50), Emerging (50–60), Elevated (60–80), Severe (80–100), Critical (≥100). Cell background colour matches the map markers.
- **Compound multiplier** — `risk_score_total / base_score_total`. A value of 1.0x means the vessel's risk is purely behavioural; values above 2x mean structural lookups (IUU, ICCAT, OFAC) dominate.
- **Avg / Peak risk** — average and maximum per-event risk score. More stable than sum for comparing vessels with different event counts.
- **Four behavioural flags** (Industrial / Multi-behaviour / Dark port call / Repeat offender) — display-only, never multiplied into the score. See the "How to read this table" expander for definitions.
- **Two vessel-identity columns** (Vessel class / Type mismatch) — `vessel_class` is a descriptive category (industrial_fishing / artisanal_fishing / carrier / tanker / cargo / support / passenger / other) derived from the GFW Vessels API `shiptypes` field. `type_mismatch` fires when the event-level `vessel_type` and the registry `shiptypes` map to **different** canonical classes — the open-data equivalent of Kpler's "irregular vessel information" Grey Fleet indicator. Both display-only, never scored.
- **MPA intersection + tier** — sourced from GFW's `regions.mpa` field (WDPA point-in-polygon, server-side). Unlike the four flags, MPA tier *is* multiplied into the base score.
- **Fishing-in-MPA events / hours** — pre-joined from a separate GFW fishing-events query. Display-only.

**Pill filters** sit above the subtabs and cascade to all five Fleet Analytics subtabs. Narrow by event type, risk band, flag state, or vessel class. Switch to the **Vessel Investigation** tab for per-vessel drill-down.

### Plots in the Ranking expanders

| Expander | Chart | Reads |
|---|---|---|
| Risk band distribution | Bar chart of vessel count per band, coloured by band | "What's the shape of the fleet?" |
| Base vs structural-amplifier decomposition | Stacked horizontal bar (fleet total) split into behavioural base + IUU (black) + ICCAT (blue) + OFAC (dark red) segments | "How does the scoring methodology work, on this data?" |
| Top vessels: base vs structural amplifier | Top-10 horizontal bars, each split base + amplifier | "Who are the worst actors and why?" |

## Fleet Analytics → Exploration

Behavioural deep dives — repeat offenders, encounter patterns, and AIS gap analysis.

### Plots in the Exploration expanders

| Expander | Chart | Reads |
|---|---|---|
| Repeat offenders | Bar of vessels with ≥2 events + timeline of top-3 | "Who keeps coming back?" |
| Encounter analysis | Scatter of encounter distance vs duration + carrier alert | "Who's transshipping with whom?" |
| AIS gap behaviour | Distribution + geographic scatter of GAP events | "Who's going dark?" |

Every plot has a **"How to read this chart"** expander immediately above it that explains exactly what the axes mean and what to look for.

---

## Fleet Analytics → Trends & Patterns

Aggregate fleet view. The two main charts at the top are:

- **Risk Heatmap: Flag State vs Event Type** — bright cells are high-risk (flag, event-type) combinations. Sorted bottom-to-top by total risk.
- **Daily Behavioral Risk Trend** — total risk per day, with IUU-event dates marked as black dashed verticals. Below it, a stacked area split by event type — the Med analogue of Kpler *Turning Tides* Graph 4.

### Plots in the Trends & Patterns expanders

| Expander | Chart |
|---|---|
| Risk exposure by MPA tier | Donut of total risk split by GFCM-FRA / EU-site / Other WDPA / Outside MPA |
| Fleet composition by vessel class | Donut of unique vessels per `vessel_class` (industrial_fishing / artisanal_fishing / carrier / tanker / cargo / support / passenger / other). Descriptive — orthogonal to the size-based `is_industrial` flag. |
| Type mismatch by vessel class | Horizontal bar of `vessel_type_mismatch` counts grouped by `vessel_class` + table of mismatched vessels. Kpler Grey Fleet "irregular vessel information" equivalent. |
| Flag breakdown | Horizontal bar of risk per flag + stacked variant + IUU/ICCAT/OFAC summary tables |
| Event type distribution | Pie of risk share + summary table + event-level band distribution |
| Event duration distribution | Histogram of durations + duration vs risk scatter |

---

## Fleet Analytics → Fisheries Context

GFW behavioural events overlaid with EU JRC FDI baseline data — fishing effort and species landings aggregated to 0.5° c-squares.

**The interpretation rule:** events that fall in *low-effort* c-squares are the suspicious ones, because they happen in waters where legitimate fishing rarely occurs.

### Plots in the Fisheries Context expanders

| Expander | Chart |
|---|---|
| Geographic risk breakdown | Sub-zone risk bars + port-distance vs risk scatter |

---

## Fleet Analytics → Fishing Activity

GFW-classified fishing events (CNN model, `public-global-fishing-events` feed) with risk signal attribution. Separate from the behavioural events (gaps, encounters, loitering) — these are actual fishing detections.

**Toggle filters:** In MPA only / Non-GFCM flag / With behavioural events / Fishing-only (no behavioural). Filters cascade to both the scatter map and vessel table.

### Views in the Fishing Activity subtab

| View | What it shows |
|---|---|
| Scatter map | Background grey dots = all fishing inside MPAs; foreground coloured shapes = events that fired risk tree leaves (closed area, low-effort cell, non-GFCM flag). Shape encodes leaf type; colour encodes severity. |
| Fishing vessel table | One row per fishing vessel: event counts, total hours, in-MPA events, non-GFCM flag, whether the vessel also appears in the behavioural ranking. Includes fishing-only vessels not visible in the Ranking subtab. |

**Static-demo caveat:** the bundled fishing dataset has only ~5 fishing-in-MPA events. Switch to live GFW mode for the full picture.

---

## Vessel Investigation — risk tree highlights

The per-vessel investigation evaluates 41 leaves across 8 branches. Key branches to know:

- **Fishing Activity** (4 leaves) — `fishing_in_mpa` (any MPA), `fishing_in_closed_area` (no-take via GFW `mpaNoTake` as primary + curated closed-area CSV as fallback), `gap_then_fishing_sequence` (AIS dark 4h+ then fishing within 72h — classic IUU evasion signature), `fishing_in_low_effort_cell` (EU vessel in bottom 5% FDI effort area).
- **Network Exposure** (6 leaves) — encounter partner checked against IUU list, OFAC SDN, weak-cooperation flags (LBY/SYR), distant-water flags, and recurrence patterns.
- **Authorization** — includes GFW Insights cross-references (`gfw_iuu_crosscheck`, `gfw_no_rfmo_authorization`) when insights data is available, plus FAO unregulated checks (`stateless_vessel`, `unregulated_flag_in_gfcm_area`).

AIS coverage percentage (from GFW Insights API) is shown in the identity section when available.

**Gap evasion detection:** AIS gap events use `gap_intentional_disabling` (fires 1.5x) and `gap_implied_speed_knots` (>8 kn = 1.4x, >4 kn = 1.2x) instead of before/after speed comparison.

---

## Reference & Methodology

Three things live here:

1. The **risk-tree framework** as a static diagram (from `risk_tree.py`)
2. The **multiplier tables**: IUU × ICCAT × OFAC
3. The **scoring formula**, expanded with each term annotated

If a stakeholder asks "where do these numbers come from?" — point them here first.

---

## AI Analyst

Gemini 2.5 Flash with a sandboxed code-execution environment. The system prompt loads the entire `knowledge/` directory as RAG context, so the model knows the column names, the multiplier tables, the scoring formula, the McDonald 2024 caveat, the visualisation catalogue, and the 41-leaf risk tree framework.

**What the analyst can do:**

- Filter `df` and `fishing_df` with pandas
- Group, sort, aggregate, plot with Plotly
- Cite the exact columns it used and explain its reasoning

**What it cannot do:**

- Read or write files
- Make network calls
- Modify the live dataframes (it operates on copies)

**Example questions:**

- "Which vessels had fishing activity inside a GFCM Fisheries Restricted Area? Show their flag, base vs compounded risk scores, and the FRA name."
- "How many industrial-class vessels (`is_industrial=True`) had multi-behaviour flags, and what's their flag state distribution?"
- "Plot the top 5 flag states by total risk in the current filter window."
- "Show fishing-only vessels (in fishing_df but not df) with non-GFCM flags."

---

## Structural rules to remember

1. **Fishing events are never scored.** GFW's fishing classifier fires on every commercial fishing trip globally. We display fishing events as context in the Fishing Activity subtab and as a per-vessel flag in Investigation. Do not concatenate `fishing_df` into `df`.

2. **The four behavioural flags are display-only.** `is_industrial`, `multi_behaviour_flag`, `dark_port_call_candidate`, and `repeat_offender_90d` are parallel indicators, not score amplifiers. They show up in the Ranking subtab and fire rules in the risk tree, but they are never multiplied into `risk_score` because the underlying signals are already captured at the event level.

3. **The two vessel-identity columns are also display-only.** `vessel_class` (descriptive label) and `vessel_type_mismatch` (event-level vs registry-level disagreement) are derived from the GFW Vessels API `shiptypes` field. `vessel_type_mismatch` fires the `identity_misrepresentation` leaf in the risk tree at medium severity, but is never multiplied into `risk_score`.

All three rules exist to avoid double-counting and to keep the score interpretable as `behavioural_observation × structural_lookup`.
