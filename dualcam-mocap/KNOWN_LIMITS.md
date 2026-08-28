# Known V1 limits

- Software-synced UVC cameras; no hardware trigger.
- RTMPose inference currently runs the two views sequentially through one shared model session; batching is the next optimization.
- EMA filter only; no One Euro filter or velocity gap filling yet.
- Body-first retarget mapping; hands/face/feet and twist-bone handling are not yet implemented.
- Production-rig binding uses direction alignment and common Rigify/Mixamo bone names; actor/rest-pose calibration should be added before calling retargeting production-ready.
