#!/usr/bin/env bash
# Rebuild every demo from the CSVs in /data, run the tests, and capture screenshots.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m demo3_invoice_reader.make_samples
python3 -m demo3_invoice_reader.run
python3 -m demo1_project_control.run
python3 -m demo2_plant_allocation.run
python3 -m pytest -q -p no:cacheprovider tests
python3 -m common.screenshots || echo "(screenshots skipped: Playwright/Chrome not installed)"
