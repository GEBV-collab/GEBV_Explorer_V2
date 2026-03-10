import os
import streamlit as st
import pandas as pd
import altair as alt
import json
import time
#new
# ─── Resolve paths relative to this script’s folder ───
BASE = os.path.dirname(__file__)
QCSV = os.path.join(BASE, "data", "GEBVs_quality_23trait_n423.csv")
ACSV = os.path.join(BASE, "data", "GEBVs_ag_73traitmean_n423.csv")

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
SMITH_HAZEL_STATE_FILE = "smith_hazel_result.json"

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

# ─── API Key sidebar input ────────────────────────────
_server_key = os.getenv("ANTHROPIC_API_KEY", "")
st.sidebar.header("API Key")
_user_api_key = st.sidebar.text_input(
    "Anthropic API Key",
    type="password",
    key="user_api_key",
    placeholder="Using server key" if _server_key else "sk-ant-...",
    help="Required for Chat with Data Filtering. Get your key at https://console.anthropic.com/",
)
_effective_api_key = _user_api_key or _server_key
if not _effective_api_key:
    st.sidebar.warning("Enter an API key above to enable the chat feature.")
st.sidebar.divider()

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
            result = chat_with_mcp(user_q, context, api_key=_effective_api_key or None)

        # Store result in session state
        st.session_state.chat_result = result

        # Check if any interactive tool was used (sliders or index)
        interactive_tools = ('adjust_slider', 'reset_all_sliders', 'compute_smith_hazel_index')
        tool_used = any(tc['tool'] in interactive_tools for tc in result.get('tool_calls', []))

        if tool_used:
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

# ─── Genomic Selection Index ──────────────────────
import requests as _req

st.write("---")
st.subheader("Genomic Selection Index")
st.caption(
    "Rank lines using an accuracy-adjusted genomic selection index. "
    "First select the traits you want to include, then assign economic weights. "
    "The index derives adjusted coefficients using b = (RGR)⁻¹RGa, where "
    "G is the covariance of selected GEBV traits and R is the diagonal matrix "
    "of trait prediction accuracies."
)

with st.expander("Configure economic weights and compute index", expanded=True):
    st.markdown("**1. Select traits to include**")

    default_sh_traits = [
        t for t in ["GEBV_yield", "GEBV_DATmaturity", "GEBV_Fruit_pungency"]
        if t in trait_cols
    ]

    selected_sh_traits = st.multiselect(
        "Traits for genomic selection index",
        options=trait_cols,
        default=default_sh_traits,
        format_func=lambda x: x.replace("GEBV_", ""),
        key="sh_selected_traits"
    )

    sh_weights = {}

    if selected_sh_traits:
        st.markdown("**2. Assign economic weights**")

        n_cols = 3
        trait_chunks = [
            selected_sh_traits[i:i + n_cols]
            for i in range(0, len(selected_sh_traits), n_cols)
        ]

        for chunk in trait_chunks:
            cols = st.columns(len(chunk))
            for c, trait in zip(cols, chunk):
                default_weight = 1.0
                if trait == "GEBV_yield":
                    default_weight = 0.7
                elif trait == "GEBV_DATmaturity":
                    default_weight = 0.1
                elif trait == "GEBV_Fruit_pungency":
                    default_weight = 0.2

                sh_weights[trait] = c.number_input(
                    label=trait.replace("GEBV_", ""),
                    min_value=0.0,
                    max_value=100.0,
                    value=float(default_weight),
                    step=0.1,
                    key=f"sh_{trait}"
                )
    else:
        st.info("Select at least two traits to begin.")

    sh_top_n = st.number_input(
        "Top N lines to show",
        min_value=1,
        max_value=500,
        value=20,
        step=1,
        key="sh_top_n"
    )

    sh_btn = st.button("Compute Genomic Selection Index", key="sh_compute_btn")

