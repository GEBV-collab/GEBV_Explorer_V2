# GEBV Explorer (v2)

Interactive visualization of genomic estimated breeding values (GEBVs) for Capsicum (pepper) crops.

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

## Running the App

The app requires two services to run:

### Terminal 1: Start the API server
```bash
source venv/bin/activate
python gebv_api_server.py
```
This starts the Flask API server on port 5001 that manages slider state.

### Terminal 2: Start the Streamlit app
```bash
source venv/bin/activate
streamlit run GEBV_app.py
```
This starts the web interface on http://localhost:8501

### Quick Start (both services)
```bash
# Start API server in background, then Streamlit
source venv/bin/activate
python gebv_api_server.py &
streamlit run GEBV_app.py
```

## Usage

### Manual Filtering
- Adjust sliders on the left sidebar to filter lines by any GEBV trait
- The filtered table updates in real time
- Red points in the scatter plot highlight lines meeting all threshold criteria

### Chat with Data Filtering
Use natural language commands to adjust filters:
- "Show me the top 10% for yield"
- "Filter for high Brix and low pungency"
- "Show plants with the highest fruit weight"
- "Reset all filters"

The chat understands trait synonyms (e.g., "spicy" = pungency, "sugar" = Brix).

### Scatter Plot
- Select any two traits for X and Y axes
- Gray points show all lines; red points show filtered lines
- Interactive zoom and pan

### Export
- Click "Download filtered CSV" to export the current filtered dataset

## Data

The app contains GEBV data for the Capsicum core collection (n=423):
- **Quality traits** (16): `data/GEBV_quality_core_16traits_n423.csv`
- **Agronomic traits** (13): `data/GEBVs_core_13_agronomic_traits_avg.csv` (averaged over three experimental timepoints)
- **Trait metadata**: `data/Trait_Metadata_with_Synonyms.xlsx`

## Architecture

```
GEBV_app.py          # Streamlit web interface
gebv_api_server.py   # Flask API for slider state management
gebv_mcp_server.py   # MCP server for tool-based interactions
mcp_chat.py          # Chat integration module
llm_utils.py         # LLM utilities (legacy OpenAI integration)
slider_state.json    # Persisted slider state
```

## Deactivating the Environment

When done, deactivate the virtual environment:
```bash
deactivate
```
