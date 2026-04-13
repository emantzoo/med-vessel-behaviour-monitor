# Risk Score Methodology

## GFW Alignment

This scoring model replicates and extends the Global Fishing Watch transshipment
detection methodology (Miller et al. 2018, "The Global View of Transshipment").

GFW classifies encounters when two vessels are:
- Within 500 meters of each other
- For at least 2 hours
- At median speed < 2 knots
- At least 10km from a coastal anchorage

GFW distinguishes two tiers:
- **Likely transshipment**: reefer + fishing vessel meet >20nm from shore
- **Potential transshipment**: reefer loiters alone (fishing vessel AIS off)

## Risk Score Formula

Each event is scored as:

```
risk = (duration_h ^ 0.75)
     x event_weight
     x flag_multiplier
     x shore_distance_factor
     x mpa_tier_multiplier
     x event_specific_factors
```

### Base Components
- **Event weights**: ENCOUNTER=5.0 (transshipment), GAP=3.2 (dark activity), LOITERING=2.0 (staging)
- **Flag multipliers**: Derived from the Poseidon IUU Fishing Risk Index
  (https://iuufishingindex.net/). The 10 Flag-responsibility indicators per
  country are averaged (score 1-5) and mapped linearly to a multiplier:
  `multiplier = 1.0 + (mean_score - 1.0) * 0.3`. Score 1 -> 1.0x, score 3
  -> 1.6x, score 5 -> 2.2x. 152 countries covered. Flags not in the Index
  receive 1.0x (neutral). Replaces earlier hand-curated multipliers inherited
  from shadow-fleet-tanker contexts. Regenerate via
  `scripts/prepare_iuu_risk_index.py`
- **Non-linear duration** (exponent 0.75): prevents single extreme events from dominating

### Shore Distance Factor (all event types)
- \>20nm (37km): 1.5x -- high suspicion zone (GFW "likely transshipment" threshold)
- \>10km: 1.2x -- GFW encounter threshold
- <10km: 0.8x -- near-shore, less suspicious

### Encounter-Specific Factors
- **Proximity**: <500m = 1.8x (GFW threshold), <1km = 1.3x, else 1.0x
- **Speed**: <2 knots = 1.5x (GFW "likely transfer" threshold)
- **Vessel type**: carrier/tanker = 1.4x (reefer encounters are key transshipment indicator)

### Loitering-Specific Factors
- **Vessel type**: carrier/tanker = 1.6x (GFW "potential transshipment" = reefer loitering alone)
- **Speed**: avg <2 knots = 1.4x (staging behaviour)

### Gap-Specific Factors
- **Speed change**: |speed_before - speed_after| > 5kn = 1.5x (evasion indicator),
  > 2kn = 1.2x (vessel was moving, went dark, reappeared at different speed)

## Vessel Investigation Template

When asked to investigate a specific vessel, follow this structured workflow
using all available data sources.

### Step 1: Identity Confirmation
Query the df for the vessel by name or MMSI. Report vessel name, MMSI, IMO,
flag, vessel type, number of events, and match confidence.

Risk tree leaves evaluated at this step:
- **imo_present** (gate) -- missing IMO = identity unverifiable, escalate to Elevated minimum
- **identity_misrepresentation** (medium) -- vessel_type_mismatch fires when event-level vessel_type and registry shiptypes map to different canonical classes
- mmsi_consistent, name_history -- future work (need longitudinal data)

### Step 2: IUU Listing Status
Check iuu_matched, iuu_vessel_name, iuu_listing_rfmos, iuu_match_type,
iuu_match_confidence, iuu_is_gfcm. Report listing RFMOs and reason.

Risk tree leaf: **iuu_listed** (regulatory_status branch, gate). GFCM-listed = high severity, other RFMO = medium.

### Step 3: ICCAT Authorization Status
Check iccat_authorized, iccat_authorizations, iccat_risk_tier. Note if
authorized as a Carrier (requires Regional Observer Programme coverage).

Risk tree leaves: **iccat_authorized** and **authorization_mismatch** (authorization branch, contextual). Authorization is an opportunity indicator, not exoneration.

### Step 3b: GFCM Authorisation Status

Check gfcm_registered, gfcm_vrn, gfcm_licence_indicator,
gfcm_operational_status. Two leaves fire on positive evidence only:

1. **gfcm_listed_no_licence** (medium severity) -- vessel in GFCM register
   with licence_indicator = 'No'. Direct regulatory mismatch.

2. **gfcm_listed_inactive** (medium severity) -- vessel in GFCM register
   marked operational_status = 'No', with GFW observing active events.
   Register stale or vessel operating when it should not be.

Coverage caveat: the raw GFCM register has only 24% MMSI coverage. Absence
from the register is treated as unknown, not unauthorised. A vessel may be
too small for the register's size threshold, or may be in the register
without its MMSI populated. Leaves fire only on positive evidence.

- gfcm_authorized (absence-based signal) -- future work (needs enrichment of
  GFCM register MMSI coverage via EU CFR joins or commercial AIS APIs)

### Step 4: Sanctions Status
Check ofac_sanctioned, ofac_sanctions_program, ofac_vessel_name. OFAC
sanctions are the most severe compliance flag.

Risk tree leaf: **ofac_sanctioned** (regulatory_status branch, gate). Automatic Critical tier.
- eu_sanctioned -- future work (needs EU Consolidated Financial Sanctions List)

### Step 5: Fisheries Context
Look up FDI baseline for the c-square(s) where events occurred. Report
fishing days, top species, gear types, and whether the activity makes
sense in this fisheries context.

### Step 6: Behavioural Pattern Analysis and Network Exposure

Analyse event patterns: event type mix, duration patterns, speed analysis,
geographic spread, temporal clustering. For AIS gaps: speed drop suggests
mid-sea operation; >12h suggests deliberate AIS disabling. For encounters:
proximity + duration = transfer likelihood.

Risk tree leaves evaluated at this step (behavioural_history branch, additive):
- **ais_gap_count** -- 2-3 gaps = medium, 4+ = high
- **encounter_with_carrier** -- medium severity
- **loitering_in_fishing_grounds** -- medium severity
- **speed_change_at_gap** -- >3kn drop = high severity
- **multi_behaviour_compound** -- two or more distinct event types = medium
- **dark_port_call_candidate** -- loitering within 10 km of shore = medium
- **repeat_offender_90d** -- two or more events in 90-day window = medium
- **vessel_size_industrial** -- >=24m LOA or >=100 GT = medium

#### Network Exposure (associative risk)

Evaluate encounter-partner signals from the risk tree's network_exposure branch.
Five specific leaves are evaluated deterministically for each vessel:

1. **encounter_iuu_vessel** (high severity) -- vessel had an encounter with a
   partner whose name appears on the TMT Combined IUU list across 13 RFMOs.
   Report the matched partner name(s).

2. **encounter_sanctioned_vessel** (critical severity) -- vessel had an
   encounter with a partner whose name appears on the OFAC SDN list.
   Report the matched partner name(s) and the sanctions program.

3. **encounter_weak_cooperation_partner** (medium severity) -- vessel had an
   encounter with a partner flagged by a Med coastal state cited in GFCM
   non-compliance reports (Libya or Syria). Report the partner flag.

4. **encounter_distant_water_partner** (medium severity) -- vessel had an
   encounter with a partner whose flag is neither EU nor Med coastal --
   distant-water fishing fleets and non-Med flags of convenience. Report
   the partner flag.

5. **encounter_pattern_recurrence** (medium severity) -- vessel had two or
   more encounters with the same counterparty within a 90-day rolling
   window. Counterparty identified by encounter_vessel_name; fallback to
   flag + duration bucket when name is missing. Repeated encounters with
   the same partner suggest an operational relationship (carrier servicing,
   regular bunkering, coordinated offloading) rather than incidental
   contact. Report the recurring partner name(s) and encounter count.

For vessel-specific queries the exact rule evaluation will appear in the
STRUCTURED EVIDENCE block. Ground your narrative in which specific leaves
fired. If no encounter-partner leaves fire, state that the network exposure
branch is clear.

Note: none of these five leaves multiply into the numeric risk_score. They
fire in the risk tree, appear in the vessel investigation narrative, but do
not affect the score. This preserves the base-vs-compound decomposition
(base = event observation, compound = vessel-identity lookup).

### Step 7: Risk Score Decomposition
Break down risk_score into: base (duration^0.75), event weight, flag
multiplier, shore factor, MPA tier multiplier, event-specific factors,
IUU/ICCAT/OFAC multipliers.

Key columns: base_risk_score (behavioural + spatial, pre-lookup) vs
risk_score (final compounded). compound_multiplier = sum(risk_score) /
sum(base_risk_score). High compound = mostly structural (lookup-driven).
Near 1 = mostly behavioural. risk_band is derived from final risk_score.

### Step 8: Hypothesis Generation
State most likely explanation: unauthorized fishing, at-sea transshipment,
sanctions evasion, or legitimate operation. Be specific about supporting
and undermining evidence.

### Step 9: External Lookups
If IMO available, provide links:
- MarineTraffic: https://www.marinetraffic.com/en/ais/details/ships/imo:{IMO}
- VesselFinder: https://www.vesselfinder.com/vessels?name={IMO}

### Step 10: Summary and Priority Assessment
Conclude with: overall threat level (Critical/High/Moderate/Low), key
evidence points (3-5 bullets), recommended actions, what additional
information would strengthen the assessment.

Assign the summary table to result_df and any chart to fig.
