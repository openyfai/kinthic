#!/usr/bin/env bash
# Memory recall demo — record with: asciinema rec demos/memory_recall_demo.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
python benchmarks/memory_recall/demo.py "$@"
