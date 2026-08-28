from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import cv2
import msgpack
import numpy as np
import yaml
from websockets.asyncio.server import serve

from .tracker import SkellyRTMPoseTracker
from .triangulation import StereoCalibration, StereoTriangulator, EmaSkeletonFilter


class MocapServer:
    def __init__(self, config: dict):
        server_cfg = config.get("server", {})
        tracker_cfg = config.get("tracker", {})
        self.host = server_cfg.get("host", "0.0.0.0")
        self.port = int(server_cfg.get("port", 8765))
        self.blender_port = int(server_cfg.get("blender_port", 8766))
        calibration = StereoCalibration.load(server_cfg.get("calibration_file", "calibration/stereo.npz"))
        self.triangulator = StereoTriangulator(
            calibration,
            confidence_threshold=float(server_cfg.get("confidence_threshold", 0.35)),
            max_reprojection_error_px=float(server_cfg.get("max_reprojection_error_px", 12.0)),
        )
        self.filter = EmaSkeletonFilter(float(server_cfg.get("smoothing_alpha", 0.55)))
        self.tracker = SkellyRTMPoseTracker(
            model=tracker_cfg.get("model", "rtmw-x-l_256x192"),
            stage_name=tracker_cfg.get("stage_name", "body"),
        )
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
        self.blender_clients: set[asyncio.StreamWriter] = set()

    @staticmethod
    def _decode_jpeg(data: bytes):
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not decode JPEG")
        return image

    async def camera_ws(self, websocket):
        first = await websocket.recv()
        if not isinstance(first, str):
            await websocket.close(code=1003, reason="hello must be JSON text")
            return
        hello = json.loads(first)
        if hello.get("role") != "camera":
            await websocket.close(code=1008, reason="camera role required")
            return
        print(f"camera connected: {hello.get('name', 'unknown')}")
        try:
            async for raw in websocket:
                if not isinstance(raw, bytes):
                    continue
                packet = msgpack.unpackb(raw, raw=False)
                if packet.get("type") != "frame_pair":
                    continue
                if self.queue.full():
                    try:
                        self.queue.get_nowait()
                        self.queue.task_done()
                    except asyncio.QueueEmpty:
                        pass
                await self.queue.put(packet)
        finally:
            print("camera disconnected")

    async def blender_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        self.blender_clients.add(writer)
        print(f"blender client connected: {peer}")
        try:
            while not reader.at_eof():
                data = await reader.read(64)
                if not data:
                    break
        finally:
            self.blender_clients.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            print(f"blender client disconnected: {peer}")

    async def broadcast(self, payload: dict) -> None:
        if not self.blender_clients:
            return
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        dead: list[asyncio.StreamWriter] = []
        for writer in tuple(self.blender_clients):
            try:
                writer.write(line)
                await writer.drain()
            except Exception:
                dead.append(writer)
        for writer in dead:
            self.blender_clients.discard(writer)
            writer.close()

    async def process_loop(self) -> None:
        processed = 0
        started = time.monotonic()
        while True:
            packet = await self.queue.get()
            try:
                seq = int(packet["seq"])
                frame_a = self._decode_jpeg(packet["a_jpeg"])
                frame_b = self._decode_jpeg(packet["b_jpeg"])
                t0 = time.perf_counter()
                pose_a, pose_b = await asyncio.to_thread(self.tracker.process_pair, frame_a, frame_b, seq)
                points = self.filter.apply(self.triangulator.triangulate(pose_a, pose_b))
                processing_ms = (time.perf_counter() - t0) * 1000.0
                payload = {
                    "type": "skeleton",
                    "seq": seq,
                    "ts_ns": int(packet.get("ts_ns", 0)),
                    "capture_skew_ms": abs(int(packet.get("a_ts_ns", 0)) - int(packet.get("b_ts_ns", 0))) / 1e6,
                    "processing_ms": processing_ms,
                    "points": points,
                }
                await self.broadcast(payload)
                processed += 1
                if processed % 30 == 0:
                    elapsed = max(time.monotonic() - started, 1e-6)
                    print(f"processed={processed} fps={processed/elapsed:.1f} points={len(points)} processing={processing_ms:.1f}ms")
            except Exception as exc:
                print(f"frame processing failed: {exc}")
            finally:
                self.queue.task_done()

    async def run(self) -> None:
        tcp_server = await asyncio.start_server(self.blender_client, host=self.host, port=self.blender_port)
        processor = asyncio.create_task(self.process_loop())
        try:
            async with serve(self.camera_ws, self.host, self.port, max_size=None, compression=None):
                print(f"camera websocket: ws://{self.host}:{self.port}")
                print(f"blender tcp:      {self.host}:{self.blender_port}")
                async with tcp_server:
                    await asyncio.Future()
        finally:
            processor.cancel()
            self.tracker.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dual-camera mocap GPU server")
    p.add_argument("--config", default="config.yaml")
    return p.parse_args()


def load_config(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(MocapServer(load_config(args.config)).run())
