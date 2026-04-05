"""AI Maritime Analyst tab — Gemini 2.5 Flash with RAG and sandboxed code execution."""

import re
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from config import FORBIDDEN_CODE


def build_system_prompt(df, knowledge_base, fdi_effort=None, fdi_landings=None, iuu_vessels=None, iccat_vessels=None):
    """Build system prompt with dataframe context and domain knowledge."""
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

RULES:
- Always generate executable code -- no pseudocode
- Use `df` as the dataframe variable (already in scope)
- For charts, always use plotly (px or go) and assign to `fig`
- For tables, assign to `result_df`
- Keep code concise -- under 20 lines
- If the question cannot be answered from the data, say so clearly
- Do not fabricate data or make up vessel names/MMSIs
- When discussing flags, use the domain knowledge to explain risk context
- When discussing locations, reference relevant Med geography

CODE STYLE (critical -- follow exactly):
- ALWAYS work from `df` directly. Do NOT redefine or overwrite `df`.
- For bar charts: group first into a small df, then pass that to px.bar()
- For scatter/map: pass df directly to px.scatter() or px.scatter_geo()
- For spatial plots: use px.scatter(df, x="lon", y="lat", color=..., size=...) -- NOT density_heatmap (too blocky with small data)
- NEVER pass a Series where a DataFrame is expected
- NEVER use chained expressions inside plotly function arguments
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

# Scatter map pattern
fig = px.scatter(df, x="lon", y="lat", color="event_type", size="risk_score", title="Events")

# Spatial scatter pattern (preferred over density_heatmap)
fig = px.scatter(df, x="lon", y="lat", color="event_type", size="duration_h",
                 hover_data=["flag","mmsi","risk_score"], title="Event Locations")
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

    return prompt


def is_safe_code(code):
    """Basic check that generated code doesn't do anything dangerous."""
    code_lower = code.lower()
    for forbidden in FORBIDDEN_CODE:
        if forbidden.lower() in code_lower:
            return False
    return True


def render_ai_analyst(df_filtered, fdi_effort, fdi_landings, knowledge_base, gemini_key, iuu_vessels=None, iccat_vessels=None):
    """Render the AI Maritime Analyst tab."""
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
        "Which flag states have the highest total risk? Why?",
        "Show me all encounters involving Russian-flagged vessels",
        "Are there any vessels with repeated gap events?",
        "What's happening in the eastern Mediterranean (longitude > 25)?",
        "Which day had the most suspicious activity and why?",
        "Plot all events on a scatter map colored by event type",
        "Compare risk profiles of FOC-flagged vs Mediterranean-flagged vessels",
        "What's the average gap duration by flag state? Any outliers?",
        "Rank the top 5 riskiest vessels and explain what makes each one suspicious",
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
                    df_filtered, knowledge_base, fdi_effort, fdi_landings, iuu_vessels, iccat_vessels
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
                        max_output_tokens=2000,
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
