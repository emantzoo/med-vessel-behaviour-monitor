# Med Vessel Behaviour Monitor — AI Maritime Analyst

## Feature Spec: RAG + Code Generation + Execution

---

## Concept

A conversational AI assistant embedded in the Streamlit app that:
1. Answers natural language questions about the vessel data
2. Generates Python/pandas code to answer analytical questions
3. Executes the code against the live dataframe
4. Returns both a narrative explanation AND the results (tables, charts, numbers)
5. Uses RAG context (methodology docs, IUU knowledge, flag risk info) to give domain-informed answers

**Not a chatbot.** An analytical copilot. The user asks questions, the AI writes and runs the analysis.

---

## Architecture

```
User question (natural language)
        |
        v
System prompt (injected context):
  - DataFrame schema + sample rows
  - Risk model methodology
  - IUU/maritime domain knowledge (RAG docs)
  - Flag risk explanations
  - Mediterranean context
        |
        v
Claude API (Anthropic)
        |
        v
Response with two parts:
  1. Narrative explanation (text)
  2. Python code block (pandas/plotly)
        |
        v
Streamlit executes the code against df_filtered
        |
        v
Displays: narrative + code + output (table/chart/number)
```

---

## RAG Knowledge Base

Create a `knowledge/` folder with markdown files. These get injected into the
system prompt as context. Keep them short and focused.

### knowledge/methodology.md

```markdown
# Risk Score Methodology

Each event is scored as:
risk = (duration_hours ^ 0.75) x event_weight x flag_multiplier x offshore_bonus
       x night_multiplier x port_proximity x repeat_multiplier x sequence_bonus

Event weights: ENCOUNTER=5.0 (transshipment), GAP=3.2 (dark activity), LOITERING=2.0 (staging)
Flag multipliers: RUS=2.8, IRN=2.4, SYR=2.0, PRK=3.0, LBR=1.3, PAN=1.2, MHL=1.2, others=1.0
Offshore bonus: 1.4x for loitering events in central/eastern Med (lon>15, lat within 8 of 36N)
Non-linear duration exponent (0.75) prevents single extreme events from dominating.
```

### knowledge/iuu_context.md

```markdown
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
```

### knowledge/flags.md

```markdown
# Flag State Risk Context

HIGH RISK (sanctions/dark fleet):
- RUS (273): Russian shadow fleet, sanctions evasion, dark tanker operations
- IRN (422): Iranian vessels, oil sanctions, AIS manipulation
- SYR (468): Syrian conflict, sanctions
- PRK (371): North Korean vessels, weapons/sanctions

FLAGS OF CONVENIENCE (weak oversight):
- PAN (351-354): Panama, largest FOC registry globally
- LBR (636-637): Liberia, second largest FOC
- MHL (538): Marshall Islands, growing FOC
- MLT (248-249): Malta, EU flag but large FOC-like registry

MEDITERRANEAN COASTAL:
- GRC (237-241): Greece, largest EU fleet, Piraeus base
- ITA (247): Italy, major Med fleet
- TUR (271): Turkey, significant Med fleet
- ESP (224-225): Spain, western Med
- CYP (209-212): Cyprus, mixed flag use
```

### knowledge/med_geography.md

```markdown
# Mediterranean Geography for Maritime Analysis

Key areas of concern:
- Strait of Sicily: chokepoint between western and eastern Med, heavy traffic
- Libyan coast: limited MCS capacity, IUU hotspot
- Eastern Med (Cyprus-Lebanon-Syria): sanctions risk, conflict zone proximity
- Adriatic: new FRAs for Nephrops, trawling restrictions
- Aegean: dense Greek island ferry traffic, fishing fleet
- Strait of Gibraltar: Atlantic entry, sanctions monitoring

GFCM Geographical Sub-Areas (GSAs) in the Med: 37 sub-areas total.
Key GSAs: 1-3 (Spain), 5-11 (western Med), 15-21 (central/eastern), 22-29 (eastern).

EEZ boundaries are contested in several areas (Greece-Turkey, Cyprus-Turkey,
Libya-Greece, Italy-Libya). Events near contested boundaries are inherently
more suspicious.
```

---

## Implementation

### Loading RAG context

