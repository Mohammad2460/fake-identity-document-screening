# tests/test_pipeline.py
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app import config, db, pipeline
from app.engines import crossdoc
from app.models import ScreeningInput, ScreeningResult


@pytest.fixture(autouse=True)
def evidence_dir(tmp_path, monkeypatch):
    """No test may write evidence images into the repo."""
    d = tmp_path / "evidence"
    monkeypatch.setattr(config, "EVIDENCE_DIR", str(d))
    return d


@pytest.fixture
def dbfile(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    return p


def test_clean_identity_without_document_scores_low(dbfile):
    inp = ScreeningInput(claimed={
        "full_name": "Jonathan Michael Brewster", "dob": "1988-03-14",
        "passport_no": "L898902C3", "nationality": "UTO",
        "email": "jonathan.brewster@gmail.com", "phone": "9845012763",
    })
    result = pipeline.screen(inp, dbfile)
    assert result.band in ("CLEAR", "REVIEW")
    assert result.case_id


def test_watchlist_hit_forces_reject(dbfile):
    inp = ScreeningInput(claimed={"full_name": "Viktor Anatolyevich Petrov"})
    result = pipeline.screen(inp, dbfile)
    assert result.band == "REJECT"


def test_broken_document_path_does_not_crash(dbfile):
    inp = ScreeningInput(claimed={"full_name": "A B"}, doc_path="/does/not/exist.jpg")
    result = pipeline.screen(inp, dbfile)
    assert isinstance(result.score, int)


def test_engine_exception_is_captured_not_raised(dbfile, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("engine exploded")
    monkeypatch.setattr(pipeline.identity, "run", boom)
    result = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}), dbfile)
    assert any("identity" in e for e in result.engine_errors)
    assert "ENGINE_ERROR" in [s.code for s in result.signals]


def test_case_is_persisted_and_second_submission_sees_it(dbfile):
    claimed = {"full_name": "Anna Eriksson", "passport_no": "L898902C3"}
    pipeline.screen(ScreeningInput(claimed=claimed), dbfile)
    second = pipeline.screen(
        ScreeningInput(claimed={"full_name": "Different Person",
                                "passport_no": "L898902C3"}), dbfile)
    assert "VEL_ID_REUSED_NEW_NAME" in [s.code for s in second.signals]


def test_result_serialises_to_dict(dbfile):
    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}), dbfile)
    d = r.to_dict()
    assert set(d) >= {"case_id", "score", "band", "signals", "engine_errors"}


# --- Controller rulings ---

_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def test_mrz_fields_normalises_lowercase_spaced_lines():
    messy = [" ".join(_L1.lower()), " " + _L2[:20].lower() + " " + _L2[20:].lower() + " "]
    f = pipeline._mrz_fields(messy, "passport")
    assert f["passport_no"] == "L898902C3"
    assert f["dob"] == "740812"


def test_mrz_fields_for_visa_uses_personal_number_not_own_doc_number():
    """The MRV line-2 document number is the visa's own number, not the passport's -
    it must not be compared as a passport number (checkpoint-3 ruling 1). The
    passport it was issued against instead comes from the personal-number field
    (R2)."""
    f = pipeline._mrz_fields([_L1, _L2], "visa")
    assert f["passport_no"] == "ZE184226B"
    assert f["full_name"] == "ANNA MARIA ERIKSSON"
    assert f["dob"] == "740812"


def test_mrz_fields_for_visa_with_empty_personal_number_omits_passport_no():
    visa_l2 = "V123456789UTO7408122F1204159<<<<<<<<<<<<<<08"
    f = pipeline._mrz_fields([_L1, visa_l2], "visa")
    assert f["passport_no"] is None


def test_genuine_passport_and_visa_with_different_visa_number_is_not_rejected(dbfile):
    """checkpoint-3 ruling 1: visa doc number must not be compared as passport_no,
    or every genuine passport+visa pair triggers a critical false positive."""
    passport_lines = [_L1, _L2]
    visa_l2 = "V123456789UTO7408122F1204159<<<<<<<<<<<<<<08"
    visa_lines = [_L1, visa_l2]

    signals = crossdoc.run([
        pipeline._mrz_fields(passport_lines, "passport"),
        pipeline._mrz_fields(visa_lines, "visa"),
    ])
    assert "XDOC_PASSPORT_NO_MISMATCH" not in [s.code for s in signals]


