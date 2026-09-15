import numpy as np
from PIL import Image
from app import annotate

def _sample_image(tmp_path):
    p = tmp_path / "doc.jpg"
    Image.new("RGB", (100, 100), "white").save(p)
    return str(p)

def test_draw_evidence_returns_path_on_success(tmp_path):
    p = _sample_image(tmp_path)
    regions = [{"box": (10, 10, 20, 20), "suspect": True, "label": "DOB"}]
    out = annotate.draw_evidence(p, regions, str(tmp_path / "out"))
    assert out is not None

def test_draw_evidence_returns_none_for_missing_image(tmp_path):
    assert annotate.draw_evidence(str(tmp_path / "nope.jpg"), [], str(tmp_path / "out")) is None

def test_draw_evidence_returns_none_when_imwrite_fails(tmp_path, monkeypatch):
    p = _sample_image(tmp_path)
    monkeypatch.setattr(annotate.cv2, "imwrite", lambda *a, **k: False)
    out = annotate.draw_evidence(p, [], str(tmp_path / "out"))
    assert out is None
