#!/bin/bash
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    python3 stop.py
elif command -v python >/dev/null 2>&1; then
    python stop.py
else
    echo "❌ Error: Python is not installed."
    exit 1
fi
