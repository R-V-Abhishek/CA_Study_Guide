#!/bin/bash
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    python3 setup.py
elif command -v python >/dev/null 2>&1; then
    python setup.py
else
    echo "❌ Error: Python 3.12+ is not installed."
    echo "Please download and install Python from https://www.python.org/downloads/"
    exit 1
fi
