import os
import sys
import streamlit as st
import pandas as pd
import altair as alt
import json
import requests as _req

# ─── Resolve base paths ───────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
GLOBAL_DIR = os.path.join(ROOT, "global")

# ─── 1) App title ─────────────────────────────────────
st.title("🧬 Welcome to GEBV Explorer")

# ─── 2) Collection toggle ─────────────────────────────
st.sidebar.header("Collection")
collection = st.sidebar.radio(
    "Select dataset",
    ["Core Collection (n=423)", "Global Collection (n~10k)"],
    index=0
)
IS_GLOBAL = collection.startswith("Global")

# ─── 3) Collection-specific config ────────────────────
if IS_GLOBAL:
    QCSV = os.path.join(GLOBAL_DIR, "data", "GEBVs_quality_23trait_n10026.csv")
    ACSV = os.path.join(GLOBAL_DIR, "data", "GEBVs_ag_73traitmean_n10024.csv")
    STATE_FILE = os.path.join(GLOBAL_DIR, "global_slider_state.json")
    GENOMIC_STATE_FILE = os.path.join(GLOBAL_DIR, "global_genomic_selection_result.json")
    WEIGHTED_STATE_FILE = os.path.join(GLOBAL_DIR, "global_weighted_index_result.json")
    API_PORT = 5002
    CHAT_SESSION_KEY = "global_chat_result"
    RERUN_SESSION_KEY = "global_should_rerun"
    DEFAULT_X_TRAIT = "GEBV_fruitno_x"
    DEFAULT_Y_TRAIT = "GEBV_yield_y"
    DOWNLOAD_FILENAME = "filtered_global_lines.csv"
else:
    QCSV = os.path.join(ROOT, "data", "GEBVs_quality_23trait_n423.csv")
    ACSV = os.path.join(ROOT, "data", "GEBVs_ag_73traitmean_n423.csv")
    STATE_FILE = os.path.join(ROOT, "slider_state.json")
    GENOMIC_STATE_FILE = os.path.join(ROOT, "genomic_selection_result.json")
    WEIGHTED_STATE_FILE = os.path.join(ROOT, "weighted_index_result.json")
    API_PORT = 5001
    CHAT_SESSION_KEY = "core_chat_result"
    RERUN_SESSION_KEY = "core_should_rerun"
    DEFAULT_X_TRAIT = "GEBV_Brix"
    DEFAULT_Y_TRAIT = "GEBV_yield"
    DOWNLOAD_FILENAME = "filtered_lines_combined.csv"

API_BASE = f"http://127.0.0.1:{API_PORT}"

# ─── 4) Load and merge data ───────────────────────────
df_q = pd.read_csv(QCSV)
df_a = pd.read_csv(ACSV)

if "Group" in df_a.columns and "Group" in df_q.columns:
    df = pd.merge(df_q, df_a, on=["Line", "Group"], how="inner")
else:
    df = pd.merge(df_q, df_a, on="Line", how="inner")

# ─── Slider state helpers ─────────────────────────────
def load_api_slider_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
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

# ─── 5) API Key sidebar ───────────────────────────────
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

# ─── 6) Sidebar sliders ───────────────────────────────
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

# ─── 7) Apply filter ──────────────────────────────────
mask = pd.Series(True, index=df.index)
for col, (lo, hi) in thresholds.items():
    mask &= df[col].between(lo, hi)
filtered = df[mask]

# ─── 8) Chat with Data Filtering ─────────────────────
st.write("---")
st.subheader("Chat with Data Filtering")
st.caption(
    "Use natural language to adjust trait sliders or compute a selection index. "
    "Examples: 'Show me the top 10% for yield', 'Rank lines prioritising yield and Brix'"
)

if CHAT_SESSION_KEY not in st.session_state:
    st.session_state[CHAT_SESSION_KEY] = None
if RERUN_SESSION_KEY not in st.session_state:
    st.session_state[RERUN_SESSION_KEY] = False

if st.session_state[RERUN_SESSION_KEY]:
    st.session_state[RERUN_SESSION_KEY] = False
    st.rerun()

qcol1, qcol2 = st.columns([3, 1])
with qcol1:
    user_q = st.text_input(
        "Your message",
        key=f"mcp_q_{collection}",
        placeholder="e.g., Set yield to top 20% and show available traits"
    )
with qcol2:
    run_chat = st.button("Send")

