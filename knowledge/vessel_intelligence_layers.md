# Vessel Intelligence Layers

Reference for the Med Vessel Monitor AI analyst. This document describes the vessel-level intelligence layers available in the app beyond the core GFW behavioural events (gap, encounter, loitering). When answering user queries, refer to these layers by their canonical column names and use the terminology in this document.

---

## 1. MPA intersection (spatial rule-zone signal)

Each AIS event carries three MPA-related columns derived from the GFW Events API `regions.mpa` field. GFW computes point-in-polygon server-side against the World Database on Protected Areas (WDPA), so these are authoritative spatial classifications, not local inferences.

**Columns on `df`:**

- `in_mpa` (bool) — True if the event falls inside any WDPA marine protected area
- `mpa_name` (str or None) — semicolon-joined names of the MPAs intersected (many events hit only one; nested MPAs can produce multiple)
- `mpa_tier` (str) — one of `gfcm_fra`, `eu_site`, `general`, or empty string

**Tier meaning:**

- `gfcm_fra` — GFCM Fisheries Restricted Area. Legally binding under Council Regulation (EC) No 1967/2006. Strongest regulatory tier. Examples: Lophelia reef off Capo Santa Maria di Leuca, Eratosthenes Seamount, Gulf of Lion FRA, Jabuka/Pomo Pit, Cabliers Coral Mound.
- `eu_site` — EU-designated marine protected area. Includes Natura 2000 marine sites, Pelagos Sanctuary (France-Italy-Monaco cetacean MPA), national MPAs under EU member state designation.
- `general` — other WDPA entries without specific EU or GFCM regulatory designation. Contextual signal only.

**How MPA affects the score:**

The MPA tier contributes a multiplier to the event's `base_risk_score` during `compute_risk_score()`: 2.0x for `gfcm_fra`, 1.5x for `eu_site`, 1.2x for `general`, 1.0x otherwise. This is the only spatial regulatory signal that enters the base score — all other structural signals (IUU, ICCAT, OFAC) are applied post-base as compound multipliers.

**Usage notes for queries:**

- Filter events inside any MPA: `df[df["in_mpa"]]`
- Filter events inside a specific tier: `df[df["mpa_tier"] == "gfcm_fra"]`
- Count events per MPA: `df[df["in_mpa"]].groupby("mpa_name").size()`
- Remember that `mpa_name` may contain multiple names separated by semicolons if an event is inside overlapping polygons

**Caveat to state in any MPA-related answer:** AIS intersection is a lower-bound indicator. Per McDonald et al. 2024 (*Nature*), approximately 90% of fishing vessels detected by satellite radar inside MPAs are not broadcasting AIS, so the actual number of vessels in violation is much higher than what AIS alone reveals. Vessels that do broadcast inside an MPA are a strong signal precisely because they did not go dark.

---

## 2. GFW fishing events (display-only context)

A separate dataframe `fishing_df` is loaded from the GFW `public-global-fishing-events` endpoint. These are classified fishing events per AIS point, produced by the Kroodsma et al. 2018 convolutional neural network that scores each position for active fishing based on gear-specific behavioural signatures (trawler, longliner, purse seiner, drifter).

**`fishing_df` is NOT part of `df`.** Never concatenate them. Never score fishing events into `risk_score`. Fishing events are context, not behavioural anomalies — legitimate fishing outside MPAs is normal commercial activity and must not be penalised.

**Columns on `fishing_df`:**

- `mmsi` — same key as `df`, use this to join when needed
- `vessel_name`, `flag` — identity
- `date` — event date
- `lat`, `lon` — position
- `fishing_hours` — duration of the fishing event in hours (NOT `duration_h`)
- `in_mpa` (bool) — True if the fishing event is inside any WDPA MPA
- `mpa` — name of the intersected MPA (NOT `mpa_name`)
- `mpa_tier` — `gfcm_fra`, `eu_site`, `general`, or empty (same vocabulary as `df`)

