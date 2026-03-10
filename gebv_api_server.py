#!/usr/bin/env python3
"""
GEBV Explorer API Server
Simple Flask API to manage slider state between MCP server and Streamlit app.
"""

from flask import Flask, request, jsonify
import json
import os
from datetime import datetime
import numpy as np
import pandas as pd

app = Flask(__name__)

# Simple in-memory storage (in production, use Redis/database)
slider_state = {}

# In-memory store for last Smith-Hazel result
smith_hazel_result = None
state_file = "slider_state.json"
SMITH_HAZEL_STATE_FILE = "smith_hazel_result.json"
ACCURACY_PATH = os.path.join(os.path.dirname(__file__), "data", "n423_PAs_96traits.csv")

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
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/sliders', methods=['GET'])
def get_sliders():
    """Get current slider state"""
    return jsonify(slider_state)

@app.route('/sliders/<trait>', methods=['POST'])
def set_slider(trait):
    """Set a specific slider value"""
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
    """Reset all sliders"""
    global slider_state
    slider_state = {}
    save_state()
    return jsonify({"message": "All sliders reset"})

@app.route('/sliders/<trait>', methods=['DELETE'])
def reset_slider(trait):
    """Reset a specific slider"""
    if trait in slider_state:
        del slider_state[trait]
        save_state()
        return jsonify({"message": f"Reset {trait} slider"})
    else:
        return jsonify({"message": f"Slider {trait} not found"}), 404

@app.route('/traits', methods=['GET'])
def get_traits():
    """Get list of available GEBV traits from the data"""
    try:
        import pandas as pd
        import os

        # Load the data to get actual trait columns
        BASE = os.path.dirname(__file__)
        QCSV = os.path.join(BASE, "data", "GEBVs_quality_23trait_n423.csv")
        ACSV = os.path.join(BASE, "data", "GEBVs_ag_73traitmean_n423.csv")

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

@app.route('/traitinfo', methods=['POST'])
def trait_info():
    """
    Query trait metadata using a natural language question.
    Uses the metadata table (Trait, Full label, Unit, Description, Synonyms)
    and returns relevant traits and explanations via LLM or local match.
    """
    import pandas as pd
    import openai
    import json
    import os

    META_PATH = os.path.join(os.path.dirname(__file__), "data", "Trait_Metadata_with_Synonyms.xlsx")
    df = pd.read_excel(META_PATH)

    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Missing query"}), 400

    # ---- 1. Build rich metadata context including synonyms ----
    meta_text = "\n".join(
        f"{r.Trait}: {r.Full_label} ({r.Unit}) — {r.Description}. Synonyms: {r.get('Synonyms','')}"
        for _, r in df.iterrows()
    )

    prompt = f"""
    You are a crop trait expert. The following table lists traits, their full names, units, descriptions, and synonyms.

    {meta_text}

    A user asked: "{query}"

    Identify the 3–5 most relevant traits that match this query.
    Use the Synonyms column to help match related wording.
    Return the response strictly as JSON:
    [
      {{
        "trait": "<Trait>",
        "full_label": "<Full label>",
        "reason": "<Why relevant>"
      }}
    ]
    """

    # ---- 2. Call LLM if possible ----
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3
        )
        text = completion.choices[0].message.content

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = {"raw": text}

        return jsonify(result)

    # ---- 3. Fallback: local keyword matching ----
    except Exception as e:
        q = query.lower()
        mask = (
            df["Trait"].str.lower().str.contains(q, na=False)
            | df["Description"].str.lower().str.contains(q, na=False)
            | df["Synonyms"].str.lower().str.contains(q, na=False)
        )
        matches = df[mask][["Trait", "Full label", "Description", "Synonyms"]].head(5)
        results = [
            {
                "trait": r.Trait,
                "full_label": r["Full label"],
                "reason": f"Matched keywords in description or synonyms: {r['Synonyms']}"
            }
            for _, r in matches.iterrows()
        ]
        return jsonify({"fallback": True, "matches": results, "error": str(e)})


