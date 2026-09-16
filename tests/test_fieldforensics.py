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

def test_outlier_indices_tight_group_needs_a_real_margin():
    # Genuine q60 visa: fields 0.66-0.89, a tight MAD made a 0.16 wobble look like an edit.
    vals = [0.72, 0.73, 0.74, 0.73, 0.70, 0.76, 0.73, 0.75, 0.71, 0.89]
    assert ff.outlier_indices(vals) == []
    assert ff.outlier_indices(vals + [1.4]) == [10]

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

def test_background_is_measured_around_the_field_not_inside_it(doc_with_tampered_field):
    path, boxes, bad_idx = doc_with_tampered_field
    gray = np.asarray(Image.open(path).convert("L"))
    assert ff.background_luminance(gray, boxes[bad_idx]) >= 200


# --- task-16b item 4: the generated demo samples, real OCR -------------------
from scripts import make_samples as ms

_ALT = dict(surname="OKONKWO", given="CHIDI EMEKA", doc_no="K4471093B", nat="UTO",
            dob="881103", sex="M", expiry="330415")


def _ff(path):
    from app.engines import ocr
    _, _, boxes = ocr.run(path, {})
    signals, regions = ff.run(path, boxes)
    return signals, [r for r in regions if r["suspect"]], regions


def _retyped(tmp_path, field, value):
    p = str(tmp_path / "forged.jpg")
    ms.save_issued(ms.draw_passport(ms.BASE), p)
    ms.retype_field(ms.reload(p), ms.FIELDS.index(field), value).save(p, "JPEG", quality=97)
    return p


@pytest.mark.parametrize("identity", [ms.BASE, _ALT], ids=["base", "alt"])
@pytest.mark.parametrize("kind", ["passport", "visa"])
def test_genuine_rendered_documents_flag_no_region(tmp_path, identity, kind):
    p = str(tmp_path / f"{kind}.jpg")
    img = ms.draw_passport(identity) if kind == "passport" else ms.draw_visa(identity)
    ms.save_issued(img, p)
    signals, flagged, _ = _ff(p)
    assert not flagged, [(r["label"], r["score"]) for r in flagged]
    assert not _TAMPER_CODES & {s.code for s in signals}


def test_mrz_lines_are_their_own_peer_group(tmp_path):
    p = str(tmp_path / "passport.jpg")
    ms.save_issued(ms.draw_passport(ms.BASE), p)
    _, _, regions = _ff(p)
    assert len([r for r in regions if r["kind"] == "mrz"]) == 2


# --- checkpoint-4 F2/R8: a stray MRZ fragment must not be judged as a field --
def test_content_classifies_a_short_mrz_fragment():
    assert ff._is_mrz_text("<<<04")            # >=30% filler, all-MRZ charset
    assert not ff._is_mrz_text("STATE<OF")      # ordinary text with one filler


def test_band_fragment_next_to_a_real_mrz_line_is_reclassified():
    regions = [
        {"box": (10, 850, 400, 20), "kind": "mrz", "label": "L1", "suspect": False, "score": 0.0},
        {"box": (420, 852, 40, 18), "kind": "text", "label": "<<<04",
         "suspect": False, "score": 0.0},
    ]
    ff.reclassify_band_fragments(regions, img_h=1000)
    assert regions[1]["kind"] == "mrz"


def test_lone_bottom_box_with_no_mrz_anchor_is_left_as_text():
    regions = [{"box": (10, 950, 200, 30), "kind": "text", "label": "ISSUED AT",
                "suspect": False, "score": 0.0}]
    ff.reclassify_band_fragments(regions, img_h=1000)
    assert regions[0]["kind"] == "text"


def test_mrz_fragment_never_flagged_or_counted_as_skipped(tmp_path):
    p = str(tmp_path / "passport.jpg")
    ms.save_issued(ms.draw_passport(ms.BASE), p)
    from app.engines import ocr
    _, _, boxes = ocr.run(p, {})
    # Inject a fragment box, like OCR splitting one MRZ line, positioned in the
    # MRZ band next to the real lines so the alignment test picks it up.
    mrz_boxes = [b for b in boxes if "<" in b["text"]]
    assert mrz_boxes
    anchor = mrz_boxes[0]["box"]
    frag_box = (anchor[0] + anchor[2] + 5, anchor[1], 30, anchor[3])
    boxes = boxes + [{"text": "<<<04", "confidence": 0.9, "box": frag_box}]
    signals, regions = ff.run(p, boxes)
    frag = next(r for r in regions if r["label"] == "<<<04")
    assert frag["kind"] == "mrz"
    assert not frag["suspect"]
    ok = next(s for s in signals if s.code == "FF_ALL_FIELDS_CONSISTENT")
    assert "MRZ" not in ok.message


