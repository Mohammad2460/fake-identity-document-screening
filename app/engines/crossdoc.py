"""Compares identity fields across passport, visa, claim and prior submissions."""
import re
from datetime import datetime
from itertools import combinations
from rapidfuzz import fuzz
from app.models import Signal

NAME_AGREE = 85

_DOB_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def _norm(v) -> str:
    if v is None:
        return ""
    return re.sub(r"[\s<\-/]", "", str(v).upper())


def _norm_dob(v) -> str | None:
    """Normalise a dob to canonical YYMMDD, or None if missing/unparseable."""
    if not v:
        return None
    v = str(v).strip()
    if re.fullmatch(r"\d{6}", v):
        return v
    for fmt in _DOB_FORMATS:
        try:
            return datetime.strptime(v, fmt).strftime("%y%m%d")
        except ValueError:
            continue
    return None


def _names_agree(a: str, b: str) -> bool:
    return fuzz.token_sort_ratio(a.upper(), b.upper()) >= NAME_AGREE


_FIELDS = [
    ("passport_no", "XDOC_PASSPORT_NO_MISMATCH", "passport number", "critical",
     "The passport number is different on the two documents."),
    ("nationality", "XDOC_NATIONALITY_MISMATCH", "nationality", "high",
     "The nationality is different on the two documents."),
]


def run(sources: list[dict]) -> list[Signal]:
    usable = [src for src in sources if src]
    if len(usable) < 2:
        return []

    signals: list[Signal] = []
    seen: set[tuple] = set()

    for a, b in combinations(usable, 2):
        for key, code, label, severity, plain in _FIELDS:
            va, vb = _norm(a.get(key)), _norm(b.get(key))
            if va and vb and va != vb and (code, key) not in seen:
                seen.add((code, key))
                signals.append(Signal(
                    code=code, engine="crossdoc", severity=severity,
                    message=(f"The {label} disagrees between documents: "
                             f"{a.get('source', 'unknown source')} says {a.get(key)!r}, "
                             f"{b.get('source', 'unknown source')} says {b.get(key)!r}."),
                    plain=plain,
                    evidence={a.get("source", "unknown source"): a.get(key), b.get("source", "unknown source"): b.get(key)},
                ))

        dob_a, dob_b = _norm_dob(a.get("dob")), _norm_dob(b.get("dob"))
        if dob_a and dob_b and dob_a != dob_b and ("XDOC_DOB_MISMATCH", "dob") not in seen:
            seen.add(("XDOC_DOB_MISMATCH", "dob"))
            signals.append(Signal(
                code="XDOC_DOB_MISMATCH", engine="crossdoc", severity="high",
                message=(f"The date of birth disagrees between documents: "
                         f"{a.get('source', 'unknown source')} says {a.get('dob')!r}, "
                         f"{b.get('source', 'unknown source')} says {b.get('dob')!r}."),
                plain="The date of birth is different on the two documents.",
                evidence={a.get("source", "unknown source"): a.get("dob"), b.get("source", "unknown source"): b.get("dob")},
            ))

        na, nb = str(a.get("full_name") or "").strip(), str(b.get("full_name") or "").strip()
        if na and nb and not _names_agree(na, nb) and ("XDOC_NAME_MISMATCH",) not in seen:
            seen.add(("XDOC_NAME_MISMATCH",))
            signals.append(Signal(
                code="XDOC_NAME_MISMATCH", engine="crossdoc", severity="high",
                message=(f"The holder's name disagrees between documents: "
                         f"{a.get('source', 'unknown source')} says {na!r}, {b.get('source', 'unknown source')} says {nb!r}."),
                plain=f"The name is different on the two documents: {na} vs {nb}.",
                evidence={a.get("source", "unknown source"): na, b.get("source", "unknown source"): nb},
            ))

    if not signals:
        signals.append(Signal(
            code="XDOC_CONSISTENT", engine="crossdoc", severity="info",
            message=(f"Name, date of birth, passport number and nationality agree across "
                     f"all {len(usable)} sources ({', '.join(x.get('source', 'unknown source') for x in usable)})."),
            plain="The name, date of birth, passport number and nationality all "
                  "agree across every document checked.",
        ))
    return signals
