# 🧬 GEBV Explorer (v2)
## Interactive visualization of genomic estimated breeding values (GEBVs)

![App screenshot](images/screenshot.png)


## Steps to download and run GEBV Explorer
1) Clone the repo with the below command in terminal and change into the directory
```bash
git clone https://github.com/ahmccormick/GEBV_Explorer_V2.git
cd GEBV_Explorer_V2
```
2) Create a new environment (Environment_1) and activate (made using python 3.12.10)
```bash
python3 -m venv Environment_1
source Environment_1/bin/activate 
```
3) Install dependencies with the below 
```bash
pip install -r requirements.txt
```
4) Launch the app
```bash
streamlit run GEBV_app.py
```
5) Exit from the environment by typing 
```bash
deactivate
```

## Data

- App contains the GEBV data for 13 agronomic traits and 16 quality traits for the Capsicum core collection (n=423).  
- Quality traits: `data/GEBV_quality_core_16traits_n423.csv`  
- Agronomic traits: `data/GEBVs_core_13_agronomic_traits_avg.csv` (averaged over three experimental timepoints). 

## Usage

- Adjust sliders on the left to filter lines by any GEBV trait or combination.  
- The filtered table updates in real time.  
- Explore any two-trait scatterplot (default: Yield vs. Brix).  
- **Red points** highlight the lines that meet all of your threshold criteria.  
- Download filtered lines as a CSV.

