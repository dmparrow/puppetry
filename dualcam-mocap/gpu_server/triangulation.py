from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .tracker import Pose2D


@dataclass
class StereoCalibration:
    K1: np.ndarray
    D1: np.ndarray
    K2: np.ndarray
    D2: np.ndarray
    R: np.ndarray
    T: np.ndarray

    @classmethod
    def load(cls, path: str | Path) -> "StereoCalibration":
        data = np.load(str(path))
        required = ("K1", "D1", "K2", "D2", "R", "T")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"Calibration is missing arrays: {', '.join(missing)}")
        return cls(*(np.asarray(data[key], dtype=np.float64) for key in required))


class StereoTriangulator:
    def __init__(self, calibration: StereoCalibration, confidence_threshold: float = 0.35, max_reprojection_error_px: float = 12.0):
        self.cal = calibration
        self.confidence_threshold = confidence_threshold
        self.max_reprojection_error_px = max_reprojection_error_px
        self.P1 = self.cal.K1 @ np.hstack((np.eye(3), np.zeros((3, 1))))
        self.P2 = self.cal.K2 @ np.hstack((self.cal.R, self.cal.T.reshape(3, 1)))

    @staticmethod
    def _name_map(pose: Pose2D) -> dict[str, int]:
        return {name: idx for idx, name in enumerate(pose.names)}

    def _project(self, xyz: np.ndarray, camera: int) -> np.ndarray:
        points = xyz.reshape(-1, 1, 3)
        if camera == 1:
            rvec = np.zeros(3)
            tvec = np.zeros(3)
            K, D = self.cal.K1, self.cal.D1
        else:
            rvec, _ = cv2.Rodrigues(self.cal.R)
            tvec = self.cal.T.reshape(3)
            K, D = self.cal.K2, self.cal.D2
        projected, _ = cv2.projectPoints(points, rvec, tvec, K, D)
        return projected.reshape(-1, 2)

    def triangulate(self, a: Pose2D, b: Pose2D) -> dict[str, dict]:
        idx_a = self._name_map(a)
        idx_b = self._name_map(b)
        common = [name for name in a.names if name in idx_b]
        output: dict[str, dict] = {}
        for name in common:
            ia, ib = idx_a[name], idx_b[name]
            conf = float(min(a.confidence[ia], b.confidence[ib]))
            if conf < self.confidence_threshold:
                continue
            pa = np.asarray(a.xy[ia], dtype=np.float64).reshape(1, 1, 2)
            pb = np.asarray(b.xy[ib], dtype=np.float64).reshape(1, 1, 2)
            if not np.isfinite(pa).all() or not np.isfinite(pb).all():
                continue
            ua = cv2.undistortPoints(pa, self.cal.K1, self.cal.D1, P=self.cal.K1).reshape(2, 1)
            ub = cv2.undistortPoints(pb, self.cal.K2, self.cal.D2, P=self.cal.K2).reshape(2, 1)
            homogeneous = cv2.triangulatePoints(self.P1, self.P2, ua, ub).reshape(4)
            if abs(homogeneous[3]) < 1e-9:
                continue
            xyz = homogeneous[:3] / homogeneous[3]
            if not np.isfinite(xyz).all():
                continue
            reproj_a = self._project(xyz, 1)[0]
            reproj_b = self._project(xyz, 2)[0]
            err_a = float(np.linalg.norm(reproj_a - pa.reshape(2)))
            err_b = float(np.linalg.norm(reproj_b - pb.reshape(2)))
            reproj = (err_a + err_b) * 0.5
            if reproj > self.max_reprojection_error_px:
                continue
            output[name] = {"xyz": xyz.tolist(), "confidence": conf, "reprojection_error_px": reproj}
        return output


class EmaSkeletonFilter:
    def __init__(self, alpha: float = 0.55):
        self.alpha = float(np.clip(alpha, 0.0, 1.0))
        self._previous: dict[str, np.ndarray] = {}

    def apply(self, points: dict[str, dict]) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for name, payload in points.items():
            current = np.asarray(payload["xyz"], dtype=np.float64)
            previous = self._previous.get(name)
            filtered = current if previous is None else self.alpha * current + (1.0 - self.alpha) * previous
            self._previous[name] = filtered
            result[name] = {**payload, "xyz": filtered.tolist()}
        return result
