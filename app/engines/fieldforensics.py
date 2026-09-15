"""Per-field tamper localization: which field on this document was altered."""
import os
import re
import cv2
import numpy as np
from PIL import Image, ImageOps
from app.engines.tamper import ela_map
from app.models import Signal

Z_THRESHOLD = 3.5      # modified z-score above which a field is an outlier
MIN_REGIONS = 3        # fewer than this and "outlier" is meaningless
MIN_AREA = 200         # ignore specks
# Floor on the MAD as a fraction of the group median. A tight genuine group (q60 visa:
# MAD 0.035 on a median 0.73, 4.8%) otherwise turns a 0.16 wobble into z 3-4.6.
# Measured genuine MAD/median 2-15%; retyped fields sit 2x the median.
MAD_FLOOR_FRACTION = 0.08
BACKGROUND_SPLIT = 128 # median background luminance below this = light-on-dark element
BACKGROUND_RING = 8    # pixels around a box sampled as its background
BANNER_WIDTH_FRACTION = 0.8   # colour blobs this wide are banners, not stamps
STAMP_OVERLAP_MAX = 0.5       # stamp candidates overlapping a printed region more are dropped
STAMP_LETTERING_MIN = 0.5     # a text box this far inside a stamp is the stamp's lettering
# MRZ lines (ICAO OCR-B, '<' fillers) are a different printing element from the data
# fields: dense monospace glyphs on their own strip. On the genuine sample their ELA
# was 1.13-1.21 vs a data-field median of 0.60 (z 7-8), so they are compared only
# with each other (task-16b item 4). Their integrity is owned by the MRZ check digits.
_MRZ_TEXT = re.compile(r"^[A-Z0-9<]{20,}$")
# Portrait (task-16c). A detected face box covers only the face; the photograph around
# it (hair, backdrop) is often saturated enough to look like a "stamp" blob. Stamp
# candidates mostly inside this zone are part of the photograph.
PORTRAIT_ZONE_W = 1.6   # zone width  = face box width  x this
PORTRAIT_ZONE_H = 1.5   # zone height = face box height x this
# A photograph cannot be z-scored against text (different texture) and is alone in its
# peer group, so it is judged on luma ELA per unit of edge energy relative to the
# median of the dark-on-light text fields. Measured on synthetic renders: genuine
# portrait 1.3-2.5x the text median (q60-q95), a photo pasted in after issue 5.3-9.8x.
PORTRAIT_RATIO_MAX = 4.0
PORTRAIT_ELA_MIN = 0.5      # below this the probe quality matches the save: no evidence
TEXT_RATIO_FLOOR = 1e-3     # keeps a near-zero text median from inflating the ratio

def portrait_zone(face_box: tuple) -> tuple[int, int, int, int]:
    """The photograph around a detected face box (x, y, w, h)."""
    x, y, w, h = face_box
    zw, zh = w * PORTRAIT_ZONE_W, h * PORTRAIT_ZONE_H
    cx, cy = x + w / 2, y + h / 2
    return int(cx - zw / 2), int(cy - zh / 2), int(zw), int(zh)

def _is_mrz_text(text: str) -> bool:
    t = (text or "").upper().replace(" ", "")
    return "<" in t and bool(_MRZ_TEXT.match(t))

def _overlap_fraction(stamp: tuple, other: tuple) -> float:
    """Fraction of the stamp box's own area covered by the other box."""
    sx, sy, sw, sh = stamp
    ox, oy, ow, oh = other
    iw = min(sx + sw, ox + ow) - max(sx, ox)
    ih = min(sy + sh, oy + oh) - max(sy, oy)
    if iw <= 0 or ih <= 0 or sw * sh <= 0:
        return 0.0
    return (iw * ih) / (sw * sh)

def _clamp(box: tuple, w: int, h: int) -> tuple[int, int, int, int]:
    x, y, bw, bh = box
    return max(0, int(x)), max(0, int(y)), min(w, int(x + bw)), min(h, int(y + bh))

def region_scores(ela: np.ndarray, boxes: list[tuple]) -> list[float]:
    h, w = ela.shape[:2]
    out: list[float] = []
    for box in boxes:
        x0, y0, x1, y1 = _clamp(box, w, h)
        patch = ela[y0:y1, x0:x1]
        out.append(float(patch.mean()) if patch.size else 0.0)
    return out

def background_luminance(gray: np.ndarray, box: tuple) -> float:
    """Median luminance of a BACKGROUND_RING-pixel ring around the box, excluding
    the box itself - so an edit inside the field cannot change its own grouping.
    Falls back to the median inside the box when the ring is empty."""
    h, w = gray.shape[:2]
    x, y, bw, bh = box
    x0, y0, x1, y1 = _clamp((x - BACKGROUND_RING, y - BACKGROUND_RING,
                             bw + 2 * BACKGROUND_RING, bh + 2 * BACKGROUND_RING), w, h)
    window = gray[y0:y1, x0:x1]
    if not window.size:
        return 255.0
    mask = np.ones(window.shape[:2], bool)
    bx0, by0, bx1, by1 = _clamp(box, w, h)
    mask[max(0, by0 - y0):max(0, by1 - y0), max(0, bx0 - x0):max(0, bx1 - x0)] = False
    ring = window[mask]
    if ring.size:
        return float(np.median(ring))
    inside = gray[by0:by1, bx0:bx1]
    return float(np.median(inside)) if inside.size else 255.0

