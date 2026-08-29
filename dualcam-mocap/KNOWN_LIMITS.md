# Known V1 limits

- Single-camera RTMW3D is relative 3D: the skeleton is hip-centred/root-locked and does not provide reliable metric world translation.
- Mono scale is normalized from shoulder-to-hip torso length; actor calibration is still required for production-quality proportions.
- Stereo mode uses software-synced UVC cameras; no hardware trigger.
- Stereo RTMPose inference currently runs the two views sequentially through one shared model session; batching is the next optimization.
- EMA filter only; no One Euro filter or velocity gap filling yet.
- Body-first retarget mapping; hands/face/feet and twist-bone handling are not yet implemented.
- Production-rig binding uses direction alignment and common Rigify/Mixamo bone names; actor/rest-pose calibration should be added before calling retargeting production-ready.
