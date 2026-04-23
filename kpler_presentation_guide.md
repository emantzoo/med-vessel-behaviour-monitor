# Presenting the Med Vessel Behaviour Monitor at Kpler

## The 30-Second Pitch

"I built a multi-source maritime intelligence dashboard that cross-references AIS vessel behaviour from Global Fishing Watch against four independent regulatory data sources — EU fisheries records, IUU vessel blacklists, ICCAT authorization registries, and OFAC sanctions lists — to contextualise suspicious events in the Mediterranean. It turns raw AIS alerts into actionable intelligence by answering not just 'what happened' but 'does this make sense given what we know about fishing in this area, who this vessel is, and whether anyone should be doing business with it.'"

## Know Your Audience

Kpler is a commercial maritime data intelligence company. They sell to commodity traders, compliance teams, and government agencies. Their IUU Fishing Analyst role is about helping clients detect and assess illegal fishing risk using vessel tracking and regulatory data.

They care about: multi-source data integration, analytical reasoning, regulatory knowledge, scalable tooling, and the ability to communicate findings to non-technical stakeholders.

They do NOT care about: academic fisheries science, R packages, MCDA methodology, or theoretical frameworks. Keep it operational and practical.

## Tab Structure

The app is organised into four top-level tabs (with subtabs grouping related views) sized for a 30-minute demo:

1. **Vessel Investigation** — four-layer view: framework methodology, structured narrative, per-vessel coloured risk tree, cumulative risk trajectory chart (behavioural arc over time). Quick-select table for vessel switching. Case-file Markdown export. The AQUARIS-style deep dive.

2. **Fleet Analytics** — five subtabs covering all fleet-level views:
   - *Ranking* — vessel-level aggregation table with pill filters, risk bands and compounding multipliers, the four Kpler-aligned flags (industrial profile, multi-behaviour, dark port call candidate, repeat offender), the two vessel-identity columns (`vessel_class` descriptive label + `vessel_type_mismatch` Grey Fleet "irregular vessel information" flag), and a sortable length / GT profile column. Primary Kpler-vocabulary view.
   - *Exploration* — behavioural deep dives: repeat offenders, encounter/carrier alerts, AIS gap behaviour.
   - *Trends & Patterns* — risk heatmap, daily and monthly trend, type mismatch by vessel class. Secondary charts (flag breakdown, event types pie, duration distribution) in collapsed expanders.
   - *Fisheries Context* — FDI overlay, c-square context, species landings. Geographic risk breakdown in an expander.
   - *Fishing Activity* — GFW-classified fishing events with leaf attribution scatter map and vessel table. Toggle filters for MPA-only, non-GFCM flag, vessels with/without behavioural events.

3. **Reference & Methodology** — risk tree diagram from `risk_tree_framework.yaml`, end-to-end scoring pipeline, risk-band table, and per-multiplier tables. Direct conceptual link to Kpler's April 2026 shadow fleet risk tree blog post.

4. **AI Analyst** — Gemini 2.5 Flash interface with RAG knowledge base and sandboxed code execution. Conceptual parallel to Kpler's MCP beta.

Related views are grouped one level down via subtabs, and secondary diagnostic charts live inside collapsed expanders, keeping the main navigation clean while preserving the full analytical depth for follow-up questions.

## Suggested demo walkthrough (30 minutes)

1. **Vessel Investigation** — drill into one high-risk vessel. Walk through the four-layer view. This is the AQUARIS-style narrative in fisheries. Lead with the strongest signal.

2. **Fleet Analytics -> Trends & Patterns** — open on the risk heatmap and daily trend. The visual hook. Show monthly event-type trend as a direct analogue to Kpler's Graph 4 in the *Turning Tides* whitepaper.

3. **Fleet Analytics -> Ranking** — the Kpler-vocabulary moment. Point out risk bands (Low / Emerging / Elevated / Severe / Critical >=100), the base vs compounded score decomposition, the four Kpler-aligned flags (one structural + three temporal/compound), the vessel_class descriptor + vessel_type_mismatch identity flag (the open-data Grey Fleet "irregular vessel information" indicator -- KOOSHA 4 demos the obvious case, LEONARDO PADRE the subtle case), and the worst actors ranked by total risk. Use pill filters to narrow the view. The **Exploration** subtab has repeat offenders, encounter analysis, and AIS gap behaviour.

4. **Reference & Methodology** — step back to the framework. Name the direct link to Kpler's April 2026 shadow fleet risk tree blog post.

5. **Fleet Analytics -> Fisheries Context** — show the FDI overlay. This is the differentiator vs Kpler's oil and gas focus. Point out that no Kpler whitepaper covers fisheries as a product area.

6. **AI Analyst** — close with a live query. Frame it as the conceptual parallel to Kpler's MCP beta: LLM layered over structured risk data.

## Detailed click-throughs (use inside the walkthrough above)

### Open with the map (30 seconds)

Open the live app. Let the map load with the static dataset. Point out the colour-coded dots: "Red is AIS gaps — vessels going dark. Orange is loitering. Purple is encounters between vessels. The black dots are vessels matched against the IUU vessel blacklist. The dark red dots are OFAC-sanctioned vessels — the highest compliance priority. Dot size encodes the risk band — larger means higher risk. Low-risk events are filtered out of the map to keep the signal clean."

