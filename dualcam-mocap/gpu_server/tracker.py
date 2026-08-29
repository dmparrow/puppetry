from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class Pose2D:
    names: list[str]
    xy: np.ndarray
    confidence: np.ndarray


class SkellyRTMPoseTracker:
    """Thin adapter around FreeMoCap's skellytracker RTMPose backend."""

    def __init__(self, model: str = "rtmw-x-l_256x192", stage_name: str = "body"):
        try:
            from skellytracker.core import Tracker, TrackerConfig, DetectionStageConfig, TrackerState
            from skellytracker.core.detectors.object_detectors.yolox import YoloxPersonDetector, YoloxPersonDetectorConfig
            from skellytracker.core.detectors.keypoint_detectors.rtmpose import RTMPoseDetectorConfig, RTMPoseKeypointDetector
            from skellytracker.core.sessions.onnx_session import OnnxSession, OnnxSessionConfig
        except ImportError as exc:
            raise RuntimeError(
                'skellytracker is not installed. On an NVIDIA CUDA 12 host run: '
                'pip install "skellytracker[all-cuda]"'
            ) from exc

        self._stage_name = stage_name
        session = OnnxSession.create(OnnxSessionConfig(
            batch_size=1,
            models=[
                YoloxPersonDetector.model_spec("yolox-m"),
                RTMPoseKeypointDetector.model_spec(model),
            ],
        ))
        config = TrackerConfig(stages=[
            DetectionStageConfig(
                name=stage_name,
                object_detector=YoloxPersonDetectorConfig(),
                keypoint_detectors=[RTMPoseDetectorConfig()],
            )
        ])
        self._tracker = Tracker.create(config, sessions={"onnx": session})
        self._state_a = TrackerState()
        self._state_b = TrackerState()

    @staticmethod
    def _to_pose(keypoints) -> Pose2D:
        xyz = np.asarray(keypoints.xyz, dtype=np.float64)
        names = [str(n) for n in keypoints.names]
        visibility = np.asarray(keypoints.visibility, dtype=np.float64)
        if xyz.ndim == 3:
            xyz = xyz[0]
        if visibility.ndim > 1:
            visibility = visibility[0]
        visibility = visibility.reshape(-1)
        if xyz.shape[0] != len(names):
            names = names[: xyz.shape[0]]
        return Pose2D(names=names, xy=xyz[:, :2], confidence=visibility[: xyz.shape[0]])

    def process_pair(self, frame_a, frame_b, frame_number: int) -> tuple[Pose2D, Pose2D]:
        obs_a, self._state_a = self._tracker.process_image(frame_a, frame_number=frame_number, state=self._state_a)
        obs_b, self._state_b = self._tracker.process_image(frame_b, frame_number=frame_number, state=self._state_b)
        kp_a = obs_a.stages[self._stage_name].keypoints
        kp_b = obs_b.stages[self._stage_name].keypoints
        return self._to_pose(kp_a), self._to_pose(kp_b)

    def close(self) -> None:
        self._tracker.close()
