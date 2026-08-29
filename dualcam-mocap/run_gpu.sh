#!/usr/bin/env bash
set -euo pipefail
python -m gpu_server.main --config "${1:-config.yaml}"