Don't explain every marker. Let them absorb the visual, then move to specifics.

### Show an OFAC-sanctioned vessel (60 seconds)

Click on a dark red marker (SABITI or ADRIAN DARYA 1). "These are real OFAC-sanctioned Iranian tankers. SABITI is on the SDN list under the Iran sanctions program. Any commercial entity transacting with this vessel faces secondary sanctions exposure. The risk model applies a 2.5x multiplier on top of the Iranian flag multiplier and any behavioural factors. This is the kind of vessel where Kpler's compliance clients would want an immediate alert — not a fisheries case, but a sanctions case where the maritime intelligence framework still applies."

This demonstrates: understanding that the same risk model framework works across compliance use cases — sanctions, IUU fishing, regulatory authorization. The architecture is general; the data layers determine the use case.

### Show an IUU match (60 seconds)

Click on a black marker (KOOSHA 4). Walk through the popup: "This is KOOSHA 4, Iranian-flagged, GFCM-listed for IUU fishing in the Mediterranean. It matched via MMSI — the strongest identity match. Its risk score is multiplied by 3x because it has a confirmed IUU history in these waters. The FDI baseline below shows this c-square has 200 fishing days of trawl activity and high-value hake landings — so this is an active fishing ground where an IUU vessel showing up is operationally concerning."

This demonstrates: multi-source cross-referencing, identity matching, risk compounding, fisheries context — all in one popup.

### Show an ICCAT-authorized vessel (60 seconds)

Select FRIO NARUTO from the Vessel Investigation dropdown (or find it in the Ranking table — it carries an ICCAT authorization label). "This is a Bahamas-flagged carrier, ICCAT-authorized — meaning it's legally permitted to transship tuna in the Med. It appeared in an encounter event. The risk model gives it a 1.4x multiplier because authorized carriers have the infrastructure and cover to launder unauthorized catch through legitimate channels. ICCAT-authorized vessels no longer get separate blue map markers — authorization is an opportunity indicator, not a risk signal, so they're rendered like any other vessel by event type. The question an analyst should ask is: was this transshipment under ICCAT Regional Observer Programme coverage? If not, why not?"

This demonstrates: understanding that authorization is an opportunity indicator, not exoneration. This is a nuanced analytical point that shows domain depth.

### Show the vessel-type-mismatch flag (60 seconds — the Grey Fleet beat)

Open the **Ranking** subtab. Sort by the `type_mismatch` column. Two vessels surface in the static demo:

- **KOOSHA 4** — Iranian-flagged, IUU-listed (already covered in the IUU walkthrough). Event-level `vessel_type` says FISHING, registry `shiptypes` says cargo. The obvious case: a deceptive vessel broadcasting one identity in AIS while its registry record says another.
- **LEONARDO PADRE** — Italian-flagged, ICCAT-authorised artisanal vessel. Event-level `vessel_type` says FISHING, registry `shiptypes` says carrier. The subtle case: a vessel that passes IUU, OFAC, and ICCAT cross-reference cleanly, but whose two self-reported identity fields disagree at the class level.

"This is the Kpler *Grey Fleet* paper's 'irregular vessel information' indicator on open data. The event-level `vessel_type` comes from the GFW Events API — often AIS self-reported. The registry `shiptypes` comes from the GFW Vessels API — `registry_info` and `self_reported_info`. Both fields are normalised through the same canonical class taxonomy, and the flag fires only when both are populated and map to **different** classes. So `TRAWLER` versus `FISHING` does not trigger — both map to `industrial_fishing`. `FISHING` versus `CARGO` does. The class-level comparison is what makes the flag actually useful — string-level would drown in spelling-variant false positives."

Open the **Type mismatch by vessel class** expander. The horizontal bar visualises the two mismatches grouped by their registry-side class, and a small detail table lists exactly which event-level vs registry-level disagreement fired. "Display-only — never multiplied into the risk score, fires the `identity_misrepresentation` leaf in the risk tree at medium severity. Same family as the four other Kpler-aligned flags."

This demonstrates: open-data parity with a Kpler proprietary indicator, careful design that avoids false positives, awareness that Grey Fleet vocabulary applies to fisheries as much as to oil tankers.

### Show the Fisheries Context tab (60 seconds)

Switch to the **Fisheries Context** subtab. "This subtab overlays GFW events against the EU's official fisheries data. The FDI choropleth now covers all Mediterranean c-squares (not just near events), so you can see the full effort baseline at a glance. Each event is mapped to a c-square — a 0.5 degree grid cell used by STECF for fisheries reporting. I can see whether an event occurred in a known fishing ground, what species are typically caught there, and what the economic value is. High-value c-squares — swordfish, bluefin tuna areas — are where transshipment risk is highest because the incentive to launder unauthorized catch is strongest."

This demonstrates: spatial analysis capability, understanding of EU fisheries data infrastructure, economic reasoning about IUU incentives.

### Show the Vessel Investigation tab (90 seconds — the methodology + the case file)

Switch to the **Vessel Investigation** tab. Open the "Risk Assessment Framework (methodology)" expander at the top.

