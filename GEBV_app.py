import os
import streamlit as st
import pandas as pd
import altair as alt
import json
import time
#new
# ─── Resolve paths relative to this script’s folder ───
BASE = os.path.dirname(__file__)
QCSV = os.path.join(BASE, "data", "GEBV_quality_core_16traits_n423.csv")
ACSV = os.path.join(BASE, "data", "GEBVs_core_13_agronomic_traits_avg.csv")

# ─── 1) App title ─────────────────────────────────────
st.title("🧬 Welcome to GEBV Explorer")

# ─── 2) Load and merge data ──────────────────────────
df_q = pd.read_csv(QCSV)   # ← use QCSV here
df_a = pd.read_csv(ACSV)   # ← and ACSV here

if "Group" in df_a.columns and "Group" in df_q.columns:
    df = pd.merge(df_q, df_a, on=["Line", "Group"], how="inner")
else:
    df = pd.merge(df_q, df_a, on="Line", how="inner")

# ─── Shared State Management ─────────────────────────
STATE_FILE = "slider_state.json"

def load_api_slider_state():
    """Load slider state from shared file"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def get_slider_value_from_api(trait_col, df):
    """Get slider range from API state or return full range"""
    api_state = load_api_slider_state()
    
    if trait_col in api_state:
        state = api_state[trait_col]
        min_val = float(df[trait_col].quantile(state["start_percent"] / 100))
        max_val = float(df[trait_col].quantile(state["end_percent"] / 100))
        return (min_val, max_val), True
    
    # Return full range if no API override
    lo, hi = float(df[trait_col].min()), float(df[trait_col].max())
    return (lo, hi), False

# ─── 3) Sidebar sliders (with API integration) ─────
trait_cols = [c for c in df.columns if c.startswith("GEBV_")]
st.sidebar.header("Thresholds")
thresholds = {}

for col in trait_cols:
    lo, hi = float(df[col].min()), float(df[col].max())
    
    # Check if API has set a value for this slider
    (api_min, api_max), has_api_value = get_slider_value_from_api(col, df)
    
    # Use API value if available, otherwise use full range
    default_value = (api_min, api_max) if has_api_value else (lo, hi)
    
    # Add indicator for AI-controlled sliders
    label = f"🤖 {col}" if has_api_value else col
    
    thresholds[col] = st.sidebar.slider(
        label=label,
        min_value=lo,
        max_value=hi,
        value=default_value,
        help=f"Select {col} between {lo:.2f} and {hi:.2f}" + 
             (" - AI controlled" if has_api_value else "")
    )

# ─── 4) Apply filter ──────────────────────────────────
mask = pd.Series(True, index=df.index)
for col, (lo, hi) in thresholds.items():
    mask &= df[col].between(lo, hi)
filtered = df[mask]

# ─── 5) Display filtered table ───────────────────────
st.write(f"Lines passing all thresholds: **{len(filtered)}**")
st.dataframe(filtered)

# ─── 6) All-lines expander ───────────────────────────
with st.expander("Show all lines (unfiltered)"):
    st.dataframe(df)

# ─── 7) Scatter plot layering ────────────────────────
st.write("---")
st.subheader("Scatter plot of two traits")

default_x = trait_cols.index("GEBV_Brix") if "GEBV_Brix" in trait_cols else 0
default_y = trait_cols.index("GEBV_yield") if "GEBV_yield" in trait_cols else 1

col1, col2 = st.columns(2)
with col1:
    x_sel = st.selectbox("X-axis trait", trait_cols, index=default_x)
with col2:
    y_sel = st.selectbox("Y-axis trait", trait_cols, index=default_y)

if x_sel and y_sel:
    base = (
        alt.Chart(df)
        .mark_circle(size=60, color="lightgray")
        .encode(
            x=alt.X(x_sel, type="quantitative"),
            y=alt.Y(y_sel, type="quantitative"),
            tooltip=["Line", x_sel, y_sel]
        )
    )
    highlight = (
        alt.Chart(filtered)
        .mark_circle(size=60, color="red")
        .encode(
            x=alt.X(x_sel, type="quantitative"),
            y=alt.Y(y_sel, type="quantitative"),
            tooltip=["Line", x_sel, y_sel]
        )
    )
    st.altair_chart(alt.layer(base, highlight).interactive(),
                    use_container_width=True)

# ─── 8) Download filtered CSV ─────────────────────────
st.write("---")
st.download_button(
    "Download filtered CSV",
    filtered.to_csv(index=False).encode("utf-8"),
    file_name="filtered_lines_combined.csv",
    mime="text/csv",
)
# ─── 7a) Chat with Data Filtering ─────────────────────────
st.write("---")
st.subheader("Chat with Data Filtering")
st.caption("Use natural language to adjust trait sliders. Examples: 'Show me the top 10% for yield', 'Filter for high Brix and low pungency'")

# Initialize session state for chat history
if 'chat_result' not in st.session_state:
    st.session_state.chat_result = None
if 'should_rerun' not in st.session_state:
    st.session_state.should_rerun = False

# Check if we need to rerun (after sliders were adjusted)
if st.session_state.should_rerun:
    st.session_state.should_rerun = False
    st.rerun()

qcol1, qcol2 = st.columns([3,1])
with qcol1:
    user_q = st.text_input("Your message", key="mcp_q", placeholder="e.g., Set yield to top 20% and show available traits")
with qcol2:
    run_chat = st.button("Send")

if run_chat and user_q:
    try:
        from mcp_chat import chat_with_mcp

        # Build context about current state
        context = f"Available traits: {', '.join(trait_cols)}"

        with st.spinner("Processing..."):
            result = chat_with_mcp(user_q, context)

        # Store result in session state
        st.session_state.chat_result = result

        # Check if any slider was adjusted or reset
        slider_adjusted = any(tc['tool'] in ('adjust_slider', 'reset_all_sliders') for tc in result.get('tool_calls', []))

        if slider_adjusted:
            st.session_state.should_rerun = True
            st.rerun()

    except Exception as e:
        st.error(f"Chat failed: {e}")

# Display the last chat result (persists across reruns)
if st.session_state.chat_result:
    result = st.session_state.chat_result
    st.markdown(f"**Response:** {result['response']}")

    if result['tool_calls']:
        with st.expander("Tool calls executed"):
            for tc in result['tool_calls']:
                st.code(f"Tool: {tc['tool']}\nInput: {tc['input']}\nResult: {tc['result']}", language="yaml")

# ─── 7b) Trait–Trait Correlation Heatmap ──────────────
import seaborn as sns
import matplotlib.pyplot as plt

st.write("---")
st.subheader("Trait–Trait Correlation Heatmap")

# Compute correlation matrix for selected traits
corr = df[trait_cols].corr()

fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(
    corr,
    annot=True,
    fmt=".2f",
    cmap="coolwarm",
    center=0,
    ax=ax,
    cbar_kws={'label': 'Pearson Correlation'},
    annot_kws={"size": 5}  # 👈 Set annotation font size here
)

st.pyplot(fig)
