#!/bin/bash
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    python3 start.py
elif command -v python >/dev/null 2>&1; then
    python start.py
else
    echo "❌ Error: Python is not installed."
    exit 1
fi