The graphviz diagram renders showing the full Mediterranean IUU risk tree — eight branches (identity, flag risk, regulatory status, authorization, behavioural history, spatial context, network exposure, fishing activity) feeding into five tier outcomes (Critical, High, Elevated, Moderate, Low). Walk through it briefly:

"I read your April blog post on building risk trees for shadow fleet exposure. The methodology transfers cleanly to IUU fishing — same playbook, weak flags, dark vessels, opaque ownership, suspicious encounters. I built the Mediterranean IUU equivalent. The structure has three branch types: gating branches like identity verification and sanctions status that override everything else, additive branches like flag risk and behavioural history that contribute cumulatively, and contextual branches like fishing authorization that don't fit either category cleanly."

"The compound logic matters. A flag of convenience alone tells you nothing. A flag of convenience plus an AIS gap plus an encounter with a reefer near the Libyan EEZ tells you a lot. The framework encodes those combinations explicitly rather than flattening them into a multiplicative score."

"Since you last saw the tree, I've added a fishing activity branch with four leaves that analyse GFW-classified fishing events: fishing inside any MPA, fishing inside a no-take zone — using GFW's own mpaNoTake signal as primary and a curated CSV for Med-specific closures as fallback — a gap-then-fishing evasion sequence, and an anomalous-location detector for EU vessels fishing in the bottom 5% of FDI effort cells. Plus two FAO 'unregulated' leaves: stateless vessel and non-GFCM-party flag in the Med. That brings the tree to 41 leaves across 8 branches."

Collapse the framework expander. Then select KOOSHA 4 from the dropdown, click Run Investigation.

The 10-step structured report renders instantly: identity confirmation, IUU listing status (red error box), ICCAT check, OFAC check, fisheries context, behavioural pattern, risk decomposition, hypothesis, external links, threat assessment.

Below the risk tree, the **risk trajectory** chart shows the cumulative risk score over time — each event marker shows when the vessel crossed band thresholds. For KOOSHA 4, the line shoots into Critical on the first GAP event alone.

"This is the framework applied to a specific vessel. The methodology document above shows how an analyst would think about IUU risk. The investigation below executes that same logic against the data — rule-based, deterministic, no LLM. The trajectory chart shows *when* the risk accumulated — the behavioural arc over the observation window, the same framing you used in the AQUARIS case study in Turning Tides."

This demonstrates: structured analytical thinking, the ability to encode domain expertise as rules, direct extension of Kpler's published methodology into an adjacent domain, temporal-arc analysis, and awareness that LLMs aren't always the right tool for the job.

### Show the AI Analyst (90 seconds — take your time here)

This is the feature that separates your project from every other "I made a dashboard." Kpler launched their own MCP for maritime intelligence in early 2026. Showing you've built a working conversational analytics layer on top of maritime data is directly aligned with where their product is heading.

**First query — cross-source intelligence:**

Switch to the AI Analyst tab. Ask: "Show me IUU-listed vessels in c-squares with high swordfish landings."

Wait for Gemini to generate and execute the code. While it runs, explain: "The AI has access to all seven dataframes — GFW events, FDI effort, FDI landings, IUU vessel list, ICCAT authorized vessels, OFAC sanctions, and fishing events. It can join across them, filter, aggregate, and produce charts. The code it writes runs in a sandboxed environment — only pandas, numpy, and plotly are available, no filesystem or network access."

**Second query — full vessel investigation (the closer):**

Type: "Investigate KOOSHA 4."

The AI detects the vessel name, runs the deterministic risk tree evaluation from `investigation.py`, and injects the full trace as a STRUCTURED EVIDENCE block into its system prompt. It then walks through ten structured steps grounded in the specific leaves that fired and the severities assigned — identity confirmation, IUU listing history, ICCAT authorization status, OFAC sanctions check, fisheries context for the event location, behavioural pattern analysis and network exposure, risk score decomposition, hypothesis generation, external lookup links, and a summary threat assessment.

Explain while it runs: "This is what an analyst would do manually — cross-reference five data sources, build a vessel profile, generate hypotheses, decide what to escalate. The AI does it in one query, but it's not reasoning from scratch — the deterministic risk tree runs first and its results are injected as structured evidence. The AI grounds its narrative in those specific leaf evaluations. The output includes MarineTraffic and VesselFinder links so the analyst can verify current position and ownership directly without leaving the workflow."

**What to say about the architecture:**

"The RAG approach means the AI doesn't hallucinate about maritime concepts — it has specific, curated knowledge about IUU indicators, GFCM regulations, ICCAT observer programmes, OFAC sanctions programs, and the investigation workflow itself. The live dataframe schema is injected into the system prompt so the AI knows exactly what columns are available and what's queryable. For vessel-specific queries, it also receives a STRUCTURED EVIDENCE block — the full deterministic risk tree trace from `investigation.py`, showing which of the 41 leaves fired and at what severity. The AI is instructed not to contradict those results."

"The sandbox is important — generated code can only read the data and produce visualisations. It can't modify the source dataframes, access the filesystem, or make network calls. That matters when you're executing AI-generated code against compliance-sensitive data."

**The MCP framing (use this if they bring up Kpler MCP, or proactively if the conversation goes there):**

