#!/bin/bash
set -euo pipefail

exec 2>&1

mkdir -p /app
python3 /solution/solve.py
