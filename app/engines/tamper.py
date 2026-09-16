"""Pixel-level tamper heuristics: ELA, copy-move cloning, noise inconsistency."""
import os
import tempfile
import cv2
import numpy as np
from PIL import Image, ImageOps
from app.models import Signal

# Calibration (task-16b, numbers in README "Calibration"). Every check compares like
# with like, because a document is hard-edged text on flat paper - not a photograph.
ELA_BLOCK = 16            # px; ELA is judged per block, never over flat paper
ELA_TEXTURE_MIN = 20.0    # mean edge energy for a block to count as textured
ELA_RATIO_FLOOR = 0.005   # residual-per-edge floor; idempotent re-saves have median 0
ELA_SUSPICIOUS = 8.0      # block residual-per-edge vs document median (clean max 6.5)
ELA_MIN_BLOCKS = 2        # a splice is a contiguous area, not one 16px block
CLONE_MATCH_MIN = 12      # self-matches with one consistent offset, in one compact area
# An axis-aligned offset (dx=0 or dy=0) is both the PS's own attack (a stamp
# cloned straight across or down) AND the shape typeset repeats coincidentally
# fall into at low counts (measured on clean genuine renders: up to 14 matches
# in one 2D-spread cluster at an exact axis offset). A real clone at that same
# axis, measured on a synthetic pasted patch, produces far more (31). The
# higher floor only applies on this axis; a diagonal offset uses CLONE_MATCH_MIN.
CLONE_MATCH_MIN_AXIS = 20
CLONE_AXIS_TOL = 1        # rounded offset units (d/8); 0-1 counts as "on the axis"
CLONE_WINDOW = 96         # px; a cloned region's matches sit within one window
CLONE_MIN_EXTENT = 24     # px; ...and span 2D, not one text line or one column
NOISE_EDGE = 100.0        # blurred edge energy above which a pixel is print, not noise
NOISE_SMOOTH_FRACTION = 0.6   # tiles with less smooth area are text-dominated: skipped
NOISE_FLOOR = 0.5         # grey levels; below this sigma is JPEG quantisation, not sensor
NOISE_SPREAD_MAX = 3.0    # loudest vs median smooth-area noise (clean max 1.2)

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
        original = ImageOps.exif_transpose(im).convert("RGB")
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

def _gray(path: str) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(ImageOps.exif_transpose(im).convert("L"), np.float32)

def _block_means(a: np.ndarray, b: int) -> np.ndarray:
    h, w = a.shape[0] - a.shape[0] % b, a.shape[1] - a.shape[1] % b
    return a[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3))

def ela_block_ratios(path: str) -> np.ndarray:
    """Per-block luma ELA residual per unit of edge energy, relative to the document.

    Whole-image p99/median ELA is meaningless on a document: the median is flat
    paper (residual ~0) and the p99 is text edges, so every page "looks spliced"
    (rendered genuine passport: 8.0). Here each 16px block's residual is divided
    by its own edge energy - a hard glyph edge and a hard pasted edge are then
    compared on equal terms - and only textured blocks are judged. Returns a
    block grid of ratio / document median (0 for flat blocks).
    """
    ela = ela_map(path, channel="luma")
    g = _gray(path)
    grad = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1))
    e, gr = _block_means(ela, ELA_BLOCK), _block_means(grad, ELA_BLOCK)
    textured = gr > ELA_TEXTURE_MIN
    if textured.sum() < 4:
        return np.zeros_like(e)
    ratio = np.where(textured, e / np.maximum(gr, 1e-6), 0.0)
    base = max(float(np.median(ratio[textured])), ELA_RATIO_FLOOR)
    return ratio / base

def ela_anomaly(path: str) -> tuple[float, int]:
    """(peak block ratio, blocks in the largest contiguous suspicious area)."""
    k = ela_block_ratios(path)
    if not k.size:
        return 0.0, 0
    mask = (k > ELA_SUSPICIOUS).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    largest = int(stats[1:, cv2.CC_STAT_AREA].max()) if n > 1 else 0
    return float(k.max()), largest

def ela_score(path: str) -> float:
    return ela_anomaly(path)[0]

def copy_move_score(path: str) -> tuple[float, int]:
    """Largest group of self-matches sharing one offset AND one compact 2D area.

    On a typeset page ORB self-matches are repeated glyphs and aligned fields:
    their offsets lie on a row or column (measured on the genuine samples: every
    top group had dx=0 or dy=0, 15-25 matches spread across whole text lines).
    A cloned region moves a block of pixels, so its matches share an offset and
    cluster in one window spanning both axes.
    """
    img = _load_bgr(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=2000)
    kp, desc = orb.detectAndCompute(gray, None)
    if desc is None or len(kp) < 20:
        return 0.0, 0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    knn = matcher.knnMatch(desc, desc, k=3)

    groups: dict[tuple, list] = {}
    for group in knn:
        for m in group[1:]:                       # skip self-match at index 0
            p1 = np.array(kp[m.queryIdx].pt)
            p2 = np.array(kp[m.trainIdx].pt)
            d = p1 - p2
            if np.linalg.norm(d) <= 40 or m.distance >= 40:
                continue                          # near itself, or not visually identical
            # checkpoint-4 R3: the axis test used to run per-pair, on the offset
            # alone, which drops the PS's own attack - a stamp cloned straight
            # across or down. It is applied below, per candidate cluster,
            # against the matched keypoints' own spread instead - a text row
            # is thin across its line even though it runs the length of the
            # line; a pasted stamp is compact in both directions.
            groups.setdefault(tuple(np.round(d / 8).astype(int)), []).append(p2)

    best = 0
    half = CLONE_WINDOW / 2
    for d_key, pts in groups.items():
        floor = (CLONE_MATCH_MIN_AXIS if min(abs(d_key[0]), abs(d_key[1])) <= CLONE_AXIS_TOL
                 else CLONE_MATCH_MIN)
        if len(pts) < floor:
            continue
        arr = np.asarray(pts)
        for c in arr:
            sel = arr[(np.abs(arr[:, 0] - c[0]) <= half) & (np.abs(arr[:, 1] - c[1]) <= half)]
            if len(sel) <= best or len(sel) < floor:
                continue
            # A 2D-compact cluster (both extents wide) is never a typeset row or
            # column - a text line runs long but sits in a narrow band across
            # it, so it fails this test regardless of its offset's axis. A
            # pasted region, even at a pure vertical/horizontal offset, passes.
            if np.ptp(sel[:, 0]) < CLONE_MIN_EXTENT or np.ptp(sel[:, 1]) < CLONE_MIN_EXTENT:
                continue
            best = len(sel)
    return best / max(len(kp), 1) * 100, best

