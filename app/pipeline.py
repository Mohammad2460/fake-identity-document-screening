"""Fans a screening request out across every engine and folds the result."""
import os
import uuid
from app import annotate, config, db, scoring
from app.engines import (crossdoc, face, fieldforensics, identity, metadata, mrz,
                         ocr, tamper, velocity, watchlist)
from app.models import ScreeningInput, ScreeningResult, Signal


def _error_signal(engine_name: str, what: str, e: Exception) -> Signal:
    return Signal(code="ENGINE_ERROR", engine=engine_name, severity="low",
                  message=f"{what} could not complete: {type(e).__name__}: {e}")


def _safe(engine_name: str, fn, *args, **kwargs):
    """Run an engine; convert any failure into a signal instead of an exception."""
    try:
        return fn(*args, **kwargs), None
    except Exception as e:
        err = f"{engine_name}: {type(e).__name__}: {e}"
        return [_error_signal(engine_name, f"The {engine_name} engine", e)], err


def _ocr_document(path: str, claimed: dict, label: str, signals: list, errors: list):
    """OCR one document. Returns (mrz_lines, boxes); never raises."""
    try:
        sigs, mrz_lines, boxes = ocr.run(path, claimed)
        for sg in sigs:
            if label != "passport":
                sg.message = f"[{label}] {sg.message}"
        signals.extend(sigs)
        return mrz_lines, boxes
    except Exception as e:
        errors.append(f"ocr[{label}]: {type(e).__name__}: {e}")
        signals.append(_error_signal("ocr", f"OCR of the {label}", e))
        return [], []


def _mrz_fields(lines: list[str], label: str) -> dict | None:
    if len(lines) < 2:
        return None
    try:
        # Same normalisation mrz.run applies: case, spaces, dropped trailing fillers
        # and letter/digit look-alikes repaired by ICAO field type (task-16b item 2).
        l1, l2 = mrz.normalise_td3(lines)[:2]
        f = mrz.parse_td3(l1, l2)
    except Exception:
        return None
    # A visa's MRZ line-2 document number (ICAO 9303 Part 7) is the visa's OWN
    # number, not the passport it was issued against - it must never be compared
    # as a passport number (checkpoint-3 ruling 1). The passport it was issued
    # against travels in the personal-number / optional-data field instead
    # (task-16a ruling R2).
    if label == "visa":
        personal = f["personal_number"].replace(mrz.FILLER, "")
        passport_no = personal or None
    else:
        passport_no = f["doc_number"]
    return {"source": f"{label} MRZ", "full_name": f"{f['given_names']} {f['surname']}",
            "dob": f["dob"], "passport_no": passport_no, "nationality": f["nationality"]}


def _portrait_box(path: str) -> tuple | None:
    """Box of the document's primary portrait, or None when absent or ambiguous."""
    try:
        kind, primary, _ = face.classify_portraits(face.detect_faces(path))
        if kind in ("single", "ghost") and primary:
            return tuple(primary["box"])
    except Exception:
        pass
    return None


