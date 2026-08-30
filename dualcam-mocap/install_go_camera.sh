#!/usr/bin/env bash
set -euo pipefail

command -v go >/dev/null || { echo "Go 1.23+ is required"; exit 1; }
mkdir -p bin

echo "Building Linux V4L2 camera client..."
go build -trimpath -o bin/mocap-camera ./cmd/camera

echo
echo "Built: $(pwd)/bin/mocap-camera"
echo "Mono:   ./bin/mocap-camera --server GPU_IP:50051 --cam-a /dev/video0"
echo "Stereo: ./bin/mocap-camera --server GPU_IP:50051 --mode stereo --cam-a /dev/video0 --cam-b /dev/video2"