# Compute from button press
sh_data = None
if sh_btn:
    active_sh = {t: w for t, w in sh_weights.items() if w != 0.0}

    if len(selected_sh_traits) < 2:
        st.warning("Select at least 2 traits for the genomic selection index.")
    elif len(active_sh) < 2:
        st.warning("Assign non-zero economic weights to at least 2 selected traits.")
    else:
        try:
            resp = _req.post(
                "http://127.0.0.1:5001/smith_hazel_index",
                json={"trait_weights": active_sh, "top_n": int(sh_top_n)},
                timeout=15
            )
            if resp.status_code == 200:
                sh_data = resp.json()
            else:
                st.error(f"API error: {resp.json().get('error', 'Unknown error')}")
        except Exception as e:
            st.error(f"Could not reach API server: {e}")
            st.info("Make sure gebv_api_server.py is running on port 5001.")

# If no button press, check for persisted result (from chat/MCP)
if sh_data is None:
    try:
        if os.path.exists(SMITH_HAZEL_STATE_FILE):
            with open(SMITH_HAZEL_STATE_FILE, 'r') as f:
                sh_data = json.load(f)
    except Exception:
        pass

# Display results (from button OR persisted state)
if sh_data and "ranked_lines" in sh_data:
    sh_df = pd.DataFrame(sh_data["ranked_lines"])
    sh_coeffs = sh_data.get("index_coefficients", {})
    econ_w = sh_data.get("economic_weights", {})
    trait_acc = sh_data.get("trait_accuracies", {})
    active_traits = list(econ_w.keys())

    econ_w_str = ", ".join(f"{t.replace('GEBV_', '')}={v:.2f}" for t, v in econ_w.items())
    acc_str = ", ".join(
        f"{t.replace('GEBV_', '')}={trait_acc[t]:.2f}"
        for t in active_traits if t in trait_acc
    )

    st.info(
        f"**How these results are ordered:** Lines are ranked from highest to lowest "
        f"genomic selection index score. You assigned these economic weights: {econ_w_str}. "
        f"The final ranking adjusts those priorities using both the genetic covariance "
        f"among traits and their prediction accuracies. "
        f"Trait prediction accuracies used: {acc_str}. "
        f"Rank 1 = best overall line given your priorities."
    )

    st.caption(
        f"Computed at: {sh_data.get('computed_at', 'unknown')} | "
        f"{sh_data.get('n_lines_scored', '?')} lines scored | "
        f"{sh_data.get('n_lines_covariance', '?')} lines used for G covariance estimation | "
        f"{sh_data.get('note', '')}"
    )

    if trait_acc:
        st.markdown("**Trait prediction accuracies used in the genomic index**")
        acc_df = pd.DataFrame({
            "Trait": [t.replace("GEBV_", "") for t in active_traits],
            "Prediction Accuracy": [trait_acc.get(t, None) for t in active_traits]
        })
        st.dataframe(acc_df, use_container_width=True)

    st.markdown("**Your economic weights vs. derived genomic index coefficients**")
    coeff_df = pd.DataFrame({
        "Trait": [t.replace("GEBV_", "") for t in econ_w],
        "Economic Weight": [econ_w[t] for t in econ_w],
        "Prediction Accuracy": [trait_acc.get(t, None) for t in econ_w],
        "Derived Index Coefficient (b)": [sh_coeffs.get(t, 0) for t in econ_w],
    })
    st.dataframe(coeff_df, use_container_width=True)

    st.markdown(f"**Top {len(sh_df)} lines** (sorted by genomic selection index score, highest first):")
    st.dataframe(sh_df, use_container_width=True)

    bar_sh = (
        alt.Chart(sh_df)
        .mark_bar()
        .encode(
            x=alt.X("SmithHazel_Index:Q", title="Genomic Selection Index Score"),
            y=alt.Y("Line:N", sort="-x", title="Line"),
            tooltip=["Line"] + active_traits + ["SmithHazel_Index"]
        )
        .properties(title=f"Top {len(sh_df)} Lines — Genomic Selection Index (highest = best)")
    )
    st.altair_chart(bar_sh, use_container_width=True)

    col_dl, col_clear = st.columns(2)
    with col_dl:
        st.download_button(
            "Download genomic selection index results CSV",
            sh_df.to_csv(index=False).encode("utf-8"),
            file_name="genomic_selection_index_results.csv",
            mime="text/csv",
        )
    with col_clear:
        if st.button("Clear index results", key="sh_clear"):
            if os.path.exists(SMITH_HAZEL_STATE_FILE):
                os.remove(SMITH_HAZEL_STATE_FILE)
            st.rerun()
