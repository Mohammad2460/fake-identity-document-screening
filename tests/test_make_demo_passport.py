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


# --- The full stage set: a matching visa and three realistic forgeries -------

def _build_set(tmp_path):
    from scripts import make_demo_passport
    return make_demo_passport.main(["--consent", "--photo", PHOTO_A,
                                    "--name", "RAHUL SHARMA",
                                    "--out", str(tmp_path / "demo")])


def _screen_pair(doc_path, visa_path, claimed, tmp_path):
    p = str(tmp_path / "pair.db")
    if os.path.exists(p):
        os.remove(p)
    db.init_db(p)
    return pipeline.screen(ScreeningInput(claimed=claimed, doc_path=doc_path,
                                          visa_path=visa_path), p)


def test_the_visa_watermark_avoids_the_portrait_the_stamp_and_the_mrz():
    from scripts import make_demo_passport as m
    from scripts.make_samples import H, PORTRAIT_BOX
    top, bottom = m.VISA_WATERMARK_BAND
    assert top > PORTRAIT_BOX[3]          # below the portrait
    assert bottom < H - 110               # above the MRZ band
    # and to the left of the entry stamp, which starts at x=720
    from scripts.make_samples import STAMP_BOX
    assert m.VISA_WATERMARK_CENTER_X + m.VISA_WATERMARK_MAX_WIDTH // 2 < STAMP_BOX[0]
    # and below the last printed row ("Valid until", value drawn at y=394..426)
    assert top > 426


@needs_models
def test_the_genuine_passport_and_visa_screen_clear_together(tmp_path):
    written = _build_set(tmp_path)
    assert os.path.exists(written["visa"])
    result = _screen_pair(written["genuine"], written["visa"],
                          written["claimed"], tmp_path)
    codes = [s.code for s in result.signals]
    assert "XDOC_PASSPORT_NO_MISMATCH" not in codes
    assert "FF_PHOTO_TAMPERED" not in codes
    assert "FF_STAMP_TAMPERED" not in codes
    assert result.band == "CLEAR", (result.band, result.score, codes)


@needs_models
def test_the_dob_variant_flags_the_date_of_birth_field(tmp_path):
    written = _build_set(tmp_path)
    result = _screen(written["dob_altered"], written["claimed_dob_altered"], tmp_path)
    assert "FF_FIELD_TAMPERED" in [s.code for s in result.signals]


@needs_models
def test_the_mrz_variant_fails_the_document_number_check_digit(tmp_path):
    written = _build_set(tmp_path)
    result = _screen(written["mrz_altered"], written["claimed"], tmp_path)
    assert "MRZ_DOCNUM_CHECKSUM_FAIL" in [s.code for s in result.signals]


@needs_models
def test_the_visa_variant_flags_the_entry_stamp(tmp_path):
    written = _build_set(tmp_path)
    result = _screen_pair(written["genuine"], written["visa_stamp_forged"],
                          written["claimed"], tmp_path)
    assert "FF_STAMP_TAMPERED" in [s.code for s in result.signals]


def _band_is_marked(path, band, x_range):
    """True when the watermark band carries the red-tinted SPECIMEN lettering."""
    from PIL import Image
    with Image.open(path) as im:
        crop = im.convert("RGB").crop((x_range[0], band[0], x_range[1], band[1]))
    # WATERMARK_RGBA is red over a pale page, so marked pixels are the ones
    # whose red channel clearly leads their blue channel.
    return sum(1 for r, g, b in crop.getdata() if r - b > 18) > 200


@needs_models
def test_every_written_document_carries_the_specimen_watermark(tmp_path):
    from scripts import make_demo_passport as m
    written = _build_set(tmp_path)
    visa_x = (m.VISA_WATERMARK_CENTER_X - m.VISA_WATERMARK_MAX_WIDTH // 2,
              m.VISA_WATERMARK_CENTER_X + m.VISA_WATERMARK_MAX_WIDTH // 2)
    for key in ("genuine", "dob_altered", "name_altered", "mrz_altered"):
        assert os.path.exists(written[key]), key
        assert _band_is_marked(written[key], m.WATERMARK_BAND, (20, 980)), key
    for key in ("visa", "visa_stamp_forged", "visa_wrong_passport"):
        assert os.path.exists(written[key]), key
        assert _band_is_marked(written[key], m.VISA_WATERMARK_BAND, visa_x), key


@needs_models
def test_the_name_variant_flags_the_field_and_contradicts_the_mrz(tmp_path):
    written = _build_set(tmp_path)
    result = _screen(written["name_altered"], written["claimed_name_altered"], tmp_path)
    codes = [s.code for s in result.signals]
    assert "FF_FIELD_TAMPERED" in codes
    assert "MRZ_NAME_MISMATCH" in codes


@needs_models
def test_the_wrong_passport_visa_is_caught_only_across_the_two_documents(tmp_path):
    written = _build_set(tmp_path)
    result = _screen_pair(written["genuine"], written["visa_wrong_passport"],
                          written["claimed"], tmp_path)
    codes = [s.code for s in result.signals]
    assert "XDOC_PASSPORT_NO_MISMATCH" in codes
    # neither page is tampered - only the pair disagrees
    assert "FF_PHOTO_TAMPERED" not in codes
    assert "FF_STAMP_TAMPERED" not in codes


def test_two_people_never_share_a_document_number():
    """Otherwise the velocity engine reports the second set as the first
    person's passport presented under a new name."""
    from scripts.make_demo_passport import claimed_details, document_numbers
    a, b = document_numbers("MOHAMMAD KHALID"), document_numbers("MOHAMMAD ZAID")
    assert a[0] != b[0] and a[1] != b[1]
    assert document_numbers("MOHAMMAD ZAID") == b          # deterministic
    assert len(a[0]) == 8 and len(a[1]) == 9   # widths the OCR reads reliably
    assert claimed_details("MOHAMMAD ZAID")["passport_no"] == b[0]
