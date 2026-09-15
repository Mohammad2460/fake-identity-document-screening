import os
import numpy as np
import pytest
from PIL import Image
from app.engines import face

pytestmark = pytest.mark.skipif(
    not os.path.exists("models/face_detection_yunet_2023mar.onnx"),
    reason="face models not downloaded",
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

def test_run_handles_missing_files():
    signals = face.run("/nope.png", "/also-nope.png")
    assert "FACE_UNREADABLE" in [s.code for s in signals]
