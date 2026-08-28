# Hardware smoke test checklist

- Camera machine can open both intended device indices at 1280x720/30.
- Calibration RMS and measured baseline are plausible.
- Camera client reports stable FPS and low pair skew.
- GPU host uses CUDA execution provider for RTMPose/YOLOX.
- GPU processing stays below the desired live frame budget or drops stale frames rather than queueing.
- Blender receives points on TCP 8766 and updates debug empties.
- Driver armature orientation is correct before binding a production rig.
- Rig mapping is checked visually before enabling Record.
