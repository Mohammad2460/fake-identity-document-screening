import pytest
from PIL import Image, ImageDraw, ImageFont
from app.engines import ocr

def _font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()

@pytest.fixture
def text_image(tmp_path):
    img = Image.new("RGB", (800, 260), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 50), "ANNA MARIA ERIKSSON", fill="black", font=_font(44))
    d.text((30, 140), "DOB 1974-08-12", fill="black", font=_font(44))
    p = tmp_path / "doc.png"
    img.save(p)
    return str(p)

def test_find_mrz_lines_picks_out_chevron_rows():
    lines = [
        "REPUBLIC OF UTOPIA",
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
        "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
    ]
    assert ocr.find_mrz_lines(lines) == lines[1:]

def test_find_mrz_lines_returns_empty_when_absent():
    assert ocr.find_mrz_lines(["JUST A NAME", "AND A DATE"]) == []

def test_extract_boxes_returns_text_and_geometry(text_image):
    boxes = ocr.extract_boxes(text_image)
    assert boxes, "OCR found no text at all"
    joined = " ".join(b["text"] for b in boxes).upper()
    assert "ERIKSSON" in joined or "ANNA" in joined
    for b in boxes:
        x, y, w, h = b["box"]
        assert w > 0 and h > 0
        assert x >= 0 and y >= 0

def test_run_returns_signals_mrz_and_boxes(text_image):
    signals, mrz_lines, boxes = ocr.run(text_image, {"full_name": "Anna Maria Eriksson"})
    assert isinstance(signals, list) and isinstance(mrz_lines, list)
    assert boxes and "box" in boxes[0]

def test_name_present_on_document_is_not_flagged(text_image):
    signals, _, _ = ocr.run(text_image, {"full_name": "Anna Maria Eriksson"})
    assert "OCR_NAME_NOT_ON_DOCUMENT" not in [s.code for s in signals]

def test_name_absent_from_document_is_flagged(text_image):
    signals, _, _ = ocr.run(text_image, {"full_name": "Bartholomew Cubbins"})
    assert "OCR_NAME_NOT_ON_DOCUMENT" in [s.code for s in signals]

def test_name_mismatch_is_high_not_critical(text_image):
    signals, _, _ = ocr.run(text_image, {"full_name": "Bartholomew Cubbins"})
    hit = [s for s in signals if s.code == "OCR_NAME_NOT_ON_DOCUMENT"][0]
    assert hit.severity == "high"

def test_name_partial_match_is_flagged(text_image):
    signals, _, _ = ocr.run(text_image, {"full_name": "Anna Smith"})
    assert "OCR_NAME_NOT_ON_DOCUMENT" in [s.code for s in signals]

def test_name_score_helper_uses_min_across_tokens():
    blob = "ANNA MARIA ERIKSSON"
    score = ocr.name_match_score("Anna Smith", blob)
    assert score < ocr.NAME_MATCH_THRESHOLD

def test_name_score_helper_short_tokens_use_whole_name():
    blob = "SURNAME LI GIVEN WU"
    score = ocr.name_match_score("LI WU", blob)
    assert score > 0

def test_run_handles_missing_file():
    signals, mrz, boxes = ocr.run("/nope.png", {})
    assert "OCR_UNREADABLE" in [s.code for s in signals]
    assert mrz == [] and boxes == []

def test_extract_boxes_filters_degenerate_point_polygon(monkeypatch):
    stub = lambda path: (
        [
            [[[10, 10], [10, 10], [10, 10], [10, 10]], "DOT", 0.9],
            [[[0, 0], [50, 0], [50, 20], [0, 20]], "GOOD", 0.95],
        ],
        None,
    )
    monkeypatch.setattr(ocr, "_engine", lambda: stub)
    boxes = ocr.extract_boxes("any.png")
    assert len(boxes) == 1
    assert boxes[0]["text"] == "GOOD"
    assert boxes[0]["box"] == (0, 0, 50, 20)

def test_extract_boxes_filters_degenerate_horizontal_line(monkeypatch):
    stub = lambda path: (
        [
            [[[0, 5], [40, 5], [40, 5], [0, 5]], "LINE", 0.9],
            [[[0, 0], [50, 0], [50, 20], [0, 20]], "GOOD", 0.95],
        ],
        None,
    )
    monkeypatch.setattr(ocr, "_engine", lambda: stub)
    boxes = ocr.extract_boxes("any.png")
    assert len(boxes) == 1
    assert boxes[0]["text"] == "GOOD"
    assert boxes[0]["box"] == (0, 0, 50, 20)