**Vessel-level aggregation on `df`:**

- `fishing_in_mpa_count` (int) — number of fishing events the vessel had inside any MPA. Zero for most vessels. Any positive count is a strong IUU signal because it represents GFW's own classification of active fishing inside a closed area, not a behavioural inference.

**Usage notes for queries:**

- Vessels with any fishing-in-MPA activity: `df[df["fishing_in_mpa_count"] > 0]`
- Full fishing history for a vessel: `fishing_df[fishing_df["mmsi"] == target_mmsi]`
- Fishing-in-MPA hours per vessel: `fishing_df[fishing_df["in_mpa"]].groupby("mmsi")["fishing_hours"].sum()`
- Fishing inside GFCM FRAs specifically: `fishing_df[fishing_df["mpa_tier"] == "gfcm_fra"][["vessel_name","flag","mpa","fishing_hours"]]`
- IMPORTANT: the MPA name column on `fishing_df` is `mpa`, not `mpa_name`. The hours column is `fishing_hours`, not `duration_h`.

**Why this matters:** Fishing-in-MPA is the strongest publicly available signal for IUU fishing in protected areas. It is display-only (never in the score) because GFW's fishing classification applies globally to all commercial fishing, and scoring it would penalise legal EU fishing across the board. The signal becomes meaningful only when combined with MPA intersection — which is why the vessel-level flag only counts MPA-intersecting fishing events.

---

## 3. Kpler-aligned vessel-level behavioural flags

Four vessel-level flags are computed per vessel after scoring, displayed in the Ranking subtab alongside the risk band, and fire rules in the risk tree framework. They are **never multiplied into the risk score** — they are parallel indicators, not score amplifiers. This avoids double-counting with signals already captured in `compute_risk_score()`.

**Columns on `df` (propagated from vessel-level aggregation):**

- `is_industrial` (bool) — vessel length ≥ 24 m OR gross tonnage ≥ 100 GT. Threshold from the ICCAT industrial classification and the EU Control Regulation (EC) No 1224/2009 reporting break. Length and tonnage come from the GFW Vessels API metadata, harvested during MMSI-to-IMO enrichment.

- `multi_behaviour_flag` (bool) — vessel shows two or more distinct event types (gap, encounter, loitering). Mirrors Kpler's "three or more deceptive behaviours" compound indicator from the October 2025 *Deceptive Shipping Practices* whitepaper.

- `dark_port_call_candidate` (bool, per event) — loitering events within 10 km of shore. Aggregated per vessel as a count. Derived from AIS inference, not satellite-verified, so labelled "candidate" rather than confirmed.

- `repeat_offender_90d` (bool) — vessel has two or more events within any 90-day window. Operationalises Kpler's "exposure drift" concept from the December 2025 *Turning Tides* report.

**Supporting columns:**

- `length_m` (float or None) — vessel length in metres from GFW Vessels API
- `tonnage_gt` (float or None) — gross tonnage from GFW Vessels API
- `shiptypes` (str or None) — GFW-registered vessel type from `registry_info` / `self_reported_info`. Used to derive `vessel_class` and `vessel_type_mismatch` (Section 7).

**Usage notes for queries:**

- Industrial vessels: `df[df["is_industrial"]]`
- Industrial vessels with any suspicious signal: `df[df["is_industrial"] & (df["multi_behaviour_flag"] | df["repeat_offender_90d"] | df["in_mpa"])]`
- Multi-behaviour repeat offenders: `df[df["multi_behaviour_flag"] & df["repeat_offender_90d"]]`
- Flag distribution of industrial vessels: `df[df["is_industrial"]].groupby("flag").size()`

**When answering queries about these flags:**

State explicitly that they are display-only and do not affect `risk_score`. The risk band classification uses the compounded risk score, which does not include these flags. Do not compute a synthetic score by adding or multiplying them into `risk_score`.

