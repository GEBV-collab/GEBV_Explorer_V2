#!/usr/bin/env python3
"""
GEBV Explorer API Server — Global Collection
Flask API to manage slider state between MCP server and Streamlit app.
Runs on port 5002 (core collection uses port 5001).
"""

from flask import Flask, request, jsonify
import json
import os
from datetime import datetime
import numpy as np
import pandas as pd

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Simple in-memory storage
slider_state = {}
smith_hazel_result = None
state_file = os.path.join(BASE_DIR, "global_slider_state.json")
SMITH_HAZEL_STATE_FILE = os.path.join(BASE_DIR, "global_smith_hazel_result.json")
ACCURACY_PATH = os.path.join(BASE_DIR, "data", "n10k_PAs_96traits.csv")


def load_state():
    """Load slider state from file if it exists"""
    global slider_state
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                slider_state = json.load(f)
        except:
            slider_state = {}


def save_state():
    """Save current slider state to file"""
    with open(state_file, 'w') as f:
        json.dump(slider_state, f, indent=2)


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.route('/sliders', methods=['GET'])
def get_sliders():
    return jsonify(slider_state)


@app.route('/sliders/<trait>', methods=['POST'])
def set_slider(trait):
    data = request.get_json()

    if not data or 'start_percent' not in data or 'end_percent' not in data:
        return jsonify({"error": "Missing start_percent or end_percent"}), 400

    start = float(data['start_percent'])
    end = float(data['end_percent'])

    if not (0 <= start <= 100) or not (0 <= end <= 100):
        return jsonify({"error": "Percentages must be between 0 and 100"}), 400

    if start > end:
        return jsonify({"error": "start_percent cannot be greater than end_percent"}), 400

    slider_state[trait] = {
        "start_percent": start,
        "end_percent": end,
        "updated_at": datetime.now().isoformat()
    }

    save_state()

    return jsonify({
        "message": f"Set {trait} slider to {start}% - {end}%",
        "trait": trait,
        "start_percent": start,
        "end_percent": end
    })


@app.route('/sliders/reset', methods=['POST'])
def reset_sliders():
    global slider_state
    slider_state = {}
    save_state()
    return jsonify({"message": "All sliders reset"})


@app.route('/sliders/<trait>', methods=['DELETE'])
def reset_slider(trait):
    if trait in slider_state:
        del slider_state[trait]
        save_state()
        return jsonify({"message": f"Reset {trait} slider"})
    else:
        return jsonify({"message": f"Slider {trait} not found"}), 404


@app.route('/traits', methods=['GET'])
def get_traits():
    """Get list of available GEBV traits from the global data"""
    try:
        QCSV = os.path.join(BASE_DIR, "data", "GEBVs_quality_23trait_n10026.csv")
        ACSV = os.path.join(BASE_DIR, "data", "GEBVs_ag_73traitmean_n10024.csv")

        df_q = pd.read_csv(QCSV)
        df_a = pd.read_csv(ACSV)

        if "Group" in df_a.columns and "Group" in df_q.columns:
            df = pd.merge(df_q, df_a, on=["Line", "Group"], how="inner")
        else:
            df = pd.merge(df_q, df_a, on="Line", how="inner")

        trait_cols = [c for c in df.columns if c.startswith("GEBV_")]

        return jsonify({
            "traits": trait_cols,
            "count": len(trait_cols)
        })

    except Exception as e:
        return jsonify({"error": f"Could not load traits: {str(e)}"}), 500


def _load_df():
    """Load and merge the GEBV dataframes."""
    QCSV = os.path.join(BASE_DIR, "data", "GEBVs_quality_23trait_n10026.csv")
    ACSV = os.path.join(BASE_DIR, "data", "GEBVs_ag_73traitmean_n10024.csv")
    df_q = pd.read_csv(QCSV)
    df_a = pd.read_csv(ACSV)
    if "Group" in df_a.columns and "Group" in df_q.columns:
        return pd.merge(df_q, df_a, on=["Line", "Group"], how="inner")
    return pd.merge(df_q, df_a, on="Line", how="inner")


def _load_accuracy_lookup():
    """Load trait prediction accuracies and return a dict keyed by trait name without GEBV_ prefix."""
    acc_df = pd.read_csv(ACCURACY_PATH)

    required_cols = {"trait", "r.mean"}
    if not required_cols.issubset(acc_df.columns):
        raise ValueError(
            f"Accuracy file must contain columns: {', '.join(sorted(required_cols))}"
        )

    acc_df["trait"] = acc_df["trait"].astype(str).str.strip()
    acc_df["r.mean"] = acc_df["r.mean"].astype(float)
    return dict(zip(acc_df["trait"], acc_df["r.mean"]))


def _trait_to_pa_name(trait_name):
    """
    Convert app/API trait names to PA table trait names.

    Examples:
      GEBV_Brix -> Brix
      GEBV_yield_y -> yield
      GEBV_fruitno_x -> fruitno
    """
    t = trait_name.replace("GEBV_", "", 1)
    if t.endswith("_x") or t.endswith("_y"):
        t = t[:-2]
    return t


