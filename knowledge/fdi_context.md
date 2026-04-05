# FDI Spatial Data Context

The EU Fisheries Dependent Information (FDI) spatial dataset provides
officially compiled fishing effort and landings at 0.5x0.5 degree
c-square resolution, by quarter, gear type, and species.

Source: JRC/STECF -- compiled from EU Member State logbooks, sales
notes, and sampling programmes. Not raw declarations but statistically
processed estimates reviewed by STECF EWGs.

Mediterranean spatial data available from 2017 onwards.

Key fields:
- totfishdays: fishing days per c-square per quarter
- totwghtlandg: landings weight in tonnes
- totvallandg: landings value in euros
- gear_type: fishing gear (OTB=bottom trawl, PS=purse seine, GNS=gillnet, LLS=longline, etc.)
- species: FAO 3-letter species codes

High-value Med species relevant to transshipment risk:
- BFT (Bluefin tuna): highest per-kg value, ICCAT quota, major IUU target
- SWO (Swordfish): high value, driftnets still used illegally
- HKE (Hake): most important demersal species, trawl-caught
- DPS (Deep-water rose shrimp): high value trawl species
- PIL/ANE (Sardine/Anchovy): highest volume small pelagics, purse seine

Integration with AIS/GFW data:
- AIS provides observed vessel behaviour (real-time, vessel-level)
- FDI provides compiled effort and catch estimates (annual, aggregated)
- Neither is ground truth -- both are independent estimates
- Discrepancies between GFW activity patterns and FDI reported effort
  may indicate unreported fishing, misreported catches, or data gaps
- C-squares with GFW events but no FDI effort may signal activity
  outside officially reported fishing grounds
- Confidentiality suppression: some FDI cells omitted (<3 vessel rule).
  Absence of FDI data does not necessarily mean no fishing.
