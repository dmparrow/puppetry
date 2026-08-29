#!/usr/bin/env bash
set -euo pipefail

command -v docker >/dev/null || { echo "docker is required"; exit 1; }
docker compose version >/dev/null
command -v nvidia-smi >/dev/null || { echo "nvidia-smi is required on the GPU host"; exit 1; }

echo "Checking NVIDIA Container Toolkit..."
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/dev/null

echo "Starting Go mocap server + Python GPU worker..."
docker compose -f compose.grpc.yaml up -d --build

echo "Camera gRPC: :50051"
echo "Blender TCP:  :8766"
docker compose -f compose.grpc.yaml ps