@app.route('/smith_hazel_index', methods=['POST'])
def compute_smith_hazel_index():
    """
    Compute an accuracy-adjusted genomic selection index.

    G matrix is estimated as the sample covariance of the selected GEBV traits.
    R is a diagonal matrix of trait prediction accuracies loaded from the PA table.

    Index coefficients are calculated as:
        b = (R G R)^-1 (R G a)
    where a is the vector of user-supplied economic weights.
    """
    global smith_hazel_result

    data = request.get_json()
    if not data or "trait_weights" not in data:
        return jsonify({"error": "Missing trait_weights"}), 400

    trait_weights = data["trait_weights"]
    top_n = int(data.get("top_n", 20))

    if len(trait_weights) < 2:
        return jsonify({"error": "Index requires at least 2 traits"}), 400

    try:
        df = _load_df()
    except Exception as e:
        return jsonify({"error": f"Could not load data: {str(e)}"}), 500

    try:
        accuracy_lookup = _load_accuracy_lookup()
    except Exception as e:
        return jsonify({"error": f"Could not load prediction accuracies: {str(e)}"}), 500

    missing = [t for t in trait_weights if t not in df.columns]
    if missing:
        return jsonify({"error": f"Traits not found: {', '.join(missing)}"}), 400

    traits = list(trait_weights.keys())
    w = np.array([trait_weights[t] for t in traits], dtype=float).reshape(-1, 1)

    # Match selected traits to PA table names
    pa_traits = [_trait_to_pa_name(t) for t in traits]
    missing_acc = [t for t in pa_traits if t not in accuracy_lookup]
    if missing_acc:
        return jsonify({
            "error": (
                "Prediction accuracies not found for: "
                + ", ".join(missing_acc)
                + ". Check that the PA file uses trait names matching the GEBV traits "
                  "after removing the 'GEBV_' prefix and any trailing _x/_y suffix."
            )
        }), 400

    # Use only lines with complete data for the selected traits
    df_complete = df.dropna(subset=traits).copy()

    if len(df_complete) < 3:
        return jsonify({"error": "Too few lines with complete GEBV data for the selected traits"}), 400

    X = df_complete[traits].values
    line_ids = df_complete["Line"].values
    group_col = df_complete["Group"].values if "Group" in df_complete.columns else None

    # G from selected GEBV covariance
    G = np.cov(X, rowvar=False)

    # R from prediction accuracies
    acc = np.array([accuracy_lookup[t] for t in pa_traits], dtype=float)
    R = np.diag(acc)

    # Solve b = (RGR)^-1 (RGa)
    try:
        M = R @ G @ R
        M = M + np.eye(M.shape[0]) * 1e-8  # numerical stability
        b = np.linalg.solve(M, R @ G @ w)
    except np.linalg.LinAlgError:
        return jsonify({"error": "RGR matrix is singular — selected traits may be too highly correlated"}), 400

    scores = (X @ b).ravel()

    result_df = pd.DataFrame({"Line": line_ids, "SmithHazel_Index": scores})
    for t in traits:
        result_df[t] = df_complete[t].values
    if group_col is not None:
        result_df["Group"] = group_col

    result_df = result_df.sort_values("SmithHazel_Index", ascending=False).head(top_n)

    index_coefficients = {t: float(b[i, 0]) for i, t in enumerate(traits)}
    trait_accuracies = {traits[i]: float(acc[i]) for i in range(len(traits))}

    smith_hazel_result = {
        "ranked_lines": result_df.to_dict(orient="records"),
        "index_coefficients": index_coefficients,
        "economic_weights": trait_weights,
        "trait_accuracies": trait_accuracies,
        "n_lines_scored": int(len(df_complete)),
        "n_lines_covariance": int(len(df_complete)),
        "computed_at": datetime.now().isoformat(),
        "note": (
            "G was estimated from selected GEBV covariance and R from trait prediction "
            "accuracies. Index coefficients were computed using b = (RGR)^-1(RGa)."
        )
    }

    with open(SMITH_HAZEL_STATE_FILE, 'w') as f:
        json.dump(smith_hazel_result, f, indent=2)

    return jsonify(smith_hazel_result)


@app.route('/smith_hazel_index/result', methods=['GET'])
def get_smith_hazel_result():
    if smith_hazel_result is None:
        return jsonify({"error": "No result yet"}), 404
    return jsonify(smith_hazel_result)


if __name__ == '__main__':
    load_state()
    print("GEBV Global API Server starting on port 5002...")
    print("Endpoints:")
    print("  GET  /health - Health check")
    print("  GET  /traits - Get available GEBV trait names")
    print("  GET  /sliders - Get all slider states")
    print("  POST /sliders/<trait> - Set slider (JSON: {start_percent, end_percent})")
    print("  POST /sliders/reset - Reset all sliders")
    print("  DEL  /sliders/<trait> - Reset specific slider")
    print("  POST /smith_hazel_index - Compute accuracy-adjusted genomic selection index")
    print("  GET  /smith_hazel_index/result - Get last computed index result")

    app.run(host='0.0.0.0', port=5002, debug=False)
