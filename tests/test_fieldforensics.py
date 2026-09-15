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
