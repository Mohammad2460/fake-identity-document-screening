"""R7: build_mrz's personal-number field must itself be checksum-valid."""
from app.engines import mrz
from scripts.make_samples import build_mrz


def test_build_mrz_with_personal_field_has_no_checksum_failures():
    l1, l2 = build_mrz("V", "ERIKSSON", "ANNA MARIA", "V10293847", "UTO",
                        "740812", "F", "301231", personal="L898902C3")
    signals = mrz.run([l1, l2], {})
    codes = [s.code for s in signals if s.code.startswith("MRZ_") and s.code.endswith("FAIL")]
    assert codes == []


def test_build_mrz_personal_field_round_trips_through_parse_td3():
    l1, l2 = build_mrz("V", "ERIKSSON", "ANNA MARIA", "V10293847", "UTO",
                        "740812", "F", "301231", personal="X47281956")
    parsed = mrz.parse_td3(l1, l2)
    assert parsed["personal_number"].replace(mrz.FILLER, "") == "X47281956"


def test_build_mrz_without_personal_field_is_unchanged():
    l1, l2 = build_mrz("P", "ERIKSSON", "ANNA MARIA", "L898902C3", "UTO",
                        "740812", "F", "301231")
    signals = mrz.run([l1, l2], {})
    codes = [s.code for s in signals if s.code.startswith("MRZ_") and s.code.endswith("FAIL")]
    assert codes == []
    parsed = mrz.parse_td3(l1, l2)
    assert parsed["personal_number"].replace(mrz.FILLER, "") == ""


def test_rendered_genuine_passport_ocr_to_mrz_is_valid_with_nationality_uto(tmp_path):
    """Real rendered sample -> RapidOCR -> MRZ: valid digits, nationality UTO."""
    from app import pipeline
    from app.engines import ocr
    from scripts.make_samples import BASE, draw_passport, save_issued
    p = str(tmp_path / "clean.jpg")
    save_issued(draw_passport(BASE), p)
    _, lines, _ = ocr.run(p, {})
    codes = [s.code for s in mrz.run(lines, {"full_name": "Anna Maria Eriksson"})]
    assert codes == ["MRZ_ALL_CHECKS_PASS"]
    fields = pipeline._mrz_fields(lines, "passport")
    assert fields["nationality"] == "UTO" and fields["passport_no"] == "L898902C3"


# --- T16c: photorealistic synthetic portraits (SFHQ, non-existent people) ---
import os as _os
import pytest as _pytest

_needs_faces = _pytest.mark.skipif(
    not (_os.path.exists("data/faces/sfhq_01.jpg")
         and _os.path.exists("models/face_detection_yunet_2023mar.onnx")),
    reason="data/faces crops or face models missing (run scripts.fetch_faces / download_models)")


@_needs_faces
def test_rendered_passport_portrait_is_detected_as_a_single_face(tmp_path):
    from app.engines import face
    from scripts.make_samples import BASE, draw_passport, save_issued, PORTRAIT_BOX
    p = str(tmp_path / "clean.jpg")
    save_issued(draw_passport(BASE), p)
    kind, primary, _ = face.classify_portraits(face.detect_faces(p))
    assert kind == "single"
    x, y, w, h = primary["box"]
    x0, y0, x1, y1 = PORTRAIT_BOX
    assert x0 <= x + w / 2 <= x1 and y0 <= y + h / 2 <= y1


@_needs_faces
def test_rendered_visa_portrait_is_detected(tmp_path):
    from app.engines import face
    from scripts.make_samples import BASE, draw_visa, save_issued
    p = str(tmp_path / "visa.jpg")
    save_issued(draw_visa(BASE), p)
    assert face.classify_portraits(face.detect_faces(p))[0] == "single"


@_needs_faces
def test_substituted_photo_is_a_different_person(tmp_path):
    from app.engines import face
    from scripts.make_samples import BASE, FACE_B, draw_passport, paste_portrait, save_issued, reload
    genuine = str(tmp_path / "genuine.jpg")
    forged = str(tmp_path / "forged.jpg")
    save_issued(draw_passport(BASE), genuine)
    save_issued(draw_passport(BASE), forged)
    paste_portrait(reload(forged), FACE_B).save(forged, "JPEG", quality=97)
    assert face.match_score(genuine, forged) < face.SAME_PERSON