def test_visa_personal_number_field_is_used_as_issued_against_passport_no():
    """R2: the visa MRZ's personal-number field (TD3 line 2 chars 28-41) carries
    the passport it was issued against. When it disagrees with the passport's own
    MRZ number, that is a critical cross-document mismatch."""
    passport_lines = [_L1, _L2]
    visa_l2 = "V123456789UTO7408122F1204159X47281956<<<<<08"
    visa_lines = [_L1, visa_l2]

    f = pipeline._mrz_fields(visa_lines, "visa")
    assert f["passport_no"] == "X47281956"

    signals = crossdoc.run([
        pipeline._mrz_fields(passport_lines, "passport"),
        f,
    ])
    hit = [s for s in signals if s.code == "XDOC_PASSPORT_NO_MISMATCH"]
    assert hit and hit[0].severity == "critical"


def test_mrz_passport_no_vs_claimed_mismatch_is_still_critical():
    claimed = {"source": "claimed", "full_name": "ANNA MARIA ERIKSSON",
              "dob": "1974-08-12", "passport_no": "X99999999", "nationality": "UTO"}
    signals = crossdoc.run([pipeline._mrz_fields([_L1, _L2], "passport"), claimed])
    hit = [s for s in signals if s.code == "XDOC_PASSPORT_NO_MISMATCH"]
    assert hit and hit[0].severity == "critical"


def test_persistence_failure_is_recorded_not_raised(tmp_path):
    bad_db = str(tmp_path / "no_such_dir" / "t.db")
    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}), bad_db)
    assert any("persistence" in e for e in r.engine_errors)


def test_portrait_box_ignores_ambiguous_multiple_faces(monkeypatch):
    big = {"box": (0, 0, 100, 100)}
    monkeypatch.setattr(pipeline.face, "detect_faces", lambda p: [big, {"box": (0, 0, 90, 90)}])
    assert pipeline._portrait_box("x.jpg") is None
    monkeypatch.setattr(pipeline.face, "detect_faces", lambda p: [big, {"box": (0, 0, 10, 10)}])
    assert pipeline._portrait_box("x.jpg") == (0, 0, 100, 100)

    def boom(p):
        raise RuntimeError("no models")
    monkeypatch.setattr(pipeline.face, "detect_faces", boom)
    assert pipeline._portrait_box("x.jpg") is None


def test_visa_is_ocrd_only_once(dbfile, tmp_path, monkeypatch):
    calls = []

    def fake_ocr(path, claimed):
        calls.append(path)
        return [], [], []
    monkeypatch.setattr(pipeline.ocr, "run", fake_ocr)
    visa = tmp_path / "visa.jpg"
    Image.new("RGB", (64, 64), "white").save(visa, "JPEG")
    pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}, visa_path=str(visa)), dbfile)
    assert calls == [str(visa)]


def test_fieldforensics_exception_becomes_engine_error(dbfile, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ff exploded")
    monkeypatch.setattr(pipeline.fieldforensics, "run", boom)
    doc = tmp_path / "doc.jpg"
    Image.new("RGB", (64, 64), "white").save(doc, "JPEG")
    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}, doc_path=str(doc)), dbfile)
    assert any(e.startswith("fieldforensics") for e in r.engine_errors)
    assert any(s.code == "ENGINE_ERROR" and s.engine == "fieldforensics" for s in r.signals)


# --- End to end on a rendered passport with a retyped DOB ---

_FONT_CANDIDATES = ["/System/Library/Fonts/Supplemental/Arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def _font_factory():
    for f in _FONT_CANDIDATES:
        if Path(f).exists():
            return lambda size: ImageFont.truetype(f, size)
    pytest.skip("no TrueType font available to render the passport")


def _render_clean_passport(path, font):
    img = Image.new("RGB", (900, 520), (236, 234, 224))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 900, 70], fill=(22, 52, 96))
    draw.text((24, 18), "REPUBLIC OF UTOPIA  PASSPORT", font=font(30), fill="white")
    rows = [("SURNAME", "ERIKSSON"), ("GIVEN NAMES", "ANNA MARIA"),
            ("PASSPORT NO", "L898902C3"), ("NATIONALITY", "UTO"),
            ("DATE OF BIRTH", "12/08/1974"), ("SEX", "F")]
    for i, (label, value) in enumerate(rows):
        y = 100 + i * 62
        draw.text((300, y), label, font=font(14), fill=(110, 110, 110))
        draw.text((300, y + 18), value, font=font(28), fill=(15, 15, 15))
    img.save(path, "JPEG", quality=70)


