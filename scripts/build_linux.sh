#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION="$($PYTHON_BIN -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
ARCH="$(uname -m)"
PACKAGE_NAME="ResearchOS-linux-${ARCH}-v${VERSION}"

"$PYTHON_BIN" -m unittest discover -s tests -v
"$PYTHON_BIN" scripts/verify_demo.py

# The GUI binary is optional: the source/JSON agent package below remains
# useful on minimal Linux images where PyInstaller or Tk is unavailable.
rm -rf build dist
if "$PYTHON_BIN" -c 'import PyInstaller' >/dev/null 2>&1; then
  "$PYTHON_BIN" -m PyInstaller --noconfirm --clean --windowed --name ResearchOS --paths . run_researchos.py
else
  echo "PyInstaller is not installed; skipping the optional GUI binary" >&2
  mkdir -p dist
fi

PACKAGE_DIR="dist/${PACKAGE_NAME}"
mkdir -p "$PACKAGE_DIR/researchos" "$PACKAGE_DIR/scripts" "$PACKAGE_DIR/demo_workspace"
cp README.md LICENSE pyproject.toml run_researchos_cli.py "$PACKAGE_DIR/"
cp -R researchos/. "$PACKAGE_DIR/researchos/"
cp scripts/verify_demo.py scripts/researchos-agent "$PACKAGE_DIR/scripts/"
cp -R demo_workspace/. "$PACKAGE_DIR/demo_workspace/"
chmod +x "$PACKAGE_DIR/scripts/researchos-agent"
if [[ -x dist/ResearchOS/ResearchOS ]]; then
  mkdir -p "$PACKAGE_DIR/bin"
  cp dist/ResearchOS/ResearchOS "$PACKAGE_DIR/bin/ResearchOS"
fi

tar -C dist -czf "dist/${PACKAGE_NAME}.tar.gz" "$PACKAGE_NAME"
sha256sum "dist/${PACKAGE_NAME}.tar.gz" > "dist/${PACKAGE_NAME}.tar.gz.sha256"
echo "Build complete: dist/${PACKAGE_NAME}.tar.gz"
if [[ -x "$PACKAGE_DIR/bin/ResearchOS" ]]; then
  echo "GUI binary: dist/${PACKAGE_NAME}/bin/ResearchOS"
fi
echo "Agent CLI: dist/${PACKAGE_NAME}/scripts/researchos-agent"