---

## 4. The base-vs-compound score decomposition

The app preserves two risk scores per event:

- `base_risk_score` — the behavioural score from `compute_risk_score()`, including all event-specific factors, shore distance, flag risk, and the MPA tier multiplier. Captures what was observed about the event itself.
- `risk_score` — the final compounded score after applying IUU, ICCAT, and OFAC multipliers as list lookups. Captures what was looked up about the vessel.

The ratio `risk_score_total / base_score_total` per vessel is the `compound_multiplier` — how much of the vessel's total risk comes from structural lookups versus pure observation. A high compound multiplier (e.g. 5x+) means the vessel's score was significantly amplified by its listing or authorisation status; a compound multiplier close to 1 means the score is almost entirely behavioural.

**Framing:** base = what we observed, compound = what we looked up about the vessel. The MPA factor lives in the base because it is observation (where the event happened), not lookup (who the vessel is).

**Usage notes for queries:**

- Vessels whose risk is mostly structural: `vessel_summary[vessel_summary["compound_multiplier"] > 3]`
- Vessels whose risk is mostly behavioural: `vessel_summary[vessel_summary["compound_multiplier"] < 1.5]`
- Always prefer `risk_score` for ranking; use `base_risk_score` when the user asks specifically about behavioural risk.

---

## 5. Risk bands

The final compounded `risk_score` per vessel is classified into bands aligned with Kpler's December 2025 *Turning Tides* vocabulary:

| Band | Score range | Meaning |
|---|---|---|
| Low | < 50 | Sparse risk signals |
| Emerging | 50–60 | First risk flags |
| Elevated | 60–80 | Multiple risk indicators |
| Severe | 80–100 | Compounding risk |
| Critical | ≥ 100 | Threshold breach |

Intervals are half-open (the upper bound belongs to the next band). Use `risk_band` column for categorical queries and `risk_score_total` for numeric filtering.

---

## 7. Vessel class and identity misrepresentation

Two descriptive columns derived from `shiptypes` (registry-level, GFW Vessels API) and `vessel_type` (event-level, GFW Events API). Both fields are normalised through the same `VESSEL_CLASS_PATTERNS` table in `config.py` (substring match against the lowercased input, first match wins, ordered list with `artisanal_fishing` before `industrial_fishing` and `carrier` before `cargo`). The output is one of `industrial_fishing`, `artisanal_fishing`, `carrier`, `tanker`, `cargo`, `support`, `passenger`, or `other`.

**Columns on `df`:**

- `vessel_class` (str) — canonical descriptive class. Prefers the registry value (`shiptypes`) when present, falling back to the event-level (`vessel_type`) otherwise. Display-only.
- `vessel_type_mismatch` (bool) — fires only when **both** fields are populated **and** map to **different** canonical classes. Class-level comparison is what makes this useful: a `vessel_type` of `TRAWLER` and a `shiptypes` of `FISHING` both map to `industrial_fishing` and the flag does not fire on the spelling difference. A `vessel_type` of `FISHING` against a `shiptypes` of `CARGO` does fire — that is the irregular vessel information signal.

**Why this is the Kpler Grey Fleet equivalent:**

The Kpler *Grey Fleet* paper (March 2025) lists "irregular vessel information" as one of the indicators that distinguishes deceptive vessels — a vessel broadcasting one identity in AIS while its registry record says something different. `vessel_type_mismatch` operationalises that exact indicator on open data: AIS-self-reported type (event-level) vs the GFW Vessels API registry record. Like the Kpler-aligned behavioural flags, it is **never multiplied into the risk score** — it is a parallel indicator that fires a rule in the risk tree (`identity_misrepresentation` leaf, medium severity) and shows up in the Trends & Patterns subtab.

**`vessel_class` is orthogonal to `is_industrial`:**

