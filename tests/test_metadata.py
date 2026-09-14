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
