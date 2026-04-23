# Med Vessel Behaviour Monitor — 10-Minute Showcase Guide

## Pre-demo checklist

- App loaded in **API snapshot** mode (no API delays)
- Sidebar: "Include fishing events" toggle ON
- Sidebar: "Fisheries context only" toggle OFF (show full fleet first)
- Browser maximised, dark theme off

---

## Step 1 — Hook: The Map (1 min)

**Show:** Main map with all events loaded. Pan/zoom briefly.

**Say:** "Every dot is a behavioural anomaly detected by Global Fishing Watch — AIS gaps, vessel encounters, and loitering events across the Mediterranean. Colour encodes the event type, size encodes the risk score. Black dots are IUU-listed vessels. Dark red are OFAC-sanctioned."

**Background context:**

- **Data source:** GFW Events API (`public-global-events:v3.0`). Async queries with Med polygon filter `[-6,30] to [36.5,46]`, limit 5,000 per query.
- **Event types:** GAP = AIS transponder went silent (possible intentional disabling). ENCOUNTER = two vessels in close proximity at low speed (possible transshipment). LOITERING = vessel drifting in open water (possible at-sea transfer or waiting).
- **Map engine:** PyDeck (deck.gl, WebGL/GPU-accelerated). Replaced Folium — no iframe re-serialisation, instant pan/zoom, click-to-select works natively.
- **Low-band events excluded** from map to reduce noise (risk_score < 50).
- **FDI layer** (blue choropleth rectangles, toggleable in sidebar): EU Joint Research Centre fishing effort by 0.5x0.5 degree c-square grid, rendered as filled rectangles (PolygonLayer). Blue scale: light < 50 days, medium 50-500, dark 500-2000, navy > 2000 fishing days.

---

## Step 2 — Click a Vessel (1 min)

**Show:** Click KOOSHA 4 marker on map. Toast confirms "Selected KOOSHA 4 for investigation". Switch to Investigation tab — it's pre-loaded with the clicked vessel.

**Say:** "Clicking any marker selects it for investigation. The system decomposes risk into a tree: what behaviour was observed, where it happened, and what we know about the vessel from external databases."

**Background context:**

- **Click mechanism:** `st.pydeck_chart(on_select="rerun", selection_mode="single-object")`. Returns the full data row of the clicked point. Vessel name is written to `st.session_state["investigate_vessel"]`, which the Investigation tab reads on next render.
- **Investigation tab** is wrapped in `@st.fragment` — the dropdown/report rerun only within the fragment, not the entire page.
- **Risk tree** is deterministic (no LLM) — same input always produces same output. Implemented in `investigation.py`.

---

## Step 3 — Investigation Deep-Dive: KOOSHA 4 (2 min)

**Show:** Walk the four-part Investigation display:
1. Framework expander (methodology)
2. Structured narrative (the investigation report)
3. Risk tree diagram (coloured branches: red = fired, grey = not)
4. Cumulative risk trajectory chart

**Say:** "KOOSHA 4 is an Iranian-flagged cargo vessel that appears on the GFCM IUU list. It had a 72-hour AIS gap near the Libyan coast. The base behavioural score captures the event itself — duration, proximity to shore, MPA intersection, flag risk. Then lookup multipliers compound: IUU listing at 3.0x. The final score lands in Critical band."

**Background context:**

- **Risk score formula:**
  ```
  risk = (duration_h ^ 0.75) x event_weight x flag_multiplier x shore_factor
         x mpa_multiplier x event_factors x iuu_multiplier x iccat_multiplier
         x ofac_multiplier
  ```
- **Event weights:** GAP = 3.2, LOITERING = 2.0, ENCOUNTER = 5.0
- **Shore distance factor:** > 37 km offshore = 1.5x (lower enforcement), 10-37 km = 1.2x, < 10 km = 0.8x (higher surveillance)
- **MPA multiplier** (part of base score, not lookup chain):
  - GFCM Fisheries Restricted Area: 2.0x
  - EU Natura 2000 site: 1.5x
  - General WDPA designation: 1.2x
- **Lookup multipliers** (compound on top of base):
  - IUU: GFCM-listed = 3.0x, other RFMO = 2.0x
  - ICCAT: Carrier = 1.4x, BFT = 1.3x, SWO/ALB = 1.2x
  - OFAC: 2.5x (flat)
  - Flag risk: 1.0x to 2.2x (Poseidon IUU Fishing Risk Index, 152 countries)
- **base_risk_score** is snapshotted immediately after `compute_risk_score()`, before any IUU/ICCAT/OFAC multiplier. This allows decomposition: compound_multiplier = total / base.
- **Risk bands** (Kpler "Turning Tides" vocabulary, Dec 2025):
  - Low: < 50
  - Emerging: 50-60
  - Elevated: 60-80
  - Severe: 80-100
  - Critical: >= 100
