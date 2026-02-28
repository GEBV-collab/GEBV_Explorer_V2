#!/bin/bash
set -e

python gebv_api_server.py &

exec streamlit run GEBV_app.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true
