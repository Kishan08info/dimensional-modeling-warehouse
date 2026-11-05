#!/bin/bash
# End-to-end demo: generate synthetic source data -> build the star schema
# (SCD Type 2 dimensions + fact) -> run analysis queries -> run data tests.
# Not a production DAG — just a shell sequence for the demo.
set -e
cd "$(dirname "$0")"
python3 src/generate.py
python3 src/build.py
echo "Demo complete. Summary in results/summary.json"
