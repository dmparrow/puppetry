#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required."
  exit 1
fi

if ! nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi failed on the host. Install/repair the NVIDIA driver first."
  exit 1
fi

if ! docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
  echo "Docker cannot access the GPU. Install/configure NVIDIA Container Toolkit."
  echo "See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
  exit 1
fi

if [ ! -f config.yaml ]; then
  cp config.example.yaml config.yaml
  echo "Created config.yaml from config.example.yaml"
fi

mkdir -p calibration

docker compose up -d --build

echo ""
echo "Mocap GPU server started."
echo "Camera input: ws://$(hostname -I | awk '{print $1}'):8765"
echo "Blender TCP: $(hostname -I | awk '{print $1}'):8766"
echo "Logs: docker compose logs -f mocap-gpu"