```python
import os
import glob

def load_knowledge_base():
    """Load all markdown files from knowledge/ folder."""
    docs = []
    knowledge_dir = "knowledge"
    if os.path.exists(knowledge_dir):
        for filepath in sorted(glob.glob(os.path.join(knowledge_dir, "*.md"))):
            with open(filepath, "r") as f:
                docs.append(f"## {os.path.basename(filepath)}\n\n{f.read()}")
    return "\n\n---\n\n".join(docs)

KNOWLEDGE_BASE = load_knowledge_base()
```

### Building the system prompt

```python
def build_system_prompt(df):
    """Build system prompt with dataframe context and domain knowledge."""

    # DataFrame schema
    schema = f"""
DATAFRAME SCHEMA (variable name: df)
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

    system_prompt = f"""You are a maritime intelligence analyst assistant embedded in the
Med Vessel Behaviour Monitor dashboard. You help users analyse vessel behaviour
data in the Mediterranean Sea.

You have access to a pandas DataFrame called `df` containing vessel events
(AIS gaps, encounters, loitering) with risk scores.

{schema}

DOMAIN KNOWLEDGE:
{KNOWLEDGE_BASE}

YOUR CAPABILITIES:
1. Answer questions about the data with domain-informed explanations
2. Generate Python code (pandas, plotly) to analyse the data
3. The code will be executed against the real dataframe

RESPONSE FORMAT:
Always respond with TWO clearly separated sections:

ANALYSIS:
[Your narrative explanation — interpret results with domain knowledge.
 Explain WHY something matters, not just WHAT the numbers are.
 Reference IUU indicators, flag risks, geographic context where relevant.]

CODE:
```python
# Your pandas/plotly code here
# The dataframe is available as `df`
# For charts, assign to `fig` (plotly) — it will be rendered automatically
# For tables, assign to `result_df` — it will be displayed automatically
# For single values, assign to `result_value` — it will be displayed
# Available libraries: pandas (pd), numpy (np), plotly.express (px),
#   plotly.graph_objects (go)
```

RULES:
- Always generate executable code — no pseudocode
- Use `df` as the dataframe variable (already in scope)
- For charts, always use plotly (px or go) and assign to `fig`
- For tables, assign to `result_df`
- Keep code concise — under 30 lines
- If the question cannot be answered from the data, say so clearly
- Do not fabricate data or make up vessel names/MMSIs
- When discussing flags, use the domain knowledge to explain risk context
- When discussing locations, reference relevant Med geography
"""
    return system_prompt
```

### The AI analyst tab

```python
import anthropic
import re

# Add as a new tab in the existing tab structure
# tab6 = "AI Analyst"

with tab_ai:
    st.subheader("AI Maritime Analyst")
    st.markdown(
        "Ask questions about the vessel data in natural language. "
        "The AI will explain the findings and generate analytical code."
    )

    # API key input
    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        help="Get a key at console.anthropic.com"
    )

    # Chat history
    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = []

    # Example questions
    with st.expander("Example questions"):
        examples = [
            "Which flag states have the highest total risk? Why?",
            "Show me all encounters involving Russian-flagged vessels",
            "Are there any vessels with repeated gap events? What pattern do you see?",
            "What's happening in the eastern Mediterranean (longitude > 25)?",
            "Which day had the most suspicious activity and why?",
            "Create a heatmap of event density by latitude and longitude",
            "Compare risk profiles of FOC-flagged vs Mediterranean-flagged vessels",
            "Find vessels that had both a gap and an encounter — could this indicate transshipment?",
            "What's the average gap duration by flag state? Any outliers?",
            "Rank the top 5 riskiest vessels and explain what makes each one suspicious",
        ]
        for ex in examples:
            if st.button(ex, key=f"ex_{hash(ex)}"):
                st.session_state.pending_question = ex

    # Question input
    question = st.chat_input("Ask about the vessel data...")

    # Check for pending question from examples
    if hasattr(st.session_state, "pending_question"):
        question = st.session_state.pending_question
        del st.session_state.pending_question

    if question and api_key:
        # Add user message
        st.session_state.ai_messages.append({"role": "user", "content": question})

        # Call Claude
        try:
            client = anthropic.Anthropic(api_key=api_key)

            # Build messages with history (keep last 10 exchanges for context)
            messages = st.session_state.ai_messages[-20:]

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=build_system_prompt(df_filtered),
                messages=messages,
            )

            assistant_msg = response.content[0].text
            st.session_state.ai_messages.append(
                {"role": "assistant", "content": assistant_msg}
            )

        except Exception as e:
            st.error(f"API error: {e}")
            assistant_msg = None

    # Display conversation
    for msg in st.session_state.ai_messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                # Parse response into narrative and code
                content = msg["content"]

                # Extract code blocks
                code_blocks = re.findall(r"```python\n(.*?)```", content, re.DOTALL)

                # Display narrative (everything outside code blocks)
                narrative = re.sub(r"```python\n.*?```", "", content, flags=re.DOTALL).strip()
                if narrative:
                    st.markdown(narrative)

                # Execute and display code blocks
                for code in code_blocks:
                    with st.expander("Generated Code", expanded=True):
                        st.code(code, language="python")

                    # Execute the code
                    try:
                        # Create execution namespace with the dataframe and libraries
                        exec_namespace = {
                            "df": df_filtered.copy(),
                            "pd": pd,
                            "np": __import__("numpy"),
                            "px": px,
                            "go": __import__("plotly.graph_objects", fromlist=["graph_objects"]),
                        }
                        exec(code, exec_namespace)

                        # Check for outputs
                        if "fig" in exec_namespace and exec_namespace["fig"] is not None:
                            st.plotly_chart(exec_namespace["fig"], use_container_width=True)

                        if "result_df" in exec_namespace and exec_namespace["result_df"] is not None:
                            st.dataframe(exec_namespace["result_df"], use_container_width=True)

                        if "result_value" in exec_namespace and exec_namespace["result_value"] is not None:
                            st.metric("Result", exec_namespace["result_value"])

                    except Exception as e:
                        st.error(f"Code execution error: {e}")
            else:
                st.markdown(msg["content"])

    # Clear chat button
    if st.session_state.ai_messages:
        if st.button("Clear conversation"):
            st.session_state.ai_messages = []
            st.rerun()
```

