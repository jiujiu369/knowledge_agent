#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_EXE="./.venv/Scripts/python.exe"
if [ ! -x "$PYTHON_EXE" ]; then
  echo "missing .venv/Scripts/python.exe"
  exit 1
fi

"$PYTHON_EXE" --version
"$PYTHON_EXE" scripts/verify_readme.py

echo "Start backend:"
echo "$PYTHON_EXE -m uvicorn agent_server.main:app --host 127.0.0.1 --port 8000"

echo "Start frontend:"
echo "$PYTHON_EXE -m streamlit run web/app.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false"
