from __future__ import annotations

import argparse
import asyncio
import json
import socket
import time
from dataclasses import dataclass

import cv2
import msgpack
from websockets.asyncio.client import connect


@dataclass
class CameraConfig:
    index: int
    width: int
    height: int
    fps: int


def open_camera(cfg: CameraConfig) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(cfg.index, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap = cv2.VideoCapture(cfg.index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {cfg.index}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
    cap.set(cv2.CAP_PROP_FPS, cfg.fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    return cap


def read_single(cap: cv2.VideoCapture):
    if not cap.grab():
        raise RuntimeError("Camera grab failed")
    ts_ns = time.monotonic_ns()
    ok, frame = cap.retrieve()
    if not ok or frame is None:
        raise RuntimeError("Camera retrieve failed")
    return frame, ts_ns


def read_pair(cap_a: cv2.VideoCapture, cap_b: cv2.VideoCapture):
    if not cap_a.grab():
        raise RuntimeError("Camera A grab failed")
    a_ts_ns = time.monotonic_ns()
    if not cap_b.grab():
        raise RuntimeError("Camera B grab failed")
    b_ts_ns = time.monotonic_ns()
    ok_a, frame_a = cap_a.retrieve()
    ok_b, frame_b = cap_b.retrieve()
    if not ok_a or frame_a is None:
        raise RuntimeError("Camera A retrieve failed")
    if not ok_b or frame_b is None:
        raise RuntimeError("Camera B retrieve failed")
    return frame_a, a_ts_ns, frame_b, b_ts_ns


def encode_jpeg(frame, quality: int) -> bytes:
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return encoded.tobytes()


async def run(args: argparse.Namespace) -> None:
    mode = args.mode
    cap_a = open_camera(CameraConfig(args.cam_a, args.width, args.height, args.fps))
    cap_b = None
    if mode == "stereo":
        cap_b = open_camera(CameraConfig(args.cam_b, args.width, args.height, args.fps))

    seq = 0
    sent = 0
    started = time.monotonic()
    host = socket.gethostname()
    camera_ids = [str(args.cam_a)] if mode == "mono" else [str(args.cam_a), str(args.cam_b)]

    try:
        while True:
            try:
                async with connect(args.server, max_size=None, ping_interval=20, ping_timeout=20, compression=None) as ws:
                    await ws.send(json.dumps({
                        "type": "hello",
                        "role": "camera",
                        "name": host,
                        "mode": mode,
                        "camera_ids": camera_ids,
                    }))
                    print(f"Connected to {args.server} mode={mode}")
                    while True:
                        if mode == "mono":
                            frame, ts_ns = read_single(cap_a)
                            packet = {
                                "type": "frame_single",
                                "seq": seq,
                                "ts_ns": ts_ns,
                                "camera_ts_ns": ts_ns,
                                "jpeg": encode_jpeg(frame, args.jpeg_quality),
                            }
                            skew_ms = None
                        else:
                            assert cap_b is not None
                            frame_a, a_ts_ns, frame_b, b_ts_ns = read_pair(cap_a, cap_b)
                            packet = {
                                "type": "frame_pair",
                                "seq": seq,
                                "ts_ns": (a_ts_ns + b_ts_ns) // 2,
                                "a_ts_ns": a_ts_ns,
                                "b_ts_ns": b_ts_ns,
                                "a_jpeg": encode_jpeg(frame_a, args.jpeg_quality),
                                "b_jpeg": encode_jpeg(frame_b, args.jpeg_quality),
                            }
                            skew_ms = abs(a_ts_ns - b_ts_ns) / 1e6

                        await ws.send(msgpack.packb(packet, use_bin_type=True))
                        seq += 1
                        sent += 1
                        if sent % 60 == 0:
                            elapsed = max(time.monotonic() - started, 1e-6)
                            suffix = "" if skew_ms is None else f" capture_skew={skew_ms:.2f}ms"
                            print(f"sent={sent} fps={sent/elapsed:.1f} mode={mode}{suffix}")
            except asyncio.CancelledError:
                raise
            except KeyboardInterrupt:
                return
            except Exception as exc:
                print(f"Camera stream disconnected: {exc}; reconnecting...")
                await asyncio.sleep(1.0)
    finally:
        cap_a.release()
        if cap_b is not None:
            cap_b.release()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mono/stereo mocap capture client")
    p.add_argument("--server", required=True, help="ws://GPU_HOST:8765")
    p.add_argument("--mode", choices=("mono", "stereo"), default="mono")
    p.add_argument("--cam-a", type=int, default=0, help="camera used by mono mode and stereo camera A")
    p.add_argument("--cam-b", type=int, default=2, help="stereo camera B")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--jpeg-quality", type=int, default=82)
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
