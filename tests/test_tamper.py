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


# --- task-16b item 3: document-aware tamper checks ---------------------------
from PIL import ImageDraw
from scripts import make_samples as ms

ALT = dict(surname="OKONKWO", given="CHIDI EMEKA", doc_no="K4471093B", nat="UTO",
           dob="881103", sex="M", expiry="330415")


@pytest.mark.parametrize("identity", [ms.BASE, ALT], ids=["base", "alt"])
@pytest.mark.parametrize("kind", ["passport", "visa"])
@pytest.mark.parametrize("quality", [70, 90, 95])
def test_clean_rendered_documents_emit_no_tamper_signal(tmp_path, identity, kind, quality):
    """Typeset text repeats glyphs, has hard edges and flat paper - none of it is tampering."""
    img = ms.draw_passport(identity) if kind == "passport" else ms.draw_visa(identity)
    p = str(tmp_path / f"{kind}.jpg")
    ms.save_issued(img, p, quality=quality)
    codes = [s.code for s in tamper.run(p)]
    assert codes == ["TAMPER_NONE_DETECTED"], codes


def test_layout_aligned_glyph_repeats_are_not_copy_move(tmp_path):
    p = str(tmp_path / "doc.jpg")
    ms.save_issued(ms.draw_passport(ALT), p)
    _, matches = tamper.copy_move_score(p)
    assert matches < tamper.CLONE_MATCH_MIN


def test_substituted_photo_on_document_raises_ela_anomaly(tmp_path):
    """Sample case 04: a different person's photo pasted in after issue, re-saved at q97."""
    p = str(tmp_path / "04.jpg")
    ms.save_issued(ms.draw_passport(ms.BASE), p)
    ms.paste_portrait(ms.reload(p), ms.FACE_B).save(p, "JPEG", quality=97)
    assert "TAMPER_ELA_ANOMALY" in [s.code for s in tamper.run(p)]


def test_noisy_camera_photo_pasted_into_document_is_noise_inconsistent(tmp_path):
    rng = np.random.default_rng(5)
    p = str(tmp_path / "doc.jpg")
    ms.save_issued(ms.draw_passport(ms.BASE), p)
    arr = np.asarray(ms.reload(p)).astype(float)
    arr[120:380, 50:250] = np.clip(np.array([180, 160, 140])
                                   + rng.normal(0, 12, (260, 200, 1)), 0, 255)
    Image.fromarray(arr.astype(np.uint8)).save(p, "JPEG", quality=95)
    assert "TAMPER_NOISE_INCONSISTENT" in [s.code for s in tamper.run(p)]


def test_noisier_splice_on_a_photo_raises_noise_spread(tmp_path, photo_like):
    arr = np.asarray(Image.open(photo_like).convert("L")).astype(float)
    arr[40:200, 40:200] += np.random.default_rng(0).normal(0, 22, (160, 160))
    p = str(tmp_path / "noisy_splice.jpg")
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGB").save(p, "JPEG", quality=85)
    assert tamper.noise_spread(p) > tamper.NOISE_SPREAD_MAX > tamper.noise_spread(photo_like)
