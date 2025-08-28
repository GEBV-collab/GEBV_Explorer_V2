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

if __name__ == '__main__':
    load_state()
    print("🌶️  GEBV API Server starting...")
    print("Endpoints:")
    print("  GET  /health - Health check") 
    print("  GET  /traits - Get available GEBV trait names")
    print("  GET  /sliders - Get all slider states")
    print("  POST /sliders/<trait> - Set slider (JSON: {start_percent, end_percent})")
    print("  POST /sliders/reset - Reset all sliders")
    print("  DEL  /sliders/<trait> - Reset specific slider")
    
    app.run(host='127.0.0.1', port=5001, debug=True)