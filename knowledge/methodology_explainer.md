# Risk Scoring Methodology — Explainer

Quick reference for the "how does your app estimate risk?" question and the follow-up "where does that come from?" probe.

---

## The two-step logic

**8 multiplicative factors in the base score, 3 lookup-based amplifiers on top.** The base captures the event itself: duration, event type, flag, shore distance, **MPA intersection tier**, and up to three event-specific factors. The amplifiers are structural vessel-level lookups (IUU listing, ICCAT authorisation, OFAC sanctions; the flag multiplier is counted in the base).

### Step 1: Score each event individually

For every AIS event (gap, encounter, or loitering), compute a base behavioural score:

```
base = (duration^0.75) × event_weight × flag_multiplier × shore_factor × mpa_multiplier × event_specific_factors
```

**Factor-by-factor:**

- **Duration^0.75** — longer events are riskier, with diminishing returns. A 10-hour gap isn't 10x worse than a 1-hour gap; the exponent dampens linear dominance of long events.
- **Event weight** — encounters 5.0, gaps 3.2, loitering 2.0. Encounters weighted heaviest because they are the direct transshipment signal.
- **Flag multiplier** — derived from the Poseidon IUU Fishing Risk Index (152 coastal states, 10 Flag-responsibility indicators averaged, mapped linearly to a multiplier via `1.0 + (mean_score - 1.0) * 0.3`). Sanctions/conflict states score high organically (RUS 1.93x, IRN 1.63x, PRK 1.26x, SYR 1.24x); flags of convenience also score high due to weak oversight indicators (PAN 1.81x, LBR 1.48x, MHL 1.39x). Flags not in the Index receive 1.0x (neutral).
- **Shore factor** — offshore events are riskier for transshipment (>20nm gets 1.5x, 10-20nm gets 1.2x, inshore gets 0.8x). Aligned with Miller et al. 2018 criteria.
- **MPA intersection tier** — applied per event from GFW's `regions.mpa` field (pre-computed point-in-polygon against WDPA). Three regulatory tiers, classified by config substring match on the MPA name:
  - `gfcm_fra` — GFCM Fisheries Restricted Area, legally binding under Council Reg (EC) 1967/2006: **2.0×**
  - `eu_site` — Natura 2000 marine, Pelagos Sanctuary, EU-designated marine site: **1.5×**
  - `general` — any other WDPA entry: **1.2×**
- **Event-specific factors**:
  - *Encounters*: proximity multiplier (<500m = 1.8x), speed multiplier (<2kn = 1.5x), vessel type multiplier (carrier/tanker = 1.4x)
  - *Loitering*: vessel type (carrier/tanker = 1.6x), speed (<2kn = 1.4x)
  - *Gaps*: speed-change evasion proxy (>5 knots change = 1.5x)

### Step 2: Apply structural multipliers

After base scoring, three independent lookup-based multipliers amplify the score:

- **IUU multiplier** — 3.0x for GFCM-listed vessels, 2.0x for other RFMO listings (via TMT Combined IUU List, which mirrors the EU IUU list under Article 30 of Reg 1005/2008)
- **ICCAT multiplier** — 1.4x for carriers, 1.3x for bluefin tuna authorisation, 1.2x for swordfish/albacore
- **OFAC multiplier** — 2.5x for sanctioned vessels

Final formula:

```
risk_score = base × iuu_multiplier × iccat_multiplier × ofac_multiplier
```

---

## The critical design principle

**Multipliers amplify existing behavioural signal; they never substitute for it.**

A vessel that is ICCAT-authorised for bluefin but has no suspicious AIS events carries no risk score at all — the 1.3x multiplier has nothing to act on. Structural factors only become risk amplifiers when paired with behavioural evidence.

Same for IUU and OFAC: the lookup tells you "this vessel has prior enforcement history, so its current suspicious behaviour is more concerning", not "this vessel is automatically risky regardless of what it does".

This is why ICCAT authorisation is treated as an **opportunity indicator, not an exoneration** — authorisation to fish high-value species or operate as a carrier creates conditions under which IUU behaviour is most consequential, so conditional on suspicious AIS patterns, those vessels warrant elevated scrutiny.

---

## Classification into bands

After final scoring, classify the **final compounded** `risk_score` (not `base_risk_score`) into five bands aligned with Kpler's December 2025 "Turning Tides" vocabulary. Ranges are half-open intervals (`low ≤ score < high`):