- `is_industrial` is **size-based** (length ≥ 24 m or GT ≥ 100), aligned with the EU Control Regulation 1224/2009 and ICCAT industrial classification. It is a regulatory threshold.
- `vessel_class` is **category-based** (what kind of vessel is this). It is a descriptive label.

A small artisanal trawler classifies as `vessel_class=industrial_fishing` (because it is a trawler) and `is_industrial=False` (because it is below 24 m). Both columns are useful; neither is a substitute for the other.

**Static demo seeded examples:**

- `KOOSHA 4` (Iranian, IUU-listed): event-level `vessel_type=FISHING`, registry `shiptypes=cargo`. Obvious mismatch tied to a known IUU listing — illustrates the pattern where a deceptive vessel broadcasts one identity in AIS while the registry says another.
- `LEONARDO PADRE` (Italian, ICCAT-authorised artisanal): event-level `vessel_type=FISHING`, registry `shiptypes=carrier`. Subtle mismatch on a clean ICCAT vessel — shows that the flag catches anomalies that other layers (IUU, OFAC, MPA) would miss entirely.

**Usage notes for queries:**

- Vessels with mismatched identity: `df[df["vessel_type_mismatch"]]`
- Mismatch counts grouped by registry class: `df[df["vessel_type_mismatch"]].drop_duplicates("mmsi").groupby("vessel_class").size()`
- Composition of the fleet by descriptive class: `df.drop_duplicates("mmsi")["vessel_class"].value_counts()`
- IMPORTANT: when answering misrepresentation queries, always state explicitly that the comparison is class-level (after normalisation), not string-level — otherwise users will assume the flag fires on every spelling difference.

---

## Quick reference — column glossary

| Column | Dataframe | Type | Meaning |
|---|---|---|---|
| `in_mpa` | df, fishing_df | bool | Event inside any WDPA MPA |
| `mpa_name` | df | str | Name(s) of intersected MPA(s) on `df` |
| `mpa` | fishing_df | str | Name of intersected MPA on `fishing_df` (NOT `mpa_name`) |
| `fishing_hours` | fishing_df | float | Duration of the fishing event in hours (NOT `duration_h`) |
| `mpa_tier` | df, fishing_df | str | `gfcm_fra`, `eu_site`, `general`, or empty |
| `rfmo_name` | df | str | RFMO area name from regions field |
| `base_risk_score` | df | float | Pre-compound-multiplier event score |
| `risk_score` | df | float | Post-compound-multiplier event score |
| `risk_score_total` | vessel summary | float | Sum of risk_score per vessel |
| `base_score_total` | vessel summary | float | Sum of base_risk_score per vessel |
| `compound_multiplier` | vessel summary | float | risk_score_total / base_score_total |
| `risk_band` | vessel summary | str | Low / Emerging / Elevated / Severe / Critical |
| `is_industrial` | df, vessel summary | bool | Length ≥ 24m or GT ≥ 100 |
| `length_m` | df, vessel summary | float | Vessel length in metres |
| `tonnage_gt` | df, vessel summary | float | Gross tonnage |
| `multi_behaviour_flag` | df, vessel summary | bool | Two or more distinct event types |
| `dark_port_call_candidate` | df | bool | Loitering within 10km of shore |
| `repeat_offender_90d` | df, vessel summary | bool | Two or more events within 90 days |
| `fishing_in_mpa_count` | vessel summary | int | Count of fishing events inside MPAs |
| `vessel_class` | df, vessel summary | str | Canonical descriptive class derived from shiptypes/vessel_type via VESSEL_CLASS_PATTERNS |
| `vessel_type_mismatch` | df, vessel summary | bool | Event-level vessel_type and registry shiptypes map to different canonical classes |

---

## 6. Visualisations that expose these layers

Seven plots in the UI surface the vessel intelligence layers visually. They live in expanders inside the existing four-tab layout, never as a separate tab. Each plot has a "How to read this chart" expander immediately above it.

