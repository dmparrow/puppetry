import numpy as np

from gpu_server.mono3d import RTMLibMono3DTracker


def test_mono_pose_is_root_locked_and_torso_scaled():
    tracker = RTMLibMono3DTracker.__new__(RTMLibMono3DTracker)
    tracker.confidence_threshold = 0.25
    tracker.torso_length_m = 0.55

    xyz = np.zeros((1, 133, 3), dtype=np.float64)
    scores = np.ones((1, 133), dtype=np.float64)

    # COCO indices: shoulders 5/6, hips 11/12.
    xyz[0, 5] = [-1.0, -2.0, 0.25]
    xyz[0, 6] = [1.0, -2.0, 0.25]
    xyz[0, 11] = [-0.5, 0.0, 0.0]
    xyz[0, 12] = [0.5, 0.0, 0.0]
    xyz[0, 7] = [-1.5, -3.0, 0.5]
    xyz[0, 8] = [1.5, -3.0, 0.5]

    tracker._model = lambda _frame: (xyz.copy(), scores.copy(), xyz.copy(), xyz[..., :2].copy())

    points = tracker.process(np.zeros((8, 8, 3), dtype=np.uint8))

    left_hip = np.asarray(points["left_hip"]["xyz"])
    right_hip = np.asarray(points["right_hip"]["xyz"])
    left_shoulder = np.asarray(points["left_shoulder"]["xyz"])
    right_shoulder = np.asarray(points["right_shoulder"]["xyz"])

    hip_center = (left_hip + right_hip) * 0.5
    shoulder_center = (left_shoulder + right_shoulder) * 0.5

    assert np.allclose(hip_center, np.zeros(3), atol=1e-9)
    assert np.isclose(np.linalg.norm(shoulder_center - hip_center), 0.55, atol=1e-9)
    assert points["left_shoulder"]["source"] == "rtmw3d_mono"
