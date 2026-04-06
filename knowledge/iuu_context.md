# IUU Fishing & Maritime Risk Context

IUU fishing generates ~$36B in annual losses. 1 in 5 fish caught globally is IUU.
Mediterranean: 75% of stocks overfished. 50% of Med tuna/swordfish catch from IUU.

Key behavioural indicators:
- AIS gaps (going dark): vessel disables transponder, especially near EEZ boundaries
- Encounters: vessel-to-vessel meetings, potential transshipment of illegal catch
- Loitering: carrier vessels waiting, often staging for transshipment
- Flag hopping: frequent flag changes to avoid scrutiny
- FOC registration: Panama, Liberia, Marshall Islands used to avoid regulation

EU IUU Regulation 1005/2008: catch certification required for all fishery imports.
CATCH digital system mandatory since January 2026.
EU carding system: 28 countries yellow-carded since 2010. Cambodia, Comoros,
St Vincent & Grenadines currently red-carded.

## IUU Vessel List Cross-Reference

The app cross-references GFW event vessels against the Combined IUU
Vessel List (iuu-vessels.org), maintained by TMT (Trygg Mat Tracking).
The list merges IUU fishing vessel lists from all 13 Regional Fisheries
Management Organisations (RFMOs): GFCM, ICCAT, IOTC, CCAMLR, WCPFC,
IATTC, NEAFC, NAFO, SEAFO, SPRFMO, CCSBT, NPFC, SIOFA.

Matching is performed on MMSI (exact), vessel name (exact and fuzzy/substring).

Two alert tiers:
- Tier 1 — GFCM-listed: vessel confirmed to have carried out IUU
  fishing in the Mediterranean/Black Sea (GFCM area). 3.0x risk multiplier.
- Tier 2 — Other RFMO: vessel IUU-listed by another RFMO (ICCAT,
  IOTC, etc.) detected operating in Mediterranean waters. 2.0x risk multiplier.

Match confidence levels:
- High: MMSI exact match (strongest identity link)
- Medium: Vessel name exact or fuzzy match (name >= 5 characters)
- Low: Vessel name fuzzy match on short names (< 5 characters)

The IUU list contains 369 vessels (213 currently listed, 156 delisted).
150 vessels have GFCM listings. 64 vessels have MMSI numbers for
direct AIS matching.

Key flags on the IUU list: Unknown (64), India (36), China (29),
Belize (14), Sri Lanka (10), Indonesia (9), Malaysia (9), Russia (5),
Panama (4).

Common vessel types: Fishing Vessel, Reefer, Fish carrier — the same
vessel types associated with transshipment in GFW encounter events.

Delisted vessels can optionally be shown (sidebar toggle). A delisted
vessel is worth flagging as it may indicate a vessel with a compliance
history, though it no longer receives the risk multiplier.

MMSI numbers can be spoofed or reassigned. An MMSI match is strong
evidence but not proof. Matches are flagged as "potential match" not
"confirmed IUU vessel."

## ICCAT Authorized Vessel Cross-Reference

The app cross-references GFW event vessels against the ICCAT Record
of Vessels authorized for Mediterranean fisheries.

Authorization types:
- SWO-Med: Mediterranean swordfish (longline)
- ALB-Med: Mediterranean albacore
- BFT-Catching: Bluefin tuna catching vessels (purse seine, longline, trap)
- BFT-Other: Support vessels for BFT operations (towing, transport)
- Carrier: Authorized transshipment/carrier vessels

ICCAT-authorized vessels appearing in suspicious events receive a
risk multiplier (1.2x-1.4x) because authorization provides access,
infrastructure, and economic incentive that makes IUU activity more
operationally plausible:
- Authorized carriers in encounters = potential catch laundering
- BFT catching vessels going dark = potential quota evasion
- SWO vessels active during seasonal closures = potential violation

A vessel showing fishing behaviour for BFT/SWO that is NOT on the
ICCAT authorized list is potentially fishing without authorization.

An ICCAT-authorized vessel that is ALSO on the IUU vessel list is
the highest-priority signal — a vessel with legitimate access that
has been confirmed to have engaged in IUU fishing.

ICCAT Regional Observer Programme (Rec. 24-05) requires observer
coverage on all purse seiners authorized for BFT, during all
transfers and caging operations. Transshipment by authorized
carriers should also be observed.

## OFAC SDN Sanctions Cross-Reference

The app cross-references GFW event vessels against the US Treasury OFAC
Specially Designated Nationals (SDN) list, filtered to vessel entries.

OFAC sanctions are a legal compliance obligation distinct from fisheries
management. The SDN list includes vessels sanctioned under programs such as:
- IRAN: Iranian shipping (NITC, IRISL fleets)
- SYRIA: Syrian regime-linked vessels
- UKRAINE-EO13662: Russia-related sanctions (Crimea)
- DPRK: North Korean vessels

Matching is performed on MMSI (exact), IMO (exact), and vessel name (exact).
No fuzzy matching is used for OFAC due to the serious legal implications
of false positives.

A vessel on the OFAC SDN list receives a 2.5x risk multiplier. This is
additive with IUU and ICCAT multipliers -- a vessel that is OFAC-sanctioned,
IUU-listed, AND ICCAT-authorized receives all three multipliers.

Priority signals:
- OFAC + IUU: Sanctioned vessel with confirmed illegal fishing history
- OFAC + ICCAT: Sanctioned vessel holding legitimate fishing authorization
- OFAC + IUU + ICCAT: Triple-flagged -- highest possible compliance concern

Any entity (port, company, financial institution) engaging in business
with an OFAC-sanctioned vessel risks exposure to US secondary sanctions.
This makes OFAC matches a concern for port authorities, insurers, and
flag state registries in addition to fisheries enforcement.
