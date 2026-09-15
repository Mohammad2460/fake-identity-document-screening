# tests/test_pipeline.py
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app import config, db, pipeline
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
