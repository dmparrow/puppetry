from __future__ import annotations

import argparse
from pathlib import Path
import cv2


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="charuco_board.png")
    p.add_argument("--squares-x", type=int, default=7)
    p.add_argument("--squares-y", type=int, default=5)
    p.add_argument("--square-mm", type=float, default=40.0)
    p.add_argument("--marker-mm", type=float, default=30.0)
    p.add_argument("--width-px", type=int, default=2000)
    p.add_argument("--height-px", type=int, default=1400)
    args = p.parse_args()
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
    board = cv2.aruco.CharucoBoard(
        (args.squares_x, args.squares_y),
        args.square_mm / 1000.0,
        args.marker_mm / 1000.0,
        dictionary,
    )
    image = board.generateImage((args.width_px, args.height_px), marginSize=40, borderBits=1)
    out = Path(args.out)
    cv2.imwrite(str(out), image)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
