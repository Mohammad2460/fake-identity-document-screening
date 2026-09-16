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
def test_upload_filenames_are_sanitised(client, filename, monkeypatch):
    # Uploads are deleted right after screening (checkpoint-3 ruling 4), so the
    # saved path is captured via the screen() call it's passed to rather than
    # read back off disk afterwards.
    from app import config, main
    seen = {}
    real_screen = main.screen

    def spying_screen(inp, db_path):
        seen["doc_path"] = inp.doc_path
        return real_screen(inp, db_path)
    monkeypatch.setattr(main, "screen", spying_screen)

    buf = io.BytesIO(b"not really an image")
    r = client.post("/api/screen",
                    data={"full_name": "Sanitise Me"},
                    files={"document": (filename, buf, "application/octet-stream")})
    assert r.status_code == 200
    name = os.path.basename(seen["doc_path"])
    stem, ext = os.path.splitext(name)
    assert re.fullmatch(r"[0-9a-f]{32}", stem)
    assert re.fullmatch(r"\.[a-z0-9]{1,5}", ext) or ext == ".bin"
    # never traverses out of the upload dir, never keeps the client path
    assert ".." not in name and "/" not in name
    # and it is gone once the response has been built
    assert os.listdir(config.UPLOAD_DIR) == []


def test_screen_response_includes_engines_run(client):
    body = client.post("/api/screen", data={"full_name": "Jonathan Brewster"}).json()
    assert isinstance(body["engines_run"], list)
    assert "watchlist" in body["engines_run"]


# --- Checkpoint 3 ruling 3: api_screen runs in the threadpool, screening is serialised ---

def test_api_screen_is_not_a_coroutine():
    import inspect
    from app.main import api_screen
    assert not inspect.iscoroutinefunction(api_screen)


def test_api_screen_serialises_with_a_module_level_lock():
    import threading
    from app import main
    assert isinstance(main._screen_lock, type(threading.Lock()))


# --- Checkpoint 3 ruling 4: uploads are deleted after screening, evidence stays ---

def test_uploads_are_deleted_after_a_successful_screen(client):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    buf.seek(0)
    r = client.post("/api/screen",
                    data={"full_name": "Jonathan Brewster"},
                    files={"document": ("id.png", buf, "image/png")})
    assert r.status_code == 200
    from app import config
    assert os.listdir(config.UPLOAD_DIR) == []


def test_uploads_are_deleted_even_when_screen_raises(client, monkeypatch):
    from app import config, main
    from PIL import Image

    def boom(*a, **k):
        raise RuntimeError("screen exploded")
    monkeypatch.setattr(main, "screen", boom)

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    buf.seek(0)
    from fastapi.testclient import TestClient
    raising_client = TestClient(main.app, raise_server_exceptions=False)
    r = raising_client.post("/api/screen",
                            data={"full_name": "Jonathan Brewster"},
                            files={"document": ("id.png", buf, "image/png")})
    assert r.status_code == 500
    assert os.listdir(config.UPLOAD_DIR) == []


def test_evidence_still_served_after_upload_cleanup(client):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    buf.seek(0)
    r = client.post("/api/screen",
                    data={"full_name": "Jonathan Brewster"},
                    files={"document": ("id.png", buf, "image/png")})
    assert r.status_code == 200
    evidence_url = r.json()["evidence_url"]
    if evidence_url:
        assert client.get(evidence_url).status_code == 200


# --- T16e: liveness challenge frames ---------------------------------------

def _jpeg(size=(64, 64)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "JPEG")
    buf.seek(0)
    return buf


def test_screen_accepts_repeated_selfie_frames(client):
    files = [("selfie_frames", (f"f{i}.jpg", _jpeg(), "image/jpeg")) for i in range(5)]
    r = client.post("/api/screen",
                    data={"full_name": "Jonathan Brewster", "liveness_direction": "left"},
                    files=files)
    assert r.status_code == 200
    from app import config
    assert os.listdir(config.UPLOAD_DIR) == []


def test_selfie_frames_are_size_capped_like_every_other_upload(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024)
    files = [("selfie_frames", ("f0.jpg", io.BytesIO(b"x" * 4096), "image/jpeg"))]
    r = client.post("/api/screen", data={"full_name": "Big Frame"}, files=files)
    assert r.status_code == 413
    assert os.listdir(config.UPLOAD_DIR) == []


def test_too_many_frames_are_ignored_not_saved(client):
    from app import config
    files = [("selfie_frames", (f"f{i}.jpg", _jpeg(), "image/jpeg"))
             for i in range(config.MAX_LIVENESS_FRAMES + 8)]
    r = client.post("/api/screen", data={"full_name": "Flood"}, files=files)
    assert r.status_code == 200
    assert os.listdir(config.UPLOAD_DIR) == []


def test_frames_reach_the_pipeline_and_are_deleted_afterwards(client, monkeypatch):
    from app import config, main
    seen = {}
    real_screen = main.screen

    def spying_screen(inp, db_path):
        seen["frames"] = list(inp.selfie_frames)
        seen["direction"] = inp.liveness_direction
        seen["existed"] = [os.path.exists(p) for p in inp.selfie_frames]
        return real_screen(inp, db_path)
    monkeypatch.setattr(main, "screen", spying_screen)

    files = [("selfie_frames", (f"f{i}.jpg", _jpeg(), "image/jpeg")) for i in range(4)]
    r = client.post("/api/screen",
                    data={"full_name": "Frames Reach", "liveness_direction": "right"},
                    files=files)
    assert r.status_code == 200
    assert len(seen["frames"]) == 4
    assert all(seen["existed"])
    assert seen["direction"] == "right"
    assert not any(os.path.exists(p) for p in seen["frames"])
    assert os.listdir(config.UPLOAD_DIR) == []


def test_no_frames_means_no_liveness_signal_over_http(client):
    r = client.post("/api/screen", data={"full_name": "Plain Upload"})
    codes = [s["code"] for s in r.json()["signals"]]
    assert not [c for c in codes if c.startswith("LIVENESS_")]
