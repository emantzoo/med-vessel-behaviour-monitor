"""AI Maritime Analyst tab — Gemini 2.5 Flash with RAG and sandboxed code execution."""

import re
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from config import FORBIDDEN_CODE
from investigation import investigate_vessel, format_trace_for_llm


def _cross_ref_summary(df):
    """Build a concise ground-truth summary of IUU/ICCAT/OFAC flags per vessel."""
    flag_cols = []
    if "iuu_matched" in df.columns:
        flag_cols.append("iuu_matched")
    if "iccat_authorized" in df.columns:
        flag_cols.append("iccat_authorized")
    if "ofac_sanctioned" in df.columns:
        flag_cols.append("ofac_sanctioned")
    if not flag_cols:
        return "No cross-reference columns available."

    lines = []
    for name, group in df.groupby("vessel_name"):
        row = group.iloc[0]
        iuu = bool(row.get("iuu_matched", False))
        iccat = bool(row.get("iccat_authorized", False))
        ofac = bool(row.get("ofac_sanctioned", False))
        if iuu or iccat or ofac:
            flags = []
            if iuu:
                flags.append(f"IUU={row.get('iuu_listing_rfmos', 'yes')}")
            if iccat:
                flags.append(f"ICCAT={row.get('iccat_authorizations', 'yes')}")
            if ofac:
                flags.append(f"OFAC={row.get('ofac_sanctions_program', 'yes')}")
            lines.append(f"- {name}: {', '.join(flags)}")
    if not lines:
        return "No vessels matched to IUU, ICCAT, or OFAC lists."
    # Also list a few clean vessels
    clean = df[~df["vessel_name"].isin([l.split(":")[0].strip("- ") for l in lines])]["vessel_name"].unique()[:3]
    for c in clean:
        lines.append(f"- {c}: IUU=no, ICCAT=no, OFAC=no")
    return "\n".join(lines)


