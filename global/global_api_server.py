#!/usr/bin/env python3
"""
GEBV Explorer API Server — Global Collection
Flask API to manage slider state and compute selection indices.
Runs on port 5002 (global collection, n~10k).
"""

from flask import Flask, request, jsonify
import json
import os
from datetime import datetime
import numpy as np
import pandas as pd

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

slider_state = {}
_genomic_selection_result = None
_weighted_index_result = {}

state_file = os.path.join(BASE_DIR, "global_slider_state.json")
GENOMIC_SELECTION_STATE_FILE = os.path.join(BASE_DIR, "global_genomic_selection_result.json")
WEIGHTED_INDEX_STATE_FILE = os.path.join(BASE_DIR, "global_weighted_index_result.json")
ACCURACY_PATH = os.path.join(DATA_DIR, "n10k_PAs_96traits.csv")


def load_state():
    global slider_state
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                slider_state = json.load(f)
        except:
            slider_state = {}


def save_state():
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
    return jsonify({"message": f"Slider {trait} not found"}), 404


@app.route('/traits', methods=['GET'])
def get_traits():
    try:
        df = _load_df()
        trait_cols = [c for c in df.columns if c.startswith("GEBV_")]
        return jsonify({"traits": trait_cols, "count": len(trait_cols)})
    except Exception as e:
        return jsonify({"error": f"Could not load traits: {str(e)}"}), 500


def _load_df():
    """Load and merge the global GEBV dataframes."""
    QCSV = os.path.join(DATA_DIR, "GEBVs_quality_23trait_n10026.csv")
    ACSV = os.path.join(DATA_DIR, "GEBVs_ag_73traitmean_n10024.csv")
    df_q = pd.read_csv(QCSV)
    df_a = pd.read_csv(ACSV)
    if "Group" in df_a.columns and "Group" in df_q.columns:
        return pd.merge(df_q, df_a, on=["Line", "Group"], how="inner")
    return pd.merge(df_q, df_a, on="Line", how="inner")


def _load_accuracy_lookup():
    """
    Load trait prediction accuracies from the PA CSV.
    Returns a dict keyed by trait name with GEBV_ prefix and _x/_y suffixes removed.
    """
    acc_df = pd.read_csv(ACCURACY_PATH)
    required_cols = {"trait", "r.mean"}
    if not required_cols.issubset(acc_df.columns):
        raise ValueError(f"Accuracy file must contain columns: {', '.join(sorted(required_cols))}")
    acc_df["trait"] = acc_df["trait"].astype(str).str.strip()
    return dict(zip(acc_df["trait"], acc_df["r.mean"].astype(float)))


def _trait_to_pa_name(trait_name):
    """
    Convert app trait name to PA table trait name.
    Strips GEBV_ prefix and _x/_y suffix (from merged CSV columns).

    Examples:
      GEBV_Brix      -> Brix
      GEBV_yield_y   -> yield
      GEBV_fruitno_x -> fruitno
    """
    t = trait_name.replace("GEBV_", "", 1)
    if t.endswith("_x") or t.endswith("_y"):
        t = t[:-2]
    return t


@app.route('/genomic_selection_index', methods=['POST'])
def compute_genomic_selection_index():
    """
    Compute an accuracy-adjusted genomic selection index.

    This is a modified genomic selection index (not classic Smith-Hazel).
    G is estimated from the sample covariance of selected GEBVs.
    R is a diagonal matrix of trait prediction accuracies from the PA table.

    Index coefficients:
        b = (R G R)^-1 (R G a)

    where a is the vector of user-supplied economic weights.
    This formulation avoids the collinearity issues that arise when using
    training GEBVs and phenotypic data together in the classic Smith-Hazel equation.

    Note: global collection traits may have _x/_y suffixes from the CSV merge.
    The PA lookup strips these suffixes automatically.
    """
    global _genomic_selection_result

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

    # Strip GEBV_ prefix and _x/_y suffix for PA lookup
    pa_trait_names = [_trait_to_pa_name(t) for t in traits]
    missing_acc = [t for t in pa_trait_names if t not in accuracy_lookup]
    if missing_acc:
        return jsonify({
            "error": (
                "Prediction accuracies not found for: " + ", ".join(missing_acc)
                + ". The PA file should contain trait names matching GEBV traits "
                  "after removing 'GEBV_' prefix and any trailing _x/_y suffix."
            )
        }), 400

    df_complete = df.dropna(subset=traits).copy()
    if len(df_complete) < 3:
        return jsonify({"error": "Too few lines with complete GEBV data for the selected traits"}), 400

    # Estimate G from selected GEBV covariance
    Xg = df_complete[traits].values
    G = np.cov(Xg, rowvar=False)

    # Build diagonal R from prediction accuracies
    acc = np.array([accuracy_lookup[t] for t in pa_trait_names], dtype=float)
    R = np.diag(acc)

    # Solve b = (RGR)^-1 (RGa)
    try:
        M = R @ G @ R
        M = M + np.eye(M.shape[0]) * 1e-8  # ridge for numerical stability
        b = np.linalg.solve(M, R @ G @ w)
    except np.linalg.LinAlgError:
        return jsonify({"error": "RGR matrix is singular — selected traits may be too highly correlated"}), 400

    scores = (df_complete[traits].values @ b).ravel()

    result_df = pd.DataFrame({"Line": df_complete["Line"].values, "Genomic_Selection_Index": scores})
    for t in traits:
        result_df[t] = df_complete[t].values
    if "Group" in df_complete.columns:
        result_df["Group"] = df_complete["Group"].values
    result_df = result_df.sort_values("Genomic_Selection_Index", ascending=False).head(top_n)

    index_coefficients = {t: float(b[i, 0]) for i, t in enumerate(traits)}
    trait_accuracies = {traits[i]: float(acc[i]) for i in range(len(traits))}

    _genomic_selection_result = {
        "ranked_lines": result_df.to_dict(orient="records"),
        "index_coefficients": index_coefficients,
        "economic_weights": trait_weights,
        "trait_accuracies": trait_accuracies,
        "n_lines_scored": int(len(df_complete)),
        "n_lines_covariance": int(len(df_complete)),
        "computed_at": datetime.now().isoformat(),
        "note": (
            "G estimated from selected GEBV covariance; R from trait prediction accuracies. "
            "Coefficients computed using b = (RGR)^-1(RGa). This avoids the collinearity "
            "issues of classic Smith-Hazel when using training GEBVs."
        )
    }

    with open(GENOMIC_SELECTION_STATE_FILE, 'w') as f:
        json.dump(_genomic_selection_result, f, indent=2)

    return jsonify(_genomic_selection_result)


