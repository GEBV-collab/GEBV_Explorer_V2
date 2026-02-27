#!/bin/bash
set -e

python global/global_api_server.py &

exec streamlit run global/global_app.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true
