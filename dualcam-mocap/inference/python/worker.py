from __future__ import annotations

import argparse
import base64
import json
import os
import time
from concurrent import futures

import cv2
import grpc
import numpy as np

from gpu_server.mono3d import RTMLibMono3DTracker
from gpu_server.tracker import SkellyRTMPoseTracker
from gpu_server.triangulation import EmaSkeletonFilter, StereoCalibration, StereoTriangulator


class InferenceWorker:
    def __init__(self):
        self._mono = None
        self._stereo_tracker = None
        self._triangulator = None
        self._mono_filter = EmaSkeletonFilter(float(os.getenv("MOCAP_SMOOTHING_ALPHA", "0.55")))
        self._stereo_filter = EmaSkeletonFilter(float(os.getenv("MOCAP_SMOOTHING_ALPHA", "0.55")))

    @staticmethod
    def _decode(frame: dict):
        raw = base64.b64decode(frame["jpeg"])
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("could not decode JPEG")
        return image

    def _mono_points(self, image):
        if self._mono is None:
            self._mono = RTMLibMono3DTracker(
                device=os.getenv("MOCAP_MONO_DEVICE", "cuda"),
                backend=os.getenv("MOCAP_MONO_BACKEND", "onnxruntime"),
                confidence_threshold=float(os.getenv("MOCAP_CONFIDENCE", "0.25")),
                torso_length_m=float(os.getenv("MOCAP_TORSO_LENGTH_M", "0.55")),
            )
        return self._mono_filter.apply(self._mono.process(image))

    def _stereo_points(self, a, b, sequence: int):
        if self._stereo_tracker is None:
            self._stereo_tracker = SkellyRTMPoseTracker(
                model=os.getenv("MOCAP_RTMPOSE_MODEL", "rtmw-x-l_256x192"),
                stage_name="body",
            )
            cal = StereoCalibration.load(os.getenv("MOCAP_CALIBRATION", "/app/calibration/stereo.npz"))
            self._triangulator = StereoTriangulator(
                cal,
                confidence_threshold=float(os.getenv("MOCAP_CONFIDENCE", "0.35")),
                max_reprojection_error_px=float(os.getenv("MOCAP_MAX_REPROJECTION_PX", "12.0")),
            )
        pose_a, pose_b = self._stereo_tracker.process_pair(a, b, sequence)
        return self._stereo_filter.apply(self._triangulator.triangulate(pose_a, pose_b))

    def infer(self, request: dict, _context):
        started = time.perf_counter()
        sequence = int(request.get("sequence", 0))
        mode = request.get("capture_mode", "mono")
        frames = request.get("frames", [])
        if not frames:
            return self._reply(sequence, mode, 0, {}, started)

        if mode == "stereo":
            if len(frames) < 2:
                raise ValueError("stereo capture requires two frames")
            points = self._stereo_points(self._decode(frames[0]), self._decode(frames[1]), sequence)
            root_translation = "measured"
            timestamp_ns = (int(frames[0]["timestamp_ns"]) + int(frames[1]["timestamp_ns"])) // 2
        else:
            points = self._mono_points(self._decode(frames[0]))
            root_translation = "locked"
            timestamp_ns = int(frames[0]["timestamp_ns"])

        return self._reply(sequence, mode, timestamp_ns, points, started, root_translation)

    @staticmethod
    def _reply(sequence, mode, timestamp_ns, points, started, root_translation="locked"):
        joints = []
        for name, value in points.items():
            xyz = value.get("xyz")
            if not xyz or len(xyz) < 3:
                continue
            joints.append({
                "name": name,
                "x": float(xyz[0]), "y": float(xyz[1]), "z": float(xyz[2]),
                "confidence": float(value.get("confidence", 0.0)),
            })
        return {
            "sequence": sequence,
            "timestamp_ns": timestamp_ns,
            "capture_mode": mode,
            "root_translation": root_translation,
            "joints": joints,
            "processing_ms": (time.perf_counter() - started) * 1000.0,
        }


def loads(data: bytes):
    return json.loads(data.decode("utf-8"))


def dumps(value) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0:50052")
    args = parser.parse_args()

    worker = InferenceWorker()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    handler = grpc.method_handlers_generic_handler(
        "mocap.v1.Inference",
        {"Infer": grpc.unary_unary_rpc_method_handler(
            worker.infer,
            request_deserializer=loads,
            response_serializer=dumps,
        )},
    )
    server.add_generic_rpc_handlers((handler,))
    server.add_insecure_port(args.listen)
    server.start()
    print(f"Python inference worker listening on {args.listen}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
