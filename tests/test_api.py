import io
import os
import re
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(config, "EVIDENCE_DIR", str(tmp_path / "evidence"))
    from app.main import app, startup
    startup()
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_screen_fields_only(client):
    r = client.post("/api/screen", data={"full_name": "Jonathan Brewster",
                                         "passport_no": "L898902C3"})
    assert r.status_code == 200
    body = r.json()
    assert body["band"] in ("CLEAR", "REVIEW", "REJECT")
    assert isinstance(body["signals"], list)
    assert "top_reasons" in body


def test_screen_flags_watchlist_name(client):
    r = client.post("/api/screen", data={"full_name": "Viktor Anatolyevich Petrov"})
    assert r.json()["band"] == "REJECT"


def test_screen_accepts_an_upload(client):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    buf.seek(0)
    r = client.post("/api/screen",
                    data={"full_name": "Jonathan Brewster"},
                    files={"document": ("id.png", buf, "image/png")})
    assert r.status_code == 200
    assert r.json()["case_id"]


def test_screen_with_no_input_still_returns_a_verdict(client):
    r = client.post("/api/screen", data={})
    assert r.status_code == 200
    assert r.json()["band"] == "CLEAR"


def test_cases_listing_grows(client):
    client.post("/api/screen", data={"full_name": "Aaa Bbb"})
    r = client.get("/api/cases")
    assert r.status_code == 200
    assert len(r.json()["cases"]) >= 1


def test_evidence_url_is_none_without_document(client):
    r = client.post("/api/screen", data={"full_name": "No Document Here"})
    assert r.status_code == 200
    assert r.json()["evidence_url"] is None


def test_oversized_upload_is_rejected(client, tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024)
    big = io.BytesIO(b"x" * 4096)
    r = client.post("/api/screen",
                    data={"full_name": "Big File"},
                    files={"document": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 413
    assert "error" in r.json()
    upload_dir = config.UPLOAD_DIR
    if os.path.isdir(upload_dir):
        assert os.listdir(upload_dir) == []


def test_oversized_second_upload_cleans_up_earlier_saved_files(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024)
    small = io.BytesIO(b"y" * 100)
    big = io.BytesIO(b"x" * 4096)
    r = client.post(
        "/api/screen",
        data={"full_name": "Orphan Check"},
        files={
            "document": ("doc.jpg", small, "image/jpeg"),
            "visa": ("visa.jpg", big, "image/jpeg"),
        },
    )
    assert r.status_code == 413
    assert "error" in r.json()
    upload_dir = config.UPLOAD_DIR
    if os.path.isdir(upload_dir):
        assert os.listdir(upload_dir) == []


def test_evidence_endpoint_serves_existing_file(client):
    from app import config
    name = "ab" * 16 + ".jpg"  # 32 hex chars
    os.makedirs(config.EVIDENCE_DIR, exist_ok=True)
    with open(os.path.join(config.EVIDENCE_DIR, name), "wb") as fh:
        fh.write(b"\xff\xd8\xff\xe0fakejpegbytes")
    r = client.get(f"/evidence/{name}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_evidence_endpoint_404_for_missing_valid_name(client):
    name = "00" * 16 + ".jpg"
    r = client.get(f"/evidence/{name}")
    assert r.status_code == 404


@pytest.mark.parametrize("name", ["evil.jpg", "abc.png", "../../etc/passwd.jpg"])
def test_evidence_endpoint_404_for_invalid_name(client, name):
    r = client.get(f"/evidence/{name}")
    assert r.status_code == 404


def test_root_serves_static_index(client):
    r = client.get("/")
    assert r.status_code == 200


@pytest.mark.parametrize("filename", ["../../evil.jpg", "x.PHP5", "noext"])
def test_upload_filenames_are_sanitised(client, filename):
    from app import config
    buf = io.BytesIO(b"not really an image")
    r = client.post("/api/screen",
                    data={"full_name": "Sanitise Me"},
                    files={"document": (filename, buf, "application/octet-stream")})
    assert r.status_code == 200
    stored = os.listdir(config.UPLOAD_DIR)
    assert len(stored) == 1
    name = stored[0]
    stem, ext = os.path.splitext(name)
    assert re.fullmatch(r"[0-9a-f]{32}", stem)
    assert re.fullmatch(r"\.[a-z0-9]{1,5}", ext) or ext == ".bin"
    # never traverses out of the upload dir, never keeps the client path
    assert ".." not in name and "/" not in name
