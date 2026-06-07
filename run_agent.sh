#!/bin/bash

# Change directory to script folder
cd "$(dirname "$0")"

# Activate environment and run local agent in the background
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    # Run python in background
    python3 local_agent.py &
    echo "[✓] Smart Video Agent started in the background."
    exit 0
else
    echo "[ERROR] Virtual environment not found. Please run setup_unix.sh first."
    exit 1
fi
