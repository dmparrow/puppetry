from __future__ import annotations

import numpy as np


COCO_BODY_NAMES = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]


class RTMLibMono3DTracker:
    """Monocular RTMW3D adapter using rtmlib's Wholebody3d solution.

    RTMW3D predicts relative 3D pose, not reliable metric world translation.
    We therefore root-lock the skeleton at the hip centre and normalize scale by
    the shoulder-to-hip torso length before sending it to Blender.
    """

    def __init__(
        self,
        device: str = "cuda",
        backend: str = "onnxruntime",
        confidence_threshold: float = 0.25,
        torso_length_m: float = 0.55,
    ):
        try:
            from rtmlib import Wholebody3d
        except ImportError as exc:
            raise RuntimeError(
                "rtmlib is required for single-camera 3D. Run: pip install rtmlib==0.0.16"
            ) from exc

        self._model = Wholebody3d(
            mode="balanced",
            to_openpose=False,
            backend=backend,
            device=device,
        )
        self.confidence_threshold = float(confidence_threshold)
        self.torso_length_m = float(torso_length_m)

    @staticmethod
    def _first_person(array, dims: int):
        value = np.asarray(array, dtype=np.float64)
        if value.size == 0:
            return None
        while value.ndim > dims:
            value = value[0]
        return value

    def process(self, frame) -> dict[str, dict]:
        _xyz, scores, xyz_simcc, _xy_2d = self._model(frame)

        # xyz_simcc keeps the three decoded SimCC axes in a common model-space
        # scale. This is more useful for relative limb geometry than mixing
        # image-space X/Y with RTMW3D's normalized depth value.
        xyz = self._first_person(xyz_simcc, 2)
        conf = self._first_person(scores, 1)
        if xyz is None or conf is None or xyz.ndim != 2 or xyz.shape[1] < 3:
            return {}

        count = min(17, xyz.shape[0], conf.shape[0])
        if count < 17:
            return {}

        body = xyz[:17, :3].copy()
        conf = conf[:17].reshape(-1)
        if not np.isfinite(body).all():
            return {}

        hips = (body[11] + body[12]) * 0.5
        shoulders = (body[5] + body[6]) * 0.5
        torso = float(np.linalg.norm(shoulders - hips))
        if torso < 1e-6:
            return {}

        scale = self.torso_length_m / torso
        body = (body - hips) * scale

        output: dict[str, dict] = {}
        for idx, name in enumerate(COCO_BODY_NAMES):
            score = float(conf[idx])
            if not np.isfinite(score) or score < self.confidence_threshold:
                continue
            output[name] = {
                "xyz": body[idx].tolist(),
                "confidence": score,
                "source": "rtmw3d_mono",
            }
        return output

    def close(self) -> None:
        # rtmlib's high-level solution owns ONNX sessions internally and does
        # not currently expose an explicit close method.
        pass
