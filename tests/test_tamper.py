import cv2
import numpy as np
import pytest
from PIL import Image
from app.engines import tamper

@pytest.fixture
def photo_like(tmp_path):
    """A noisy gradient — stands in for a real photograph."""
    rng = np.random.default_rng(0)
    base = np.linspace(40, 200, 256, dtype=np.uint8)
    img = np.tile(base, (256, 1))
    img = np.clip(img + rng.normal(0, 6, img.shape), 0, 255).astype(np.uint8)
    p = tmp_path / "clean.jpg"
    Image.fromarray(img).convert("RGB").save(p, "JPEG", quality=85)
    return str(p)

@pytest.fixture
def spliced(tmp_path, photo_like):
    """Same image with a hard-pasted uncompressed block."""
    arr = np.array(Image.open(photo_like))
    arr[80:150, 80:150] = np.random.default_rng(1).integers(0, 255, (70, 70, 3))
    p = tmp_path / "spliced.jpg"
    Image.fromarray(arr).save(p, "JPEG", quality=95)
    return str(p)

def test_ela_map_matches_image_shape(photo_like):
    m = tamper.ela_map(photo_like)
    assert m.shape[:2] == (256, 256)

def test_ela_map_applies_exif_orientation(tmp_path):
    """A 200x100 (w x h) image saved with EXIF Orientation=6 (rotate 90) should
    be read the same way cv2.imread reads it — orientation-applied, i.e. what a
    human sees — by both ela_map and cv2.imread."""
    from PIL import Image as PILImage
    img = PILImage.new("RGB", (200, 100), "white")
    p = tmp_path / "rotated.jpg"
    exif = img.getexif()
    exif[274] = 6
    img.save(p, "JPEG", exif=exif)

    ela = tamper.ela_map(str(p))
    cv_shape = cv2.imread(str(p)).shape[:2]
    assert ela.shape == cv_shape == (200, 100)

def test_spliced_region_raises_ela_score(photo_like, spliced):
    assert tamper.ela_score(spliced) > tamper.ela_score(photo_like)

def test_cloned_region_is_detected(tmp_path):
    """A gradient has too few distinctive keypoints for ORB; use random texture instead,
    and compare a cloned image against an un-cloned control of the same texture."""
    rng = np.random.default_rng(3)
    tex = rng.integers(0, 255, (320, 320, 3), dtype=np.uint8)
    tex = cv2.GaussianBlur(tex, (3, 3), 0)

    control_p = tmp_path / "control.jpg"
    Image.fromarray(tex).save(control_p, "JPEG", quality=95)

    cloned = tex.copy()
    cloned[200:290, 200:290] = tex[0:90, 0:90]   # clone a 90x90 patch >120px away
    cloned_p = tmp_path / "cloned.jpg"
    Image.fromarray(cloned).save(cloned_p, "JPEG", quality=95)

    _, control_matches = tamper.copy_move_score(str(control_p))
    _, cloned_matches = tamper.copy_move_score(str(cloned_p))

    assert cloned_matches >= tamper.CLONE_MATCH_MIN
    assert cloned_matches > control_matches

def test_run_returns_signals_for_valid_image(photo_like):
    signals = tamper.run(photo_like)
    assert signals and all(s.engine == "tamper" for s in signals)

def test_run_never_raises_on_garbage(tmp_path):
    p = tmp_path / "bad.jpg"
    p.write_bytes(b"not an image at all")
    signals = tamper.run(str(p))
    assert "TAMPER_UNREADABLE" in [s.code for s in signals]

def test_run_handles_missing_file():
    assert "TAMPER_UNREADABLE" in [s.code for s in tamper.run("/nope.jpg")]

def test_no_tamper_signal_exceeds_high(photo_like, spliced):
    for p in (photo_like, spliced):
        assert all(s.severity != "critical" for s in tamper.run(p))