@pytest.fixture
def tampered_passport(tmp_path):
    font = _font_factory()
    base = tmp_path / "passport_base.jpg"
    _render_clean_passport(base, font)
    img = Image.open(base).convert("RGB")
    draw = ImageDraw.Draw(img)
    y = 100 + 4 * 62 + 18
    draw.rectangle([296, y - 2, 720, y + 34], fill=(236, 234, 224))
    draw.text((300, y), "12/08/1994", font=font(28), fill=(15, 15, 15))
    p = tmp_path / "passport_tampered.jpg"
    img.save(p, "JPEG", quality=97)
    return str(p)


def test_end_to_end_retyped_dob_is_flagged_with_evidence(dbfile, tampered_passport,
                                                         evidence_dir):
    inp = ScreeningInput(claimed={"full_name": "Anna Maria Eriksson", "dob": "1974-08-12",
                                  "passport_no": "L898902C3", "nationality": "UTO"},
                         doc_path=tampered_passport)
    result = pipeline.screen(inp, dbfile)
    assert isinstance(result, ScreeningResult)
    assert "FF_FIELD_TAMPERED" in [s.code for s in result.signals]
    assert result.evidence_path is not None
    assert os.path.exists(result.evidence_path)
    assert Path(result.evidence_path).resolve().parent == evidence_dir.resolve()


# --- Checkpoint 3 ruling 2: single evidence image, chosen after both analyses ---

def _stub_regions(suspect):
    return [{"box": (0, 0, 10, 10), "suspect": suspect, "label": "x"}]


def test_evidence_source_is_passport_when_both_have_suspect_regions(dbfile, tmp_path,
                                                                     evidence_dir, monkeypatch):
    doc = tmp_path / "doc.jpg"
    visa = tmp_path / "visa.jpg"
    Image.new("RGB", (64, 64), "white").save(doc, "JPEG")
    Image.new("RGB", (64, 64), "white").save(visa, "JPEG")

    def fake_ff(path, boxes, portrait_box):
        suspect = path == str(doc)
        return [], _stub_regions(suspect)
    monkeypatch.setattr(pipeline.fieldforensics, "run", fake_ff)

    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"},
                                       doc_path=str(doc), visa_path=str(visa)), dbfile)
    assert r.evidence_source == "passport"
    assert r.evidence_path is not None
    assert len(list(evidence_dir.iterdir())) == 1


def test_evidence_source_is_visa_when_only_visa_has_suspect_region(dbfile, tmp_path,
                                                                    evidence_dir, monkeypatch):
    doc = tmp_path / "doc.jpg"
    visa = tmp_path / "visa.jpg"
    Image.new("RGB", (64, 64), "white").save(doc, "JPEG")
    Image.new("RGB", (64, 64), "white").save(visa, "JPEG")

    def fake_ff(path, boxes, portrait_box):
        suspect = path == str(visa)
        return [], _stub_regions(suspect)
    monkeypatch.setattr(pipeline.fieldforensics, "run", fake_ff)

    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"},
                                       doc_path=str(doc), visa_path=str(visa)), dbfile)
    assert r.evidence_source == "visa"
    assert r.evidence_path is not None
    assert len(list(evidence_dir.iterdir())) == 1


def test_evidence_source_is_passport_all_green_when_neither_suspect(dbfile, tmp_path,
                                                                     evidence_dir, monkeypatch):
    doc = tmp_path / "doc.jpg"
    visa = tmp_path / "visa.jpg"
    Image.new("RGB", (64, 64), "white").save(doc, "JPEG")
    Image.new("RGB", (64, 64), "white").save(visa, "JPEG")
    monkeypatch.setattr(pipeline.fieldforensics, "run",
                        lambda path, boxes, portrait_box: ([], _stub_regions(False)))

    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"},
                                       doc_path=str(doc), visa_path=str(visa)), dbfile)
    assert r.evidence_source == "passport"
    assert len(list(evidence_dir.iterdir())) == 1


