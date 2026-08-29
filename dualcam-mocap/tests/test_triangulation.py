from __future__ import annotations

import numpy as np

from gpu_server.tracker import Pose2D
from gpu_server.triangulation import StereoCalibration, StereoTriangulator


def test_synthetic_triangulation():
    K = np.array([[800.0, 0, 640.0], [0, 800.0, 360.0], [0, 0, 1.0]])
    D = np.zeros(5)
    R = np.eye(3)
    T = np.array([[-0.5], [0.0], [0.0]])
    cal = StereoCalibration(K, D, K, D, R, T)
    tri = StereoTriangulator(cal, confidence_threshold=0.1, max_reprojection_error_px=1.0)
    target = np.array([0.2, -0.3, 3.0])

    def project(K, R, T, point):
        camera_point = R @ point + T.reshape(3)
        uv = K @ camera_point
        return uv[:2] / uv[2]

    pa = project(K, np.eye(3), np.zeros((3, 1)), target)
    pb = project(K, R, T, target)
    a = Pose2D(["left_shoulder"], np.array([pa]), np.array([0.9]))
    b = Pose2D(["left_shoulder"], np.array([pb]), np.array([0.95]))
    out = tri.triangulate(a, b)
    assert np.linalg.norm(np.array(out["left_shoulder"]["xyz"]) - target) < 1e-6