"This is conceptually the same pattern as Kpler's MCP — natural language in, structured maritime intelligence out. The user asks a question, the LLM translates it into executable analysis against the underlying data, the results come back as narrative plus visualisation. I built this because I thought it was where the industry was heading. Glad to see Kpler is already there — the MCP product is exactly the architecture I'd want to work on."

**If they ask about limitations:**

"Each question is independent — there's no multi-turn memory yet, so you can't say 'now filter that to 2024.' That's a deliberate simplification for the portfolio version. In production you'd maintain conversation history. The AI also can't currently make external lookups — it generates clickable links instead. With Claude's API and web search enabled, the investigation could include live external data pulls during the analysis itself."

This demonstrates: LLM integration in a production-style app, RAG with domain-specific knowledge AND structured analytical workflows, sandboxed code execution, cross-source data querying, and understanding of where maritime intelligence products are heading. The investigation walkthrough is the moment that turns the dashboard into an intelligence tool.

### Close with the risk formula (30 seconds)

Open the methodology sidebar. "The risk scoring replicates GFW's published transshipment detection criteria from Miller et al. 2018. Duration, proximity, speed, vessel type, flag state, shore distance, MPA intersection — all compound multiplicatively into the base score. IUU, ICCAT, and OFAC multipliers stack on top. So the riskiest event in the dataset is one involving an IUU-listed, ICCAT-authorized, OFAC-sanctioned carrier vessel in an encounter far from shore with an Iranian flag inside a GFCM Fisheries Restricted Area."

The MPA factor is applied at the event level from the GFW `regions.mpa` field, which returns a pre-computed point-in-polygon intersection against WDPA. MPAs are classified into three regulatory tiers: GFCM FRA (`gfcm_fra` 2.0x, legally binding under Council Regulation 1967/2006), EU-designated marine site (`eu_site` 1.5x, includes Natura 2000 and Pelagos Sanctuary), general WDPA entry (`general` 1.2x). Welch et al. 2025 (Science) is the methodological backbone; McDonald et al. 2024 (Nature) bounds the approach as a lower-bound indicator (~90% of fishing vessels inside MPAs do not broadcast AIS).

## Questions They Might Ask (and how to answer)

### "How would you scale this to cover all oceans, not just the Med?"

"The architecture is region-agnostic. The GFW API covers the entire globe. The c-square grid system works anywhere. The IUU vessel list is already global — 13 RFMOs. The only Med-specific component is the FDI data, which covers EU waters. For non-EU regions, you'd substitute equivalent fisheries data — FAO regional catch statistics, or national logbook data where available. The risk model and matching logic don't change."

### "The GFW Events API only gives you suspicious events. How would you get a complete picture?"

"You're right — GFW events are pre-filtered for suspicious behaviour. For a complete operational picture, you'd need continuous AIS position data (which Kpler already has) and run your own fishing activity detection algorithms. My app demonstrates the analytical framework — multi-source cross-referencing, identity resolution, risk scoring — on top of GFW's event feed. The same framework would apply on top of Kpler's own AIS data pipeline."

### "How reliable is vessel name matching?"

"It's the weakest link. IUU vessels change names deliberately. Name matching has three tiers in the app: MMSI exact (highest confidence), IMO exact (high — permanent hull identifier resolved via GFW Vessels API), and name matching (medium to low). I display the match type and confidence level in the UI so analysts can assess reliability. The proper long-term solution is a vessel identity graph that tracks name/flag/ownership changes over time — which is essentially what Kpler's vessel database does."

### "Why did you treat ICCAT authorization as a risk multiplier rather than a mitigating factor?"

"Authorization provides access, cover, and infrastructure. An authorized carrier in an encounter event isn't necessarily doing something wrong — but it has the means to do so more effectively than an unauthorized vessel. The multiplier is modest (1.2-1.4x) precisely because authorization alone doesn't indicate wrongdoing. It's an opportunity indicator, not an accusation. The highest-priority signal in the entire system is a vessel that is both IUU-listed and ICCAT-authorized — confirmed history plus current access."

### "What data sources would you add next?"

"Three priorities. First, GFCM stock assessment data — stock status by area and species, so events in critically overfished zones get prioritised. Second, EU sanctions vessel lists beyond OFAC for full coverage. Third, port state control inspection data from the Paris and Med MoU — vessels with detention history appearing in suspicious events are higher priority targets. All three are publicly available."

### "What features would you add next?"

"The risk tree framework I showed you is the methodology layer. The natural next step is to make it dynamic — per-vessel tree visualisation where the diagram highlights the specific path a vessel took through the framework. The static framework I built is the document. The interactive version would be the runtime. I scoped that out as a deliberate choice — the framework spec is where the analytical thinking lives, and the investigation tab already executes the same logic per-vessel. Building the interactive tree would be a presentation enhancement, not new analysis."

"Beyond that — an ownership network graph. Most IUU operations involve multiple vessels under common beneficial ownership, and visualising those relationships would expose patterns that single-vessel risk scores miss. Kpler's vessel ownership API would be the natural data source. That's where the existing framework would extend most naturally."

### "How does this compare to what Kpler already offers?"

Don't pretend your portfolio project competes with a commercial platform. But show you've done your homework: "I reviewed Kpler's Compliance API schema. The risk categories map directly — AIS gaps, dark STS events, flag risks, sanctions screening all have equivalents in my risk model. The architecture is similar: compound multiple risk signals into a consolidated vessel risk indicator, which is what Kpler launched in March 2026.

