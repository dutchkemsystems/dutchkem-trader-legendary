#!/usr/bin/env bash
# Generate a Software Bill of Materials for this repository.
# Requires: syft (https://github.com/anchore/syft) OR pip-licenses for Python.
set -u
OUT="sbom.json"
if command -v syft >/dev/null 2>&1; then
  syft . -o spdx-json > "$OUT"
  echo "Wrote $OUT via syft"
elif [ -f requirements.txt ]; then
  python -m pip install pip-licenses --quiet 2>/dev/null || true
  pip-licenses --format=json > "$OUT" 2>/dev/null || echo "{}" > "$OUT"
  echo "Wrote $OUT via pip-licenses"
else
  echo "{}" > "$OUT"
  echo "Wrote empty $OUT (no supported tooling found)"
fi
