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

**Methodology at this step:**
- Event detection criteria follow **Miller et al. 2018** (*Frontiers in Marine Science*): encounter thresholds (<500m, >=2h, <2kn, >=10km from shore), shore distance as empirical discriminator.
- Marker colour priority (OFAC > IUU > event type) implements the **gate branch logic** from the risk tree — sanctions and IUU status override behavioural classification.
- Size encoding uses the 5-band Kpler "Turning Tides" (Dec 2025) vocabulary: Low (<50), Emerging (50-60), Elevated (60-80), Severe (80-100), Critical (>=100).

---

## Step 2 — Click a Vessel (1 min)

**Show:** Click KOOSHA 4 marker on map. Toast confirms "Selected KOOSHA 4 for investigation". Switch to Investigation tab — it's pre-loaded with the clicked vessel.

**Say:** "Clicking any marker selects it for investigation. The system decomposes risk into a tree: what behaviour was observed, where it happened, and what we know about the vessel from external databases."

**Background context:**

- **Click mechanism:** `st.pydeck_chart(on_select="rerun", selection_mode="single-object")`. Returns the full data row of the clicked point. Vessel name is written to `st.session_state["investigate_vessel"]`, which the Investigation tab reads on next render.
- **Investigation tab** is wrapped in `@st.fragment` — the dropdown/report rerun only within the fragment, not the entire page.
- **Risk tree** is deterministic (no LLM) — same input always produces same output. Implemented in `investigation.py`.

**Methodology at this step:**
- The risk tree framework has **8 branches and 41 leaves** (35 wired, 6 future work), defined in `risk_tree_framework.yaml`. Three branch types: **gate** (override — identity, regulatory status, network exposure), **additive** (cumulative — flag risk, behavioural history, spatial context, fishing activity), and **contextual** (direction-dependent — authorization).
- Investigation follows a structured 10-step workflow adapted from the **EFCA 2018 fisheries compliance risk assessment methodology**.

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

**Methodology at this step:**
- The formula implements **multiplicative compounding** — independent evidence streams modify belief non-linearly (standard multi-criteria risk assessment).
- **Duration exponent (0.75)** is a heuristic damping factor — not empirically calibrated, but prevents single extreme events from dominating. Flagged as heuristic in the methodology.
- **Shore distance factor** aligns with **Miller et al. 2018**: legitimate transshipment rarely occurs close to shore; the >20nm (37km) threshold matches GFW's "likely transshipment" criterion.
- **MPA multiplier tiers** are anchored in three papers: **Seguin et al. 2025** (*Science*) — industrial fishing in 47% of coastal MPAs; **Raynor et al. 2025** (*Science*) — 9x fewer vessels in fully protected MPAs (anchors GFCM-FRA 2.0x as strictest tier); **McDonald et al. 2024** (*Nature*) — ~90% of fishing vessels inside MPAs are AIS-dark (bounds MPA intersection as lower-bound indicator).
- **base_risk_score vs risk_score** decomposition enables the narrative: "this vessel is Critical because it's GFCM-listed, but its base behaviour alone would only be Elevated." Structural amplification is made visible.
- **Risk tree branches evaluated**: identity (IMO gate, type mismatch), regulatory_status (IUU listing gate), flag_risk (IRN high-risk flag), behavioural_history (AIS gap count, speed evasion), spatial_context (offshore location).
- **IUU list source**: TMT Combined IUU Vessel List, mirrors EU IUU list under Article 30 of Regulation 1005/2008.

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

**Methodology at this step:**
- **EU/non-EU pill** uses the `EU_FLAGS` set (27 member states) from `config.py`. Relevant because EU vessels are subject to CFP reporting obligations and FDI coverage, while non-EU vessels in the Med may operate under weaker oversight.
- **ICCAT pill** filters on `iccat_authorized` — ICCAT authorization is an **opportunity indicator, not exoneration** (authorization provides access to high-value species and transshipment infrastructure).
- **GFCM pill** filters on `gfcm_registered` — GFCM register data comes from GFW Vessels API, with only ~24% MMSI coverage. Absence is treated as unknown, not unauthorised.
- **FDI spatial join** uses `assign_csquare(lat, lon)` to map each event to the 0.5x0.5 dd JRC FDI grid. The FDI data is compiled annually by EU Member States and reviewed by STECF — statistically processed estimates, not raw declarations.

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

