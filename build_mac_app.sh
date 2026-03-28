#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt pyinstaller

pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --argv-emulation \
  --osx-bundle-identifier com.furkanakman.tomoflow \
  --icon assets/TomoFlowLogo.png \
  --add-data "assets/TomoFlowLogo.png:." \
  --name TomoFlow \
  src/manga_translator_app.py

echo "Build complete: dist/TomoFlow.app"