- **IUU matching priority chain:** MMSI exact → IMO exact → name exact → name fuzzy (token-overlap + SequenceMatcher >= 80%).
- **KOOSHA 4 is a cargo vessel on a fishing IUU list** — this is intentional. IUU lists include reefer/cargo vessels that support illegal fishing operations (transshipment at sea).
- **Trajectory chart:** Cumulative risk_score over time. Dashed horizontal lines at band thresholds (50, 60, 80, 100). Shows whether risk is accumulating or one-off.

---

## Step 4 — Pill Filters on Map (1 min)

**Show:** Return to map. Use pill filters:
1. Filter to ENCOUNTER only
2. Then filter to Critical + Severe bands
3. Toggle FDI layer ON — show blue effort rectangles underneath

**Say:** "I can slice the fleet in real time. These are the encounters that scored highest. Now with the FDI layer — blue rectangles show EU-declared fishing effort by c-square. Notice encounters clustering in high-effort zones near the Sicilian Channel and Aegean."

**Background context:**

- **Five pill controls** above the map: Event type, Risk band, Flag origin (EU/non-EU), ICCAT status, GFCM status.
- **Pills do NOT re-run the scoring pipeline.** The pipeline result is cached in `st.session_state` with a fingerprint. Pills only filter `df_map_base` from the cached `df_filtered`.
- **Vessel class** is derived from GFW Vessels API `shiptypes` (registry data), falling back to event-level `vessel_type` (AIS self-reported). Pattern matching: `VESSEL_CLASS_PATTERNS` in config.py: industrial_fishing, artisanal_fishing, carrier, tanker, cargo, support, passenger, other.
- **FDI c-square join:** Each GFW event is assigned to a 0.5-degree c-square via `assign_csquare(lat, lon)`. The FDI context lookup returns: total fishing days, top gear types, top species, known-fishing-ground flag.
- **Why encounters in high-effort zones matter:** Encounters between fishing vessels and carriers in active fishing grounds suggest at-sea transshipment — a key mechanism for laundering IUU catch.

---

## Step 5 — Fleet Analytics: Ranking (2 min)

**Show:** Switch to Fleet Analytics tab > Ranking subtab. Show the sortable table. Point out:
- Top vessels by total risk score
- Compound multiplier column (base vs total)
- Vessel flags: multi_behaviour, repeat_offender, dark_port_call_candidate
- IUU/ICCAT/OFAC columns
- Export button (CSV + Markdown)

**Say:** "Every vessel ranked by compounded risk. The compound multiplier column shows how much the lookup databases amplified the base behavioural score. Top 5 are all IUU or OFAC flagged — that's the multiplier effect. Multi-behaviour means the vessel triggered multiple event types. Repeat offender means multiple events within 90 days."

**Background context:**

- **Ranking is vessel-level aggregation** — sums risk_score across all events per vessel.
- **Key columns:**
  - vessel_class + type_mismatch: does AIS self-report match registry?
  - is_industrial: length >= 24m OR tonnage >= 100 GT (EU Reg 1224/2009)
  - multi_behaviour: >= 2 distinct event types
  - dark_port_call_candidate: loitering within 10 km of shore
  - repeat_offender_90d: >= 2 events in any 90-day window
  - fishing_in_mpa_events/hours: from separate fishing_df (display-only, not scored)
  - compound_multiplier: risk_score_total / base_score_total
- **Exports:**
  - CSV: full vessel summary with all columns
  - Markdown cover sheet: dataset scope, filter summary, band distribution, methodology
- **Band colour coding:** rows coloured by risk band (red = Critical, orange = Severe, etc.)

---

## Step 6 — Fishing Activity (1.5 min)

**Show:** Switch to Fisheries Context section (within Fleet Analytics). The fishing-in-MPA map loads with three layers. Toggle "In MPA only". Show the vessel table below.

**Say:** "45,000 GFW fishing detections. The blue background is EU-declared effort. Coloured dots are fishing events inside protected areas that triggered risk signals — fishing in closed areas, low-effort cells, non-GFCM flags. Switch to Fishing-only — these are vessels with fishing activity but NO behavioural events. They're invisible to traditional AIS gap monitoring. This is the gap the system fills."

**Background context:**

- **Separate data source:** GFW `public-global-fishing-events` — CNN-classified fishing activity (Kroodsma et al. 2018). Loaded into `fishing_df`, NEVER merged into scored events. This prevents double-counting.
- **Three-layer PyDeck map:**
  1. FDI effort rectangles (blue scale, background)
  2. Background fishing dots (grey, ≥ 0.5h, capped at 2,000)
  3. Foreground high-signal dots (coloured by severity)
- **High-signal risk tree leaves:**
  - `fishing_in_closed_area` (red): fishing in no-take MPA or GFCM FRA
  - `fishing_in_low_effort_cell` (orange): EU vessel fishing in bottom 5% FDI c-square
  - `gfw_no_rfmo_authorization` (orange): GFW Insights flagged no RFMO auth
  - `unregulated_flag` (orange): non-GFCM member state flag
  - `fishing_in_mpa` (blue): general WDPA MPA (lower confidence)