---

## Security Considerations

Executing LLM-generated code has risks. For a portfolio project this is
acceptable, but add these safeguards:

```python
# Before exec(), add basic safety checks
FORBIDDEN = ["import os", "import sys", "subprocess", "eval(", "open(",
             "__import__", "exec(", "shutil", "pathlib", "requests",
             "urllib", "socket"]

def is_safe_code(code):
    """Basic check that generated code doesn't do anything dangerous."""
    code_lower = code.lower()
    for forbidden in FORBIDDEN:
        if forbidden.lower() in code_lower:
            return False
    return True

# In the execution block:
if is_safe_code(code):
    exec(code, exec_namespace)
else:
    st.warning("Generated code contains restricted operations. Skipping execution.")
```

Also: the exec namespace only includes pandas, numpy, and plotly — no access
to file system, network, or other libraries.

---

## Example Interactions

### Example 1: Simple factual question

**User:** "How many Russian-flagged vessels had gap events?"

**AI Response:**

ANALYSIS:
There are 4 Russian-flagged vessels (MID 273) with AIS gap events in the current
dataset. Russia is flagged as the highest-risk state (multiplier 2.8) due to its
role in operating shadow fleet tankers for sanctions evasion. AIS gaps from
Russian-flagged vessels in the Mediterranean are particularly concerning given
the ongoing sanctions regime and documented dark fleet activity in the eastern
Med.

CODE:
```python
result_df = df[
    (df["flag"] == "RUS") & (df["event_type"] == "GAP")
][["mmsi", "flag", "duration_h", "lat", "lon", "risk_score", "date"]].sort_values(
    "risk_score", ascending=False
)
result_value = f"{len(result_df)} Russian-flagged gap events"
```

### Example 2: Analytical question requiring computation

**User:** "Compare average risk scores between FOC flags and Mediterranean coastal flags"

**AI Response:**

ANALYSIS:
Flag of convenience (FOC) vessels — Panama, Liberia, Marshall Islands — show
meaningfully higher average risk scores than Mediterranean coastal flags (Greece,
Italy, Turkey, Spain, Malta). This is expected: FOC vessels receive a risk
multiplier (1.2-1.3) reflecting weaker regulatory oversight, and FOC-flagged
vessels are disproportionately involved in encounters and longer gap events.
The gap is particularly pronounced for Liberian-flagged vessels which appear
frequently in encounter events.

