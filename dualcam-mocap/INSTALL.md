# Install / first run

## GPU machine

```bash
cd dualcam-mocap
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-gpu.txt
pip install onnxruntime-gpu
cp config.example.yaml config.yaml
python -m gpu_server.main --config config.yaml
```

`rtmlib` supplies the single-camera RTMW3D solver. For stereo mode also install:

```bash
pip install "skellytracker[all-cuda]"
```

Ports:

- `8765/tcp`: WebSocket camera input
- `8766/tcp`: newline-delimited JSON skeleton output for Blender

## Camera machine — single camera (default)

```bash
cd dualcam-mocap
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-camera.txt
python -m camera_client.main --server ws://GPU_IP:8765 --mode mono --cam-a 0
```

No calibration is needed. Mono mode provides relative 3D pose with hip-centred/root-locked motion.

## Camera machine — stereo

First calibrate the two cameras:

```bash
python tools/generate_charuco.py
# print charuco_board.png at 100% / known physical scale
python tools/calibrate_stereo.py --cam-a 0 --cam-b 2 --out calibration/stereo.npz
```

Copy `calibration/stereo.npz` to the same path on the GPU machine, then run:

```bash
python -m camera_client.main --server ws://GPU_IP:8765 --mode stereo --cam-a 0 --cam-b 2
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
