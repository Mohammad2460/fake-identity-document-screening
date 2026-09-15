from PIL import Image
from app.engines import metadata

def _make_jpeg(tmp_path, name="x.jpg", **save_kwargs):
    p = tmp_path / name
    Image.new("RGB", (64, 64), (128, 128, 128)).save(p, "JPEG", **save_kwargs)
    return str(p)

def test_sha256_is_stable_and_differs_between_files(tmp_path):
    a = _make_jpeg(tmp_path, "a.jpg")
    b = _make_jpeg(tmp_path, "b.jpg", quality=50)
    assert metadata.file_sha256(a) == metadata.file_sha256(a)
    assert metadata.file_sha256(a) != metadata.file_sha256(b)

def test_image_without_camera_exif_is_flagged(tmp_path):
    p = _make_jpeg(tmp_path)
    codes = [s.code for s in metadata.run(p)]
    assert "META_NO_CAMERA_EXIF" in codes

def test_editing_software_tag_is_flagged(tmp_path):
    p = tmp_path / "edited.jpg"
    img = Image.new("RGB", (64, 64), (10, 10, 10))
    exif = img.getexif()
    exif[305] = "Adobe Photoshop 25.0"   # 305 = Software
    img.save(p, "JPEG", exif=exif)
    codes = [s.code for s in metadata.run(str(p))]
    assert "META_EDITING_SOFTWARE" in codes

def test_missing_file_does_not_raise():
    signals = metadata.run("/nonexistent/file.jpg")
    assert "META_UNREADABLE" in [s.code for s in signals]

def test_unknown_extension_is_handled(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"not an image")
    assert metadata.run(str(p))  # returns signals, does not raise

def test_pdf_date_digits_helper_compares_correctly():
    created = "D:20240101120000+05'30'"
    modified = "D:20240102"
    c = metadata.pdf_date_digits(created)
    m = metadata.pdf_date_digits(modified)
    assert m > c

def test_pdf_date_digits_helper_ignores_short_dates():
    assert metadata.pdf_date_digits("D:2024") is None
    assert metadata.pdf_date_digits("") is None


def test_missing_camera_exif_is_info_not_scored(tmp_path):
    """Task-16b ruling: scanned or issued document images legitimately carry no camera
    EXIF, so absence is recorded for the officer but never raises the risk score."""
    p = _make_jpeg(tmp_path)
    sig = [s for s in metadata.run(p) if s.code == "META_NO_CAMERA_EXIF"]
    assert sig and sig[0].severity == "info"


def test_editing_software_tag_still_scores_medium(tmp_path):
    p = tmp_path / "edited.jpg"
    img = Image.new("RGB", (64, 64), (10, 10, 10))
    exif = img.getexif()
    exif[305] = "GIMP 2.10"
    img.save(p, "JPEG", exif=exif)
    sig = [s for s in metadata.run(str(p)) if s.code == "META_EDITING_SOFTWARE"]
    assert sig and sig[0].severity == "medium"
