"""OCR extraction with geometry, and cross-validation of printed vs claimed fields."""
import functools
import os
import re
from rapidfuzz import fuzz
from app.models import Signal

MRZ_RE = re.compile(r"^[A-Z0-9<]{25,}$")
NAME_MATCH_THRESHOLD = 80
MIN_CONFIDENCE_TO_JUDGE = 0.45   # below this, a miss is illegible text, not fraud

@functools.lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()

def _poly_to_box(poly) -> tuple[int, int, int, int]:
    xs = [float(pt[0]) for pt in poly]
    ys = [float(pt[1]) for pt in poly]
    x, y = int(min(xs)), int(min(ys))
    return x, y, int(max(xs)) - x, int(max(ys)) - y

def extract_boxes(path: str) -> list[dict]:
    result, _ = _engine()(path)
    if not result:
        return []
    out = []
    for item in result:
        poly, text, score = item[0], item[1], item[2]
        out.append({"text": text, "confidence": float(score), "box": _poly_to_box(poly)})
    return out

def find_mrz_lines(lines: list[str]) -> list[str]:
    candidates = [ln.strip().upper().replace(" ", "") for ln in lines if ln and "<" in ln]
    return [ln for ln in candidates if MRZ_RE.match(ln)]

def run(path: str, claimed: dict) -> tuple[list[Signal], list[str], list[dict]]:
    if not path or not os.path.exists(path):
        return ([Signal(code="OCR_UNREADABLE", engine="ocr", severity="low",
                        message="No document image available for text extraction.")], [], [])
    try:
        boxes = extract_boxes(path)
    except Exception as e:
        return ([Signal(code="OCR_UNREADABLE", engine="ocr", severity="low",
                        message=f"OCR failed: {type(e).__name__}: {e}")], [], [])

    if not boxes:
        return ([Signal(code="OCR_NO_TEXT_FOUND", engine="ocr", severity="medium",
                        message="No readable text found on the document. Genuine travel "
                                "documents always carry printed text.")], [], [])

    texts = [b["text"] for b in boxes]
    mrz_lines = find_mrz_lines(texts)
    blob = " ".join(texts).upper()
    avg_conf = sum(b["confidence"] for b in boxes) / len(boxes)
    signals: list[Signal] = []

    if avg_conf < 0.55:
        signals.append(Signal(
            code="OCR_LOW_CONFIDENCE", engine="ocr", severity="low",
            message=f"Average OCR confidence is {avg_conf:.0%}; the document is blurred, "
                    f"low resolution, or a photograph of a screen.",
            evidence={"avg_confidence": round(avg_conf, 3)},
        ))

    name = (claimed.get("full_name") or "").strip()
    if name and avg_conf >= MIN_CONFIDENCE_TO_JUDGE:
        best = max((fuzz.partial_ratio(part.upper(), blob)
                    for part in name.split() if len(part) > 2), default=0)
        if best < NAME_MATCH_THRESHOLD:
            signals.append(Signal(
                code="OCR_NAME_NOT_ON_DOCUMENT", engine="ocr", severity="high",
                message=(f"The claimed name {name!r} does not appear in the text printed "
                         f"on the uploaded document (best match {best:.0f}%). The applicant "
                         f"may be presenting another person's document."),
                evidence={"claimed_name": name, "best_match_pct": round(best, 1)},
            ))
        else:
            signals.append(Signal(
                code="OCR_NAME_CONFIRMED", engine="ocr", severity="info",
                message=f"Claimed name is printed on the document ({best:.0f}% match)."))

    if avg_conf >= MIN_CONFIDENCE_TO_JUDGE:
        flat = re.sub(r"[\s\-/]", "", blob)
        for field, code, label in (("dob", "OCR_DOB_NOT_ON_DOCUMENT", "date of birth"),
                                   ("passport_no", "OCR_NUMBER_NOT_ON_DOCUMENT",
                                    "passport number")):
            value = re.sub(r"[\s\-/]", "", (claimed.get(field) or "")).upper()
            if value and len(value) >= 6 and fuzz.partial_ratio(value, flat) < 80:
                signals.append(Signal(
                    code=code, engine="ocr", severity="medium",
                    message=f"The claimed {label} is not printed on the uploaded document.",
                    evidence={field: value},
                ))

    if mrz_lines:
        signals.append(Signal(
            code="OCR_MRZ_FOUND", engine="ocr", severity="info",
            message=f"Located {len(mrz_lines)} machine-readable zone line(s); "
                    f"passed to MRZ validation.",
            evidence={"lines": mrz_lines}))

    return signals, mrz_lines, boxes