Where my tool adds a dimension Kpler's compliance product doesn't currently cover is the fisheries-specific layer — linking vessel behaviour to officially reported catches and effort via FDI spatial data, and cross-referencing against ICCAT fishing authorization records. That's the IUU fishing intelligence layer on top of the general maritime compliance framework. For an IUU Fishing Analyst role, that's the relevant gap — Kpler has world-class AIS and sanctions data, but fisheries context is what turns a compliance alert into an IUU intelligence product."

### The four-of-six framework line (memorise this)

From Kpler's "How Deception Detection Works" brief:

"What was once a binary question — is the vessel sanctioned or not? — has evolved into layered risk assessment across six dimensions."

The six Kpler risk layers are: formal sanctions status, behavioural indicators, associative risk, geographic risk, cargo risk, ownership opacity.

Med Vessel Monitor implements four and a half of these six layers:

1. **Formal sanctions status** — TMT Combined IUU List, ICCAT IUU list, OFAC SDN screening, GFW Insights API live IUU cross-reference, plus FAO "unregulated" detection (stateless vessels, non-GFCM-party flags)
2. **Behavioural indicators** — GFW gap, encounter, loitering events aligned with Miller et al. 2018, plus fishing activity analysis (fishing in no-take MPAs via GFW `mpaNoTake`, gap-then-fishing evasion sequences, anomalous fishing locations)
3. **Associative risk** — five encounter-partner leaves in the risk tree's network_exposure branch: partner name matched against IUU list (high), partner name matched against OFAC SDN (critical), partner flag in weak-cooperation Med coastal set (LBY/SYR, medium), partner flag in distant-water/non-Med FoC set (medium), encounter pattern recurrence (same counterparty 2+ times within 90 days, medium). First-degree only — fleet-network propagation and ownership graph still out of scope.
4. **Geographic risk** — GSA-based hotspot weighting, shore distance factor
5. **Cargo risk** — ICCAT species multipliers (BFT 1.3x, SWO/ALB 1.2x, carrier 1.4x) as the fisheries-cargo equivalent

The remaining gap is **ownership opacity** (beneficial ownership unwinding). This is the layer where Kpler's Maritime 2.0 ownership graph adds value over an open-source stack. Associative risk is partially implemented (first-degree encounter-partner checks) but fleet-network propagation requires the same ownership data. Naming the gap honestly in Kpler's own vocabulary is a pitch strength, not a weakness.

### Kpler Compliance API Alignment (know this for technical conversations)

Their API has four risk categories. Here's how your app maps:

```
KPLER                                    YOUR APP
-----                                    --------
OperationalRisks.aisGaps                 GAP events + intentional disabling + implied speed
OperationalRisks.darkStsEvents           ENCOUNTER events (vessel meetings)
OperationalRisks.stsEvents               ENCOUNTER + ICCAT carrier matching
SanctionRisks.sanctionedVessels          OFAC SDN cross-reference (2.5x multiplier)
SanctionRisks.sanctionedFlag             Flag multipliers + OFAC program data
FlagRisks.flagOfConvenience              IUU Risk Index flag multipliers (152 countries)
FlagRisks.flagRankings (MoU lists)       FLAG_RISKS dict (loaded from IUU Risk Index CSV)
ManagementRisks.portStateControl         Planned enhancement
AisSpoof (spoofing detection)            Not in your app
FleetStatusCounters                      KPI metrics (events, IUU/OFAC counts, risk)
```

What you have that their Compliance API doesn't:
- FDI fisheries baseline (catch/effort per c-square)
- ICCAT authorization cross-reference
- Species-level economic context
- GFW fishing activity analysis (no-take MPA detection, gap-then-fishing evasion, anomalous location detection)
- FAO "unregulated" fishing detection (stateless vessels, non-GFCM-party flags)
- GFW Insights API cross-references (RFMO authorization from 40+ registries, live IUU list)
- AI natural language querying across all sources

What they have that you don't:
- AIS spoofing detection
- Ownership layer analysis (beneficial owner, operator, ISM, P&I)
- Cargo-level sanctions (commodities, HS codes)
- Port state control (inspections, detentions)

If asked "what would you build first at Kpler?": "The fisheries context layer. Kpler already has best-in-class AIS, sanctions, and ownership data. What's missing for IUU-specific intelligence is the fisheries dimension — what's being caught where, who's authorized to catch it, and whether vessel behaviour aligns with legitimate fishing patterns. That's what I'd integrate."

### "Tell me about the FDI data — what are its limitations?"

"FDI is compiled annually by EU Member States and reviewed by STECF. It's not raw declarations — it's statistically processed estimates raised from logbooks, sales notes, and sampling. The spatial data uses 0.5 degree c-squares, which is much coarser than AIS resolution, so I aggregate GFW events up to that grid. Mediterranean spatial data is only reliable from 2017 onwards, and there's no coverage for non-EU waters — Libya, eastern Med, North Africa. Confidentiality suppression means some c-squares with fewer than 3 vessels are omitted. I display these coverage gaps in the app rather than hiding them."

## Vocabulary notes

