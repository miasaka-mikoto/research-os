#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -v
python3 scripts/verify_demo.py
rm -rf build dist
pyinstaller --noconfirm --clean --windowed --name ResearchOS --paths . run_researchos.py
echo "Build complete: dist/ResearchOS/ResearchOS"
