# Static demo flag distribution

The static demo dataset has been rebalanced to reflect realistic
Mediterranean fisheries fleet composition. EU flags (ITA, GRC, ESP, FRA,
HRV, MLT, CYP) account for roughly 53% of events. Non-EU Med coastal
states (TUR, TUN, MAR, DZA, LBY, EGY, LBN, SYR) account for roughly 33%.
Flags of convenience (PAN, LBR) account for ~3%. The remainder (~11%) are
protected demo vessels with special flags (IRN, HND, BHS, UNK).

This replaces an earlier shadow-fleet-tanker flag distribution which
was inherited from initial prototyping. The rebalanced distribution
preserves test cases for all risk tree leaves including weak-cooperation
(LBY, SYR) and distant-water / FoC partner encounters (PAN, LBR, MHL).

## Protected vessels (flags not changed)

| Vessel | Flag | Role |
|--------|------|------|
| KOOSHA 4 | IRN | IUU demo (GFCM-listed) |
| SABITI | IRN | OFAC demo |
| ADRIAN DARYA 1 | IRN | OFAC demo |
| ACROS NO. 2 | HND | IUU demo |
| FRIO NARUTO | BHS | ICCAT demo |
| LEONARDO PADRE | ITA | ICCAT demo |
| PEDRO Y BEATRIZ | ESP | ICCAT demo |
| MISTRAL III | UNK | Unknown-flag demo |
