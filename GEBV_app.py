import os
import streamlit as st
import pandas as pd
import altair as alt
import json
import requests as _req

# ─── Resolve paths relative to this script’s folder ───
BASE = os.path.dirname(__file__)
QCSV = os.path.join(BASE, "data", "GEBVs_quality_23trait_n423.csv")
ACSV = os.path.join(BASE, "data", "GEBVs_ag_73traitmean_n423.csv")

# ─── 1) App title ─────────────────────────────────────
st.title("🧬 Welcome to GEBV Explorer")

# ─── 2) Load and merge data ──────────────────────────
df_q = pd.read_csv(QCSV)
df_a = pd.read_csv(ACSV)

if "Group" in df_a.columns and "Group" in df_q.columns:
    df = pd.merge(df_q, df_a, on=["Line", "Group"], how="inner")
else:
    df = pd.merge(df_q, df_a, on="Line", how="inner")

# ─── Shared State Management ─────────────────────────
STATE_FILE = "slider_state.json"
WEIGHTED_INDEX_STATE_FILE = "weighted_index_result.json"

def load_api_slider_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def get_slider_value_from_api(trait_col, df):
    api_state = load_api_slider_state()

    if trait_col in api_state:
        state = api_state[trait_col]
        min_val = float(df[trait_col].quantile(state["start_percent"] / 100))
        max_val = float(df[trait_col].quantile(state["end_percent"] / 100))
        return (min_val, max_val), True

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

# ─── 3) Sidebar sliders ──────────────────────────────
trait_cols = [c for c in df.columns if c.startswith("GEBV_")]
st.sidebar.header("Thresholds")
thresholds = {}

for col in trait_cols:
    lo, hi = float(df[col].min()), float(df[col].max())
    (api_min, api_max), has_api_value = get_slider_value_from_api(col, df)
    default_value = (api_min, api_max) if has_api_value else (lo, hi)
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

# ─── 5) Chat with Data Filtering ─────────────────────
st.write("---")
st.subheader("Chat with Data Filtering")
st.caption(
    "Use natural language to adjust trait sliders. Examples: "
    "'Show me the top 10% for yield', 'Filter for high Brix and low pungency'"
)

if "chat_result" not in st.session_state:
    st.session_state.chat_result = None
if "should_rerun" not in st.session_state:
    st.session_state.should_rerun = False

if st.session_state.should_rerun:
    st.session_state.should_rerun = False
    st.rerun()

qcol1, qcol2 = st.columns([3, 1])
with qcol1:
    user_q = st.text_input(
        "Your message",
        key="mcp_q",
        placeholder="e.g., Set yield to top 20% and show available traits"
    )
with qcol2:
    run_chat = st.button("Send")

if run_chat and user_q:
    try:
        from mcp_chat import chat_with_mcp

        context = f"Available traits: {', '.join(trait_cols)}"

        with st.spinner("Processing..."):
            result = chat_with_mcp(user_q, context, api_key=_effective_api_key or None)

        st.session_state.chat_result = result

        interactive_tools = ("adjust_slider", "reset_all_sliders", "compute_selection_index")
        tool_used = any(tc["tool"] in interactive_tools for tc in result.get("tool_calls", []))

        if tool_used:
            st.session_state.should_rerun = True
            st.rerun()

    except Exception as e:
        st.error(f"Chat failed: {e}")

if st.session_state.chat_result:
    result = st.session_state.chat_result
    st.markdown(f"**Response:** {result['response']}")

    if result["tool_calls"]:
        with st.expander("Tool calls executed"):
            for tc in result["tool_calls"]:
                st.code(
                    f"Tool: {tc['tool']}\nInput: {tc['input']}\nResult: {tc['result']}",
                    language="yaml"
                )

# ─── 6) Scatter plot ─────────────────────────────────
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
    st.altair_chart(alt.layer(base, highlight).interactive(), use_container_width=True)

# ─── 7) Lines passing thresholds ─────────────────────
st.write("---")
st.subheader("Lines passing thresholds")
st.write(f"Lines passing all thresholds: **{len(filtered)}**")
st.dataframe(filtered, use_container_width=True)

