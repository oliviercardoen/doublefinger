#!/bin/bash
set -e
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
echo "doublefinger is ready. Activate with: source .venv/bin/activate"