if run_chat and user_q:
    try:
        if IS_GLOBAL:
            sys.path.insert(0, GLOBAL_DIR)
            from global_mcp_chat import chat_with_mcp
        else:
            from mcp_chat import chat_with_mcp

        context = f"Available traits: {', '.join(trait_cols)}"

        with st.spinner("Processing..."):
            result = chat_with_mcp(user_q, context, api_key=_effective_api_key or None)

        st.session_state[CHAT_SESSION_KEY] = result

        interactive_tools = (
            "adjust_slider", "reset_all_sliders",
            "compute_genomic_selection_index", "compute_selection_index"
        )
        tool_used = any(tc["tool"] in interactive_tools for tc in result.get("tool_calls", []))

        if tool_used:
            st.session_state[RERUN_SESSION_KEY] = True
            st.rerun()

    except Exception as e:
        st.error(f"Chat failed: {e}")

if st.session_state[CHAT_SESSION_KEY]:
    result = st.session_state[CHAT_SESSION_KEY]
    st.markdown(f"**Response:** {result['response']}")

    if result["tool_calls"]:
        with st.expander("Tool calls executed"):
            for tc in result["tool_calls"]:
                st.code(
                    f"Tool: {tc['tool']}\nInput: {tc['input']}\nResult: {tc['result']}",
                    language="yaml"
                )

# ─── 9) Scatter plot ──────────────────────────────────
st.write("---")
st.subheader("Scatter plot of two traits")

default_x = trait_cols.index(DEFAULT_X_TRAIT) if DEFAULT_X_TRAIT in trait_cols else 0
default_y = trait_cols.index(DEFAULT_Y_TRAIT) if DEFAULT_Y_TRAIT in trait_cols else 1

col1, col2 = st.columns(2)
with col1:
    x_sel = st.selectbox("X-axis trait", trait_cols, index=default_x)
with col2:
    y_sel = st.selectbox("Y-axis trait", trait_cols, index=default_y)

if x_sel and y_sel:
    base = (
        alt.Chart(df)
        .mark_circle(size=60, color="lightgray")
        .encode(x=alt.X(x_sel, type="quantitative"), y=alt.Y(y_sel, type="quantitative"),
                tooltip=["Line", x_sel, y_sel])
    )
    highlight = (
        alt.Chart(filtered)
        .mark_circle(size=60, color="red")
        .encode(x=alt.X(x_sel, type="quantitative"), y=alt.Y(y_sel, type="quantitative"),
                tooltip=["Line", x_sel, y_sel])
    )
    st.altair_chart(alt.layer(base, highlight).interactive(), use_container_width=True)

# ─── 10) Lines passing thresholds ────────────────────
st.write("---")
st.subheader("Lines passing thresholds")
st.write(f"Lines passing all thresholds: **{len(filtered)}**")
st.dataframe(filtered, use_container_width=True)

# ─── 11) All lines expander ───────────────────────────
with st.expander("Show all lines (unfiltered)"):
    st.dataframe(df, use_container_width=True)

# ─── 12) Download filtered CSV ────────────────────────
st.write("---")
st.download_button(
    "Download filtered CSV",
    filtered.to_csv(index=False).encode("utf-8"),
    file_name=DOWNLOAD_FILENAME,
    mime="text/csv",
)

# ══════════════════════════════════════════════════════
# ─── 13) Genomic Selection Index ─────────────────────
# ══════════════════════════════════════════════════════
st.write("---")
st.subheader("Genomic Selection Index")
st.caption(
    "Rank lines using an accuracy-adjusted genomic selection index: b = (RGR)⁻¹RGa. "
    "G is the covariance matrix of selected GEBVs; R is a diagonal matrix of trait "
    "prediction accuracies. This is a modified genomic selection approach — not the "
    "classic Smith-Hazel equation — designed to avoid collinearity issues that arise "
    "when training GEBVs and phenotypic data overlap. "
    "First select traits, then assign economic weights."
)

_gsi_prefix = "gsi_global" if IS_GLOBAL else "gsi_core"

