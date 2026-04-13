# Flag State Risk Context

## Flag multiplier calibration

Flag-level risk multipliers are derived from the Poseidon IUU Fishing Risk
Index (https://iuufishingindex.net/), covering 152 coastal states. The 10
Flag-responsibility indicators per country (vulnerability, prevalence,
response) are averaged and mapped linearly to a multiplier:
`multiplier = 1.0 + (mean_score - 1.0) * 0.3`. All flags are loaded from
`data/iuu_risk_index_flags.csv` at startup; flags not in the Index receive
1.0x. Regenerate from latest Index via `scripts/prepare_iuu_risk_index.py`.

## Sanctions / conflict flags (context, not hardcoded)

These jurisdictions score high on the Index because sanctions, conflict, and
weak governance drive the underlying indicator scores. No special-case
multiplier is hardcoded -- the Index captures the risk organically.

- **RUS** (1.93x): Shadow fleet operations, sanctions evasion, AIS manipulation.
- **IRN** (1.63x): NITC/IRISL sanctions, oil smuggling, AIS spoofing.
- **SYR** (1.24x): Conflict state, limited oversight capacity.
- **PRK** (1.26x): Weapons/sanctions, flag rarely seen in Med data.

## Flags of convenience (context, not hardcoded)

FOC registries score higher on the Index due to weak flag-state oversight
indicators. The multiplier comes from the Index, not a manual FOC list.

- **PAN** (1.81x): Largest FOC registry globally.
- **LBR** (1.48x): Second largest FOC.
- **MHL** (1.39x): Growing FOC registry.

## Mediterranean coastal states (fishing nations)

These are the flags that dominate actual Med fishing catches (GFCM data,
percentage variation chart, 2024 vs 2023). All carry Index-derived
multipliers (ranging from GRC 1.21x to LBY 1.66x); their presence in
the data is normal operational activity, not a risk signal per se -- the
Index captures governance quality, not suspicion of the flag itself.

**Northern shore (EU + candidate):**
- **TUR**: Turkey. Largest Med fishing nation by catch volume. -26.8% variation.
- **ITA**: Italy. Second largest EU Med fleet. -8.7% variation.
- **GRC**: Greece. Largest EU fleet by vessel count (Piraeus base). -2.0% variation.
- **ESP**: Spain. Western Med + Alboran. -11.3% variation.
- **FRA**: France. Western Med (Marseille, Sete). -1.5% variation.
- **HRV**: Croatia. Adriatic. -10.7% variation.
- **MLT**: Malta. Central Med hub, EU flag but large registry. +16.7% variation.
- **CYP**: Cyprus. Eastern Med, mixed flag use. +6.8% variation.
- **SVN**: Slovenia. Adriatic (small fleet). -9.1% variation.
- **MNE**: Montenegro. Adriatic (small fleet). -2.3% variation.
- **ALB**: Albania. Adriatic. -6.3% variation.
- **PRT**: Portugal. Atlantic/western approaches. -7.9% variation.

**Southern shore (North Africa):**
- **DZA**: Algeria. Largest catch increase in the Med (+36.6%, +24,978 tonnes).
- **TUN**: Tunisia. Major south Med fleet. +4.1% variation.
- **EGY**: Egypt. Eastern south Med. +4.8% variation.
- **LBY**: Libya. Central south Med. +1.5% variation.
- **MAR**: Morocco. Western Med / Atlantic interface. -45.7% variation (largest decline).

**Eastern shore:**
- **ISR**: Israel. +4.1% variation.
- **LBN**: Lebanon. +4.4% variation.
- **SYR**: Syria (also listed under sanctions above). +11.5% variation.
- **PSE**: Palestine. -20.0% variation.

**Black Sea (adjacent basin):**
- **BGR**: Bulgaria. -19.5% variation.
- **ROU**: Romania. -14.7% variation.
- **GEO**: Georgia. -6.7% variation.
- **TUR**: Turkey (also Black Sea). +19.4% variation in Black Sea basin.
- **RUS**: Russia (also listed under sanctions above). -25.3% variation.

## Demo data flag distribution

The static demo dataset (`data/med_events_static.csv`, 95 events) uses a
flag distribution roughly proportional to actual Med fishing activity:
GRC 13, ITA 13, TUR 12, TUN 9, DZA 7, MLT 6, ESP 5, IRN 5, EGY 5,
MAR 3, LBY 3, HRV 3, FRA 2, CYP 2, BHS 2, HND 2, ALB 1, UNK 1.

IRN events are the three real OFAC/IUU demo vessels (KOOSHA 4, SABITI,
ADRIAN DARYA 1). HND and BHS are real IUU/ICCAT demo vessels (ACROS NO. 2,
FRIO NARUTO). All other flags are realistic Med coastal states.
