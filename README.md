# GEBV Explorer (v2)

Interactive visualization of genomic estimated breeding values (GEBVs) for Capsicum (pepper) crops. A single unified app covering both the core and global collections, with AI-assisted filtering and multi-trait selection indices.

![App screenshot](images/screenshot.png)

## Features

- **Collection Toggle**: Switch between the Core Collection (n=423) and Global Collection (n~10k) from the sidebar
- **Interactive Sliders**: Filter lines by any GEBV trait using sidebar threshold sliders
- **Chat with Data Filtering**: Use natural language to adjust filters or rank lines (e.g., "Show me the top 10% for yield", "Rank lines prioritising yield and Brix")
- **Genomic Selection Index**: Accuracy-adjusted ranking using `b = (RGR)⁻¹RGa` — accounts for genetic covariance between traits and unequal prediction accuracies
- **Weighted Selection Index**: Simple z-score weighted ranking `I = Σ(wⱼ × zᵢⱼ)` — straightforward weighted composite score
- **Scatter Plot**: Explore any two-trait scatterplot with filtered points highlighted
- **CSV Export**: Download filtered lines or index results as CSV

---

## Running with Docker (Recommended)

Docker bundles everything — no Python setup, no virtual environments, no dependency conflicts.

### Requirements
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Windows) or Docker Engine (Linux)
- An Anthropic API key from https://console.anthropic.com/

### Setup

**1. Clone the repository**
```bash
git clone https://github.com/GEBV-collab/GEBV_Explorer_V2.git
cd GEBV_Explorer_V2
```

**2. Start the app**
```bash
docker compose up
```

The app will be available at **http://localhost:8501**

To stop: press `Ctrl+C`, then `docker compose down`.

**Providing your API key:**

Enter your Anthropic API key directly in the app sidebar — no `.env` file needed. Alternatively, create a `.env` file to pre-fill it automatically:
```bash
echo "ANTHROPIC_API_KEY=your-api-key-here" > .env
```

> **Note:** The first `docker compose up` will take a few minutes to build the image and download dependencies. Subsequent starts are fast.

---

## Running Manually (Without Docker)

### 1. Clone the repository
```bash
git clone https://github.com/GEBV-collab/GEBV_Explorer_V2.git
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

### 4. Set up API key (required for Chat)
```bash
echo "ANTHROPIC_API_KEY=your-api-key-here" > .env
```

### 5. Start both API servers and the app

```bash
# Terminal 1: Core API server (port 5001)
python gebv_api_server.py

# Terminal 2: Global API server (port 5002)
python global/global_api_server.py

# Terminal 3: Streamlit app
streamlit run GEBV_app.py
```

Opens at **http://localhost:8501**

---

## Usage

### Switching Collections
Use the **Collection** radio button in the sidebar to toggle between:
- **Core Collection (n=423)** — Capsicum core collection, 96 GEBV traits
- **Global Collection (n~10k)** — Global Capsicum collection, 96 GEBV traits

### Manual Filtering
- Adjust sliders on the left sidebar to filter lines by any GEBV trait
- The scatter plot and filtered table update in real time
- Red points in the scatter plot highlight lines meeting all threshold criteria

### Chat with Data Filtering
Use natural language commands to adjust filters or rank lines:
- *"Show me the top 10% for yield"*
- *"Filter for high Brix and low pungency"*
- *"Rank lines prioritising yield twice as much as Brix"*
- *"Reset all filters"*

### Genomic Selection Index
Ranks all lines using an accuracy-adjusted genomic index `b = (RGR)⁻¹RGa`:
- Select traits and assign economic weights
- The index accounts for genetic covariance between traits and prediction accuracies
- Results show derived coefficients alongside your input weights so you can see how the adjustment affected the ranking

### Weighted Selection Index
Ranks all lines using a simple z-score weighted composite score `I = Σ(wⱼ × zᵢⱼ)`:
- Select traits and assign weights
- Traits are standardised before combining so they are on the same scale
- A straightforward approach when you want a transparent, assumption-free ranking

---

## Data

All data files are in the `data/` directory.

| File | Description |
|---|---|
| `GEBVs_quality_23trait_n423.csv` | Core collection quality traits (23 traits, n=423) |
| `GEBVs_STI_73traits_BLUEadjusted_ALL_n423.csv` | Core collection agronomic traits (73 traits, n=423) |
| `n423_PAs_96traits.csv` | Trait prediction accuracies for core collection |
| `GEBVs_quality_23trait_n10026.csv` | Global collection quality traits (23 traits, n=10,026) |
| `GEBVs_STI_73traits_BLUEadjusted_ALL_10k.csv` | Global collection agronomic traits (73 traits, n=10,026) |
| `n10k_PAs_96traits.csv` | Trait prediction accuracies for global collection |
| `Trait_Metadata_with_Synonyms.xlsx` | Trait descriptions, units, and synonyms used by the chat assistant |

**Note on global collection trait naming:** The global CSVs share 13 overlapping trait columns. After merging, these appear with suffixes:
- `_x` — value from the quality/phenotyping CSV
- `_y` — value from the agronomic averages CSV (averaged across 3 timepoints)

The chat assistant defaults to the `_y` variant when a trait is requested without a suffix.

---

## Architecture

```
GEBV_app.py              # Unified Streamlit app (Core + Global, both indices)
gebv_api_server.py       # Flask API — core collection (port 5001)
gebv_mcp_server.py       # MCP server — core collection tools
mcp_chat.py              # Chat integration — core collection

global/
├── global_api_server.py     # Flask API — global collection (port 5002)
├── global_mcp_server.py     # MCP server — global collection tools
└── global_mcp_chat.py       # Chat integration — global collection

data/                        # All data files (core + global)

Dockerfile                   # Single image
docker-compose.yml           # Single service, starts both API servers + app
start_core.sh                # Startup script (used by Docker)
```

Both API servers must be running for the collection toggle to work. The Docker setup starts them both automatically via `start_core.sh`.