def _load_df():
    """Load and merge the GEBV dataframes."""
    BASE = os.path.dirname(__file__)
    df_q = pd.read_csv(os.path.join(BASE, "data", "GEBVs_quality_23trait_n423.csv"))
    df_a = pd.read_csv(os.path.join(BASE, "data", "GEBVs_ag_73traitmean_n423.csv"))
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
    return dict(zip(acc_df["trait"], acc_df["r.mean"]))


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

    # Validate GEBV traits
    missing = [t for t in trait_weights if t not in df.columns]
    if missing:
        return jsonify({"error": f"Traits not found: {', '.join(missing)}"}), 400

    traits = list(trait_weights.keys())
    w = np.array([trait_weights[t] for t in traits], dtype=float).reshape(-1, 1)

    # Validate accuracy lookup using trait names without GEBV_ prefix
    pa_traits = [t.replace("GEBV_", "", 1) for t in traits]
    missing_acc = [t for t in pa_traits if t not in accuracy_lookup]
    if missing_acc:
        return jsonify({
            "error": (
                "Prediction accuracies not found for: "
                + ", ".join(missing_acc)
                + ". Check that the PA file uses trait names matching the GEBV traits "
                  "without the 'GEBV_' prefix."
            )
        }), 400

    # ---- Estimate G from selected GEBVs ----
    df_complete = df.dropna(subset=traits).copy()

    if len(df_complete) < 3:
        return jsonify({
            "error": "Too few lines with complete GEBV data for the selected traits"
        }), 400

    Xg = df_complete[traits].values
    G = np.cov(Xg, rowvar=False)

    # ---- Build diagonal R from prediction accuracies ----
    acc = np.array([accuracy_lookup[t] for t in pa_traits], dtype=float)
    R = np.diag(acc)

    # ---- Compute genomic selection index coefficients: b = (RGR)^-1 (RGa) ----
    try:
        M = R @ G @ R
        M = M + np.eye(M.shape[0]) * 1e-8  # ridge for numerical stability
        b = np.linalg.solve(M, R @ G @ w)
    except np.linalg.LinAlgError:
        return jsonify({
            "error": "RGR matrix is singular — selected traits may be too highly correlated"
        }), 400

    # ---- Score all lines with complete selected GEBVs ----
    X_score = df_complete[traits].values
    scores = (X_score @ b).ravel()

    # Build result dataframe
    result_df = pd.DataFrame({
        "Line": df_complete["Line"].values,
        "SmithHazel_Index": scores
    })

    for t in traits:
        result_df[t] = df_complete[t].values

    if "Group" in df_complete.columns:
        result_df["Group"] = df_complete["Group"].values

    result_df = result_df.sort_values("SmithHazel_Index", ascending=False).head(top_n)

    # Index coefficients with trait names
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

    # Persist to file so Streamlit can pick it up on rerun
    with open(SMITH_HAZEL_STATE_FILE, 'w') as f:
        json.dump(smith_hazel_result, f, indent=2)

    return jsonify(smith_hazel_result)


@app.route('/smith_hazel_index/result', methods=['GET'])
def get_smith_hazel_result():
    """Return the last computed Smith-Hazel index result."""
    if smith_hazel_result is None:
        return jsonify({"error": "No result yet — run a computation first"}), 404
    return jsonify(smith_hazel_result)


if __name__ == '__main__':
    load_state()
    print("GEBV API Server starting...")
    print("Endpoints:")
    print("  GET  /health - Health check")
    print("  GET  /traits - Get available GEBV trait names")
    print("  POST /traitinfo - Query trait metadata with natural language")
    print("  GET  /sliders - Get all slider states")
    print("  POST /sliders/<trait> - Set slider (JSON: {start_percent, end_percent})")
    print("  POST /sliders/reset - Reset all sliders")
    print("  DEL  /sliders/<trait> - Reset specific slider")
    print("  POST /smith_hazel_index - Compute accuracy-adjusted genomic selection index")
    print("  GET  /smith_hazel_index/result - Get last computed index result")

    app.run(host='0.0.0.0', port=5001, debug=False)
