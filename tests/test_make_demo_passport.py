"""T16d Part B: the stage-demo specimen passport built around a live person's
photo. The photo itself is never committed; these tests stand in for a
teammate with a committed SFHQ crop (a synthetic, non-existent face)."""
import os

import pytest

from app import config, db, pipeline
from app.models import ScreeningInput

PHOTO_A = "data/faces/sfhq_03.jpg"
PHOTO_B = "data/faces/sfhq_04.jpg"

needs_models = pytest.mark.skipif(
    not (os.path.exists(PHOTO_A)
         and os.path.exists("models/face_detection_yunet_2023mar.onnx")),
    reason="data/faces crops or face models missing "
           "(run scripts.fetch_faces / scripts.download_models)")


@pytest.fixture(autouse=True)
def evidence_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVIDENCE_DIR", str(tmp_path / "evidence"))


def _screen(doc_path, claimed, tmp_path):
    p = str(tmp_path / "demo.db")
    if os.path.exists(p):
        os.remove(p)
    db.init_db(p)
    return pipeline.screen(ScreeningInput(claimed=claimed, doc_path=doc_path), p)


def test_without_consent_it_exits_non_zero_and_writes_nothing(tmp_path):
    from scripts import make_demo_passport
    out = tmp_path / "demo"
    with pytest.raises(SystemExit) as exc:
        make_demo_passport.main(["--photo", PHOTO_A, "--name", "RAHUL SHARMA",
                                 "--out", str(out)])
    assert exc.value.code != 0
    assert not out.exists()


def test_it_refuses_a_photo_that_does_not_exist(tmp_path):
    from scripts import make_demo_passport
    out = tmp_path / "demo"
    with pytest.raises(SystemExit) as exc:
        make_demo_passport.main(["--consent", "--photo", str(tmp_path / "nope.jpg"),
                                 "--name", "RAHUL SHARMA", "--out", str(out)])
    assert exc.value.code != 0


def test_the_specimen_watermark_avoids_the_portrait_and_the_mrz():
    """The watermark must not cover the two regions the engines depend on."""
    from scripts.make_demo_passport import WATERMARK_BAND
    from scripts.make_samples import PORTRAIT_BOX, H
    top, bottom = WATERMARK_BAND
    assert top >= PORTRAIT_BOX[3], "watermark overlaps the portrait"
    assert bottom <= H - 110, "watermark overlaps the MRZ"


@needs_models
def test_the_demo_passport_portrait_is_one_face_and_screens_clear(tmp_path):
    from app.engines import face
    from scripts import make_demo_passport
    out = tmp_path / "demo"
    written = make_demo_passport.main(["--consent", "--photo", PHOTO_A,
                                       "--name", "RAHUL SHARMA", "--out", str(out)])
    genuine = written["genuine"]
    assert os.path.exists(genuine)
    assert face.classify_portraits(face.detect_faces(genuine))[0] == "single"
    result = _screen(genuine, written["claimed"], tmp_path)
    assert result.band == "CLEAR", [s.code for s in result.signals
                                    if s.severity != "info"]
    codes = [s.code for s in result.signals]
    # A short name leaves a short MRZ line 1; the MRZ must still read clean.
    assert "MRZ_ALL_CHECKS_PASS" in codes
    assert "OCR_NAME_CONFIRMED" in codes


@needs_models
def test_the_forged_variant_flags_the_photograph(tmp_path):
    from scripts import make_demo_passport
    out = tmp_path / "demo"
    written = make_demo_passport.main(["--consent", "--photo", PHOTO_A,
                                       "--forge-photo", PHOTO_B,
                                       "--name", "RAHUL SHARMA", "--out", str(out)])
    forged = written["forged"]
    assert os.path.exists(forged)
    result = _screen(forged, written["claimed"], tmp_path)
    assert "FF_PHOTO_TAMPERED" in [s.code for s in result.signals]


@needs_models
def test_the_genuine_and_forged_portraits_are_different_people(tmp_path):
    from app.engines import face
    from scripts import make_demo_passport
    written = make_demo_passport.main(["--consent", "--photo", PHOTO_A,
                                       "--forge-photo", PHOTO_B,
                                       "--name", "RAHUL SHARMA",
                                       "--out", str(tmp_path / "demo")])
    assert face.match_score(written["genuine"], written["forged"]) < face.SAME_PERSON


def test_data_demo_is_gitignored():
    assert "data/demo/" in open(".gitignore").read()
