#!/bin/bash
set -e

# Start both API servers (core on 5001, global on 5002)
python gebv_api_server.py &
python global/global_api_server.py &

exec streamlit run GEBV_app.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true
