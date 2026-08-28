#!/usr/bin/env bash
set -euo pipefail
SERVER="${1:?usage: ./run_camera.sh ws://GPU_HOST:8765 [cam-a] [cam-b]}"
CAM_A="${2:-0}"
CAM_B="${3:-2}"
python -m camera_client.main --server "$SERVER" --cam-a "$CAM_A" --cam-b "$CAM_B"
