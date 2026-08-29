# Install / first run — Go + gRPC branch

## GPU machine

Prerequisites:

- NVIDIA driver working (`nvidia-smi`)
- Docker Engine + Docker Compose v2
- NVIDIA Container Toolkit

Start the stack:

```bash
cd dualcam-mocap
chmod +x run_go_stack.sh
./run_go_stack.sh
```

This starts two containers:

- `mocap-server`: Go gRPC broker/orchestrator, no GPU access
- `inference`: temporary Python CUDA worker on the private Compose network

LAN ports:

- `50051/tcp`: bidirectional camera gRPC
- `8766/tcp`: newline-delimited skeleton JSON for Blender

The Python worker listens on `50052` only inside Compose. Model cache is persisted in the `mocap-models` volume.

Useful commands:

```bash
docker compose -f compose.grpc.yaml logs -f
docker compose -f compose.grpc.yaml restart
docker compose -f compose.grpc.yaml down
```

## Camera machine — Go V4L2 client

The first Go capture backend is Linux/V4L2 and requests MJPEG directly from the camera, so there is no Python or OpenCV runtime on the camera machine.

Prerequisite: Go 1.23+.

```bash
cd dualcam-mocap
chmod +x install_go_camera.sh
./install_go_camera.sh
```

Single camera, default:

```bash
./bin/mocap-camera --server GPU_IP:50051 --cam-a /dev/video0
```

Mono capture needs no camera calibration and produces a root-locked relative 3D skeleton.

Stereo:

```bash
./bin/mocap-camera \
  --server GPU_IP:50051 \
  --mode stereo \
  --cam-a /dev/video0 \
  --cam-b /dev/video2
```

## Stereo calibration

The existing ChArUco calibration utility is still Python for this branch because it is an offline setup tool, not part of the live capture runtime.

```bash
python3 -m venv .venv-tools
source .venv-tools/bin/activate
pip install -r requirements-camera.txt
python tools/generate_charuco.py
python tools/calibrate_stereo.py --cam-a 0 --cam-b 2 --out calibration/stereo.npz
```

Place `calibration/stereo.npz` on the GPU host in the same repository directory. Compose mounts it read-only into the inference container.

## Blender

Zip `blender_addon/dualcam_mocap` and install it from Blender Preferences > Add-ons > Install from Disk.

In **3D View > Sidebar > Mocap**:

1. Set GPU Host.
2. Keep port `8766`.
3. Press **Connect**.
4. Verify `MOCAP_*` debug points.
5. Press **Create Driver Rig** or bind the selected Rigify/Mixamo-style rig.
6. Toggle **Record** to insert animation keys.

Blender still uses only Python's standard `socket` library. No gRPC or pip packages are installed inside Blender.

## Temporary Python boundary

Python now exists only in the `inference` container. Its external contract is:

```text
mocap.v1.Inference/Infer(FrameSet) -> Skeleton
```

The planned C++/ONNX Runtime worker will implement this same service, allowing the Python inference container to be removed without changing the camera binary, Go server, Blender add-on, or LAN API.

See `GO_GRPC.md` for the service layout and protocol notes.
