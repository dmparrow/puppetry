# Install / first run

## Camera machine

```bash
cd dualcam-mocap
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-camera.txt
python -m camera_client.main --server ws://GPU_IP:8765 --cam-a 0 --cam-b 2
```

## Calibrate the two cameras

Run this on the camera machine before starting the camera client:

```bash
python tools/generate_charuco.py
# print charuco_board.png at 100% / known physical scale
python tools/calibrate_stereo.py --cam-a 0 --cam-b 2 --out calibration/stereo.npz
```

Copy `calibration/stereo.npz` to the same path on the GPU machine.

## GPU machine

```bash
cd dualcam-mocap
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-gpu.txt
pip install "skellytracker[all-cuda]"
cp config.example.yaml config.yaml
python -m gpu_server.main --config config.yaml
```

Ports:

- `8765/tcp`: WebSocket camera input
- `8766/tcp`: newline-delimited JSON skeleton output for Blender

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

The Blender add-on uses only Python's standard `socket` library; no Blender-side pip installation is required.