def test_evidence_drawing_failure_is_recorded_not_raised(dbfile, tmp_path,
                                                         evidence_dir, monkeypatch):
    doc = tmp_path / "doc.jpg"
    Image.new("RGB", (64, 64), "white").save(doc, "JPEG")
    monkeypatch.setattr(pipeline.fieldforensics, "run",
                        lambda path, boxes, portrait_box: ([], _stub_regions(True)))

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(pipeline.annotate, "draw_evidence", boom)

    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}, doc_path=str(doc)), dbfile)
    assert r.evidence_path is None and r.evidence_source is None
    assert any(e.startswith("annotate:") for e in r.engine_errors)


def test_evidence_source_is_none_when_no_regions(dbfile):
    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}), dbfile)
    assert r.evidence_source is None
    assert r.evidence_path is None


def test_result_to_dict_includes_evidence_source(dbfile):
    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}), dbfile)
    assert "evidence_source" in r.to_dict()


def test_engines_run_lists_every_invoked_engine_for_fields_only(dbfile):
    r = pipeline.screen(ScreeningInput(claimed={"full_name": "Jonathan Brewster"}), dbfile)
    for name in ("identity", "watchlist", "velocity", "crossdoc"):
        assert name in r.engines_run
    for name in ("tamper", "metadata", "face", "fieldforensics", "ocr", "mrz"):
        assert name not in r.engines_run
    assert len(r.engines_run) == len(set(r.engines_run))
    assert r.to_dict()["engines_run"] == r.engines_run


# --- T16e: liveness challenge frames -------------------------------------

def _models_present():
    return os.path.exists("models/face_detection_yunet_2023mar.onnx")


needs_face_models = pytest.mark.skipif(
    not _models_present(), reason="face models not downloaded")
needs_face_data = pytest.mark.skipif(
    not os.path.exists("data/faces/sfhq_00.jpg"), reason="data/faces crops not present")


def test_no_liveness_signal_when_no_frames_are_submitted(dbfile):
    """An officer uploading files, or a judge screening their own document,
    must never see a liveness signal."""
    result = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}), dbfile)
    assert not [s for s in result.signals if s.code.startswith("LIVENESS_")]


@needs_face_models
@needs_face_data
def test_a_photograph_sequence_moves_a_clean_case_to_review(dbfile, tmp_path):
    from scripts.tune_liveness import photo_sequence

    clean = {"full_name": "Jonathan Michael Brewster", "dob": "1988-03-14",
             "passport_no": "L898902C3", "nationality": "UTO",
             "email": "jonathan.brewster@gmail.com", "phone": "9845012763"}
    baseline = pipeline.screen(ScreeningInput(claimed=clean), dbfile)
    assert baseline.band == "CLEAR"

    frames = photo_sequence("data/faces/sfhq_00.jpg", str(tmp_path), "s")
    result = pipeline.screen(ScreeningInput(claimed=clean, selfie_frames=frames), dbfile)

    failed = [s for s in result.signals if s.code == "LIVENESS_FAILED"]
    assert failed and failed[0].severity == "medium"
    assert result.band == "REVIEW"
    assert "liveness" in result.engines_run


@needs_face_models
@needs_face_data
def test_a_failed_liveness_challenge_alone_never_rejects(dbfile, tmp_path):
    from scripts.tune_liveness import photo_sequence
    frames = photo_sequence("data/faces/sfhq_00.jpg", str(tmp_path), "s")
    result = pipeline.screen(ScreeningInput(selfie_frames=frames), dbfile)
    assert result.band != "REJECT"
    assert result.score < 65


@needs_face_models
@needs_face_data
def test_a_turning_head_adds_no_risk(dbfile, tmp_path):
    from scripts.tune_liveness import live_sequence
    frames = live_sequence("data/faces/sfhq_00.jpg", str(tmp_path), "l")
    result = pipeline.screen(ScreeningInput(selfie_frames=frames), dbfile)
    assert "LIVENESS_PASS" in [s.code for s in result.signals]
    assert result.band == "CLEAR"


def test_liveness_engine_failure_is_isolated(dbfile, monkeypatch, tmp_path):
    frame = tmp_path / "f.png"
    Image.new("RGB", (64, 64), "white").save(frame)

    def boom(*a, **k):
        raise RuntimeError("liveness exploded")
    monkeypatch.setattr(pipeline.liveness, "run", boom)
    result = pipeline.screen(
        ScreeningInput(selfie_frames=[str(frame)]), dbfile)
    assert any("liveness" in e for e in result.engine_errors)
    assert isinstance(result.score, int)
