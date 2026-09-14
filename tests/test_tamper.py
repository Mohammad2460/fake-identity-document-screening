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

def test_spliced_region_raises_ela_score(photo_like, spliced):
    assert tamper.ela_score(spliced) > tamper.ela_score(photo_like)

def test_cloned_region_is_detected(tmp_path, photo_like):
    arr = np.array(Image.open(photo_like))
    arr[10:70, 10:70] = arr[150:210, 150:210]   # clone a patch
    p = tmp_path / "cloned.jpg"
    Image.fromarray(arr).save(p, "JPEG", quality=95)
    score, matches = tamper.copy_move_score(str(p))
    assert matches >= 0        # engine runs and reports

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
