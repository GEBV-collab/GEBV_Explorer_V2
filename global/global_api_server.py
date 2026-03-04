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
import pandas as pd
import numpy as np

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Simple in-memory storage
slider_state = {}
_last_index_result = {}
state_file = os.path.join(BASE_DIR, "global_slider_state.json")
WEIGHTED_INDEX_STATE_FILE = os.path.join(BASE_DIR, "global_weighted_index_result.json")


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


@app.route('/selection_index', methods=['POST'])
def compute_selection_index():
    """Compute a weighted linear selection index: I_i = sum(w_j * z_ij)"""
    global _last_index_result

    data = request.get_json()
    if not data or "trait_weights" not in data:
        return jsonify({"error": "Missing trait_weights in request body"}), 400

    trait_weights = data["trait_weights"]
    top_n = int(data.get("top_n", 20))

    if not trait_weights:
        return jsonify({"error": "trait_weights must be a non-empty dict"}), 400

    try:
        QCSV = os.path.join(BASE_DIR, "data", "GEBVs_quality_23trait_n10026.csv")
        ACSV = os.path.join(BASE_DIR, "data", "GEBVs_ag_73traitmean_n10024.csv")
        df_q = pd.read_csv(QCSV)
        df_a = pd.read_csv(ACSV)
        if "Group" in df_a.columns and "Group" in df_q.columns:
            df = pd.merge(df_q, df_a, on=["Line", "Group"], how="inner")
        else:
            df = pd.merge(df_q, df_a, on="Line", how="inner")
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
    _last_index_result = payload

    with open(WEIGHTED_INDEX_STATE_FILE, 'w') as f:
        json.dump(payload, f, indent=2)

    return jsonify(payload)


@app.route('/selection_index/result', methods=['GET'])
def get_last_selection_index():
    if not _last_index_result:
        return jsonify({"message": "No index computed yet"}), 404
    return jsonify(_last_index_result)


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
    print("  POST /selection_index - Compute weighted linear selection index")
    print("  GET  /selection_index/result - Get last weighted index result")

    app.run(host='0.0.0.0', port=5002, debug=False)
