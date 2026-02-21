# GEBV Explorer (v2)

Interactive visualization of genomic estimated breeding values (GEBVs) for Capsicum (pepper) crops. This repository contains two apps:

- **Core Collection App** — 423 accessions (Capsicum core collection)
- **Global Collection App** — 10,026 accessions (global Capsicum collection)

Both apps share the same feature set and are powered by the same virtual environment.

![App screenshot](images/screenshot.png)

## Features

- **Interactive Sliders**: Filter lines by any GEBV trait or combination using sidebar sliders
- **Chat with Data Filtering**: Use natural language to adjust filters (e.g., "Show me the top 10% for yield")
- **Scatter Plot Visualization**: Explore any two-trait scatterplot with filtered points highlighted in red
- **Trait Correlation Heatmap**: View correlations between all GEBV traits
- **CSV Export**: Download filtered lines as a CSV file

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/ahmccormick/GEBV_Explorer_V2.git
cd GEBV_Explorer_V2
```

### 2. Create and activate a virtual environment (Python 3.12)
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up API key (required for Chat with Data Filtering)
Create a `.env` file in the project root:
```bash
echo "ANTHROPIC_API_KEY=your-api-key-here" > .env
```
Replace `your-api-key-here` with your Anthropic API key from https://console.anthropic.com/

---

## Core Collection App (n=423)

### Running

The app requires two services:

```bash
# Terminal 1: API server (port 5001)
source venv/bin/activate
python gebv_api_server.py

# Terminal 2: Streamlit app
source venv/bin/activate
streamlit run GEBV_app.py
```

The web interface opens at http://localhost:8501

### Data
- **Quality traits** (16): `data/GEBV_quality_core_16traits_n423.csv`
- **Agronomic traits** (13): `data/GEBVs_core_13_agronomic_traits_avg.csv` (averaged over three experimental timepoints)
- **Trait metadata**: `data/Trait_Metadata_with_Synonyms.xlsx`

---

## Global Collection App (n=10,026)

### Running

The global app uses its own API server on a separate port to avoid conflicts with the core app:

```bash
# Terminal 1: API server (port 5002)
source venv/bin/activate
python global/global_api_server.py

# Terminal 2: Streamlit app
source venv/bin/activate
streamlit run global/global_app.py
```

The web interface opens at http://localhost:8501 (or 8502 if the core app is already running)

### Data
Both CSVs in `global/data/` contain the same 13 GEBV traits measured under different conditions. After merging, each trait appears with a suffix indicating its source:
- `_x` suffix: value from the phenotyping/quality CSV
- `_y` suffix: value from the agronomic averages CSV (averaged over three experimental timepoints)

This results in 26 total trait columns (13 × 2).

- `global/data/GEBV_quality_global_16traits_10k_FIN.csv`
- `global/data/GEBVs_global_13_agronomic_traits_avg.csv`

### Chat with Data Filtering
The global app's chat understands the `_x`/`_y` trait naming convention. When asking about a trait, specify which variant you want or the assistant will choose the most appropriate one (defaulting to `_y` for yield and agronomic averages).

---

## Running Both Apps Simultaneously

Both apps can run at the same time since they use different API server ports:

```bash
source venv/bin/activate

# Core app services
python gebv_api_server.py &        # port 5001
streamlit run GEBV_app.py &        # port 8501

# Global app services
python global/global_api_server.py &   # port 5002
streamlit run global/global_app.py     # port 8502
```

---

## Usage

### Manual Filtering
- Adjust sliders on the left sidebar to filter lines by any GEBV trait
- The filtered table updates in real time
- Red points in the scatter plot highlight lines meeting all threshold criteria

### Chat with Data Filtering
Use natural language commands to adjust filters:
- "Show me the top 10% for yield"
- "Filter for high Brix and low pungency" *(core app)*
- "Show plants with the highest fruit number" *(global app)*
- "Reset all filters"

### Scatter Plot
- Select any two traits for X and Y axes
- Gray points show all lines; red points show filtered lines
- Interactive zoom and pan

### Export
- Click "Download filtered CSV" to export the current filtered dataset

---

## Architecture

```
# Core collection
GEBV_app.py              # Streamlit web interface
gebv_api_server.py       # Flask API for slider state (port 5001)
gebv_mcp_server.py       # MCP server for tool-based interactions
mcp_chat.py              # Chat integration module
llm_utils.py             # LLM utilities (legacy OpenAI integration)
data/                    # Core collection data files

# Global collection
global/
├── global_app.py            # Streamlit web interface
├── global_api_server.py     # Flask API for slider state (port 5002)
├── global_mcp_server.py     # MCP server for tool-based interactions
├── global_mcp_chat.py       # Chat integration module
└── data/                    # Global collection data files
```

Both apps share the single `venv/` at the repo root and the `.env` file for the Anthropic API key.

## Deactivating the Environment

```bash
deactivate
```