# ─── 8) Weighted Selection Index ────────────────────
st.write("---")
st.subheader("Weighted Selection Index")
st.caption(
    "Rank lines by a composite score I = Σ(wⱼ × zᵢⱼ), where zᵢⱼ is the "
    "z-score of trait j for line i. First select the traits you want to include, "
    "then assign weights. Weights are normalized automatically."
)

with st.expander("Configure weights and compute index", expanded=True):
    st.markdown("**1. Select traits to include**")

    default_traits = [
        t for t in ["GEBV_yield", "GEBV_DATmaturity", "GEBV_Fruit_pungency"]
        if t in trait_cols
    ]

    selected_traits = st.multiselect(
        "Traits for weighted index",
        options=trait_cols,
        default=default_traits,
        format_func=lambda x: x.replace("GEBV_", ""),
        key="wt_selected_traits"
    )

    weight_inputs = {}

    if selected_traits:
        st.markdown("**2. Assign weights**")

        n_cols = 3
        trait_chunks = [selected_traits[i:i + n_cols] for i in range(0, len(selected_traits), n_cols)]

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

                weight_inputs[trait] = c.number_input(
                    label=trait.replace("GEBV_", ""),
                    min_value=0.0,
                    max_value=100.0,
                    value=float(default_weight),
                    step=0.1,
                    key=f"wt_{trait}"
                )
    else:
        st.info("Select one or more traits to begin.")

    top_n_index = st.number_input(
        "Top N lines to show",
        min_value=1,
        max_value=500,
        value=20,
        step=1,
        key="wt_top_n"
    )

    compute_btn = st.button("Compute Index", key="wt_compute_btn")

idx_data = None
if compute_btn:
    active_weights = {t: w for t, w in weight_inputs.items() if w != 0.0}

    if not selected_traits:
        st.warning("Select at least one trait.")
    elif not active_weights:
        st.warning("Assign a non-zero weight to at least one selected trait.")
    else:
        try:
            resp = _req.post(
                "http://127.0.0.1:5001/selection_index",
                json={"trait_weights": active_weights, "top_n": int(top_n_index)},
                timeout=15,
            )
            if resp.status_code == 200:
                idx_data = resp.json()
            else:
                st.error(f"API error: {resp.json().get('error', 'Unknown error')}")
        except Exception as e:
            st.error(f"Could not reach API server: {e}")
            st.info("Make sure gebv_api_server.py is running on port 5001.")

if idx_data and "results" in idx_data:
    idx_df = pd.DataFrame(idx_data["results"])
    nw = idx_data.get("normalized_weights", {})
    raw_w = idx_data.get("trait_weights", {})
    active_traits = list(raw_w.keys())

    nw_str = ", ".join(f"{t.replace('GEBV_', '')}={v:.1%}" for t, v in nw.items())
    st.info(
        f"**How these results are ordered:** Lines are ranked from highest to lowest "
        f"composite index score. Each trait is z-score standardised (mean=0, sd=1) so "
        f"they are on the same scale, then combined using your normalised weights: "
        f"{nw_str}. Rank 1 = best overall line given your priorities."
    )

    st.caption(f"Computed at: {idx_data.get('computed_at', 'unknown')}")
    st.markdown(f"**Top {len(idx_df)} lines** (sorted by index score, highest first):")
    st.dataframe(idx_df, use_container_width=True)

    bar = (
        alt.Chart(idx_df)
        .mark_bar()
        .encode(
            x=alt.X("index_score:Q", title="Index Score (z-score units)"),
            y=alt.Y("Line:N", sort="-x", title="Line"),
            tooltip=["rank", "Line"] + active_traits + ["index_score"],
        )
        .properties(title=f"Top {len(idx_df)} Lines — Weighted Selection Index (highest = best)")
    )
    st.altair_chart(bar, use_container_width=True)

# ─── 9) Show all lines ───────────────────────────────
st.write("---")
with st.expander("Show all lines (unfiltered)"):
    st.dataframe(df, use_container_width=True)

# ─── 10) Download filtered CSV ───────────────────────
st.write("---")
st.download_button(
    "Download filtered CSV",
    filtered.to_csv(index=False).encode("utf-8"),
    file_name="filtered_lines_combined.csv",
    mime="text/csv",
)
