# Hardware smoke test checklist

## Mono first

- Camera machine opens the intended device at 1280x720/30.
- Camera client reports stable FPS in `mode=mono`.
- GPU host loads RTMW3D through ONNX Runtime CUDA.
- GPU emits non-empty body points with `capture_mode=mono` and `root_translation=locked`.
- Blender receives points on TCP 8766 and updates debug empties.
- `MOCAP_DRIVER` follows arm/leg/spine directions without explosive depth jumps.

## Stereo second

- Camera machine opens both intended device indices at 1280x720/30.
- Calibration RMS and measured baseline are plausible.
- Camera client reports stable FPS and low pair skew.
- GPU host uses CUDA execution provider for RTMPose/YOLOX.
- Stereo output reports `capture_mode=stereo` and `root_translation=measured`.

## Both modes

- GPU processing stays below the desired live frame budget or drops stale frames rather than queueing.
- Driver armature orientation is correct before binding a production rig.
- Rig mapping is checked visually before enabling Record.