CODE:
```python
foc_flags = ["PAN", "LBR", "MHL"]
med_flags = ["GRC", "ITA", "TUR", "ESP", "MLT"]

df["flag_category"] = df["flag"].apply(
    lambda x: "FOC" if x in foc_flags
    else "Med Coastal" if x in med_flags
    else "High Risk" if x in ["RUS", "IRN", "SYR", "PRK"]
    else "Other"
)

result_df = df.groupby("flag_category").agg(
    avg_risk=("risk_score", "mean"),
    total_risk=("risk_score", "sum"),
    event_count=("mmsi", "count"),
    unique_vessels=("mmsi", "nunique"),
).round(1).sort_values("avg_risk", ascending=False)

fig = px.bar(
    result_df.reset_index(),
    x="flag_category", y="avg_risk",
    color="flag_category",
    title="Average Risk Score by Flag Category",
    labels={"avg_risk": "Avg Risk Score", "flag_category": "Flag Category"},
)
```

### Example 3: Pattern detection

**User:** "Find vessels that had both a gap and an encounter. Could this indicate transshipment after dark activity?"

**AI Response:**

ANALYSIS:
This is a classic IUU/sanctions evasion pattern: a vessel goes dark (AIS gap),
then conducts a vessel-to-vessel encounter (potential transshipment), then
reappears. This sequence is one of the primary behavioural indicators used by
maritime intelligence platforms to flag suspicious activity.

In the current dataset, I found 3 vessels that had both gap and encounter events.
Two are flagged to flags of convenience (Panama, Liberia), and one is
Russian-flagged. The Russian vessel's gap lasted 42 hours before an encounter
event — a duration and sequence strongly consistent with deliberate concealment
of a transshipment.

CODE:
```python
gap_vessels = set(df[df["event_type"] == "GAP"]["mmsi"].unique())
encounter_vessels = set(df[df["event_type"] == "ENCOUNTER"]["mmsi"].unique())
both = gap_vessels & encounter_vessels

result_df = df[df["mmsi"].isin(both)].sort_values(
    ["mmsi", "date"]
)[["mmsi", "flag", "event_type", "duration_h", "risk_score", "lat", "lon", "date"]]

result_value = f"{len(both)} vessels with both gap and encounter events"
```

---

## Requirements Update

Add to `requirements.txt`:
```
anthropic
```

---

## Integration with Existing App

Add the AI tab to the existing tab structure:

```python
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Daily Risk Trend",
    "Flag Breakdown",
    "Event Type Breakdown",
    "Top 10 Riskiest Vessels",
    "Methodology",
    "AI Analyst",
])
```

The AI Analyst tab goes last — it's the advanced feature. Users who just
want the dashboard ignore it. Users who want to dig deeper use it.

---

## Cost

Claude Sonnet via API: ~$3 per 1M input tokens, ~$15 per 1M output tokens.
A typical question + dataframe context + knowledge base = ~2,000-3,000 input
tokens. A typical answer = ~500-1,000 output tokens.

Cost per question: ~$0.01-0.02.
100 questions during a demo/interview: ~$1-2.

Negligible for a portfolio project.

---

## Interview Talking Points

"The AI Analyst tab is what makes this more than a dashboard. You can ask it
'show me all Russian vessels that went dark near the Libyan coast' and it
generates the pandas code, executes it against the live dataset, and explains
the results with domain context — why Russian flags matter in a sanctions
context, why gaps near Libya are concerning, what transshipment indicators
to look for."

"It uses RAG — the knowledge base includes IUU regulatory context, flag risk
explanations, Mediterranean geography. So the AI doesn't just filter data,
it interprets it like a maritime analyst would."

"I built it with the Anthropic API. Kpler actually launched their own MCP
for maritime intelligence in January 2026 — so this is directly aligned
with where the industry is going: conversational interfaces on top of
maritime data."

---

## What This Demonstrates

- LLM integration in a production-style app (API, system prompts, RAG)
- Code generation and execution (the AI writes pandas, the app runs it)
- Domain-informed AI (not generic ChatGPT — this knows about IUU, flags, Med geography)
- Practical security considerations (sandboxed execution, forbidden operations)
- Conversation memory (multi-turn analysis sessions)
- The same pattern Kpler is pursuing with their MCP product

This is the feature that separates your portfolio from every other
"I made a dashboard" project. It shows you understand where data
products are heading — conversational, AI-augmented, domain-specific.
