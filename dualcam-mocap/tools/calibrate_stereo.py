from __future__ import annotations

import argparse
from pathlib import Path
import time

import cv2
import numpy as np


def open_camera(index: int, width: int, height: int, fps: int):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {index}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    return cap


def read_pair(a, b):
    if not a.grab() or not b.grab():
        raise RuntimeError("camera grab failed")
    ok_a, fa = a.retrieve()
    ok_b, fb = b.retrieve()
    if not ok_a or not ok_b:
        raise RuntimeError("camera retrieve failed")
    return fa, fb


def detect(detector, frame):
    corners, ids, marker_corners, marker_ids = detector.detectBoard(frame)
    if corners is None or ids is None or len(ids) < 6:
        return None, None, marker_corners, marker_ids
    return corners, ids, marker_corners, marker_ids


def common_points(board, ca, ia, cb, ib):
    map_a = {int(i): ca[k, 0] for k, i in enumerate(ia.reshape(-1))}
    map_b = {int(i): cb[k, 0] for k, i in enumerate(ib.reshape(-1))}
    common = sorted(set(map_a).intersection(map_b))
    if len(common) < 6:
        return None
    board_points = board.getChessboardCorners()
    obj = np.asarray([board_points[i] for i in common], dtype=np.float32)
    pa = np.asarray([map_a[i] for i in common], dtype=np.float32)
    pb = np.asarray([map_b[i] for i in common], dtype=np.float32)
    return obj, pa, pb


def main() -> None:
    p = argparse.ArgumentParser(description="Live dual-camera ChArUco stereo calibration")
    p.add_argument("--cam-a", type=int, default=0)
    p.add_argument("--cam-b", type=int, default=2)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--samples", type=int, default=24)
    p.add_argument("--out", default="calibration/stereo.npz")
    p.add_argument("--squares-x", type=int, default=7)
    p.add_argument("--squares-y", type=int, default=5)
    p.add_argument("--square-mm", type=float, default=40.0)
    p.add_argument("--marker-mm", type=float, default=30.0)
    args = p.parse_args()

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
    board = cv2.aruco.CharucoBoard(
        (args.squares_x, args.squares_y),
        args.square_mm / 1000.0,
        args.marker_mm / 1000.0,
        dictionary,
    )
    detector = cv2.aruco.CharucoDetector(board)
    cap_a = open_camera(args.cam_a, args.width, args.height, args.fps)
    cap_b = open_camera(args.cam_b, args.width, args.height, args.fps)
    charuco_a, ids_a, charuco_b, ids_b = [], [], [], []
    stereo_sets = []
    last_capture = 0.0

    print("Show the board to BOTH cameras from varied angles/distances.")
    print("SPACE = capture sample, Q = finish when enough samples are collected")
    try:
        while len(stereo_sets) < args.samples:
            fa, fb = read_pair(cap_a, cap_b)
            ca, ia, ma, mia = detect(detector, fa)
            cb, ib, mb, mib = detect(detector, fb)
            va, vb = fa.copy(), fb.copy()
            if mia is not None and len(mia):
                cv2.aruco.drawDetectedMarkers(va, ma, mia)
            if mib is not None and len(mib):
                cv2.aruco.drawDetectedMarkers(vb, mb, mib)
            if ca is not None:
                cv2.aruco.drawDetectedCornersCharuco(va, ca, ia)
            if cb is not None:
                cv2.aruco.drawDetectedCornersCharuco(vb, cb, ib)
            status = f"samples {len(stereo_sets)}/{args.samples} | SPACE capture | Q finish"
            cv2.putText(va, status, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(vb, status, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            preview = np.hstack((cv2.resize(va, (640, 360)), cv2.resize(vb, (640, 360))))
            cv2.imshow("DualCam calibration", preview)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == 32 and time.monotonic() - last_capture > 0.25:
                last_capture = time.monotonic()
                if ca is None or cb is None:
                    print("board must be visible in both cameras")
                    continue
                shared = common_points(board, ca, ia, cb, ib)
                if shared is None:
                    print("not enough common ChArUco corners")
                    continue
                charuco_a.append(ca.astype(np.float32))
                ids_a.append(ia.astype(np.int32))
                charuco_b.append(cb.astype(np.float32))
                ids_b.append(ib.astype(np.int32))
                stereo_sets.append(shared)
                print(f"captured sample {len(stereo_sets)}")
    finally:
        cap_a.release()
        cap_b.release()
        cv2.destroyAllWindows()

    if len(stereo_sets) < 8:
        raise RuntimeError("Need at least 8 good stereo samples")

    image_size = (args.width, args.height)
    rms_a, K1, D1, _, _ = cv2.aruco.calibrateCameraCharuco(charuco_a, ids_a, board, image_size, None, None)
    rms_b, K2, D2, _, _ = cv2.aruco.calibrateCameraCharuco(charuco_b, ids_b, board, image_size, None, None)
    object_points = [x[0] for x in stereo_sets]
    image_points_a = [x[1] for x in stereo_sets]
    image_points_b = [x[2] for x in stereo_sets]
    rms_stereo, _, _, _, _, R, T, E, F = cv2.stereoCalibrate(
        object_points, image_points_a, image_points_b,
        K1, D1, K2, D2, image_size,
        flags=cv2.CALIB_FIX_INTRINSIC,
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        out, K1=K1, D1=D1, K2=K2, D2=D2, R=R, T=T, E=E, F=F,
        image_size=np.asarray(image_size), rms_a=np.asarray(rms_a),
        rms_b=np.asarray(rms_b), rms_stereo=np.asarray(rms_stereo),
    )
    print(f"saved {out}")
    print(f"RMS: camera A={rms_a:.3f}, camera B={rms_b:.3f}, stereo={rms_stereo:.3f}")
    print(f"baseline: {float(np.linalg.norm(T)):.3f} m")


if __name__ == "__main__":
    main()
