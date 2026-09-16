import io
import os
import numpy as np
import pytest
from PIL import Image
from app.engines import face

pytestmark = pytest.mark.skipif(
    not os.path.exists("models/face_detection_yunet_2023mar.onnx"),
    reason="face models not downloaded",
)

FACES_DIR = "data/faces"
FACE_A = os.path.join(FACES_DIR, "sfhq_01.jpg")
FACE_B = os.path.join(FACES_DIR, "sfhq_02.jpg")

no_face_data = pytest.mark.skipif(
    not os.path.exists(FACE_A) or not os.path.exists(FACE_B),
    reason="data/faces crops not present (run scripts.fetch_faces)",
)

@pytest.fixture
def blank(tmp_path):
    p = tmp_path / "blank.png"
    Image.new("RGB", (320, 320), "white").save(p)
    return str(p)

def test_no_face_in_blank_image(blank):
    assert face.detect_faces(blank) == []

def test_missing_portrait_on_document_is_flagged(blank):
    signals = face.run(blank, None)
    assert "FACE_NO_PORTRAIT_ON_DOC" in [s.code for s in signals]

def test_run_without_selfie_does_not_emit_match_signals(blank):
    codes = [s.code for s in face.run(blank, None)]
    assert "FACE_MISMATCH" not in codes and "FACE_MATCH" not in codes

def test_no_document_portrait_skips_selfie_comparison(blank):
    codes = [s.code for s in face.run(blank, blank)]
    assert "FACE_NO_PORTRAIT_ON_DOC" in codes
    assert "FACE_NO_SELFIE_FACE" not in codes

def test_run_handles_missing_files():
    signals = face.run("/nope.png", "/also-nope.png")
    assert "FACE_UNREADABLE" in [s.code for s in signals]

def _face(x, y, w, h):
    return {"box": [x, y, w, h], "confidence": 0.9, "raw": None}

def test_classify_portraits_small_second_face_is_ghost():
    faces = [_face(0, 0, 100, 100), _face(200, 0, 45, 45)]   # 20% area
    kind, primary, extras = face.classify_portraits(faces)
    assert kind == "ghost"
    assert extras == [faces[1]]

def test_classify_portraits_similar_sized_faces_is_multiple():
    faces = [_face(0, 0, 100, 100), _face(200, 0, 70, 70)]   # 49% area >= 40%
    kind, primary, extras = face.classify_portraits(faces)
    assert kind == "multiple"

def test_detect_faces_handles_repeated_resizing_of_shared_detector(tmp_path):
    p1 = tmp_path / "a.png"
    Image.new("RGB", (320, 320), "white").save(p1)
    p2 = tmp_path / "b.png"
    Image.new("RGB", (640, 200), "white").save(p2)

    assert face.detect_faces(str(p1)) == []
    assert face.detect_faces(str(p2)) == []
    assert face.detect_faces(str(p1)) == []


@no_face_data
def test_committed_crop_detects_exactly_one_face():
    faces = face.detect_faces(FACE_A)
    assert len(faces) == 1


@no_face_data
def test_same_face_transformed_scores_at_or_above_same_person(tmp_path):
    """Resize + JPEG re-save of the same crop should still read as the same person."""
    with Image.open(FACE_A) as im:
        im = im.convert("RGB").resize((240, 240))
    transformed = tmp_path / "a_transformed.jpg"
    im.save(transformed, "JPEG", quality=80)

    score = face.match_score(FACE_A, str(transformed))
    print(f"same-person (transformed) cosine: {score:.4f}")
    assert score >= face.SAME_PERSON

    signals = face.run(FACE_A, str(transformed))
    assert "FACE_MATCH" in [s.code for s in signals]


@no_face_data
def test_different_faces_score_below_same_person(tmp_path):
    score = face.match_score(FACE_A, FACE_B)
    print(f"different-person cosine: {score:.4f} "
          f"(below DEFINITE_MISMATCH={face.DEFINITE_MISMATCH}: {score < face.DEFINITE_MISMATCH})")
    assert score < face.SAME_PERSON

    signals = face.run(FACE_A, FACE_B)
    codes = [s.code for s in signals]
    assert ("FACE_MISMATCH" in codes) or ("FACE_MATCH_INCONCLUSIVE" in codes)


@no_face_data
def test_sample_document_with_matching_selfie_emits_face_match(tmp_path):
    from scripts.make_samples import draw_passport, save_issued, BASE

    doc_path = tmp_path / "doc.jpg"
    save_issued(draw_passport(BASE), str(doc_path))

    signals = face.run(str(doc_path), FACE_A)
    codes = [s.code for s in signals]
    assert "FACE_MATCH" in codes


@no_face_data
def test_sample_document_with_different_person_selfie_emits_mismatch(tmp_path):
    from scripts.make_samples import draw_passport, save_issued, BASE

    doc_path = tmp_path / "doc.jpg"
    save_issued(draw_passport(BASE), str(doc_path))

    signals = face.run(str(doc_path), FACE_B)
    codes = [s.code for s in signals]
    assert ("FACE_MISMATCH" in codes) or ("FACE_MATCH_INCONCLUSIVE" in codes)
