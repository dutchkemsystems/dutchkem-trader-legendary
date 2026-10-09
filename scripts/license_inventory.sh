#!/usr/bin/env bash
# Produce a CSV of dependencies and their licenses.
set -u
if [ -f requirements.txt ]; then
  python -m pip install pip-licenses --quiet 2>/dev/null || true
  pip-licenses --format=csv --with-urls > LICENSES.csv 2>/dev/null || echo "name,license" > LICENSES.csv
elif [ -f package.json ]; then
  npx license-checker --csv > LICENSES.csv 2>/dev/null || echo "name,license" > LICENSES.csv
else
  echo "name,license" > LICENSES.csv
fi
echo "Wrote LICENSES.csv"
