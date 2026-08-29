# DualCam Mocap

Low-friction single- or dual-camera motion capture for Blender. **Single camera is the default quick-start path**; stereo is the higher-accuracy option when a calibrated second camera is available.

Architecture:

```text
camera machine
  -> mono: one JPEG stream
  -> stereo: synchronized JPEG pair
GPU machine
  -> mono: RTMW3D relative 3D pose
  -> stereo: RTMPose 2D + calibrated triangulation
  -> canonical skeleton over TCP
Blender add-on
  -> live empties / armature retargeting
  -> record action
```

## Quick start: one camera

### GPU machine

Python 3.11 is recommended.

```bash
cd dualcam-mocap
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-gpu.txt
pip install onnxruntime-gpu
cp config.example.yaml config.yaml
python -m gpu_server.main --config config.yaml
```

No camera calibration is required for mono mode. RTMW3D is loaded lazily when the first mono frame arrives.

### Camera machine

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-camera.txt
python -m camera_client.main --server ws://GPU_IP:8765 --mode mono --cam-a 0
```

Or:

```bash
./run_camera.sh ws://GPU_IP:8765
```

Mono mode predicts **relative** 3D pose. The GPU server locks the skeleton around the hip centre and normalizes scale from the torso, so limb motion is useful for live rig driving but global walking translation is not measured.

## Stereo mode

Install the CUDA-enabled SkellyTracker backend on the GPU host:

```bash
pip install "skellytracker[all-cuda]"
```

Create/copy `calibration/stereo.npz` containing:

- `K1`, `D1`: camera A intrinsics/distortion
- `K2`, `D2`: camera B intrinsics/distortion
- `R`, `T`: transform from camera A to camera B

Then start capture with:

```bash
python -m camera_client.main --server ws://GPU_IP:8765 --mode stereo --cam-a 0 --cam-b 2
# or
./run_camera.sh ws://GPU_IP:8765 stereo 0 2
```

The stereo client calls `grab()` on both UVC devices before retrieving either frame. The GPU server triangulates matching RTMPose keypoints and rejects points with excessive reprojection error.

## Blender

Install the `blender_addon/dualcam_mocap` folder as a Blender add-on (zip that folder if installing from Preferences).

Open **3D View > Sidebar > Mocap**, set the GPU host and keep port `8766`, then press **Connect**.

The Blender protocol is identical for mono and stereo, so you can switch capture modes without changing the add-on. Debug points, `MOCAP_DRIVER`, Rigify/Mixamo-style binding and Record all consume the same skeleton JSON.

## Protocol

Mono camera packet:

```python
{
  "type": "frame_single",
  "seq": 100,
  "ts_ns": 123456789,
  "jpeg": b"..."
}
```

Stereo camera packet:

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

Skeleton output stays common:

```json
{
  "type": "skeleton",
  "capture_mode": "mono",
  "root_translation": "locked",
  "seq": 100,
  "points": {
    "left_shoulder": {"xyz": [0.1, 0.2, -0.1], "confidence": 0.94}
  }
}
```

Stereo output reports `root_translation: measured`; mono reports `root_translation: locked`.

## Included now

- single UVC capture as default
- RTMW3D monocular relative 3D through `rtmlib`
- root-locked / torso-normalized mono skeleton
- dual UVC synchronized capture
- RTMPose/YOLOX stereo inference via `skellytracker`
- calibrated stereo triangulation and reprojection rejection
- newest-frame-only processing to avoid latency queues
- light temporal EMA filtering
- common Blender TCP skeleton protocol
- Blender debug skeleton, driver rig, initial Rigify/Mixamo retargeting and recording

Next useful additions are proper actor/rest-pose calibration, foot locking, global-root estimation for mono, hands/face and batched stereo inference.