@app.route('/genomic_selection_index/result', methods=['GET'])
def get_genomic_selection_result():
    if _genomic_selection_result is None:
        return jsonify({"error": "No result yet — run a computation first"}), 404
    return jsonify(_genomic_selection_result)


@app.route('/selection_index', methods=['POST'])
def compute_selection_index():
    """
    Compute a weighted linear selection index: I_i = sum(w_j * z_ij)
    where z_ij is the z-score of trait j for line i.
    Body: {"trait_weights": {"GEBV_yield_y": 0.6, "GEBV_fruitno_x": 0.4}, "top_n": 20}
    """
    global _weighted_index_result

    data = request.get_json()
    if not data or "trait_weights" not in data:
        return jsonify({"error": "Missing trait_weights in request body"}), 400

    trait_weights = data["trait_weights"]
    top_n = int(data.get("top_n", 20))

    if not trait_weights:
        return jsonify({"error": "trait_weights must be a non-empty dict"}), 400

    try:
        df = _load_df()
    except Exception as e:
        return jsonify({"error": f"Could not load data: {str(e)}"}), 500

    missing = [t for t in trait_weights if t not in df.columns]
    if missing:
        available = [c for c in df.columns if c.startswith("GEBV_")]
        return jsonify({"error": f"Traits not found: {missing}", "available_traits": available}), 400

    total_weight = sum(abs(w) for w in trait_weights.values())
    if total_weight == 0:
        return jsonify({"error": "All weights are zero"}), 400

    normalized_weights = {t: w / total_weight for t, w in trait_weights.items()}
    traits = list(normalized_weights.keys())

    id_cols = ["Line"] + (["Group"] if "Group" in df.columns else [])
    result_df = df[id_cols + traits].copy()

    for trait in traits:
        std = df[trait].std()
        result_df[f"_z_{trait}"] = 0.0 if std == 0 else (df[trait] - df[trait].mean()) / std

    result_df["index_score"] = sum(
        normalized_weights[t] * result_df[f"_z_{t}"] for t in traits
    )
    result_df = result_df.drop(columns=[f"_z_{t}" for t in traits])
    result_df = result_df.sort_values("index_score", ascending=False).head(top_n).reset_index(drop=True)
    result_df["rank"] = result_df.index + 1

    payload = {
        "trait_weights": trait_weights,
        "normalized_weights": normalized_weights,
        "top_n": top_n,
        "results": result_df.to_dict(orient="records"),
        "computed_at": datetime.now().isoformat(),
    }
    _weighted_index_result = payload

    with open(WEIGHTED_INDEX_STATE_FILE, 'w') as f:
        json.dump(payload, f, indent=2)

    return jsonify(payload)


@app.route('/selection_index/result', methods=['GET'])
def get_last_selection_index():
    if not _weighted_index_result:
        return jsonify({"message": "No index computed yet"}), 404
    return jsonify(_weighted_index_result)


if __name__ == '__main__':
    load_state()
    print("GEBV Global API Server starting on port 5002 (global collection, n~10k)...")
    print("Endpoints:")
    print("  GET  /health")
    print("  GET  /traits")
    print("  GET  /sliders")
    print("  POST /sliders/<trait>")
    print("  POST /sliders/reset")
    print("  DEL  /sliders/<trait>")
    print("  POST /genomic_selection_index - Accuracy-adjusted genomic index b=(RGR)^-1(RGa)")
    print("  GET  /genomic_selection_index/result")
    print("  POST /selection_index - Weighted linear index (z-score)")
    print("  GET  /selection_index/result")
    app.run(host='0.0.0.0', port=5002, debug=False)
