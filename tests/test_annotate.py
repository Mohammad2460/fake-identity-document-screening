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


def _overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def test_tab_goes_beside_the_box_when_it_would_cover_the_label_above():
    # 03: DOB value with its "DATE OF BIRTH" label 22px above it
    label = {"box": (298, 352, 110, 18), "suspect": False, "label": "DATE OF BIRTH"}
    dob = {"box": (299, 374, 128, 23), "suspect": True, "label": "12/08/1994"}
    tab = annotate.tab_rect(dob, [label, dob], (640, 1000))
    assert not _overlaps(tab, label["box"])
    assert not _overlaps(tab, dob["box"])
    assert tab[0] + tab[2] <= 1000 and tab[1] >= 0


def test_tab_stays_above_when_nothing_is_there():
    r = {"box": (100, 200, 80, 30), "suspect": True, "label": "X"}
    x, y, w, h = annotate.tab_rect(r, [r], (640, 1000))
    assert y + h <= 200 and x == 100
