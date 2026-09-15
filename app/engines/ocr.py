"""OCR extraction with geometry, and cross-validation of printed vs claimed fields."""
import functools
import os
import re
from datetime import datetime
from rapidfuzz import fuzz
from app.models import Signal

DOB_INPUT_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")
MONTH_ABBR = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
              "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

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
        box = _poly_to_box(poly)
        if box[2] <= 0 or box[3] <= 0:
            continue
        out.append({"text": text, "confidence": float(score), "box": box})
    return out

def name_match_score(name: str, blob: str) -> float:
    """Weakest-token match of a claimed name against the OCR text blob.

    Every claimed name token of length >= 3 must score >= NAME_MATCH_THRESHOLD
    (we use the min, not the max, so one matching token can't hide the rest of
    a stolen document's name). If no token is long enough to score on its own
    (e.g. "LI WU"), compare the whole normalised name against the blob instead
    of defaulting to 0.
    """
    tokens = [part.upper() for part in name.split() if len(part) >= 3]
    if not tokens:
        whole = " ".join(name.upper().split())
        return float(fuzz.partial_ratio(whole, blob)) if whole else 0.0
    return float(min(fuzz.partial_ratio(part, blob) for part in tokens))

def dob_candidates(claimed_dob: str) -> list[str]:
    """Printed forms a genuine passport might use for this date of birth.

    Tries "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y" in turn; returns [] if none parse
    (the identity engine already flags an unparseable claimed DOB).
    """
    parsed = None
    for fmt in DOB_INPUT_FORMATS:
        try:
            parsed = datetime.strptime(claimed_dob, fmt)
            break
        except (ValueError, TypeError):
            continue
    if parsed is None:
        return []
    month = MONTH_ABBR[parsed.month - 1]
    return [
        parsed.strftime("%Y%m%d"),
        parsed.strftime("%d%m%Y"),
        parsed.strftime("%m%d%Y"),
        parsed.strftime("%y%m%d"),
        f"{parsed.day:02d}{month}{parsed.year}",
        f"{parsed.day:02d}{month}{parsed.strftime('%y')}",
    ]

def dob_on_document(claimed_dob: str, flat_blob: str) -> bool:
    """True if any candidate printed form of claimed_dob is a substring of the
    flattened alphanumeric-uppercase OCR blob."""
    return any(c in flat_blob for c in dob_candidates(claimed_dob))

_OCR_CONFUSION = str.maketrans({"O": "0", "I": "1"})

def _normalize_number(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", value.upper())
    return cleaned.translate(_OCR_CONFUSION)

def number_on_document(claimed_number: str, flat_blob: str) -> bool:
    """Exact substring match of the claimed document number against the
    flattened OCR blob, both sides normalised for common OCR confusions
    (O<->0, I<->1)."""
    needle = _normalize_number(claimed_number)
    haystack = _normalize_number(flat_blob)
    return bool(needle) and needle in haystack

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
        best = name_match_score(name, blob)
        if best < NAME_MATCH_THRESHOLD:
            tokens = [part.upper() for part in name.split() if len(part) >= 3]
            if tokens:
                weakest = min(tokens, key=lambda t: fuzz.partial_ratio(t, blob))
            else:
                weakest = " ".join(name.upper().split())
            signals.append(Signal(
                code="OCR_NAME_NOT_ON_DOCUMENT", engine="ocr", severity="high",
                message=(f"The claimed name {name!r} does not appear in the text printed "
                         f"on the uploaded document (weakest-matching part {weakest!r}, "
                         f"{best:.0f}% match). The applicant may be presenting another "
                         f"person's document."),
                evidence={"claimed_name": name, "best_match_pct": round(best, 1),
                          "weakest_token": weakest},
            ))
        else:
            signals.append(Signal(
                code="OCR_NAME_CONFIRMED", engine="ocr", severity="info",
                message=f"Claimed name is printed on the document ({best:.0f}% match)."))

    if avg_conf >= MIN_CONFIDENCE_TO_JUDGE:
        flat = re.sub(r"[\s\-/]", "", blob)

        dob = (claimed.get("dob") or "").strip()
        if dob and dob_candidates(dob) and not dob_on_document(dob, flat):
            signals.append(Signal(
                code="OCR_DOB_NOT_ON_DOCUMENT", engine="ocr", severity="medium",
                message="The claimed date of birth is not printed on the uploaded document.",
                evidence={"dob": dob},
            ))

        value = re.sub(r"[\s\-/]", "", (claimed.get("passport_no") or "")).upper()
        if value and len(value) >= 6 and not number_on_document(value, flat):
            signals.append(Signal(
                code="OCR_NUMBER_NOT_ON_DOCUMENT", engine="ocr", severity="medium",
                message="The claimed passport number is not printed on the uploaded document.",
                evidence={"passport_no": value},
            ))

    if mrz_lines:
        signals.append(Signal(
            code="OCR_MRZ_FOUND", engine="ocr", severity="info",
            message=f"Located {len(mrz_lines)} machine-readable zone line(s); "
                    f"passed to MRZ validation.",
            evidence={"lines": mrz_lines}))

    return signals, mrz_lines, boxes