def screen(inp: ScreeningInput, db_path: str = config.DB_PATH) -> ScreeningResult:
    case_id = uuid.uuid4().hex[:12]
    signals: list[Signal] = []
    errors: list[str] = []
    doc_hash = None
    evidence_path = None
    engines_run: list[str] = []

    def ran(name):
        if name not in engines_run:
            engines_run.append(name)

    def collect(name, fn, *args):
        ran(name)
        out, err = _safe(name, fn, *args)
        signals.extend(out)
        if err:
            errors.append(err)

    has_doc = bool(inp.doc_path and os.path.exists(inp.doc_path))
    has_visa = bool(inp.visa_path and os.path.exists(inp.visa_path))

    if has_doc:
        try:
            doc_hash = metadata.file_sha256(inp.doc_path)
        except Exception as e:
            errors.append(f"hash: {type(e).__name__}: {e}")

    # 1. Text first. OCR discovers the MRZ lines and the field boxes everything else needs.
    mrz_lines, boxes = [], []
    if has_doc:
        ran("ocr")
        mrz_lines, boxes = _ocr_document(inp.doc_path, inp.claimed, "passport", signals, errors)

    visa_mrz, visa_boxes = [], []
    if has_visa:
        ran("ocr")
        visa_mrz, visa_boxes = _ocr_document(inp.visa_path, {}, "visa", signals, errors)

    # 2. MRZ check digits - the self-proving arithmetic.
    if mrz_lines:
        collect("mrz", mrz.run, mrz_lines, inp.claimed)

    # 3. Rules engines that need no image.
    collect("identity", identity.run, inp.claimed)
    collect("watchlist", watchlist.run, inp.claimed)
    collect("velocity", velocity.run, inp.claimed, doc_hash, db_path)

    # 4. Cross-document: passport MRZ vs visa MRZ vs the applicant's own claim.
    sources = [src for src in (
        _mrz_fields(mrz_lines, "passport"),
        _mrz_fields(visa_mrz, "visa"),
        {"source": "claimed", **{k: inp.claimed.get(k) for k in
                                 ("full_name", "dob", "passport_no", "nationality")}},
    ) if src]
    collect("crossdoc", crossdoc.run, sources)

    # 5. Pixel forensics on the passport image.
    doc_regions: list | None = None
    visa_regions: list | None = None

    if has_doc:
        portrait_box = _portrait_box(inp.doc_path)
        collect("metadata", metadata.run, inp.doc_path)
        collect("tamper", tamper.run, inp.doc_path)
        collect("face", face.run, inp.doc_path, inp.selfie_path)

        # 6. The centerpiece: which field was altered - regions kept, drawing deferred
        # until we know whether the visa also has a suspect region (ruling: at most
        # one evidence image per case).
        ran("fieldforensics")
        try:
            ff_signals, doc_regions = fieldforensics.run(inp.doc_path, boxes, portrait_box)
            signals.extend(ff_signals)
        except Exception as e:
            errors.append(f"fieldforensics: {type(e).__name__}: {e}")
            signals.append(_error_signal("fieldforensics", "Field-level analysis", e))

    # 7. Same analysis on the visa (reusing its OCR boxes) - catches a forged entry stamp.
    if has_visa:
        ran("fieldforensics")
        try:
            v_signals, visa_regions = fieldforensics.run(inp.visa_path, visa_boxes,
                                                          _portrait_box(inp.visa_path))
            for sg in v_signals:
                sg.message = f"[visa] {sg.message}"
            signals.extend(sg for sg in v_signals if sg.severity != "info")
        except Exception as e:
            errors.append(f"fieldforensics[visa]: {type(e).__name__}: {e}")
            signals.append(_error_signal("fieldforensics", "Field-level analysis of the visa", e))

    # 8. Exactly one evidence image, chosen after both analyses are in: the
    # passport wins if it has a suspect region, else the visa, else the passport
    # (all-green) if it was analysed at all, else no evidence.
    evidence_source = None
    chosen = None
    if doc_regions and any(r["suspect"] for r in doc_regions):
        chosen = (inp.doc_path, doc_regions, "passport")
    elif visa_regions and any(r["suspect"] for r in visa_regions):
        chosen = (inp.visa_path, visa_regions, "visa")
    elif doc_regions:
        chosen = (inp.doc_path, doc_regions, "passport")
    if chosen:
        # Drawing is presentation only: a failure loses the picture, never the verdict.
        try:
            evidence_path = annotate.draw_evidence(chosen[0], chosen[1], config.EVIDENCE_DIR)
            evidence_source = chosen[2] if evidence_path else None
        except Exception as e:
            errors.append(f"annotate: {type(e).__name__}: {e}")

    score, band = scoring.score_signals(signals)
    result = ScreeningResult(case_id=case_id, score=score, band=band, signals=signals,
                             engine_errors=errors, evidence_path=evidence_path,
                             evidence_source=evidence_source, engines_run=engines_run)

    try:
        db.save_case(db_path, case_id, inp.claimed, score, band, signals, doc_hash)
    except Exception as e:
        result.engine_errors.append(f"persistence: {type(e).__name__}: {e}")
    return result
