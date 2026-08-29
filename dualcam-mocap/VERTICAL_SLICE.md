# Vertical slice acceptance

A successful first end-to-end run is:

- both cameras stream paired 720p frames across the LAN;
- GPU server reports RTMPose keypoints and non-empty triangulated 3D points;
- bad points over the reprojection threshold are dropped;
- Blender receives skeleton JSON without third-party Python packages;
- debug points move live;
- `MOCAP_DRIVER` armature moves live;
- a selected Rigify/Mixamo-style rig reports mapped segments and follows limb directions;
- enabling Record inserts animation keyframes.

This is deliberately body-first. Hands, face, foot locking, actor rest-pose calibration, One Euro filtering, and batched dual-camera inference are the next layer after this path is proven on the real cameras/GPU.
