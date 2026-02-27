#!/usr/bin/env python3
"""
GEBV Explorer API Server
Simple Flask API to manage slider state between MCP server and Streamlit app.
"""

from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)

# Simple in-memory storage (in production, use Redis/database)
slider_state = {}
state_file = "slider_state.json"

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
        QCSV = os.path.join(BASE, "data", "GEBV_quality_core_16traits_n423.csv")
        ACSV = os.path.join(BASE, "data", "GEBVs_core_13_agronomic_traits_avg.csv")
        
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

    app.run(host='0.0.0.0', port=5001, debug=False)