- Use "grey fleet" and "shadow fleet" as near-synonyms. The March 2025 paper is titled *Grey Fleet*; the December 2025 flagship report uses *shadow fleet* as the primary umbrella term. Let Amanda lead on which one she uses first.

- "Dark activities" is an action, not a fleet. A vessel conducts dark activities; it is not a dark vessel.

- "Deceptive shipping practices" (DSP) is the Kpler-preferred umbrella for the behavioural category.

- Say "compounding risk", "score band", "threshold breach", "behavioural signal", "structural amplifier". These are Kpler's exact words from the December 2025 report.

- Reframe "AIS gap detection" as "dark activity detection" where natural — same code, Kpler's language.

## Key Kpler numbers to cite (from Turning Tides, Dec 2025)

- **302 high-risk vessels predicted in October 2025; 42 sanctioned by December 2025** — 14% confirmation rate in approximately two months. This is the single strongest data point in Kpler's 2025 material.

- **686 newly designated vessels in 2025** — the most active enforcement year on record.

- **Shadow fleet approximately 3,300 vessels by December 2025**, moving approximately 3,733 million barrels of oil — 6 to 7% of global crude flows.

- **Dark STS activity up 129% year-on-year**; AIS spoofing up 18.3%.

- **Over USD 100 billion** of crude moved through shadow and sanctioned shipping networks in 2025.

- **80.1% of eventually-sanctioned spoofing vessels** were designated within 12 months of their first spoofing incident (descriptive, not predictive — distinction matters if probed).

- **Case study: AQUARIS (IMO 9251822)**, Iran-linked tanker, OFAC-sanctioned 20 November 2025 after a textbook behavioural arc of Iranian port calls, AIS spoofing, dark STS in Iranian zones, and detention in Dalian. Kpler frames this as proof that behavioural signals predict designation.

- **VCLL Skipper seizure (10 December 2025)** — sanctioned tanker carrying Venezuelan crude intercepted at sea by US forces. Signals enforcement expansion beyond designation into physical interdiction.

- **Kpler closing tagline from Turning Tides:** "In 2026, Kpler Risk and Compliance won't chase risk, it will predict it."

- **Kpler score bands** (mirror in your own vocabulary): Low, Emerging, Elevated, Severe, Critical at score >=100.

- **MPA non-compliance base rate** (Seguin et al. 2025, *Science*): industrial fishing detected in **47% of coastal MPAs** studied -- AIS-based MPA intersection reliably surfaces a non-compliant tail that is broader than commonly assumed. Raynor et al. 2025 (Science) finds **9x fewer fishing vessels** in fully and highly protected MPAs vs unprotected coastal waters, anchoring GFCM-FRA as the strictest enforcement category.

- **AIS coverage gap inside MPAs** (McDonald et al. 2024, *Nature*): approximately **90% of fishing vessels inside MPAs do not broadcast AIS**, making AIS-based intersection a lower-bound indicator. The MPA factor in the app is anchored on broadcasting vessels only, complementary to the AIS-gap evasion signal rather than a replacement for SAR verification.

## What NOT to Say

- Don't call it "real-time monitoring" — it's a snapshot, not a live feed
- Don't claim the risk scores are validated — they're a demonstration of methodology, not operationally verified
- Don't overstate the matching reliability — be upfront about name matching limitations
- Don't try to explain the MCDA methodology from the tools4MCDA paper — it's not relevant to the role
- Don't apologise for it being a portfolio project — own it as a demonstration of analytical capability
- Don't compare it unfavourably to Kpler's products — frame it as complementary thinking

## Architecture Cheatsheet

Know this cold. If they ask "walk me through the code" or "how is it structured," you can answer confidently.

### File Map

