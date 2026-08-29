# Install / first run

## GPU machine — recommended Docker path

Prerequisites on the host:

- NVIDIA driver working (`nvidia-smi`)
- Docker Engine + Docker Compose v2
- NVIDIA Container Toolkit

Then:

```bash
cd dualcam-mocap
chmod +x run_gpu_container.sh
./run_gpu_container.sh
```

The launcher:

- verifies Docker/Compose;
- verifies the host GPU with `nvidia-smi`;
- verifies Docker can access the GPU;
- creates `config.yaml` from `config.example.yaml` if needed;
- builds and starts the mocap GPU container.

Useful commands:

```bash
docker compose logs -f mocap-gpu
docker compose restart mocap-gpu
docker compose down
```

Ports:

- `8765/tcp`: WebSocket camera input
- `8766/tcp`: newline-delimited JSON skeleton output for Blender

The model/download cache is stored in the named Docker volume `mocap-model-cache`, so rebuilding the image does not intentionally throw away downloaded model cache data.

### Native GPU install (fallback)

```bash
cd dualcam-mocap
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-gpu.txt
pip install "skellytracker[all-cuda]" rtmlib
cp config.example.yaml config.yaml
python -m gpu_server.main --config config.yaml
```

## Camera machine — single camera (default)

Keep the camera client native so Linux can access `/dev/video*` without Docker device passthrough setup.

```bash
cd dualcam-mocap
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-camera.txt
./run_camera.sh ws://GPU_IP:8765
```

No calibration is needed. Mono mode provides relative 3D pose with hip-centred/root-locked motion.

## Camera machine — stereo

First calibrate the two cameras:

```bash
python tools/generate_charuco.py
# print charuco_board.png at 100% / known physical scale
python tools/calibrate_stereo.py --cam-a 0 --cam-b 2 --out calibration/stereo.npz
```

Copy `calibration/stereo.npz` into `dualcam-mocap/calibration/` on the GPU host. The Compose service mounts that directory read-only into the container.

Then run:

```bash
./run_camera.sh ws://GPU_IP:8765 stereo 0 2
```

## Blender

Zip the folder `blender_addon/dualcam_mocap` and install it from Blender Preferences > Add-ons > Install from Disk.

In **3D View > Sidebar > Mocap**:

1. Set GPU Host.
2. Keep port `8766`.
3. Press **Connect**.
4. With Debug Points enabled, verify the tracked points move.
5. Press **Create Driver Rig** to get a live `MOCAP_DRIVER` armature.
6. Or select a Rigify/Mixamo-style armature and press **Bind Selected Rig**.
7. Toggle **Record** to keyframe mapped bones.

The Blender add-on uses only Python's standard `socket` library; no Blender-side pip installation is required, and the same add-on works for mono and stereo capture.