| Band | Score range | Meaning |
|---|---|---|
| Low | <50 | Sparse risk signals |
| Emerging | 50–60 | First risk flags |
| Elevated | 60–80 | Multiple risk indicators |
| Severe | 80–100 | Compounding risk |
| Critical | ≥100 | Threshold breach |

Because the band is derived from the compounded score, the decomposition lets an analyst say *"this vessel is Critical because it's GFCM-listed, but its base behaviour alone would only have been Elevated"* — the amplification is made visible rather than hidden inside the number.

---

## Vessel-level aggregation

Event scores are aggregated per vessel with five derived metrics:

- `base_score_total` — sum of pre-multiplier scores (behaviour only)
- `risk_score_total` — sum of post-multiplier scores (behaviour + structural)
- `compound_multiplier` — the ratio, showing how much risk comes from behaviour vs structural amplifiers
- `avg_risk` — average per-event risk score. More stable than sum for comparing vessels with different event counts.
- `peak_risk` — maximum single-event risk score. Identifies the worst individual event.

This decomposition enables the base-vs-compounded narrative move: *"this vessel's risk is 30 from behaviour, compounded to 168 because it's GFCM-listed and ICCAT-authorised as a carrier"*. The analyst sees both numbers side by side, so structural amplification is never hidden inside the final score.

---

## Vessel-level behavioural flags (display-only)

Four compound/temporal flags are computed per vessel and surfaced in the Vessel Summary and Vessel Investigation tabs:

- **`multi_behaviour_flag`** — vessel shows two or more distinct event types (gap, encounter, loitering) in the window. Compound indicator.
- **`dark_port_call_candidate`** — at least one LOITERING event within 10 km of shore. AIS-inferred, not satellite-verified (hence "candidate"). Also rendered on the Folium map as a dashed amber outline.
- **`repeat_offender_90d`** — two or more events within any 90-day rolling window. Captures exposure drift over time.
- **`vessel_type_mismatch`** — event-level vessel_type and registry shiptypes map to different canonical classes (e.g. fishing vessel broadcasting as cargo). Identity misrepresentation signal.

These mirror four of the six core inputs in Kpler's October 2025 *Deceptive Shipping Practices* predictive model.

**Critically, these flags are not multiplied into the risk score.** The underlying signal — loitering duration, shore distance, event type, event frequency — is already captured at the event level by the base scoring formula. Folding the flag back in as a multiplier would double-count. The flags are display-only triage signals, not scoring inputs.

This is a deliberate discipline worth calling out in an R&C conversation: the score stays interpretable because each piece of behavioural evidence enters the calculation exactly once. An analyst can see a vessel with three flags and a moderate score and immediately understand that the flags are *views* over the same underlying behaviour, not independent amplifiers of it.

---

## The risk tree framework

The scoring pipeline answers "how risky is this vessel's behaviour?" The risk tree answers a different question: **"what kind of risk is it, and what should we investigate next?"**

The risk tree is a hierarchical framework with **8 branches** and **41 leaf questions**, defined in `data/risk_tree_framework.yaml`. It drives the per-vessel investigation trace in the Vessel Investigation tab — each branch is evaluated for the selected vessel, coloured by severity, and rendered as expandable cards plus an interactive icicle chart.

### The three branch types

1. **Gate branches** (override) — any positive answer forces a minimum tier regardless of other branches. These are hard stops:
   - **Identity Verification** — is the vessel identifiable? Missing IMO + name changes = Elevated minimum.
   - **Regulatory Status** — is the vessel on any sanctions or IUU list? OFAC = Critical. GFCM IUU = High.
   - **Network Exposure** — six leaves (five wired, one future work): encounter partner name matched against IUU list (high) and OFAC SDN (critical), encounter partner flag in weak-cooperation Med coastal set LBY/SYR (medium), encounter partner flag in distant-water/non-Med FoC set (medium), encounter pattern recurrence — 2+ encounters with same counterparty within 90-day window (medium), and shared ownership (future work). Direct encounter with a sanctioned vessel = Critical.