def test_sample_dob_retyped_flags_exactly_the_dob_value(tmp_path):
    signals, flagged, _ = _ff(_retyped(tmp_path, "Date of birth", "12/08/1994"))
    assert [r["label"] for r in flagged] == ["12/08/1994"]
    assert [s.code for s in signals] == ["FF_FIELD_TAMPERED"]


def test_sample_surname_retyped_flags_exactly_the_surname(tmp_path):
    _, flagged, _ = _ff(_retyped(tmp_path, "Surname", "SHARMA"))
    assert [r["label"] for r in flagged] == ["SHARMA"]


def test_sample_forged_visa_stamp_is_flagged_as_the_stamp(tmp_path):
    p = str(tmp_path / "visa.jpg")
    ms.save_issued(ms.draw_visa(ms.BASE, stamp=False), p)
    img = ms.reload(p)
    d = ImageDraw.Draw(img)
    d.ellipse([720, 330, 930, 470], outline=(30, 60, 170), width=6)
    d.text((752, 382), "ENTRY  2026", font=ms._font(26), fill=(30, 60, 170))
    img.save(p, "JPEG", quality=97)
    signals, flagged, _ = _ff(p)
    assert [r["kind"] for r in flagged] == ["stamp"]
    x, y, w, h = flagged[0]["box"]
    assert x <= 725 and y <= 335 and x + w >= 925 and y + h >= 465   # whole stamp boxed
    assert [s.code for s in signals] == ["FF_STAMP_TAMPERED"]


# --- task-16c: photoreal portrait on the samples ------------------------------
import os as _os

_needs_faces = pytest.mark.skipif(
    not (_os.path.exists("data/faces/sfhq_01.jpg")
         and _os.path.exists("models/face_detection_yunet_2023mar.onnx")),
    reason="data/faces crops or face models missing")


def _ff_with_portrait(path):
    from app import pipeline
    from app.engines import ocr
    _, _, boxes = ocr.run(path, {})
    signals, regions = ff.run(path, boxes, pipeline._portrait_box(path))
    return signals, [r for r in regions if r["suspect"]], regions


@_needs_faces
@pytest.mark.parametrize("quality", [60, 70, 80, 95])
@pytest.mark.parametrize("kind", ["passport", "visa"])
def test_genuine_portrait_is_not_flagged_and_is_not_a_stamp(tmp_path, kind, quality):
    p = str(tmp_path / f"{kind}.jpg")
    img = ms.draw_passport(ms.BASE) if kind == "passport" else ms.draw_visa(ms.BASE)
    ms.save_issued(img, p, quality=quality)
    signals, flagged, regions = _ff_with_portrait(p)
    assert not flagged, [(r["kind"], r["label"], r["score"]) for r in flagged]
    assert [r for r in regions if r["kind"] == "portrait"]
    x0, y0, x1, y1 = ms.PORTRAIT_BOX
    photo = (x0, y0, x1 - x0, y1 - y0)
    assert not [r for r in regions if r["kind"] == "stamp"
                and ff._overlap_fraction(r["box"], photo) > 0.5]


@_needs_faces
@pytest.mark.parametrize("q2", [95, 97])
def test_substituted_photo_is_flagged_as_the_photograph_only(tmp_path, q2):
    p = str(tmp_path / "04.jpg")
    ms.save_issued(ms.draw_passport(ms.BASE), p)
    ms.paste_portrait(ms.reload(p), ms.FACE_B).save(p, "JPEG", quality=q2)
    signals, flagged, _ = _ff_with_portrait(p)
    assert [r["kind"] for r in flagged] == ["portrait"]
    assert [s.code for s in signals] == ["FF_PHOTO_TAMPERED"]


def test_stamp_candidate_inside_the_photograph_zone_is_not_a_stamp():
    face_box = (83, 167, 137, 184)
    zone = ff.portrait_zone(face_box)
    assert ff._overlap_fraction((50, 166, 71, 214), zone) > ff.STAMP_OVERLAP_MAX   # hair
    assert ff._overlap_fraction((720, 330, 211, 141), zone) == 0.0              # real stamp