with st.expander("Configure economic weights and compute index", expanded=True):
    st.markdown("**1. Select traits to include**")

    default_gsi_traits = [
        t for t in ["GEBV_yield", "GEBV_DATmaturity", "GEBV_Fruit_pungency",
                     "GEBV_yield_y", "GEBV_DATmaturity_y", "GEBV_Fruit_pungency_y"]
        if t in trait_cols
    ][:3]

    selected_gsi_traits = st.multiselect(
        "Traits for genomic selection index",
        options=trait_cols,
        default=default_gsi_traits,
        format_func=lambda x: x.replace("GEBV_", ""),
        key=f"{_gsi_prefix}_selected_traits"
    )

    gsi_weights = {}

    if selected_gsi_traits:
        st.markdown("**2. Assign economic weights**")
        n_cols = 3
        for chunk in [selected_gsi_traits[i:i+n_cols] for i in range(0, len(selected_gsi_traits), n_cols)]:
            cols = st.columns(len(chunk))
            for c, trait in zip(cols, chunk):
                base_name = trait.replace("GEBV_", "").rstrip("_xy").rstrip("_")
                default_w = 0.7 if "yield" in base_name else (0.1 if "DAT" in base_name or "maturity" in base_name else (0.2 if "pungency" in base_name.lower() else 1.0))
                gsi_weights[trait] = c.number_input(
                    label=trait.replace("GEBV_", ""),
                    min_value=0.0, max_value=100.0,
                    value=float(default_w), step=0.1,
                    key=f"{_gsi_prefix}_{trait}"
                )
    else:
        st.info("Select at least two traits to begin.")

    gsi_top_n = st.number_input(
        "Top N lines to show", min_value=1, max_value=500, value=20, step=1,
        key=f"{_gsi_prefix}_top_n"
    )

    gsi_btn = st.button("Compute Genomic Selection Index", key=f"{_gsi_prefix}_compute_btn")

gsi_data = None
if gsi_btn:
    active_gsi = {t: w for t, w in gsi_weights.items() if w != 0.0}

    if len(selected_gsi_traits) < 2:
        st.warning("Select at least 2 traits for the genomic selection index.")
    elif len(active_gsi) < 2:
        st.warning("Assign non-zero economic weights to at least 2 selected traits.")
    else:
        try:
            resp = _req.post(
                f"{API_BASE}/genomic_selection_index",
                json={"trait_weights": active_gsi, "top_n": int(gsi_top_n)},
                timeout=15
            )
            if resp.status_code == 200:
                gsi_data = resp.json()
            else:
                st.error(f"API error: {resp.json().get('error', 'Unknown error')}")
        except Exception as e:
            st.error(f"Could not reach API server: {e}")
            st.info(f"Make sure the API server is running on port {API_PORT}.")

if gsi_data is None:
    try:
        if os.path.exists(GENOMIC_STATE_FILE):
            with open(GENOMIC_STATE_FILE, 'r') as f:
                gsi_data = json.load(f)
    except Exception:
        pass

if gsi_data and "ranked_lines" in gsi_data:
    gsi_df = pd.DataFrame(gsi_data["ranked_lines"])
    gsi_coeffs = gsi_data.get("index_coefficients", {})
    econ_w = gsi_data.get("economic_weights", {})
    trait_acc = gsi_data.get("trait_accuracies", {})
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
        f"among traits and their prediction accuracies [b = (RGR)⁻¹RGa]. "
        f"Trait prediction accuracies used: {acc_str}. "
        f"Rank 1 = best overall line given your priorities."
    )

    st.caption(
        f"Computed at: {gsi_data.get('computed_at', 'unknown')} | "
        f"{gsi_data.get('n_lines_scored', '?')} lines scored | "
        f"{gsi_data.get('note', '')}"
    )

    if trait_acc:
        st.markdown("**Trait prediction accuracies used in the genomic index**")
        st.dataframe(pd.DataFrame({
            "Trait": [t.replace("GEBV_", "") for t in active_traits],
            "Prediction Accuracy": [trait_acc.get(t, None) for t in active_traits]
        }), use_container_width=True)

    st.markdown("**Your economic weights vs. derived genomic index coefficients**")
    st.dataframe(pd.DataFrame({
        "Trait": [t.replace("GEBV_", "") for t in econ_w],
        "Economic Weight": [econ_w[t] for t in econ_w],
        "Prediction Accuracy": [trait_acc.get(t, None) for t in econ_w],
        "Derived Index Coefficient (b)": [gsi_coeffs.get(t, 0) for t in econ_w],
    }), use_container_width=True)

    st.markdown(f"**Top {len(gsi_df)} lines** (sorted by genomic selection index score, highest first):")
    st.dataframe(gsi_df, use_container_width=True)

    bar_gsi = (
        alt.Chart(gsi_df)
        .mark_bar()
        .encode(
            x=alt.X("Genomic_Selection_Index:Q", title="Genomic Selection Index Score"),
            y=alt.Y("Line:N", sort="-x", title="Line"),
            tooltip=["Line"] + active_traits + ["Genomic_Selection_Index"]
        )
        .properties(title=f"Top {len(gsi_df)} Lines — Genomic Selection Index (highest = best)")
    )
    st.altair_chart(bar_gsi, use_container_width=True)

    col_dl, col_clear = st.columns(2)
    with col_dl:
        st.download_button(
            "Download genomic selection index results CSV",
            gsi_df.to_csv(index=False).encode("utf-8"),
            file_name=f"genomic_selection_index_{'global' if IS_GLOBAL else 'core'}_results.csv",
            mime="text/csv",
        )
    with col_clear:
        if st.button("Clear index results", key=f"{_gsi_prefix}_clear"):
            if os.path.exists(GENOMIC_STATE_FILE):
                os.remove(GENOMIC_STATE_FILE)
            st.rerun()