**Methodology at this step:**
- **Vessel-level aggregation** produces four derived metrics: `base_score_total`, `risk_score_total`, `max_event_risk`, `compound_multiplier`. The compound_multiplier ratio makes structural amplification visible — high compound = mostly lookup-driven, near 1.0 = mostly behavioural.
- **Four Kpler-aligned flags** are display-only — they mirror four of six core inputs in Kpler's Oct 2025 *Deceptive Shipping Practices* predictive model. Critically, they are **not multiplied into risk_score** — the underlying signals (duration, shore distance, event type, frequency) are already captured at the event level. Folding flags back in would double-count. This is a deliberate discipline: each piece of evidence enters the calculation exactly once.
- **vessel_type_mismatch** is the open-data equivalent of Kpler's Grey Fleet "irregular vessel information" indicator. Class-level comparison (not string-level) avoids false positives — "TRAWLER" vs "FISHING" both map to `industrial_fishing` and don't trigger.
- **Exports** include CSV, Markdown cover sheet, and HTML with embedded interactive Plotly charts.

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

**Methodology at this step:**
- **Fishing activity branch** of the risk tree has four leaves, all tree-only (no scoring multiplier):
  - `fishing_in_closed_area` (high) — two-tier detection: GFW's `mpaNoTake` field as primary (globally authoritative via WDPA), curated `closed_area_mpas.csv` (12 Med-specific closures) as fallback.
  - `gap_then_fishing_sequence` (high) — 4h+ AIS gap followed by fishing within 72h. Classic IUU evasion signature per **Miller et al. 2018**.
  - `fishing_in_low_effort_cell` (medium) — EU vessel fishing in bottom 5% of JRC FDI effort c-squares. Anomalous location signal.
  - `fishing_in_mpa` (high) — any MPA intersection on fishing events.
- **Leaf attribution** per event is computed by `attribute_leaves_to_fishing_events()` in `risk_model.py` — each fishing event gets boolean columns for which leaves fired, enabling the colour-coded scatter map.
- **GFW fishing classifier** source: **Kroodsma et al. 2018** (*Science* 359, 904-908) — CNN-based fishing activity detection from AIS data.
- **MPA non-compliance base rate**: **Seguin et al. 2025** (*Science*) found industrial fishing in 47% of coastal MPAs. **McDonald et al. 2024** (*Nature*) found ~90% of fishing vessels inside MPAs are AIS-dark — making this map a lower-bound indicator.
- **FAO IUU categories covered**: the fishing activity branch + behavioural events + formal listings cover **Illegal** and **Unregulated** fishing. The third category — **Unreported** — requires catch declaration data not available in open sources.

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

**Methodology at this step:**
- The AI analyst implements a **RAG + structured evidence** architecture: domain knowledge from 9 curated knowledge files provides the conceptual framework, while the deterministic risk tree trace provides vessel-specific ground truth. The LLM is instructed not to contradict the trace.
- **Anti-hallucination safeguards**: the system prompt includes explicit cross-reference status per vessel (IUU/ICCAT/OFAC booleans) and instructs the model to read actual column values rather than inferring status from flag or name. An Iranian tanker is NOT necessarily OFAC-sanctioned unless `ofac_sanctioned==True`.
- **Sandboxed execution** blocks filesystem/network access via `FORBIDDEN_CODE` list in `config.py`. Only `pandas`, `numpy`, `plotly` are available — no `os`, `subprocess`, `requests`, `open`, etc.
- This is conceptually the same pattern as **Kpler's MCP** (early 2026): natural language in, structured maritime intelligence out, with LLM translating queries into executable analysis against underlying data.

---

## Step 8 — Close (30 sec)

**Say:** "Six data sources, fully automated scoring pipeline, works with live GFW API or cached snapshots. Every multiplier is auditable through the risk tree. The system surfaces vessels that traditional monitoring misses — fishing-only vessels in MPAs, cargo ships on IUU lists, carrier encounters in high-effort zones."

**Methodology summary:**
- **One strong literature anchor** (Miller et al. 2018 — event detection criteria) + **three MPA empirical papers** (Seguin, Raynor, McDonald) + **principled-but-not-calibrated** design choices for multiplier values and compounding structure.
- **Epistemological discipline**: four data source types are separated by status — observed behaviour (GFW AIS), statistical estimates (FDI), enforcement actions (IUU/OFAC), authorisation records (ICCAT/GFCM). They are never collapsed into a single confidence number.
- **The honest position**: the methodology has the same shape as Kpler's — principled compounding model — minus the calibration dataset, because the fisheries equivalent of Kpler's sanctions designation data doesn't exist at comparable scale.

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