def build_system_prompt(df, knowledge_base, fdi_effort=None, fdi_landings=None, iuu_vessels=None, iccat_vessels=None, ofac_vessels=None, fishing_df=None):
    """Build system prompt with dataframe context and domain knowledge."""
    # New vessel-intelligence columns the LLM must know about
    new_cols_present = [c for c in [
        "in_mpa", "mpa_tier", "mpa_name", "rfmo_name",
        "is_industrial", "length_m", "tonnage_gt",
        "multi_behaviour_flag", "dark_port_call_candidate", "repeat_offender_90d",
        "fishing_in_mpa_count", "base_risk_score", "risk_band",
        "vessel_class", "vessel_type_mismatch", "shiptypes",
    ] if c in df.columns]

    schema = f"""DATAFRAME SCHEMA (variable name: df)
Columns: {list(df.columns)}
Dtypes:
{df.dtypes.to_string()}

Shape: {df.shape[0]} rows x {df.shape[1]} columns

Sample rows (first 5):
{df.head().to_string()}

Value counts for key columns:
- event_type: {df['event_type'].value_counts().to_dict()}
- flag: {df['flag'].value_counts().to_dict()}

Basic stats:
- duration_h: mean={df['duration_h'].mean():.1f}, min={df['duration_h'].min()}, max={df['duration_h'].max()}
- risk_score: mean={df['risk_score'].mean():.1f}, total={df['risk_score'].sum():.0f}
- date range: {df['date'].min()} to {df['date'].max()}

VESSEL INTELLIGENCE COLUMNS (present on df, see knowledge base for full vocabulary):
{', '.join(new_cols_present) if new_cols_present else '(none detected)'}

CROSS-REFERENCE STATUS (ground truth — use these values, do NOT guess):
{_cross_ref_summary(df)}
"""

    prompt = f"""You are a maritime intelligence analyst assistant embedded in the
Med Vessel Behaviour Monitor dashboard. You help users analyse vessel behaviour
data in the Mediterranean Sea.

You have access to a pandas DataFrame called `df` containing vessel events
(AIS gaps, encounters, loitering) with risk scores.

{schema}

DOMAIN KNOWLEDGE:
{knowledge_base}

YOUR CAPABILITIES:
1. Answer questions about the data with domain-informed explanations
2. Generate Python code (pandas, plotly) to analyse the data
3. The code will be executed against the real dataframe

RESPONSE FORMAT:
Always respond with TWO clearly separated sections:

ANALYSIS:
[Your narrative explanation -- interpret results with domain knowledge.
 Explain WHY something matters, not just WHAT the numbers are.
 Reference IUU indicators, flag risks, geographic context where relevant.]

CODE:
```python
# Your pandas/plotly code here
# The dataframe is available as `df`
# For charts, assign to `fig` (plotly) -- it will be rendered automatically
# For tables, assign to `result_df` -- it will be displayed automatically
# For single values, assign to `result_value` -- it will be displayed
# Available libraries: pandas (pd), numpy (np), plotly.express (px),
#   plotly.graph_objects (go)
```

VESSEL INTELLIGENCE LAYERS (canonical column reference -- use these names verbatim):

MPA intersection (on df, also on fishing_df):
- in_mpa (bool), mpa (str, semicolon-joined MPA names — column is `mpa` NOT `mpa_name`), mpa_tier (str: "gfcm_fra" | "eu_site" | "general" | "")
- mpa_tier multiplier is ALREADY baked into base_risk_score (2.0x gfcm_fra, 1.5x eu_site, 1.2x general). Do NOT re-multiply.
- For MPA queries always state the McDonald et al. 2024 caveat: AIS-based MPA intersection is a lower bound -- ~90% of fishing vessels in MPAs are dark to AIS.

Score decomposition (on df):
- base_risk_score = behavioural-only score (includes shore, flag, event factors, MPA tier).
- risk_score = base_risk_score x iuu_multiplier x iccat_multiplier x ofac_multiplier (the final compounded score).
- Vessel-level: compound_multiplier = sum(risk_score) / sum(base_risk_score). High compound = mostly structural (lookup-driven). Near 1 = mostly behavioural.
- risk_band: Low (<50), Emerging (50-60), Elevated (60-80), Severe (80-100), Critical (>=100). Always derived from FINAL risk_score.

Vessel-level Kpler-aligned flags (on df, propagated per vessel):
- is_industrial (bool): length_m >= 24 OR tonnage_gt >= 100 (ICCAT industrial / EU Reg 1224/2009 threshold).
- multi_behaviour_flag (bool): vessel shows two or more distinct event types.
- dark_port_call_candidate (bool, per event): loitering within 10 km of shore (AIS-inferred candidate).
- repeat_offender_90d (bool): two or more events within any 90-day window.
- Supporting metadata: length_m, tonnage_gt, shiptypes (from GFW Vessels API).
- CRITICAL: these four flags are DISPLAY-ONLY. Never multiply or add them into risk_score. They are parallel indicators, not score amplifiers.

Vessel identity descriptors (on df, derived from vessel_type and shiptypes via VESSEL_CLASS_PATTERNS):
- vessel_class (str): canonical descriptive class -- one of "industrial_fishing" | "artisanal_fishing" | "carrier" | "tanker" | "cargo" | "support" | "passenger" | "other" | "". Prefers the registry shiptypes over event-level vessel_type when both are present. Display-only.
- vessel_type_mismatch (bool): fires when the event-level vessel_type and the registry shiptypes BOTH map to a non-empty class AND those classes DIFFER. The comparison is class-level (after normalisation through the pattern table), NOT string-level. So "TRAWLER" vs "FISHING" does NOT fire (both -> industrial_fishing); "FISHING" vs "CARGO" does fire (industrial_fishing vs cargo).
- This is the open-data equivalent of the Kpler Grey Fleet "irregular vessel information" indicator -- a vessel broadcasting one identity in AIS while its registry record says another.
- vessel_class is ORTHOGONAL to is_industrial. is_industrial is size-based (>=24m OR >=100GT, EU regulatory threshold). vessel_class is category-based (what kind of vessel). A small artisanal trawler is vessel_class=industrial_fishing AND is_industrial=False -- both columns are useful and neither substitutes for the other.
- CRITICAL: vessel_type_mismatch is DISPLAY-ONLY. Never multiply or add it into risk_score. It fires the identity_misrepresentation leaf in the risk tree at medium severity. Static demo seeds two examples: KOOSHA 4 (Iranian, IUU-listed, FISHING vs cargo -- the obvious case) and LEONARDO PADRE (Italian, ICCAT-authorised artisanal, FISHING vs carrier -- the subtle case).

Fishing events (separate dataframe: fishing_df):
- fishing_df is a SEPARATE dataframe of GFW FISHING events (Kroodsma 2018 CNN classification). It is NOT part of df. Join on mmsi if you need to cross-reference.
- Fishing events are display-only context and are NOT scored. Do NOT sum their hours into the risk_score column. Do NOT concatenate fishing_df with df.
- ACTUAL columns on fishing_df: date, vessel_name, mmsi, flag, lat, lon, fishing_hours, mpa, mpa_tier, in_mpa.
- IMPORTANT: the MPA name column on fishing_df is `mpa` (NOT `mpa_name`). The hours column is `fishing_hours` (NOT `duration_h`). Use these names verbatim.
- Vessel-level rollup on df: fishing_in_mpa_count (count of fishing events the vessel had inside any MPA -- the strongest publicly available IUU-in-MPA signal).
- Typical query: fishing_df[fishing_df["mpa_tier"] == "gfcm_fra"] for fishing inside legally binding GFCM Fisheries Restricted Areas.

RULES:
- Always generate executable code -- no pseudocode
- Use `df` as the dataframe variable (already in scope)
- For charts, always use plotly (px or go) and assign to `fig`
- For tables, assign to `result_df`
- Keep code concise -- under 30 lines
- NEVER claim a vessel is not in the data based on the sample above. The sample only shows 5 rows but df has {df.shape[0]} rows. ALWAYS write code to search: df[df["vessel_name"].str.contains("NAME", case=False, na=False)]
- When asked to investigate a vessel, ALWAYS generate code that filters df for that vessel and displays its key columns as result_df. Follow the investigation template from the knowledge base.
- Do not fabricate data or make up vessel names/MMSIs
- CRITICAL ANTI-HALLUCINATION RULE: For IUU, ICCAT, and OFAC status you MUST generate code that reads and displays the actual boolean column values (iuu_matched, iccat_authorized, ofac_sanctioned) for the vessel. Your ANALYSIS section MUST match what the code outputs — do not contradict the data. Do NOT infer or assume a vessel is IUU/ICCAT/OFAC based on its flag, type, or name. An Iranian tanker is NOT necessarily OFAC-sanctioned unless ofac_sanctioned==True. A vessel can be IUU-listed but NOT OFAC-sanctioned — these are independent data sources. When investigating a vessel, your code MUST include these columns in result_df: iuu_matched, ofac_sanctioned, iccat_authorized, iuu_multiplier, ofac_multiplier, iccat_multiplier.
- VESSEL INVESTIGATION FORMAT: When the user asks about a specific vessel (by MMSI or name), you will receive a STRUCTURED EVIDENCE block at the end of this prompt containing the deterministic risk tree trace for that vessel. Your ANALYSIS section MUST be structured around this trace:
  1. Open with a one-line verdict (risk band + primary driver).
  2. Walk through the risk tree branch by branch, using the EXACT branch names and severities from the trace (e.g., "ais_gap branch fired at HIGH severity"). Only discuss branches present in the trace.
  3. For each branch, quote the key metrics from the trace (duration, distance, multiplier values).
  4. End with the compound multiplier decomposition: base_risk_score x IUU x ICCAT x OFAC x flag = final risk_score.
  The output must make it obvious that a structured risk tree evaluation was performed, not a free-text LLM summary. Do NOT reorganize into your own headings like "Identity & Regulatory Status" — follow the tree structure.
- When discussing flags, use the domain knowledge to explain risk context
- When discussing locations, reference relevant Med geography

CODE STYLE (critical -- follow exactly):
- ALWAYS work from `df` directly. Do NOT redefine or overwrite `df`.
- For bar charts: group first into a small df, then pass that to px.bar()
- For scatter/map: use px.scatter(df, x="lon", y="lat", ...) -- NOT px.scatter_geo() or px.scatter_mapbox()
- For spatial plots: use px.scatter(df, x="lon", y="lat", color=..., size=...) -- NOT density_heatmap (too blocky with small data)
- NEVER use px.scatter_geo with scope="mediterranean" -- that is not a valid Plotly scope. Use px.scatter with x="lon", y="lat" instead.
- NEVER pass a Series where a DataFrame is expected
- NEVER use chained expressions inside plotly function arguments
- After groupby().agg(), ONLY use column names that you explicitly created. If you used .size() or .count(), name the result explicitly with .reset_index(name="count") or assign it.
- Test mentally that all column names exist in df before using them
- Prefer simple one-step groupby().agg().reset_index() patterns
- Assign intermediate results to variables, do not nest complex expressions

WORKING CODE PATTERNS (use these):
```
# Bar chart pattern
grouped = df.groupby("flag")["risk_score"].sum().reset_index()
fig = px.bar(grouped, x="flag", y="risk_score", title="Risk by Flag")

# Table pattern
result_df = df[df["flag"]=="RUS"][["mmsi","flag","duration_h","risk_score"]]

# Single value pattern
result_value = f"{{df['risk_score'].sum():.0f}} total risk"

# Scatter map pattern (ALWAYS use px.scatter with x/y, NOT px.scatter_geo)
fig = px.scatter(df, x="lon", y="lat", color="event_type", size="risk_score", title="Events")

# Spatial scatter pattern (preferred over density_heatmap)
fig = px.scatter(df, x="lon", y="lat", color="event_type", size="duration_h",
                 hover_data=["flag","mmsi","risk_score"], title="Event Locations")

# FDI join pattern — df has csq_lon/csq_lat, fdi has rectangle_lon/rectangle_lat
# IMPORTANT: df does NOT have quarter, gear_type, species — those are in fdi_effort/fdi_landings
merged = df.merge(fdi_effort.groupby(["rectangle_lon","rectangle_lat"]).agg(total_days=("totfishdays","sum")).reset_index(),
                  left_on=["csq_lon","csq_lat"], right_on=["rectangle_lon","rectangle_lat"], how="left")

# Pivot/crosstab pattern — always use fill_value=0 and avoid .loc with values that may not exist
ct = pd.crosstab(df["flag"], df["event_type"]).fillna(0)
# Use .get() or .reindex() instead of direct column access to avoid KeyError

# Top N vessels ranking pattern (ALWAYS use this for "riskiest vessels" queries)
vessel_agg = df.groupby("mmsi").agg(
    vessel_name=("vessel_name", "first"),
    flag=("flag", "first"),
    events=("event_type", "count"),
    risk_score_total=("risk_score", "sum"),
    base_score_total=("base_risk_score", "sum"),
    iuu_matched=("iuu_matched", "max"),
    ofac_sanctioned=("ofac_sanctioned", "max"),
    iccat_authorized=("iccat_authorized", "max"),
).reset_index()
vessel_agg["compound_mult"] = (vessel_agg["risk_score_total"] / vessel_agg["base_score_total"].replace(0, 1)).round(2)
result_df = vessel_agg.nlargest(5, "risk_score_total")
```
"""

    if fdi_effort is not None and not fdi_effort.empty:
        prompt += f"""

FDI BASELINE DATA (variable names: fdi_effort, fdi_landings)
FDI effort shape: {fdi_effort.shape}
FDI landings shape: {fdi_landings.shape if fdi_landings is not None else '(empty)'}
FDI year range: {fdi_effort['year'].min()}-{fdi_effort['year'].max()}
FDI unique c-squares: {fdi_effort[['rectangle_lon','rectangle_lat']].drop_duplicates().shape[0]}
FDI gear types: {fdi_effort['gear_type'].value_counts().head(5).to_dict()}

The fdi_effort and fdi_landings DataFrames are available for analysis.
Join to GFW events using csq_lon/csq_lat (event columns) = rectangle_lon/rectangle_lat (FDI columns).
"""

    if iuu_vessels is not None and not iuu_vessels.empty:
        iuu_matched_count = int(df["iuu_matched"].sum()) if "iuu_matched" in df.columns else 0
        prompt += f"""

IUU VESSEL CROSS-REFERENCE (variable name: iuu_vessels)
IUU list size: {len(iuu_vessels)} vessels
Currently listed: {iuu_vessels['is_currently_listed'].sum()}
GFCM-listed (Med): {iuu_vessels['is_gfcm'].sum()}
IUU matches in current data: {iuu_matched_count}

IUU-related columns in df (when matches exist):
- iuu_matched: bool
- iuu_vessel_name: str (matched IUU list name)
- iuu_listing_rfmos: str (comma-separated RFMOs)
- iuu_match_type: "MMSI" | "name_exact" | "name_fuzzy"
- iuu_match_confidence: "high" | "medium" | "low"
- iuu_multiplier: float (3.0 for GFCM, 2.0 for other RFMO, 1.0 if no match)
- iuu_is_gfcm: bool

The iuu_vessels DataFrame is available for analysis.
"""

    if iccat_vessels is not None and not iccat_vessels.empty:
        iccat_matched_count = int(df["iccat_authorized"].sum()) if "iccat_authorized" in df.columns else 0
        prompt += f"""

ICCAT AUTHORIZED VESSEL CROSS-REFERENCE (variable name: iccat_vessels)
ICCAT Med-authorized vessels: {len(iccat_vessels)}
ICCAT matches in current data: {iccat_matched_count}

ICCAT-related columns in df (when matches exist):
- iccat_authorized: bool
- iccat_authorizations: str (e.g., "SWO-Med, BFT-Catching")
- iccat_risk_tier: str ("carrier", "bft_catching", "bft_other", "swo_med", "alb_med")
- iccat_multiplier: float (1.4 for carrier, 1.3 for BFT, 1.2 for SWO/ALB, 1.0 if no match)
- iccat_vessel_name: str (matched name from ICCAT list)

ICCAT authorized vessels in suspicious events are an opportunity indicator --
authorization provides access, cover, and infrastructure for IUU activity.
A vessel that is BOTH IUU-listed and ICCAT-authorized is the highest-priority signal.

The iccat_vessels DataFrame is available for analysis.
"""

    if ofac_vessels is not None and not ofac_vessels.empty:
        ofac_matched_count = int(df["ofac_sanctioned"].sum()) if "ofac_sanctioned" in df.columns else 0
        prompt += f"""

OFAC SDN SANCTIONED VESSEL CROSS-REFERENCE (variable name: ofac_vessels)
OFAC vessel list size: {len(ofac_vessels)} vessels
OFAC matches in current data: {ofac_matched_count}

OFAC-related columns in df (when matches exist):
- ofac_sanctioned: bool
- ofac_vessel_name: str (matched SDN list name)
- ofac_sanctions_program: str (e.g., "IRAN", "SYRIA", "UKRAINE-EO13662")
- ofac_listing_date: str (date added to SDN list)
- ofac_match_type: "MMSI" | "IMO" | "name_exact"
- ofac_match_confidence: "high" | "medium"
- ofac_multiplier: float (2.5 for sanctioned, 1.0 if no match)

OFAC sanctions represent a legal compliance obligation beyond fisheries management.
Vessels on the SDN list are subject to US economic sanctions. Any entity conducting
business with a sanctioned vessel risks secondary sanctions exposure. OFAC matches
are the highest-priority signal in this dashboard.

When discussing vessels with an IMO number, include external lookup links:
- MarineTraffic: https://www.marinetraffic.com/en/ais/details/ships/imo:{{IMO}}
- VesselFinder: https://www.vesselfinder.com/vessels?name={{IMO}}

The ofac_vessels DataFrame is available for analysis.
"""

    if fishing_df is not None and not fishing_df.empty:
        fishing_in_mpa = int(fishing_df["in_mpa"].fillna(False).astype(bool).sum()) if "in_mpa" in fishing_df.columns else 0
        # Detect real column names so the LLM uses them verbatim (the
        # knowledge file documents an idealised schema; the real static
        # feed uses `mpa` and `fishing_hours`).
        mpa_col = "mpa" if "mpa" in fishing_df.columns else ("mpa_name" if "mpa_name" in fishing_df.columns else None)
        hours_col = "fishing_hours" if "fishing_hours" in fishing_df.columns else ("duration_h" if "duration_h" in fishing_df.columns else None)
        prompt += f"""

GFW FISHING EVENTS (variable name: fishing_df)
fishing_df is a SEPARATE dataframe of GFW FISHING events. It is NOT part of df.
Join on mmsi if you need to cross-reference.
Fishing events are display-only context and are not scored.
Do NOT sum their hours into the risk_score column.
Do NOT concatenate fishing_df with df.

fishing_df shape: {fishing_df.shape}
Fishing events inside MPAs: {fishing_in_mpa}
ACTUAL columns (use these names verbatim): {list(fishing_df.columns)}

CRITICAL column-name notes:
- The MPA name column on fishing_df is `{mpa_col}` (NOT `mpa_name`).
- The fishing-hours column on fishing_df is `{hours_col}` (NOT `duration_h`).
- Do NOT assume any column called `mpa_name` or `duration_h` exists on fishing_df.

IMPORTANT: mmsi is STRING type on both df and fishing_df. Do NOT cast mmsi to int. Merges on mmsi work directly without type conversion.

Typical patterns:
- fishing_df[fishing_df["in_mpa"]] -- all fishing inside any MPA
- fishing_df[fishing_df["mpa_tier"] == "gfcm_fra"] -- fishing inside GFCM Fisheries Restricted Areas
- fishing_df[fishing_df["mpa_tier"] == "gfcm_fra"][["vessel_name","flag","{mpa_col}","{hours_col}"]] -- with FRA name and hours
- fishing_df.merge(df[["mmsi","vessel_name","flag","base_risk_score","risk_score"]].drop_duplicates("mmsi"), on="mmsi", how="left") -- attach scored-vessel context
"""

    return prompt