def noise_spread(path: str) -> float:
    """Loudest vs median noise level, measured only on the smooth area of each tile.

    Laplacian variance per tile measured print, not noise: text tiles against
    blank paper gave 12.6 on the genuine passport. Here print edges (found on a
    blurred copy, so pixel noise itself is not mistaken for an edge) are masked
    out, text-dominated tiles are skipped, and noise is a robust (MAD) sigma of
    the high-pass residual - smooth area compared with smooth area.
    """
    img = _load_bgr(path)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    residual = g - cv2.GaussianBlur(g, (5, 5), 0)
    gb = cv2.GaussianBlur(g, (5, 5), 0)
    edges = (np.abs(cv2.Sobel(gb, cv2.CV_32F, 1, 0))
             + np.abs(cv2.Sobel(gb, cv2.CV_32F, 0, 1))) > NOISE_EDGE
    edges = cv2.dilate(edges.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    h, w = g.shape
    th, tw = h // 6, w // 6
    sigmas = []
    for r in range(6):
        for c in range(6):
            sl = (slice(r * th, (r + 1) * th), slice(c * tw, (c + 1) * tw))
            smooth = ~edges[sl]
            if not smooth.size or smooth.mean() < NOISE_SMOOTH_FRACTION:
                continue
            v = residual[sl][smooth]
            sigmas.append(1.4826 * float(np.median(np.abs(v - np.median(v)))))
    if len(sigmas) < 4:
        return 1.0
    return float(np.percentile(sigmas, 95)) / max(float(np.median(sigmas)), NOISE_FLOOR)

def run(path: str) -> list[Signal]:
    if not path or not os.path.exists(path) or path.lower().endswith(".pdf"):
        return [Signal(code="TAMPER_UNREADABLE", engine="tamper", severity="low",
                       message="No raster image available for pixel-level analysis.",
                       plain="No image was available for the whole-page tampering check.")]
    try:
        ela, ela_blocks = ela_anomaly(path)
        clone_pct, clone_matches = copy_move_score(path)
        spread = noise_spread(path)
    except Exception as e:
        return [Signal(code="TAMPER_UNREADABLE", engine="tamper", severity="low",
                       message=f"Image could not be analysed: {type(e).__name__}: {e}",
                       plain="The whole-page tampering check could not run on this file.")]

    signals: list[Signal] = []

    if ela_blocks >= ELA_MIN_BLOCKS:
        signals.append(Signal(
            code="TAMPER_ELA_ANOMALY", engine="tamper", severity="high",
            message=(f"Error Level Analysis: an area of {ela_blocks} image blocks re-compresses "
                     f"up to {ela:.1f}x worse, per unit of edge detail, than the rest of the "
                     f"document (threshold {ELA_SUSPICIOUS}). That area has a different "
                     f"compression history, which is what splicing looks like."),
            plain="Part of this image has been pasted in from somewhere else. "
                  "That area's compression history does not match the rest "
                  "of the page.",
            evidence={"ela_ratio": round(ela, 2), "ela_blocks": ela_blocks},
        ))

    if clone_matches >= CLONE_MATCH_MIN:
        signals.append(Signal(
            code="TAMPER_COPY_MOVE", engine="tamper", severity="high",
            message=(f"{clone_matches} keypoints match another region of the same image "
                     f"at one consistent offset within one compact area - a cloned or duplicated region."),
            plain="Part of this image was copied from another part of the same "
                  "image, likely to hide or duplicate something.",
            evidence={"matches": clone_matches, "score": round(clone_pct, 2)},
        ))

    if spread > NOISE_SPREAD_MAX:
        signals.append(Signal(
            code="TAMPER_NOISE_INCONSISTENT", engine="tamper", severity="medium",
            message=(f"Noise level in smooth areas differs {spread:.1f}x across the image "
                     f"(threshold {NOISE_SPREAD_MAX}). A single capture or print has near-"
                     f"uniform noise; a pasted-in photograph carries its own."),
            plain="Different parts of this image have different grain or noise, "
                  "which is what happens when a photo from another source is "
                  "pasted in.",
            evidence={"noise_spread": round(spread, 2)},
        ))

    if not signals:
        signals.append(Signal(
            code="TAMPER_NONE_DETECTED", engine="tamper", severity="info",
            message=(f"No splicing, cloning or noise anomalies detected "
                     f"(ELA {ela:.1f}, clone matches {clone_matches}, noise {spread:.1f}x)."),
            plain="No signs of pasting, copying or mismatched image noise "
                  "were found on this page.",
            evidence={"ela_ratio": round(ela, 2), "clone_matches": clone_matches,
                      "noise_spread": round(spread, 2)},
        ))
    return signals