| # | Plot | Tab location | Purpose | Reads from |
|---|---|---|---|---|
| 1 | **Base vs structural-amplifier decomposition** | Fleet Analytics → Ranking | Fleet-wide methodology illustration. One stacked horizontal bar showing the base contribution and the structural amplifier delta. | `df["base_risk_score"]`, `df["risk_score"]` |
| 2 | **Risk band distribution** | Fleet Analytics → Ranking | Vessel count per Kpler *Turning Tides* band. The single chart that lands fastest because it uses the recognised vocabulary verbatim. | `df.groupby("mmsi")["risk_score"].sum()` then `classify_risk_band()` |
| 3 | **Top vessels: base vs structural amplifier** | Fleet Analytics → Ranking | Vessel-centric counterpart to plot #1. Top-10 horizontal bars segmented into base + structural delta. Answers "who is worst?" while #1 answers "how does scoring work?". | `df.groupby("mmsi")` of `base_risk_score` and `risk_score` |
| 4 | **Risk exposure by MPA tier** | Fleet Analytics → Trends & Patterns | Donut split of total risk by `mpa_tier`. Quantifies the spatial-regulatory layer in one glance. | `df.groupby("mpa_tier")["risk_score"].sum()` |
| 5 | **Fishing events with risk signals** | Fleet Analytics → Fisheries Context | Leaf-differentiated scatter (`go.Scattergeo`): marker shape encodes leaf type (circle = general MPA, triangle-up = closed area, square = low-effort cell, diamond = no RFMO auth), colour encodes severity (red = high, orange = medium), white border = vessel-level overlay (IUU crosscheck / stateless / unregulated flag). Sized by `fishing_hours`. Display-only context. Uses `attribute_leaves_to_fishing_events()` from `risk_model.py`. | `fishing_df` filtered to events with at least one fishing leaf fired |
| 6 | **Fleet composition by vessel class** | Fleet Analytics → Trends & Patterns | Donut of unique vessels per `vessel_class`. Answers "what kind of fleet are we monitoring?" by descriptive category, orthogonal to the size-based `is_industrial` flag. | `df.drop_duplicates("mmsi")["vessel_class"]` |
| 7 | **Type mismatch by vessel class** | Fleet Analytics → Trends & Patterns | Horizontal bar of `vessel_type_mismatch` counts grouped by `vessel_class`, plus a detail table of mismatched vessels showing the specific event-level vs registry-level disagreement. The textbook "irregular vessel information" view from Kpler's Grey Fleet paper. | `df[df["vessel_type_mismatch"]]` grouped by `vessel_class` |

**Two design rules these plots follow:**

1. **Plots 1, 3, 4 read off the base-vs-compound decomposition**, which is *the* methodological story. If the AI analyst is asked "explain how scoring works", these are the three plots to point at — together they show the principle, the worst actors, and the spatial component.
2. **Plot 5 is never scored.** It is the only place in the entire app where `fishing_df` is rendered geographically, and it is explicitly labelled "display-only" because GFW's fishing classification fires on every commercial fishing trip globally and would otherwise penalise legitimate EU fishing.

**For analyst answers about visualisations:** if a user asks "where can I see X", the table above is the canonical lookup. Refer to plots by their UI label, not by their function name.

---

## Summary for the analyst

When a user asks about MPA activity, use `df[df["in_mpa"]]` for events and cross-reference `fishing_df` for active fishing inside protected areas. When a user asks about deceptive behaviour patterns, use the four Kpler-aligned flags. When a user asks about risk ranking, use `risk_score_total` and `risk_band` from the vessel summary. When a user asks "why is this vessel scored this way", decompose into `base_score_total` (behavioural observation including MPA) and the compound multiplier chain (IUU × ICCAT × OFAC). When a user asks "where can I see this", refer to Section 6.

Never score fishing events. Never add the four flags into `risk_score`. Always caveat AIS-based findings with the McDonald 2024 lower-bound framing for MPA-related answers.