def _extract_vessel_reference(query: str, df) -> tuple:
    """Detect whether the user query references a specific vessel.

    Returns (mmsi, vessel_name) if a vessel is identified, (None, None) otherwise.
    Uses two strategies: MMSI pattern match (9-digit number) and
    vessel name match against the unique vessel_name column of df.
    """
    # MMSI pattern: 9-digit number
    mmsi_match = re.search(r"\b(\d{9})\b", query)
    if mmsi_match:
        mmsi = mmsi_match.group(1)
        if mmsi in df["mmsi"].astype(str).values:
            vessel_row = df[df["mmsi"].astype(str) == mmsi].iloc[0]
            return mmsi, vessel_row.get("vessel_name", "")

    # Vessel name match: check if any unique vessel name appears in query
    if "vessel_name" in df.columns:
        query_upper = query.upper()
        # Sort by length descending so longer names match first (avoids
        # "MARE NOSTRUM II" matching partial "MARE NOSTRUM II (HRV-2)")
        names = sorted(df["vessel_name"].dropna().unique(), key=len, reverse=True)
        for name in names:
            if isinstance(name, str) and len(name) > 3 and name.upper() in query_upper:
                mmsi = str(df[df["vessel_name"] == name].iloc[0]["mmsi"])
                return mmsi, name

    return None, None