```
app.py              → Orchestrator. Loads data, runs filters, applies risk
                      scoring, renders PyDeck (deck.gl) map, dispatches to
                      the 4 top-level tabs (with subtabs). Entry point.

config.py           → Constants and pure functions. Event weights, flag risk
                      multipliers (loaded from IUU Risk Index CSV, 152 countries),
                      IUU multipliers (GFCM=3.0x, other=2.0x),
                      ICCAT multipliers (carrier=1.4x, BFT=1.3x, SWO=1.2x),
                      OFAC multiplier (2.5x), RISK_BANDS definitions
                      (Low / Emerging / Elevated / Severe / Critical),
                      species name lookup, forbidden code list for sandbox.
                      Two spatial helpers: classify_med_zone() (longitude
                      bands) and assign_csquare() (maps point to 0.5dd grid).
                      classify_risk_band() assigns the final band label.
                      EEZ_MRGID_NAMES dict + resolve_eez_name() for resolving
                      GFW numeric MRGID region IDs to country names.

data_loading.py     → All data ingestion. Loaders, all @st.cache_data:
                      - load_static_data() → 95-row CSV or synthetic gen
                      - load_live_data() → GFW Events API (async, 3 datasets)
                      - load_fdi_effort() → ~83K rows, Med fishing days
                      - load_fdi_landings() → ~212K rows, Med catch/value
                      - load_iuu_vessels() → 369 IUU-listed vessels
                      - load_iccat_vessels() → 9,203 Med-authorized vessels
                      - load_ofac_vessels() → OFAC SDN sanctioned vessels
                      - lookup_vessel_imos() → GFW Vessels API, MMSI→IMO
                      - load_closed_area_mpas() → curated no-take/closed
                        MPAs (Tier 2 fallback for fishing_in_closed_area)
                      - download_insights_snapshot() → GFW Insights API v3
                        batch query (RFMO auth, AIS coverage, IUU cross-ref)
                        uses vessel_id already in event data (no extra API call)
                      - load_snapshot_insights() → cached Insights API data

risk_model.py       → All scoring and matching logic:
                      - compute_risk_score() → base behavioural risk per event
                      - get_fdi_context() → FDI baseline for a c-square
                      - check_iuu_match() → MMSI→IMO→name priority chain
                      - match_iuu_vessels() → applies IUU to all rows
                      - check_iccat_match() → IMO→name priority chain
                      - match_iccat_vessels() → applies ICCAT to all rows
                      - check_ofac_match() → MMSI→IMO→name (no fuzzy)
                      - match_ofac_vessels() → applies OFAC to all rows
                      - detect_gap_then_fishing_sequence() → AIS dark then
                        fishing within 72h (IUU evasion signature)
                      - get_low_effort_csquares() → bottom 5% FDI effort
                        c-squares for anomalous-location detection
                      - attribute_leaves_to_fishing_events() → per-event
                        leaf attribution for Fishing Activity scatter map
                      - get_low_effort_csquares() → bottom 5% FDI effort
                        c-squares for anomalous-location detection

investigation.py    → Deterministic vessel investigation (rule-based, no LLM):
                      - investigate_vessel() → multi-step structured report
                      - Evaluates 41 risk tree leaves across 8 branches
                      - Reads all dataframes, applies rule-based logic
                      - Returns structured dict for UI rendering
                      - Fishing activity branch: fishing_in_mpa,
                        fishing_in_closed_area (two-tier: mpaNoTake + CSV),
                        gap_then_fishing_sequence, fishing_in_low_effort_cell
                      - GFW Insights leaves: gfw_iuu_crosscheck,
                        gfw_no_rfmo_authorization (when insights available)
                      - No API calls, no LLM, instant results
                      - Used by the Vessel Investigation top-level tab
                      - For vessel-specific AI analyst queries, the risk tree
                        trace is injected into the Gemini system prompt as a
                        STRUCTURED EVIDENCE block (upstream to the LLM)

risk_tree.py        → Med IUU Risk Tree framework rendering:
                      - load_framework() → reads risk_tree_framework.yaml
                      - render_framework_tree() → graphviz diagram, with
                        optional per-vessel severity colouring and tier
                        highlighting
                      - Adapted from Kpler's April 2026 shadow fleet
                        risk tree blog post

data/risk_tree_framework.yaml → Analytical framework specification:
                      - 8 branches (gate / additive / contextual types)
                      - 41 leaf questions (35 wired, 6 future work)
                      - Compound logic rules for tier assignment
                      - 5 tier outcomes (Critical → Low)
                      - Documented methodology, not executable code

tabs.py             → Render functions invoked from the 4 top-level tabs,
                      their subtabs, and their expanders. Each receives
                      df_filtered + supplementary data. Render functions
                      are preserved even when moved into subtabs/expanders.

                      Top-level tabs (defined in app.py):
                      1. Vessel Investigation: per-vessel structured
                           report + coloured risk tree + risk trajectory
                           chart + case-file export + quick-select table
                      2. Fleet Analytics — five subtabs:
                         - Ranking: vessel-level aggregation with
                           pill filters, risk bands and Kpler-aligned flags
                         - Exploration: repeat offenders / encounter
                           analysis / gap behaviour
                         - Trends & Patterns: risk heatmap + daily/monthly
                           trends; flag breakdown, event types, duration
                           distribution in expanders
                         - Fisheries Context: FDI overlay; geographic
                           risk breakdown in expander
                         - Fishing Activity: GFW-classified fishing events
                           with leaf attribution, scatter map, vessel table
                      3. Reference & Methodology — risk tree diagram,
                         scoring pipeline, multiplier tables
                      4. AI Analyst — Gemini 2.5 Flash sandboxed interface

ai_analyst.py       → Gemini 2.5 Flash integration:
                      - build_system_prompt() → schema + RAG knowledge
                      - is_safe_code() → sandbox check vs FORBIDDEN_CODE
                      - render_ai_analyst() → UI + API call + exec()
                      - exec namespace: df, fdi_effort, fdi_landings,
                        iuu_vessels, iccat_vessels, ofac_vessels, fishing_df,
                        pd, np, px, go

exports.py          → Export helpers for analyst workflow:
                      - generate_vessel_case_file() → Markdown per vessel
                        (identity, risk summary, events, risk tree, narrative)
                      - generate_vessel_case_html() → HTML per vessel with
                        embedded interactive Plotly charts (trajectory + icicle)
                      - generate_fleet_summary() → CSV + Markdown cover
                        (scope, band distribution, top vessels, methodology)
                      - generate_fleet_summary_html() → HTML fleet report
                      - Wired to download buttons in Investigation + Ranking
```

### Data Pipeline (execution order in app.py)

