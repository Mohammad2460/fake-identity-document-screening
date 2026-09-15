"""Per-field tamper localization: which field on this document was altered."""
import os
import cv2
import numpy as np
from app.engines.tamper import ela_map
from app.models import Signal

Z_THRESHOLD = 3.5      # modified z-score above which a field is an outlier
MIN_REGIONS = 3        # fewer than this and "outlier" is meaningless
MIN_AREA = 200         # ignore specks

def region_scores(ela: np.ndarray, boxes: list[tuple]) -> list[float]:
    h, w = ela.shape[:2]
    out: list[float] = []
    for (x, y, bw, bh) in boxes:
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(w, int(x + bw)), min(h, int(y + bh))
        patch = ela[y0:y1, x0:x1]
        out.append(float(patch.mean()) if patch.size else 0.0)
    return out

def outlier_indices(values: list[float], z_threshold: float = Z_THRESHOLD) -> list[int]:
    if len(values) < MIN_REGIONS:
        return []
    arr = np.asarray(values, dtype=np.float64)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
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
    out = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
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
            label = str(b.get("text", ""))[:32]
        except (KeyError, TypeError, ValueError, AttributeError):
            continue   # malformed box: skip it rather than break the engine
        if w * h >= MIN_AREA:
            regions.append({"box": (x, y, w, h), "label": label,
                            "kind": "text", "suspect": False, "score": 0.0})
    if portrait_box:
        regions.append({"box": tuple(portrait_box), "label": "PHOTOGRAPH",
                        "kind": "portrait", "suspect": False, "score": 0.0})

    try:
        for sb in stamp_regions(path):
            regions.append({"box": sb, "label": "STAMP", "kind": "stamp",
                            "suspect": False, "score": 0.0})
    except Exception:
        pass   # stamps are a bonus; never let them break the engine

    if len(regions) < MIN_REGIONS:
        return ([Signal(
            code="FF_NO_REGIONS", engine="fieldforensics", severity="low",
            message=(f"Only {len(regions)} analysable region(s) found; field-level "
                     f"comparison needs at least {MIN_REGIONS}."))], [])

    try:
        ela = ela_map(path)
        scores = region_scores(ela, [r["box"] for r in regions])
    except Exception as e:
        return ([Signal(code="FF_UNREADABLE", engine="fieldforensics", severity="low",
                        message=f"Field analysis failed: {type(e).__name__}: {e}")], [])

    for r, sc in zip(regions, scores):
        r["score"] = round(float(sc), 2)

    bad = outlier_indices(scores)
    for i in bad:
        regions[i]["suspect"] = True

    signals: list[Signal] = []
    median = float(np.median(scores))

    for i in bad:
        r = regions[i]
        if r["kind"] == "portrait":
            signals.append(Signal(
                code="FF_PHOTO_TAMPERED", engine="fieldforensics", severity="high",
                message=(f"The photograph region has a compression residual of "
                         f"{r['score']} against a document median of {median:.2f}. "
                         f"The portrait was pasted in after the document was produced."),
                evidence={"box": list(r["box"]), "score": r["score"],
                          "document_median": round(median, 2)}))
        elif r["kind"] == "stamp":
            signals.append(Signal(
                code="FF_STAMP_TAMPERED", engine="fieldforensics", severity="high",
                message=(f"A stamp or seal region has a compression residual of "
                         f"{r['score']} against a document median of {median:.2f}. "
                         f"The stamp was added or altered after issue."),
                evidence={"box": list(r["box"]), "score": r["score"],
                          "document_median": round(median, 2)}))
        else:
            signals.append(Signal(
                code="FF_FIELD_TAMPERED", engine="fieldforensics", severity="high",
                message=(f"The field reading {r['label']!r} has a compression residual of "
                         f"{r['score']} against a document median of {median:.2f} - it was "
                         f"edited after the rest of the document was produced."),
                evidence={"field_text": r["label"], "box": list(r["box"]),
                          "score": r["score"], "document_median": round(median, 2)}))

    if not signals:
        signals.append(Signal(
            code="FF_ALL_FIELDS_CONSISTENT", engine="fieldforensics", severity="info",
            message=(f"All {len(regions)} analysed regions share a consistent compression "
                     f"history (median residual {median:.2f}). No single field stands out "
                     f"as edited."),
            evidence={"regions_analysed": len(regions),
                      "document_median": round(median, 2)}))
    return signals, regions
