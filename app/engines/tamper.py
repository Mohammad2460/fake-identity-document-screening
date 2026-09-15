"""Pixel-level tamper heuristics: ELA, copy-move cloning, noise inconsistency."""
import os
import tempfile
import cv2
import numpy as np
from PIL import Image
from app.models import Signal

ELA_SUSPICIOUS = 6.0      # brightest-1% to median residual ratio
CLONE_MATCH_MIN = 12      # self-matches with consistent offset
NOISE_SPREAD_MAX = 4.5    # ratio of loudest tile variance to median tile variance

def _load_bgr(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("image could not be decoded")
    if max(img.shape[:2]) > 1400:                 # keep the demo fast
        scale = 1400 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img

def ela_map(path: str, quality: int = 90, channel: str = "max") -> np.ndarray:
    """Per-pixel re-compression residual.

    channel="max": max absolute difference over R, G, B (whole-image tamper check).
    channel="luma": absolute difference of the grayscale images, which ignores
    chroma-subsampling error around light text on saturated colour.
    """
    if channel not in ("max", "luma"):
        raise ValueError(f"unknown ELA channel {channel!r}; use 'max' or 'luma'")
    with Image.open(path) as im:
        original = im.convert("RGB")
        fd, tmp = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            original.save(tmp, "JPEG", quality=quality)
            with Image.open(tmp) as resaved:
                if channel == "luma":
                    return np.abs(np.asarray(original.convert("L"), np.int16)
                                  - np.asarray(resaved.convert("L"), np.int16)
                                  ).astype(np.float32)
                diff = np.abs(np.asarray(original, np.int16)
                              - np.asarray(resaved.convert("RGB"), np.int16))
        finally:
            os.unlink(tmp)
    return diff.max(axis=2).astype(np.float32)

def ela_score(path: str) -> float:
    m = ela_map(path)
    hot = float(np.percentile(m, 99))
    med = float(np.median(m))
    return hot / max(med, 0.5)

def copy_move_score(path: str) -> tuple[float, int]:
    img = _load_bgr(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=2000)
    kp, desc = orb.detectAndCompute(gray, None)
    if desc is None or len(kp) < 20:
        return 0.0, 0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    knn = matcher.knnMatch(desc, desc, k=3)

    offsets = []
    for group in knn:
        for m in group[1:]:                       # skip self-match at index 0
            p1 = np.array(kp[m.queryIdx].pt)
            p2 = np.array(kp[m.trainIdx].pt)
            dist = np.linalg.norm(p1 - p2)
            if dist > 40 and m.distance < 40:     # far apart but visually identical
                offsets.append(tuple(np.round((p1 - p2) / 8).astype(int)))

    if not offsets:
        return 0.0, 0
    counts = {}
    for o in offsets:
        counts[o] = counts.get(o, 0) + 1
    best = max(counts.values())
    return best / max(len(kp), 1) * 100, best

def noise_spread(path: str) -> float:
    img = _load_bgr(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    th, tw = h // 6, w // 6
    variances = []
    for r in range(6):
        for c in range(6):
            tile = gray[r * th:(r + 1) * th, c * tw:(c + 1) * tw]
            if tile.size:
                variances.append(float(cv2.Laplacian(tile, cv2.CV_64F).var()))
    variances = [v for v in variances if v > 0]
    if len(variances) < 4:
        return 1.0
    return float(np.percentile(variances, 95)) / max(float(np.median(variances)), 0.5)

def run(path: str) -> list[Signal]:
    if not path or not os.path.exists(path) or path.lower().endswith(".pdf"):
        return [Signal(code="TAMPER_UNREADABLE", engine="tamper", severity="low",
                       message="No raster image available for pixel-level analysis.")]
    try:
        ela = ela_score(path)
        clone_pct, clone_matches = copy_move_score(path)
        spread = noise_spread(path)
    except Exception as e:
        return [Signal(code="TAMPER_UNREADABLE", engine="tamper", severity="low",
                       message=f"Image could not be analysed: {type(e).__name__}: {e}")]

    signals: list[Signal] = []

    if ela > ELA_SUSPICIOUS:
        signals.append(Signal(
            code="TAMPER_ELA_ANOMALY", engine="tamper", severity="high",
            message=(f"Error Level Analysis ratio is {ela:.1f} (threshold {ELA_SUSPICIOUS}). "
                     f"Part of this image has a different compression history from the rest, "
                     f"which is what splicing looks like."),
            evidence={"ela_ratio": round(ela, 2)},
        ))

    if clone_matches >= CLONE_MATCH_MIN:
        signals.append(Signal(
            code="TAMPER_COPY_MOVE", engine="tamper", severity="high",
            message=(f"{clone_matches} keypoints match another region of the same image "
                     f"at a consistent offset — a cloned or duplicated region."),
            evidence={"matches": clone_matches, "score": round(clone_pct, 2)},
        ))

    if spread > NOISE_SPREAD_MAX:
        signals.append(Signal(
            code="TAMPER_NOISE_INCONSISTENT", engine="tamper", severity="medium",
            message=(f"Sensor-noise variance differs {spread:.1f}x across the image. "
                     f"A single-capture photograph has near-uniform noise."),
            evidence={"noise_spread": round(spread, 2)},
        ))

    if not signals:
        signals.append(Signal(
            code="TAMPER_NONE_DETECTED", engine="tamper", severity="info",
            message=(f"No splicing, cloning or noise anomalies detected "
                     f"(ELA {ela:.1f}, clone matches {clone_matches}, noise {spread:.1f}x)."),
            evidence={"ela_ratio": round(ela, 2), "clone_matches": clone_matches,
                      "noise_spread": round(spread, 2)},
        ))
    return signals
