#!/usr/bin/env bash
set -euo pipefail
SERVER="${1:?usage: ./run_camera.sh ws://GPU_HOST:8765 [mono|stereo] [cam-a] [cam-b]}"
MODE="${2:-mono}"
CAM_A="${3:-0}"
CAM_B="${4:-2}"
python -m camera_client.main --server "$SERVER" --mode "$MODE" --cam-a "$CAM_A" --cam-b "$CAM_B"