def is_safe_code(code):
    """Basic check that generated code doesn't do anything dangerous."""
    code_lower = code.lower()
    for forbidden in FORBIDDEN_CODE:
        if forbidden.lower() in code_lower:
            return False
    return True


@st.fragment
def render_ai_analyst(df_filtered, fdi_effort, fdi_landings, knowledge_base, gemini_key, iuu_vessels=None, iccat_vessels=None, ofac_vessels=None, fishing_df=None):
    """Render the AI Maritime Analyst tab (fragment: interactions rerun only this block)."""
    st.subheader("AI Maritime Analyst")
    st.markdown(
        "Ask questions about the vessel data in natural language. "
        "The AI will explain the findings and generate analytical code."
    )

    if not gemini_key:
        st.info("This feature requires a Gemini API key. Get a free key at [aistudio.google.com](https://aistudio.google.com).")
        gemini_key = st.text_input(
            "Gemini API Key", type="password",
            help="Get a free key at aistudio.google.com",
        )
        if not gemini_key:
            st.stop()

    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = []

    examples = [
        "",
        # Investigation walkthrough — the hero question
        "Investigate KOOSHA 4",
        # New vessel-intelligence layer questions (MPA + flags + base/compound)
        "Which vessels had fishing activity inside a GFCM Fisheries Restricted Area? Show their flag, their base vs compounded risk scores, and the FRA name.",
        "How many industrial-class vessels (is_industrial=True) had multi-behaviour flags, and what's their flag state distribution?",
        "Which vessels have a vessel_type_mismatch (event-level vessel_type vs registry shiptypes disagreement)? Show their vessel_class, vessel_type, shiptypes, and IUU/ICCAT/OFAC status.",
        # Cross-source intelligence (the differentiator)
        "Show me IUU-listed vessels in c-squares with high swordfish landings",
        "Which OFAC-sanctioned vessels appear in the data and what's their pattern?",
        "Find ICCAT-authorized carriers involved in encounters",
        "Are there any vessels matched to both IUU and ICCAT lists?",
        # Domain-informed analysis
        "Which flag states have the highest gap-to-encounter ratio and why is that suspicious?",
        "Compare risk profiles of FOC-flagged vs Mediterranean EU-flagged vessels",
        "Rank the top 5 riskiest vessels and explain what makes each one suspicious",
        # Spatial and temporal patterns
        "What's happening in the eastern Mediterranean (longitude > 25)?",
        "Which c-squares have the most events and what species are landed there?",
        "Plot all events on a scatter map colored by event type",
        # Behavioural deep-dives
        "Show me long AIS gaps (>24h) with significant speed changes",
        "Are there any vessels with repeated gap events in the same area?",
        "Which day had the most suspicious activity and why?",
        # Visual analytics (plots not already in the UI)
        "Plot base_risk_score vs risk_score per vessel as a scatter — label outliers where the compound multiplier exceeds 3x",
        "Chart IUU/ICCAT/OFAC multiplier contribution per vessel as a grouped bar — which vessel has the tallest compound stack?",
        "Plot a timeline of all events coloured by risk_band — are Critical events clustered in time?",
        "Scatter plot: event duration vs distance_from_shore_km, coloured by event_type — where do long offshore gaps cluster?",
        "Box plot of risk_score by flag state (top 10 flags by event count) — which flags have the widest spread?",
    ]

    picked = st.selectbox(
        "Pick a question or type your own below", examples, index=0,
        format_func=lambda x: "-- Pick an example question --" if x == "" else x,
        key="example_sel",
    )

    typed = st.text_input(
        "Or type your own question", value="", key="typed_q",
        placeholder="Type a question here...",
    )

    ask_clicked = st.button("Ask", type="primary")

    question = None
    if ask_clicked:
        if typed.strip():
            question = typed.strip()
        elif picked:
            question = picked

    if question and gemini_key:
        st.session_state.ai_messages = []
        st.session_state.ai_messages.append({"role": "user", "parts": [question]})

        with st.spinner("Thinking..."):
            try:
                from google import genai

                client_ai = genai.Client(api_key=gemini_key)
                system_ctx = build_system_prompt(
                    df_filtered, knowledge_base, fdi_effort, fdi_landings, iuu_vessels, iccat_vessels, ofac_vessels, fishing_df
                )

                # Detect if the query references a specific vessel and append risk tree trace
                vessel_mmsi, vessel_name = _extract_vessel_reference(question, df_filtered)
                if vessel_mmsi:
                    try:
                        report = investigate_vessel(
                            vessel_mmsi, df_filtered,
                            iuu_vessels if iuu_vessels is not None else pd.DataFrame(),
                            iccat_vessels if iccat_vessels is not None else pd.DataFrame(),
                            ofac_vessels if ofac_vessels is not None else pd.DataFrame(),
                            fdi_effort if fdi_effort is not None else pd.DataFrame(),
                            fdi_landings if fdi_landings is not None else pd.DataFrame(),
                            fishing_df=fishing_df,
                        )
                        trace = report.get("trace", [])
                        trace_text = format_trace_for_llm(trace, vessel_name)
                    except Exception as e:
                        trace_text = f"(Risk tree trace unavailable: {e})"
                    system_ctx += (
                        "\n\n---\n"
                        "STRUCTURED EVIDENCE — deterministic risk tree evaluation for the vessel referenced in the query.\n"
                        "YOUR ANALYSIS MUST FOLLOW THE TREE STRUCTURE BELOW. Walk branch by branch, "
                        "quoting severities and metrics verbatim. Do NOT reorganize into your own categories. "
                        "Do NOT omit branches that fired. Do NOT add branches that did not fire. "
                        "The reader must see that a rule-based evaluation drove the output, not free-form LLM reasoning.\n\n"
                        f"{trace_text}"
                    )

                contents = []
                for msg in st.session_state.ai_messages[-20:]:
                    contents.append(
                        genai.types.Content(
                            role=msg["role"],
                            parts=[genai.types.Part(text=msg["parts"][0])],
                        )
                    )

                response = client_ai.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=system_ctx,
                        max_output_tokens=8000,
                    ),
                )

                st.session_state.ai_messages.append(
                    {"role": "model", "parts": [response.text]}
                )

            except Exception as e:
                st.error(f"Gemini API error: {e}")

    # Render conversation
    for msg in st.session_state.ai_messages:
        role = "user" if msg["role"] == "user" else "assistant"
        content = msg["parts"][0] if msg["parts"] else ""
        with st.chat_message(role):
            if role == "assistant":
                code_blocks = re.findall(r"```python\n(.*?)```", content, re.DOTALL)
                narrative = re.sub(
                    r"```python\n.*?```", "", content, flags=re.DOTALL
                ).strip()
                if narrative:
                    st.markdown(narrative)

                for code in code_blocks:
                    with st.expander("Generated Code", expanded=True):
                        st.code(code, language="python")

                    if is_safe_code(code):
                        try:
                            exec_ns = {
                                "df": df_filtered.copy(),
                                "pd": pd,
                                "np": np,
                                "px": px,
                                "go": go,
                                "fdi_effort": fdi_effort.copy() if fdi_effort is not None and not fdi_effort.empty else pd.DataFrame(),
                                "fdi_landings": fdi_landings.copy() if fdi_landings is not None and not fdi_landings.empty else pd.DataFrame(),
                                "iuu_vessels": iuu_vessels.copy() if iuu_vessels is not None and not iuu_vessels.empty else pd.DataFrame(),
                                "iccat_vessels": iccat_vessels.copy() if iccat_vessels is not None and not iccat_vessels.empty else pd.DataFrame(),
                                "ofac_vessels": ofac_vessels.copy() if ofac_vessels is not None and not ofac_vessels.empty else pd.DataFrame(),
                                "fishing_df": (lambda _f: _f.assign(mmsi=_f["mmsi"].astype(str)) if "mmsi" in _f.columns else _f)(fishing_df.copy()) if fishing_df is not None and not fishing_df.empty else pd.DataFrame(),
                            }
                            exec(code, exec_ns)

                            if "fig" in exec_ns and exec_ns["fig"] is not None:
                                st.plotly_chart(exec_ns["fig"])
                            if "result_df" in exec_ns and exec_ns["result_df"] is not None:
                                st.dataframe(exec_ns["result_df"])
                            if "result_value" in exec_ns and exec_ns["result_value"] is not None:
                                st.metric("Result", exec_ns["result_value"])
                        except Exception as e:
                            st.error(f"Code execution error: {e}")
                    else:
                        st.warning("Generated code contains restricted operations. Skipping execution.")
            else:
                st.markdown(content)