- **Filter controls:**
  - "In MPA only": fishing events inside Marine Protected Areas
  - "Non-GFCM flag": non-member state flags (potentially unregulated)
  - Radio: All / With behavioural / Fishing-only (mutually exclusive)
- **Key caveat:** McDonald et al. 2024 (Nature) — ~90% of satellite-detected fishing vessels inside MPAs are AIS-dark. This map shows a lower-bound signal only.
- **"Fishing-only" is the key insight:** Vessels with fishing activity but no AIS gaps/encounters/loitering are completely invisible to the behavioural risk pipeline. They only surface through the CNN fishing classifier.

---

## Step 7 — AI Analyst (1 min)

**Show:** Switch to AI Analyst tab. Pick "Investigate KOOSHA 4" from the preset dropdown. Show the structured output. Optionally ask a plot question: "Plot base_risk_score vs risk_score per vessel as a scatter".

**Say:** "The system feeds the vessel's full risk tree trace to Gemini 2.5 Flash and gets a structured narrative. It can also execute code — plotting risk trajectories, cross-referencing datasets, finding patterns across the fleet."

**Background context:**

- **Model:** Gemini 2.5 Flash via `google-genai` SDK. API key in secrets or sidebar input.
- **System prompt includes:**
  - Full dataframe schema (columns, dtypes, shape, sample rows)
  - Value counts for key columns
  - Cross-reference summary (IUU/ICCAT/OFAC per vessel)
  - 9 RAG knowledge base files (flags, iuu_context, med_geography, fdi_context, vessel_intelligence_layers, methodology_explainer, walkthrough, user_guide, methodology)
  - Available DataFrames: df, fdi_effort, fdi_landings, iuu_vessels, iccat_vessels, ofac_vessels, fishing_df
- **For vessel-specific queries:** A STRUCTURED EVIDENCE block is appended — the full deterministic risk tree trace from `investigation.py`. The LLM is instructed to follow the tree structure in its output.
- **Code execution sandbox:** Only pandas, numpy, plotly allowed. Filesystem/network access blocked via `FORBIDDEN_CODE` list.
- **22 preset questions** covering investigation, cross-source intelligence, domain-informed analysis, spatial/temporal patterns, behavioural deep-dives, and visual analytics.

---

## Step 8 — Close (30 sec)

**Say:** "Six data sources, fully automated scoring pipeline, works with live GFW API or cached snapshots. Every multiplier is auditable through the risk tree. The system surfaces vessels that traditional monitoring misses — fishing-only vessels in MPAs, cargo ships on IUU lists, carrier encounters in high-effort zones."

---

## Data Source Summary

| Source | Records | Update | Auth |
|--------|---------|--------|------|
| GFW Events API | ~5,000/query | Live | JWT token |
| GFW Fishing Events | ~45,000 | Live | JWT token |
| GFW Vessels API | ~2,000 vessels | Per-session | JWT token |
| EU JRC FDI | ~295K rows | Annual (2017-2024) | Public |
| Combined IUU List | 369 vessels (13 RFMOs) | Manual refresh | Public |
| ICCAT Med Record | 9,203 vessels | Manual refresh | Public |
| OFAC SDN List | ~50 vessels | Manual refresh | Public |
| Poseidon IUU Risk Index | 152 countries | Annual | Public |

## Demo Vessels Quick Reference

| Vessel | Flag | Story | Key Multipliers |
|--------|------|-------|-----------------|
| **KOOSHA 4** | IRN | Cargo on GFCM IUU list | IUU 3.0x, flag 1.63x |
| **SABITI** | IRN | Oil tanker, OFAC sanctioned | OFAC 2.5x, flag 1.63x |
| **ADRIAN DARYA 1** | IRN | Tanker, OFAC Iran program | OFAC 2.5x, flag 1.63x |
| **ACROS NO. 2** | HND | Carrier, other-RFMO IUU | IUU 2.0x |
| **FRIO NARUTO** | BHS | Carrier, ICCAT authorized | ICCAT 1.4x |
| **LEONARDO PADRE** | ITA | Artisanal, ICCAT authorized | ICCAT 1.2x |

## Risk Score Decomposition Example (KOOSHA 4)

```
Base behavioural score:
  (72h ^ 0.75)           = 27.0    (duration)
  × 3.2                  = 86.4    (GAP event weight)
  × 1.63                 = 140.8   (IRN flag risk)
  × 1.5                  = 211.2   (offshore > 37km)
  × 1.0                  = 211.2   (no MPA intersection)
  × 1.4                  = 295.7   (implied speed > 8kn evasion)
  = base_risk_score ~296

Lookup multipliers:
  × 3.0                  = 887.0   (GFCM IUU-listed)
  × 1.0                  = 887.0   (no ICCAT)
  × 1.0                  = 887.0   (no OFAC)
  = risk_score ~887 → Critical band

Compound multiplier: 887 / 296 = 3.0x
```
