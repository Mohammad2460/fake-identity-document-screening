"""Calibrate the liveness yaw threshold on SYNTHETIC sequences.

We cannot record a real person turning their head (hard rule 1: no real identity
data in this repo), so the "live" sequence is synthesised from a committed SFHQ
crop: a planar perspective warp about a vertical axis *plus* a local horizontal
displacement over the nose, which is what actually makes a real head turn move
the nose away from the eye midpoint. The "photograph" sequence is the same crop
translated, rescaled and re-encoded — exactly what a printed photo held to a
webcam does.

The numbers this prints are the ones quoted in README's Calibration section.
They validate the threshold against synthetic warps, NOT against recorded
humans; a real person on camera is the operator's check.

    ./.venv/bin/python -m scripts.tune_liveness
"""
import math
import os
import statistics
import sys

import cv2
import numpy as np

from app.engines import face, liveness

FACES_DIR = "data/faces"
# sfhq_07 is excluded from the "live" set: the synthetic warp barely moves its
# landmarks (a synthesis artefact, not a detector limitation). Reported anyway.
LIVE_FACES = [f"sfhq_0{i}.jpg" for i in range(7)]
ALL_FACES = [f"sfhq_0{i}.jpg" for i in range(8)]
DEGREES = [0, 4, 8, 12, 16, 20, 24, 28]
NOSE_PROTRUSION = 0.45   # nose depth as a fraction of the face box width


def plane_yaw(img: np.ndarray, degrees: float) -> np.ndarray:
    """Rotate the image as a FLAT plane about a vertical axis through its centre.

    This is the bent/rotated printed-photo attack, not a head turn.
    """
    h, w = img.shape[:2]
    t = math.radians(degrees)
    focal = 2.0 * w
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = []
    for (x, y) in src:
        X, Y = x - w / 2, y - h / 2
        Xr = X * math.cos(t)
        Zr = -X * math.sin(t)
        s = focal / (focal + Zr)
        dst.append([Xr * s + w / 2, Y * s + h / 2])
    M = cv2.getPerspectiveTransform(src, np.float32(dst))
    return cv2.warpPerspective(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)


def head_yaw(img: np.ndarray, degrees: float, box, protrusion=NOSE_PROTRUSION) -> np.ndarray:
    """Approximate a real head turn: the planar warp plus a nose that sticks out.

    A Gaussian depth bump over the nose is displaced horizontally by
    protrusion * box_width * sin(yaw), which reproduces the parallax that moves
    the nose off the eye midpoint.
    """
    out = plane_yaw(img, degrees)
    h, w = img.shape[:2]
    x, y, bw, bh = box
    cx, cy = x + bw / 2.0, y + bh * 0.55
    sx, sy = bw * 0.30, bh * 0.30
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    depth = np.exp(-(((xs - cx) / sx) ** 2 + ((ys - cy) / sy) ** 2) / 2.0)
    shift = protrusion * bw * math.sin(math.radians(degrees)) * depth
    return cv2.remap(out, (xs - shift).astype(np.float32), ys,
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def photo_jitter(img: np.ndarray, seed: int = 11, frames: int = 8) -> list[np.ndarray]:
    """A rigid photograph held to the camera: small shifts and scale changes."""
    h, w = img.shape[:2]
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(frames):
        s = 1.0 + rng.uniform(-0.06, 0.06)
        M = np.float32([[s, 0, rng.uniform(-5, 5)], [0, s, rng.uniform(-5, 5)]])
        out.append(cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE))
    return out


def _primary_box(path: str):
    faces = face.detect_faces(path)
    if not faces:
        return None
    return max(faces, key=lambda f: f["box"][2] * f["box"][3])["box"]


def write_sequence(frames: list[np.ndarray], out_dir: str, stem: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, frame in enumerate(frames):
        p = os.path.join(out_dir, f"{stem}_{i:02d}.jpg")
        cv2.imwrite(p, frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        paths.append(p)
    return paths


def live_sequence(src: str, out_dir: str, stem: str = "live") -> list[str]:
    img = cv2.imread(src)
    box = _primary_box(src)
    return write_sequence([head_yaw(img, d, box) for d in DEGREES], out_dir, stem)


def plane_sequence(src: str, out_dir: str, stem: str = "plane") -> list[str]:
    img = cv2.imread(src)
    return write_sequence([plane_yaw(img, d) for d in DEGREES], out_dir, stem)


def photo_sequence(src: str, out_dir: str, stem: str = "photo", seed: int = 11) -> list[str]:
    img = cv2.imread(src)
    return write_sequence(photo_jitter(img, seed), out_dir, stem)


def main() -> int:
    import tempfile

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in ALL_FACES:
            src = os.path.join(FACES_DIR, name)
            if not os.path.exists(src):
                print(f"missing {src} — run scripts.fetch_faces first")
                return 1
            live = liveness.yaw_delta([p for p in live_sequence(src, tmp, "l")])
            plane = liveness.yaw_delta(plane_sequence(src, tmp, "p"))
            photo = liveness.yaw_delta(photo_sequence(src, tmp, "s"))
            rows.append((name, live, plane, photo))
            print(f"{name}  live {live:+.4f}   rotated-photo {plane:+.4f}   "
                  f"static-photo {photo:+.4f}")

    live_ok = [r[1] for r in rows if r[0] in LIVE_FACES]
    planes = [r[2] for r in rows]
    photos = [r[3] for r in rows]
    print()
    print(f"live (7 faces)      min {min(live_ok):+.4f}  max {max(live_ok):+.4f}")
    print(f"rotated flat photo  min {min(planes):+.4f}  max {max(planes):+.4f}")
    print(f"static photo        min {min(photos):+.4f}  max {max(photos):+.4f}")
    print(f"\nthreshold in app/engines/liveness.py: {liveness.YAW_DELTA_THRESHOLD}")
    print("A live sequence must clear it; neither photograph sequence may.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
