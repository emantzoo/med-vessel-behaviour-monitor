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
     x event_specific_factors
```

### Base Components
- **Event weights**: ENCOUNTER=5.0 (transshipment), GAP=3.2 (dark activity), LOITERING=2.0 (staging)
- **Flag multipliers**: RUS=2.8, IRN=2.4, SYR=2.0, PRK=3.0, LBR=1.3, PAN=1.2, MHL=1.2, others=1.0
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