```
1.  Load data         load_live_data() or load_static_data()  [snapshot window: 30 days]
2.  Load reference    load_fdi_*(), load_iuu_vessels(), load_iccat_vessels(), load_ofac_vessels(),
                      load_closed_area_mpas()
3.  Filter            duration >= min_duration slider
4.  Score             compute_risk_score() → base risk_score column
5.  Spatialise        assign_csquare() → csq_lon, csq_lat columns
6.  Resolve identity  lookup_vessel_imos() → imo column (live only)
7.  Preserve base     base_risk_score = risk_score snapshot (pre-multiplier)
8.  IUU match         match_iuu_vessels() → iuu_* columns, risk *= iuu_multiplier
9.  ICCAT match       match_iccat_vessels() → iccat_* columns, risk *= iccat_multiplier
10. OFAC match        match_ofac_vessels() → ofac_* columns, risk *= ofac_multiplier
11. Classify band     classify_risk_band() → risk_band column (Low..Critical)
12. Join fishing      aggregate_fishing_in_mpa() + GFW Insights (optional)
13. Render map        PyDeck ScatterplotLayer (colour: OFAC dark red > IUU black > event type; size = risk band)
14. Render tabs       4 top-level tabs (with subtabs) dispatched with df_filtered + reference data
15. AI analyst        Gemini with RAG + sandboxed code execution + 41-leaf risk tree trace
```

### Identity Matching Chain

```
IUU matching:    MMSI exact (high) → IMO exact (high) → name exact (medium) → name fuzzy (low)
ICCAT matching:  IMO exact (high) → name exact (medium, min 4 chars)
OFAC matching:   MMSI exact (high) → IMO exact (high) → name exact (no fuzzy — legal risk)
```

### Risk Score Composition

```
base = (duration_h ^ 0.75) x event_weight x flag_multiplier x shore_factor x mpa_multiplier
     x encounter_factors  (proximity + speed + vessel_type)
     x loitering_factors  (vessel_type + avg_speed)
     x gap_factors        (intentional_disabling | implied_speed_knots)

final = base x iuu_multiplier x iccat_multiplier x ofac_multiplier

All multipliers compound. A worst-case event:
  TWN flag (1.96) x GFCM IUU (3.0) x OFAC sanctions (2.5) x ICCAT carrier (1.4)
  x encounter proximity (1.8) x speed (1.5) x vessel type (1.4)
  x shore >20nm (1.5) x MPA gfcm_fra (2.0) = 190x base score

MPA intersection factor (all event types, from GFW regions.mpa):
  gfcm_fra: 2.0  -- GFCM Fisheries Restricted Area, legally binding under Reg 1967/2006
  eu_site:  1.5  -- Natura 2000 marine, Pelagos Sanctuary, national MPAs
  general:  1.2  -- other WDPA entries, contextual signal only
```

All lookup-based multipliers (IUU, ICCAT, OFAC) apply at the event level, multiplying already-computed behavioural risk scores. A vessel with no suspicious AIS behaviour carries no risk score regardless of authorisation or listing status. ICCAT authorisation, flag risk, and sanctions listings therefore amplify behavioural signal rather than substituting for it. This is deliberate: ICCAT authorisation indicates *opportunity* (access to high-value species or transshipment capability), not *exoneration*, and only modifies risk when behavioural signal is already present.

After all multipliers are applied, the final compounded `risk_score` is classified into Kpler-aligned bands:

```
Low       (<50)       sparse risk signals
Emerging  (50-59)     first risk flags
Elevated  (60-79)     multiple risk indicators
Severe    (80-99)     compounding risk
Critical  (>=100)     threshold breach
```

The `base_risk_score` column preserves the pre-multiplier behavioural score, enabling explicit decomposition of how much of a vessel's risk comes from behaviour versus structural amplifiers.

### Map Marker Color Key

```
Dark red = OFAC-sanctioned vessel (highest priority, overrides all)
Black    = IUU-listed vessel (overrides event color)
Red      = AIS GAP event
Orange   = LOITERING event
Purple   = ENCOUNTER event
(Low-band events excluded from map; ICCAT markers removed — authorization is not risk)
```

## Key Numbers to Know

- 6 data sources cross-referenced (GFW, FDI, IUU, ICCAT, OFAC, GFCM register), with GFW providing four distinct feeds (Events API, `regions.mpa` WDPA intersection, `public-global-fishing-events` CNN classifier, Insights API v3)
- 95 demo events across 4 top-level tabs (Fleet Analytics has 5 subtabs; secondary charts in expanders)
- 369 IUU vessels (213 currently listed, 150 GFCM-listed)
- 9,203 ICCAT Med-authorized vessels
- ~1,000 FDI c-squares covering EU Med waters
- ~83K effort rows, ~212K landings rows
- 3-level identity matching: MMSI → IMO → vessel name
- Risk formula: 8 multiplicative factors compounding independently, then classified into 5 Kpler-aligned bands
- GFW methodology aligned with Miller et al. 2018
- 10-step structured investigation workflow — deterministic 41-leaf risk tree trace feeds LLM-powered (RAG) analysis
- Risk tree framework with 8 branches, 41 leaves, and 5 tier outcomes — adapted from Kpler's April 2026 shadow fleet methodology

## The One Thing to Communicate

You don't just monitor vessels — you contextualise their behaviour against multiple independent evidence streams. That's what separates a dashboard from an intelligence tool, and it's what Kpler sells.