# ══════════════════════════════════════════════════════
# ─── 14) Weighted Selection Index ────────────────────
# ══════════════════════════════════════════════════════
st.write("---")
st.subheader("Weighted Selection Index")
st.caption(
    "Rank lines by a composite score I = Σ(wⱼ × zᵢⱼ), where zᵢⱼ is the z-score of "
    "trait j for line i. Traits are standardised to the same scale before combining. "
    "Weights are normalized automatically. This is a simpler approach than the genomic "
    "selection index — it treats traits as independent with no covariance or accuracy adjustment."
)

_wt_prefix = "wt_global" if IS_GLOBAL else "wt_core"

with st.expander("Configure weights and compute index", expanded=True):
    st.markdown("**1. Select traits to include**")

    default_wt_traits = [
        t for t in ["GEBV_yield", "GEBV_DATmaturity", "GEBV_Fruit_pungency",
                     "GEBV_yield_y", "GEBV_DATmaturity_y", "GEBV_Fruit_pungency_y"]
        if t in trait_cols
    ][:3]

    selected_wt_traits = st.multiselect(
        "Traits for weighted index",
        options=trait_cols,
        default=default_wt_traits,
        format_func=lambda x: x.replace("GEBV_", ""),
        key=f"{_wt_prefix}_selected_traits"
    )

    wt_inputs = {}

    if selected_wt_traits:
        st.markdown("**2. Assign weights**")
        n_cols = 3
        for chunk in [selected_wt_traits[i:i+n_cols] for i in range(0, len(selected_wt_traits), n_cols)]:
            cols = st.columns(len(chunk))
            for c, trait in zip(cols, chunk):
                base_name = trait.replace("GEBV_", "").rstrip("_xy").rstrip("_")
                default_w = 0.7 if "yield" in base_name else (0.1 if "DAT" in base_name or "maturity" in base_name else (0.2 if "pungency" in base_name.lower() else 1.0))
                wt_inputs[trait] = c.number_input(
                    label=trait.replace("GEBV_", ""),
                    min_value=0.0, max_value=100.0,
                    value=float(default_w), step=0.1,
                    key=f"{_wt_prefix}_{trait}"
                )
    else:
        st.info("Select one or more traits to begin.")

    wt_top_n = st.number_input(
        "Top N lines to show", min_value=1, max_value=500, value=20, step=1,
        key=f"{_wt_prefix}_top_n"
    )

    wt_btn = st.button("Compute Weighted Index", key=f"{_wt_prefix}_compute_btn")

idx_data = None
if wt_btn:
    active_wt = {t: w for t, w in wt_inputs.items() if w != 0.0}

    if not selected_wt_traits:
        st.warning("Select at least one trait.")
    elif not active_wt:
        st.warning("Assign a non-zero weight to at least one selected trait.")
    else:
        try:
            resp = _req.post(
                f"{API_BASE}/selection_index",
                json={"trait_weights": active_wt, "top_n": int(wt_top_n)},
                timeout=15
            )
            if resp.status_code == 200:
                idx_data = resp.json()
            else:
                st.error(f"API error: {resp.json().get('error', 'Unknown error')}")
        except Exception as e:
            st.error(f"Could not reach API server: {e}")
            st.info(f"Make sure the API server is running on port {API_PORT}.")

if idx_data is None:
    try:
        if os.path.exists(WEIGHTED_STATE_FILE):
            with open(WEIGHTED_STATE_FILE, 'r') as f:
                idx_data = json.load(f)
    except Exception:
        pass

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

    col_dl, col_clear = st.columns(2)
    with col_dl:
        st.download_button(
            "Download weighted index results CSV",
            idx_df.to_csv(index=False).encode("utf-8"),
            file_name=f"weighted_index_{'global' if IS_GLOBAL else 'core'}_results.csv",
            mime="text/csv",
        )
    with col_clear:
        if st.button("Clear index results", key=f"{_wt_prefix}_clear"):
            if os.path.exists(WEIGHTED_STATE_FILE):
                os.remove(WEIGHTED_STATE_FILE)
            st.rerun()
