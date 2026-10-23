#!/bin/zsh
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run: installing (takes a minute)..."
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
( sleep 3; open "http://localhost:8501" ) &
.venv/bin/streamlit run app.py
