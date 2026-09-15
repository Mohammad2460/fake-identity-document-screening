# tests/test_fieldforensics.py
import numpy as np
import pytest
from PIL import Image
from app.engines import fieldforensics as ff

@pytest.fixture
def doc_with_tampered_field(tmp_path):
    """Five identical text-ish strips; strip 2 is repasted at a different quality."""
    rng = np.random.default_rng(0)
    canvas = np.full((400, 600, 3), 235, np.uint8)
    boxes = []
    for i in range(5):
        y = 30 + i * 70
        strip = rng.integers(60, 90, (40, 500, 3)).astype(np.uint8)
        canvas[y:y + 40, 50:550] = strip
        boxes.append((50, y, 500, 40))

    p_clean = tmp_path / "clean.jpg"
    Image.fromarray(canvas).save(p_clean, "JPEG", quality=60)

    # Reload the compressed version, then paste fresh uncompressed content into box 2
    arr = np.array(Image.open(p_clean))
    x, y, w, h = boxes[2]
    arr[y:y + h, x:x + w] = rng.integers(0, 255, (h, w, 3)).astype(np.uint8)
    p_bad = tmp_path / "tampered.jpg"
    Image.fromarray(arr).save(p_bad, "JPEG", quality=98)
    return str(p_bad), boxes, 2

def test_outlier_indices_finds_the_extreme_value():
    assert ff.outlier_indices([10.0, 10.2, 9.8, 10.1, 80.0]) == [4]

def test_outlier_indices_empty_when_uniform():
    assert ff.outlier_indices([10.0, 10.1, 9.9, 10.05]) == []

def test_outlier_indices_handles_tiny_input():
    assert ff.outlier_indices([1.0]) == []
    assert ff.outlier_indices([]) == []

def test_region_scores_one_value_per_box(doc_with_tampered_field):
    path, boxes, _ = doc_with_tampered_field
    from app.engines.tamper import ela_map
    scores = ff.region_scores(ela_map(path), boxes)
    assert len(scores) == len(boxes)
    assert all(s >= 0 for s in scores)

def test_tampered_field_scores_highest(doc_with_tampered_field):
    path, boxes, bad_idx = doc_with_tampered_field
    from app.engines.tamper import ela_map
    scores = ff.region_scores(ela_map(path), boxes)
    assert scores.index(max(scores)) == bad_idx

def test_run_names_the_tampered_field(doc_with_tampered_field):
    path, boxes, bad_idx = doc_with_tampered_field
    ocr_boxes = [{"text": f"FIELD {i}", "confidence": 0.95, "box": b}
                 for i, b in enumerate(boxes)]
    signals, regions = ff.run(path, ocr_boxes)
    assert "FF_FIELD_TAMPERED" in [s.code for s in signals]
    flagged = [r for r in regions if r["suspect"]]
    assert flagged and flagged[0]["label"] == f"FIELD {bad_idx}"

def test_run_with_no_boxes_is_graceful(tmp_path):
    p = tmp_path / "x.jpg"
    Image.new("RGB", (64, 64), "white").save(p, "JPEG")
    signals, regions = ff.run(str(p), [])
    assert "FF_NO_REGIONS" in [s.code for s in signals]
    assert regions == []

def test_run_never_raises_on_garbage(tmp_path):
    p = tmp_path / "bad.jpg"
    p.write_bytes(b"not an image")
    signals, regions = ff.run(str(p), [{"text": "A", "confidence": 1.0, "box": (0, 0, 50, 50)}])
    assert "FF_UNREADABLE" in [s.code for s in signals] or \
           "FF_NO_REGIONS" in [s.code for s in signals]

def test_no_field_signal_is_critical(doc_with_tampered_field):
    path, boxes, _ = doc_with_tampered_field
    ocr_boxes = [{"text": f"F{i}", "confidence": 0.9, "box": b} for i, b in enumerate(boxes)]
    signals, _ = ff.run(path, ocr_boxes)
    assert all(s.severity != "critical" for s in signals)

def test_annotate_writes_an_image(tmp_path, doc_with_tampered_field):
    from app import annotate
    path, boxes, bad_idx = doc_with_tampered_field
    regions = [{"box": b, "label": f"F{i}", "suspect": i == bad_idx, "score": 1.0}
               for i, b in enumerate(boxes)]
    out = annotate.draw_evidence(path, regions, str(tmp_path / "ev"))
    assert out and Image.open(out).size == Image.open(path).size


# --- Fix round 1: realistic passport with a dark header banner (real OCR) ---

from pathlib import Path
from PIL import ImageDraw, ImageFont

_FONT_CANDIDATES = ["/System/Library/Fonts/Supplemental/Arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
_TAMPER_CODES = {"FF_FIELD_TAMPERED", "FF_PHOTO_TAMPERED", "FF_STAMP_TAMPERED"}

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
def clean_passport(tmp_path):
    font = _font_factory()
    p = tmp_path / "passport_clean.jpg"
    _render_clean_passport(p, font)
    return str(p)

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

def test_clean_passport_with_dark_header_flags_nothing(clean_passport):
    from app.engines import ocr
    _, _, boxes = ocr.run(clean_passport, {})
    signals, _ = ff.run(clean_passport, boxes)
    assert not _TAMPER_CODES & {s.code for s in signals}, [s.message for s in signals]

def test_retyped_dob_is_the_only_flagged_field(tampered_passport):
    from app.engines import ocr
    _, _, boxes = ocr.run(tampered_passport, {})
    _, regions = ff.run(tampered_passport, boxes)
    flagged = [r for r in regions if r["suspect"]]
    assert len(flagged) == 1, [(r["label"], r["score"]) for r in flagged]
    assert "1994" in flagged[0]["label"]

# --- Fix round 1: stamp detector must not accept banners or printed elements ---

def test_stamp_regions_ignores_full_width_banner(tmp_path):
    img = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 600, 120], fill=(20, 60, 200))
    draw.ellipse([260, 210, 340, 290], fill=(20, 60, 200))
    p = tmp_path / "banner_and_stamp.png"
    img.save(p)
    stamps = ff.stamp_regions(str(p))
    assert len(stamps) == 1
    x, y, w, h = stamps[0]
    assert w < 0.8 * 600 and 200 <= y <= 220

def test_run_does_not_add_stamp_overlapping_text_box(tmp_path):
    img = Image.new("RGB", (600, 400), "white")
    ImageDraw.Draw(img).rectangle([110, 110, 170, 170], fill=(20, 60, 200))
    p = tmp_path / "stamp_in_text.jpg"
    img.save(p, "JPEG", quality=90)
    ocr_boxes = [{"text": "COVERS", "confidence": 0.9, "box": (100, 100, 80, 80)},
                 {"text": "A", "confidence": 0.9, "box": (300, 100, 200, 40)},
                 {"text": "B", "confidence": 0.9, "box": (300, 200, 200, 40)}]
    assert ff.stamp_regions(str(p)), "fixture must yield a stamp candidate"
    _, regions = ff.run(str(p), ocr_boxes)
    assert regions and not [r for r in regions if r["kind"] == "stamp"]

def test_zero_area_portrait_box_is_ignored(doc_with_tampered_field):
    path, boxes, _ = doc_with_tampered_field
    ocr_boxes = [{"text": f"F{i}", "confidence": 0.9, "box": b} for i, b in enumerate(boxes)]
    _, regions = ff.run(path, ocr_boxes, portrait_box=(0, 0, 0, 0))
    assert not [r for r in regions if r["kind"] == "portrait"]
