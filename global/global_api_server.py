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
        import pandas as pd

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


@app.route('/smith_hazel_index', methods=['POST'])
def compute_smith_hazel_index():
    """Compute the Smith-Hazel selection index."""
    global smith_hazel_result

    data = request.get_json()
    if not data or "trait_weights" not in data:
        return jsonify({"error": "Missing trait_weights"}), 400

    trait_weights = data["trait_weights"]
    top_n = int(data.get("top_n", 20))

    if len(trait_weights) < 2:
        return jsonify({"error": "Smith-Hazel index requires at least 2 traits"}), 400

    try:
        df = _load_df()
    except Exception as e:
        return jsonify({"error": f"Could not load data: {str(e)}"}), 500

    missing = [t for t in trait_weights if t not in df.columns]
    if missing:
        return jsonify({"error": f"Traits not found: {', '.join(missing)}"}), 400

    traits = list(trait_weights.keys())
    w = np.array([trait_weights[t] for t in traits], dtype=float)

    X = df[traits].dropna().values
    line_ids = df.loc[df[traits].dropna().index, "Line"].values
    group_col = df.loc[df[traits].dropna().index, "Group"].values if "Group" in df.columns else None

    G = np.cov(X, rowvar=False)
    E = np.diag(np.diag(G) * 0.5)
    P = G + E

    try:
        b = np.linalg.solve(P, G @ w)
    except np.linalg.LinAlgError:
        return jsonify({"error": "P matrix is singular"}), 400

    scores = X @ b

    result_df = pd.DataFrame({"Line": line_ids, "SmithHazel_Index": scores})
    for t in traits:
        result_df[t] = df.loc[df[traits].dropna().index, t].values
    if group_col is not None:
        result_df["Group"] = group_col

    result_df = result_df.sort_values("SmithHazel_Index", ascending=False).head(top_n)

    index_coefficients = {t: float(b[i]) for i, t in enumerate(traits)}

    smith_hazel_result = {
        "ranked_lines": result_df.to_dict(orient="records"),
        "index_coefficients": index_coefficients,
        "economic_weights": trait_weights,
        "n_lines_total": len(X),
        "computed_at": datetime.now().isoformat(),
        "note": "G estimated from GEBV sample covariance. P = G + E where E = 0.5*diag(G), assuming mean h2~0.5."
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
    print("  POST /smith_hazel_index - Compute Smith-Hazel selection index")
    print("  GET  /smith_hazel_index/result - Get last Smith-Hazel result")

    app.run(host='0.0.0.0', port=5002, debug=False)