def region_backgrounds(path: str, boxes: list[tuple]) -> list[float]:
    """Background luminance around each box (see background_luminance)."""
    with Image.open(path) as im:
        gray = np.asarray(ImageOps.exif_transpose(im).convert("L"))
    return [background_luminance(gray, box) for box in boxes]

def outlier_indices(values: list[float], z_threshold: float = Z_THRESHOLD) -> list[int]:
    if len(values) < MIN_REGIONS:
        return []
    arr = np.asarray(values, dtype=np.float64)
    median = float(np.median(arr))
    mad = max(float(np.median(np.abs(arr - median))), MAD_FLOOR_FRACTION * abs(median))
    if mad < 1e-6:
        spread = float(arr.std())
        if spread < 1e-6:
            return []
        z = (arr - median) / spread
    else:
        z = 0.6745 * (arr - median) / mad
    return [i for i in range(len(arr)) if z[i] > z_threshold]

def stamp_regions(path: str) -> list[tuple]:
    """Saturated colour blobs - visa stamps, seals and inked impressions."""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return []
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 90, 40), (179, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_w = img.shape[1]
    out = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w >= BANNER_WIDTH_FRACTION * img_w:
            continue   # a full-width banner or strip, not a stamp
        if w * h >= MIN_AREA * 4 and 0.2 <= w / max(h, 1) <= 6.0:
            out.append((x, y, w, h))
    return sorted(out, key=lambda b: b[2] * b[3], reverse=True)[:6]

def run(path: str, ocr_boxes: list[dict],
        portrait_box: tuple | None = None) -> tuple[list[Signal], list[dict]]:
    if not path or not os.path.exists(path):
        return ([Signal(code="FF_UNREADABLE", engine="fieldforensics", severity="low",
                        message="No document image available for field-level analysis.")], [])

    regions: list[dict] = []
    for b in ocr_boxes or []:
        try:
            x, y, w, h = b["box"]
            text = str(b.get("text", ""))
            label = text[:32]
        except (KeyError, TypeError, ValueError, AttributeError):
            continue   # malformed box: skip it rather than break the engine
        if w * h >= MIN_AREA:
            regions.append({"box": (x, y, w, h), "label": label,
                            "kind": "mrz" if _is_mrz_text(text) else "text",
                            "suspect": False, "score": 0.0})
    if portrait_box and portrait_box[2] * portrait_box[3] >= MIN_AREA:
        regions.append({"box": tuple(portrait_box), "label": "PHOTOGRAPH",
                        "kind": "portrait", "suspect": False, "score": 0.0})

    try:
        printed = [r["box"] for r in regions if r["kind"] != "portrait"]
        if portrait_box and portrait_box[2] * portrait_box[3] >= MIN_AREA:
            printed.append(portrait_zone(portrait_box))
        for sb in stamp_regions(path):
            if any(_overlap_fraction(sb, pb) > STAMP_OVERLAP_MAX for pb in printed):
                continue   # already represented by a text/portrait region
            # A stamp's own lettering (OCR box inside the stamp) is part of the stamp.
            # The stamp is judged on its lettering - text measured exactly like every
            # other text field - rather than on its bounding box, which is mostly
            # blank paper (forged sample: bbox 1.05, lettering 2.42, fields ~0.8).
            # It is still drawn as the whole stamp.
            lettering = [r for r in regions if r["kind"] == "text"
                         and _overlap_fraction(r["box"], sb) >= STAMP_LETTERING_MIN]
            for r in lettering:
                regions.remove(r)
            label = "STAMP"
            if lettering:
                label = f"STAMP {' '.join(r['label'] for r in lettering)}"[:32]
            regions.append({"box": sb, "label": label, "kind": "stamp",
                            "suspect": False, "score": 0.0,
                            "score_boxes": [r["box"] for r in lettering] or [sb]})
    except Exception:
        pass   # stamps are a bonus; never let them break the engine

    if len(regions) < MIN_REGIONS:
        return ([Signal(
            code="FF_NO_REGIONS", engine="fieldforensics", severity="low",
            message=(f"Only {len(regions)} analysable region(s) found; field-level "
                     f"comparison needs at least {MIN_REGIONS}."))], [])

    try:
        ela = ela_map(path, channel="luma")
        with Image.open(path) as im:
            gray = np.asarray(ImageOps.exif_transpose(im).convert("L"))
        grad = (np.abs(cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 1, 0))
                + np.abs(cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 0, 1)))
        scores, backgrounds = [], []
        for r in regions:
            sboxes = r.get("score_boxes") or [r["box"]]
            areas = [max(1, b[2] * b[3]) for b in sboxes]
            vals = region_scores(ela, sboxes)
            scores.append(sum(v * a for v, a in zip(vals, areas)) / sum(areas))
            backgrounds.append(float(np.median([background_luminance(gray, b) for b in sboxes])))
    except Exception as e:
        return ([Signal(code="FF_UNREADABLE", engine="fieldforensics", severity="low",
                        message=f"Field analysis failed: {type(e).__name__}: {e}")], [])

    for r, sc in zip(regions, scores):
        r["score"] = round(float(sc), 2)
        r.pop("score_boxes", None)

    # Compare like with like: light-on-dark elements (header banners) only against
    # each other, dark-on-light data fields only against each other.
    # MRZ lines form their own group (see _MRZ_TEXT).
    groups: dict[str, list[int]] = {}
    for i, bg in enumerate(backgrounds):
        if regions[i]["kind"] == "portrait":
            continue   # judged separately below: a photo is not text
        shade = "dark" if bg < BACKGROUND_SPLIT else "light"
        name = f"MRZ {shade}" if regions[i]["kind"] == "mrz" else shade
        groups.setdefault(name, []).append(i)

    group_median: dict[int, float] = {}
    bad: list[int] = []
    skipped: list[str] = []
    for name, idx in groups.items():
        if not idx:
            continue
        if len(idx) < MIN_REGIONS:
            skipped.append(f"{len(idx)} on a {name} background")
            continue
        vals = [scores[i] for i in idx]
        med = float(np.median(vals))
        for i in idx:
            group_median[i] = med
        bad.extend(idx[j] for j in outlier_indices(vals))
    portrait_ratio: dict[int, float] = {}
    text_idx = [i for i in groups.get("light", []) if regions[i]["kind"] == "text"]
    for i, r in enumerate(regions):
        if r["kind"] != "portrait" or len(text_idx) < MIN_REGIONS:
            continue
        ratio = lambda b: region_scores(ela, [b])[0] / max(region_scores(grad, [b])[0], 1e-6)
        text_med = max(float(np.median([ratio(regions[j]["box"]) for j in text_idx])),
                       TEXT_RATIO_FLOOR)
        rel = ratio(r["box"]) / text_med
        portrait_ratio[i] = round(rel, 2)
        group_median[i] = float(np.median([scores[j] for j in text_idx]))
        if scores[i] >= PORTRAIT_ELA_MIN and rel > PORTRAIT_RATIO_MAX:
            bad.append(i)
    bad.sort()
    for i in bad:
        regions[i]["suspect"] = True

    signals: list[Signal] = []

    for i in bad:
        r = regions[i]
        median = group_median[i]
        basis = (f"against a median of {median:.2f} for the other regions on a similar "
                 f"background")
        if r["kind"] == "portrait":
            rel = portrait_ratio[i]
            signals.append(Signal(
                code="FF_PHOTO_TAMPERED", engine="fieldforensics", severity="high",
                message=(f"The photograph carries {rel}x the compression residual per "
                         f"unit of detail of the printed text fields (genuine photos "
                         f"measure under {PORTRAIT_RATIO_MAX}x). The portrait was "
                         f"pasted in after the document was produced."),
                evidence={"box": list(r["box"]), "score": r["score"],
                          "relative_residual": rel, "threshold": PORTRAIT_RATIO_MAX,
                          "document_median": round(median, 2)}))
        elif r["kind"] == "stamp":
            signals.append(Signal(
                code="FF_STAMP_TAMPERED", engine="fieldforensics", severity="high",
                message=(f"A stamp or seal region has a compression residual of "
                         f"{r['score']} {basis}. "
                         f"The stamp was added or altered after issue."),
                evidence={"box": list(r["box"]), "score": r["score"],
                          "document_median": round(median, 2)}))
        else:
            signals.append(Signal(
                code="FF_FIELD_TAMPERED", engine="fieldforensics", severity="high",
                message=(f"The field reading {r['label']!r} has a compression residual of "
                         f"{r['score']} {basis} - it was "
                         f"edited after the rest of the document was produced."),
                evidence={"field_text": r["label"], "box": list(r["box"]),
                          "score": r["score"], "document_median": round(median, 2)}))

    if not signals:
        median = float(np.median(scores))
        skip_note = (f" Background group(s) too small to compare were skipped "
                     f"({'; '.join(skipped)} region(s))." if skipped else "")
        signals.append(Signal(
            code="FF_ALL_FIELDS_CONSISTENT", engine="fieldforensics", severity="info",
            message=(f"{len(regions)} regions analysed; fields on a similar background share "
                     f"a consistent compression history (median residual {median:.2f}). "
                     f"No single field stands out as edited.{skip_note}"),
            evidence={"regions_analysed": len(regions), "groups_skipped": skipped,
                      "document_median": round(median, 2)}))
    return signals, regions
