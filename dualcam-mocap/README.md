# DualCam Mocap

Low-friction dual-camera motion capture for Blender.

Architecture:

```text
camera machine (2x UVC cameras)
  -> paired JPEG frames over WebSocket
GPU machine (RTMPose via skellytracker)
  -> stereo triangulation
  -> canonical 3D skeleton over WebSocket
Blender add-on
  -> live empties / armature retargeting
  -> record action
```

## 1. GPU server

Python 3.11 is recommended.

```bash
cd dualcam-mocap
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-gpu.txt
cp config.example.yaml config.yaml
```

Install the CUDA-enabled tracker backend:

```bash
pip install "skellytracker[all-cuda]"
```

Put your stereo calibration at `calibration/stereo.npz`. It must contain:

- `K1`, `D1`: camera A intrinsics/distortion
- `K2`, `D2`: camera B intrinsics/distortion
- `R`, `T`: transform from camera A to camera B

Then run:

```bash
python -m gpu_server.main --config config.yaml
```

## 2. Camera machine

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-camera.txt
python -m camera_client.main --server ws://GPU_IP:8765 --cam-a 0 --cam-b 2
```

The client calls `grab()` on both UVC devices before retrieving either frame. This keeps software synchronization tight without requiring hardware-trigger cameras.

## 3. Blender

Install the `blender_addon/dualcam_mocap` folder as a Blender add-on (zip that folder if installing from Preferences).

Open **3D View > Sidebar > Mocap** and set:

```text
ws://GPU_IP:8765
```

Press **Connect**. The initial vertical slice creates/updates `MOCAP_*` empties so you can verify the entire network + inference + triangulation chain before retargeting a production rig.

For a Rigify-style armature, select it and press **Bind Selected Rig**. The add-on maps the body chain by common Rigify DEF bone names and applies live rotations. Record toggles Blender keyframe insertion on the mapped pose bones.

## Protocol

Camera packets are MessagePack binary messages:

```python
{
  "type": "frame_pair",
  "seq": 100,
  "ts_ns": 123456789,
  "a_ts_ns": 123456700,
  "b_ts_ns": 123456760,
  "a_jpeg": b"...",
  "b_jpeg": b"..."
}
```

Skeleton output is JSON:

```json
{
  "type": "skeleton",
  "seq": 100,
  "ts_ns": 123456789,
  "points": {
    "left_shoulder": {"xyz": [0.1, 1.4, 2.2], "confidence": 0.94}
  }
}
```

Coordinates are in camera-A space and converted to Blender axes by the add-on.

## Scope of this slice

Included now:

- dual UVC capture
- paired frame transport over LAN
- RTMPose/YOLOX inference adapter via `skellytracker`
- 17-joint COCO body extraction
- calibrated stereo triangulation
- reprojection-error rejection
- light temporal EMA filtering
- WebSocket skeleton fan-out
- Blender debug skeleton
- initial Rigify body retargeting
- action keyframe recording

Next useful additions are ChArUco calibration UI, proper rest-pose actor calibration, IK/foot locking, hands, face, and multi-camera (>2) robust triangulation.