2. **Additive branches** (cumulative) — each positive answer contributes to tier escalation. Three or more flags raised escalates one tier:
   - **Flag State Risk** — high-risk IUU country, flag of convenience, recent flag change, PSC blacklist.
   - **Behavioural History (90 days)** — AIS gap count, carrier encounters, loitering in fishing grounds, speed-change evasion, plus the four display-only flags (multi-behaviour, dark port call, repeat offender, industrial profile).
   - **Spatial / Contextual Risk** — contested EEZ, MPA/FRA intersection, high-value fishing grounds.
   - **Fishing Activity** — four leaves analysing GFW-classified fishing events: fishing inside any MPA (`fishing_in_mpa`, high), fishing inside a no-take MPA or curated closed area (`fishing_in_closed_area`, high — two-tier signal using GFW's `mpaNoTake` field as primary and `closed_area_mpas.csv` as fallback), AIS gap followed by fishing within 72 hours (`gap_then_fishing_sequence`, high — classic IUU evasion signature), and EU vessel fishing in a bottom-5% FDI effort c-square (`fishing_in_low_effort_cell`, medium — anomalous location for EU fleet).

3. **Contextual branches** (direction-dependent) — the answer changes interpretation depending on what other branches found:
   - **Fishing Authorization Status** — ICCAT/GFCM authorization is an opportunity indicator, not exoneration. A carrier authorized for bluefin paired with suspicious AIS behaviour is *more* concerning, not less. This branch also covers the FAO "unregulated" category: **stateless_vessel** (high — vessel broadcasting empty/unknown flag, outside any state's regulatory authority) and **unregulated_flag_in_gfcm_area** (medium — vessel flagged to a non-GFCM contracting party, fishing under no applicable regional conservation measures). Two GFW Insights API leaves provide cross-references: **gfw_iuu_crosscheck** (high — GFW's live RFMO IUU list confirms listing, independent of our static CSV) and **gfw_no_rfmo_authorization** (medium — GFW detected fishing in RFMO areas where vessel has no known authorization from any of 40+ registries). Together with existing illegal-fishing detection, these complete coverage of two of three FAO IUU categories.

### How it differs from the scoring pipeline

| | Scoring pipeline | Risk tree |
|---|---|---|
| **Unit** | Per event | Per vessel |
| **Logic** | Multiplicative (factors compound) | Compound (gate + additive + contextual) |
| **Output** | Numeric score + band | Tier assignment + investigation trace |
| **Question** | How severe is the behaviour? | What type of risk is it? |
| **Data consumed** | Event-level AIS + lookup multipliers | Vessel-level aggregation + network context |

The scoring pipeline feeds *into* the risk tree (event scores are aggregated per vessel before evaluation), but the risk tree also evaluates dimensions the scoring pipeline cannot capture — identity verification, network exposure, authorization context.

### Tier assignment rules (compound logic)

The final tier is not a simple sum of branch scores. It follows compound rules where combinations matter more than individual factors:

- OFAC sanctioned OR (IUU listed AND ICCAT authorized AND suspicious behaviour) → **Critical**
- GFCM IUU listed → **High minimum**
- Other RFMO IUU listed → **Elevated minimum**
- GFW-classified fishing inside an MPA → **Elevated minimum**
- Identity misrepresentation (vessel_type_mismatch) AND any behavioural flag → **escalate one tier**
- Industrial vessel profile AND (in MPA OR IUU listed) → **escalate one tier**
- Three or more additive flags raised → **escalate one tier**
- No flags raised → **Low**

### What the risk tree does not do (yet)

5 of the 41 leaf questions remain as future-work stubs, each annotated with
`status: future_work` and a `data_requirement` note in both the YAML and
`investigation.py` documenting exactly what data source would enable it:

- **`shared_ownership`** (Network Exposure) — requires vessel beneficial-ownership data (Maritime 2.0 or Equasis). The five first-degree encounter-partner leaves are wired; fleet-network propagation is the next step.
- **`mmsi_consistent`** (Identity Verification) — requires longitudinal MMSI history. Partially available in live mode via GFW Vessels API multi-SSVID entries, but not in the static demo.
- **`name_history`** (Identity Verification) — requires vessel registry change history beyond what a single GFW snapshot provides.
- **`eu_sanctioned`** (Regulatory Status) — requires EU consolidated sanctions list (only OFAC SDN currently loaded).
- **`flag_recent_change`** (Flag State Risk) — requires historical flag data.

Note: `gfcm_authorized` (absence-based authorisation signal) is partially wired — positive-evidence leaves (`gfcm_listed_no_licence`, `gfcm_listed_inactive`) are active in the `authorization` branch, but the absence-based signal requires enrichment of GFCM register MMSI coverage (currently 24%).

These are flagged as enrichment opportunities, not hidden gaps. The framework is designed to be extended as new data sources become available — the branch structure and compound logic are in place, waiting for the data layer to catch up.

### Interview answer: "What's the risk tree for?"

*"The scoring pipeline tells you how bad the behaviour looks numerically. The risk tree tells you what kind of risk it is and what to investigate next. A vessel with a high score from encounters plus an IUU listing follows a different investigation path than one with a high score from AIS gaps inside an MPA. The tree gives the analyst a structured triage workflow — identity first, then regulatory status, then behaviour, then spatial context — so they know which questions to ask in which order. It's the fisheries equivalent of Kpler's shadow fleet risk tree, adapted from the oil and gas domain to Mediterranean IUU."*

---

## Data sources -- currently wired

### 1. Global Fishing Watch (GFW)

The behavioural substrate. Three distinct feeds:

- **GFW Events API** -- AIS-derived behavioural events (gap, encounter, loitering) for the Mediterranean polygon. Anchored in Miller et al. 2018. Primary input to the scoring pipeline.
- **GFW `regions.mpa`** -- WDPA point-in-polygon intersection, computed server-side by GFW on each event. Feeds the MPA tier multiplier in the base score.
- **GFW `public-global-fishing-events`** -- Kroodsma et al. 2018 CNN-classified fishing activity. Separate feed, display-only (fishing-in-MPA flag).
- **GFW Vessels API** -- vessel metadata (length, tonnage, shiptypes, flag, IMO). Used for `is_industrial`, `vessel_class`, `vessel_type_mismatch`.
- **GFW Insights API** (v3) -- optional batch query for unique vessels in the snapshot. Returns RFMO authorization checks (fishing without known authorization from 40+ registries), AIS coverage percentage, and live IUU list cross-reference. Queried during snapshot download when "Include vessel insights" toggle is enabled (~1 min for ~200 Elevated+ vessels). Cached to `data/api_insights_snapshot.csv`. Two tree-only leaves: `gfw_iuu_crosscheck` (high) and `gfw_no_rfmo_authorization` (medium). No scoring multiplier.

### 2. EU JRC FDI (Fisheries Dependent Information)

83,000 effort rows and 212,000 landing rows, aggregated to 0.5 deg c-square x quarter x gear x species. Contextual baseline -- never multiplies risk, used in Fisheries Context tab.

### 3. TMT Combined IUU Vessel List

369 vessels across 13 RFMOs. Mirrors EU IUU list under Article 30 of Regulation 1005/2008. 168 with IMO, 64 with MMSI. Compound multiplier: GFCM-listed 3.0x, other RFMO 2.0x. Also used in `encounter_iuu_vessel` partner leaf.

### 4. ICCAT Record of Vessels (Med-authorised)

~9,200 vessels. Species tier multipliers: carrier 1.4x, BFT 1.3x, SWO/ALB 1.2x. Authorisation is an opportunity indicator, not exoneration.

### 5. OFAC SDN

~50 vessels. Hard sanctions signal. 2.5x compound multiplier. Also used in `encounter_sanctioned_vessel` partner leaf.

### 6. Poseidon IUU Fishing Risk Index

152 coastal states scored 1-5 across 40 indicators. Drives `flag_multiplier` via `multiplier = 1.0 + (mean_score - 1.0) * 0.3`.

### 7. GFCM Authorised Vessel Register

77,304 vessels, 24 Med countries. 24% MMSI coverage. Two positive-evidence leaves wired: `gfcm_listed_no_licence` (medium), `gfcm_listed_inactive` (medium). Absence-based signal remains future work due to coverage limitation.

### 8. Curated Closed-Area MPAs

52 named Mediterranean no-take zones and gear-specific closures (GFCM FRAs, national reserves) used as Tier 2 fallback in the `fishing_in_closed_area` leaf. File: `data/closed_area_mpas.csv`. Tier 1 is GFW's `mpaNoTake` field (globally authoritative). The CSV catches Med-specific closures that GFW may not classify as no-take (e.g. gear-specific GFCM restrictions).

### Data sources not wired (future work)

EU IUU carding data, EU Fleet Register (CFR), commercial AIS APIs (MarineTraffic, VesselFinder), Kpler Maritime 2.0 (ownership graph).

---

## Where the methodology comes from

### Direct literature backing

**Miller et al. 2018** — *Identifying Global Patterns of Transshipment Behavior*, Frontiers in Marine Science. This is the foundational GFW paper that defines:
- Encounter criteria: <500m distance, ≥2 hours duration, <2 knots speed, ≥10km from shore
- The distinction between "likely transshipment" (reefer + fishing vessel) and "potential transshipment" (reefer loitering alone)
- Shore distance as an empirical discriminator — legitimate transshipment rarely occurs close to shore; offshore encounters are disproportionately IUU-associated

This is the strongest literature anchor in the model. The GFW Events API implements these criteria in the feed itself, so the detection layer inherits this methodology directly.

**MPA intersection — empirical anchoring.** Three independent papers anchor the MPA factor as a high-tier risk signal rather than a heuristic guess:
- **Seguin et al. 2025** (*Science* 389, 396–401, [doi:10.1126/science.ado9468](https://doi.org/10.1126/science.ado9468)) — found industrial fishing in **47% of coastal MPAs** globally. Methodological backbone: MPA intersection is not a rare-edge signal but a routine compliance failure.
- **Raynor et al. 2025** (*Science* 389, 392–395, [doi:10.1126/science.adt9009](https://doi.org/10.1126/science.adt9009)) — found **9× fewer fishing vessels** inside fully and highly protected MPAs. Anchors the GFCM-FRA tier (2.0×) as the strictest enforcement category, where compliance pressure is highest and any detected presence carries strong signal.
- **McDonald et al. 2024** (*Nature* 625, 85–91, [doi:10.1038/s41586-023-06825-8](https://doi.org/10.1038/s41586-023-06825-8)) — satellite mapping reveals that **~90% of fishing vessels inside MPAs do not broadcast AIS**. Bounds the AIS-only approach as a **lower-bound indicator**: MPA intersection on AIS data captures the visible tail of a much larger population, so a positive MPA hit on AIS is conservatively interpreted.

**GFW `public-global-fishing-events` (Kroodsma et al. 2018, *Science* 359, 904–908, [doi:10.1126/science.aao5646](https://doi.org/10.1126/science.aao5646))** — separate CNN-classified fishing-activity feed from GFW. Loaded into a separate dataframe and **never merged into the scored events**; surfaced display-only as a per-vessel fishing-in-MPA flag in the Vessel Investigation tab. The discipline is the same as the behavioural flags: signal that is already captured at the event level (via MPA intersection on the gap/encounter/loitering feed) is not double-counted via a second feed. The fishing-events feed answers a different question — *was the vessel fishing here?* — and is shown alongside the score, not multiplied into it.

### Principled but not literature-derived

**Multiplicative compounding of risk factors** — standard practice in multi-criteria risk assessment. The logic: independent evidence streams should modify belief about risk non-linearly, because two independent concerning signals are more than twice as concerning as one. Closer to Bayesian reasoning applied informally than to a cited fisheries-specific paper.

**Duration exponent (0.75)** — a heuristic choice to dampen linear dominance of long-duration events while preserving monotonicity. Not empirically calibrated against enforcement outcomes. Calibration would require a fisheries designation dataset that doesn't exist at comparable scale to Kpler's sanctions data.

**Flag risk multipliers** — derived from the Poseidon IUU Fishing Risk Index (https://iuufishingindex.net/), covering 152 coastal states. The 10 Flag-responsibility indicators per country (vulnerability, prevalence, response) are averaged and mapped linearly to a multiplier: `1.0 + (mean_score - 1.0) * 0.3`. Sanctions/conflict states and flags of convenience score high organically because the Index captures weak governance, enforcement gaps, and oversight deficits — no manual flag list is hardcoded. Regenerated from the latest Index via `scripts/prepare_iuu_risk_index.py`.

**ICCAT risk tiers** — hierarchy reflects domain judgement about opportunity for IUU behaviour: carriers > bluefin (highest-value Med species) > swordfish/albacore. The "opportunity not exoneration" framing is an analytical choice grounded in the conditional-multiplier principle.

**IUU list tiering** — GFCM listings carry 3.0x because GFCM is the Mediterranean-specific RFMO; its listings are the most directly relevant regional enforcement signal. Other RFMO listings 2.0x. Jurisdiction logic, not cited.

### The honest position

The methodology has one strong literature anchor and several principled-but-not-calibrated design choices:

- **Event definitions and thresholds**: Miller et al. 2018 (direct)
- **Scoring structure**: standard multi-criteria compounding (principled)
- **Specific multiplier values**: domain reasoning, not empirical fit (heuristic)

This is the same shape as Kpler's approach: their October 2025 whitepaper acknowledges that their model weights "mirror" observed enforcement patterns, but they don't publish the exact values or the statistical fit. Kpler is running a principled compounding model calibrated to their designation dataset. The Med Vessel Monitor is running the same shape minus the calibration dataset — because the fisheries equivalent of Kpler's sanctions data doesn't exist at comparable scale.

---

## Interview answers

### "How does your app estimate risk?" — short version

*"Two steps. Step one, each AIS event gets a base behavioural score from duration, event type, flag, shore distance, MPA intersection tier, and event-specific factors like proximity and speed. Step two, structural multipliers from IUU listings, ICCAT authorisation, and OFAC sanctions amplify the base score — but only amplify, never substitute. A vessel with no suspicious behaviour carries no score regardless of authorisation status. Final scores are aggregated per vessel and classified into bands from Low to Critical at ≥100, mirroring Kpler's December 2025 vocabulary."*

### "Where does the methodology come from?" — short version

*"Miller et al. 2018 from GFW provides the event definitions — encounter thresholds, shore distance, duration cutoffs. Everything on top is principled compounding: multiplicative because independent risk signals should modify belief non-linearly, with specific multiplier values calibrated by domain reasoning rather than empirical fit. The calibration dataset for fisheries enforcement doesn't exist at Kpler's scale, which is why I've documented the scores as descriptive rather than predictive."*

### "Why 0.75 as the duration exponent?" — probe answer

*"Heuristic. It dampens linear dominance of long-duration events while preserving monotonicity — a 10-hour gap shouldn't score 10x a 1-hour gap because the marginal suspiciousness per hour diminishes. The specific value is chosen for reasonable output behaviour, not empirically fitted. If I had a calibration dataset of designated vessels with timestamped first-incident data, I'd fit the exponent to that. I don't, so it's flagged as heuristic in the documentation."*

### "Have you validated the scores?" — honest answer

*"Not in the statistical sense. The scores are methodology-driven — they apply a principled compounding of known risk factors, anchored in GFW methodology for the detection layer. Validation would require proxy outcomes like RFMO IUU list additions, port state denials, or STECF expert flagging over a sufficient observation window. That's named as future work. Kpler has the advantage of a large sanctions designation dataset to calibrate against; in fisheries the enforcement signal is sparser and slower, so calibration is a longer project."*

---

## Regulator lineage — and its limits

### "Does this framework come from anywhere specific?" — provenance answer

*"The three-layer structure — base impact × likelihood score, contextual modifiers layered on top, prioritised output — mirrors the EFCA 2018 fisheries compliance risk assessment methodology and its national implementation in the Hellenic General Directorate of Fisheries' 2024 Risk-Based Audit Plan. I worked with that framework at the Ministry. In the regulator environment the inputs are logbooks, VMS, ERS cross-checks, sales notes, and inspection history — all regulator-access data. Outside that environment none of it is available."*

### "So how does your app relate to it?" — the honest framing

*"The app is a deliberate methodological test. The question is whether the same three-layer structure can be rebuilt from data that is publicly observable: AIS behavioural events, IUU listings, authorisation records. The base score becomes GFW event severity rather than stock-status-weighted catches. The contextual modifiers become TMT IUU listings and ICCAT authorisation type rather than inspection history and previous findings. The prioritised output stays the same in shape — a ranked watchlist — but it answers a different question: not 'who should we inspect' but 'whose behaviour warrants investigation'."*

### "What's lost in the translation?" — the caveat that matters

*"Logbook and VMS data are ground truth in a way AIS behavioural data isn't. A logbook entry is a declaration the vessel operator is legally bound to; an AIS gap is a proxy that could mean deliberate evasion, equipment failure, or legitimate satellite coverage loss. That's why the app separates the four data sources by epistemological status — observed behaviour, statistical estimates, enforcement actions, authorisation — rather than collapsing them into a single confidence number. The regulator framework doesn't need that separation because its data is already adjudicated. A commercial tool built on open sources does."*

---

## The one-sentence summary

**You compute a per-event behavioural score from AIS data anchored in Miller et al. 2018, with a spatial regulatory factor for MPA intersection anchored in Seguin et al. 2025 and Raynor et al. 2025, apply structural multipliers from enforcement lists and authorisations as principled amplifiers of existing signal, sum to vessel level, and classify into bands — where structural factors only amplify behavioural signal and never create risk in its absence.**
