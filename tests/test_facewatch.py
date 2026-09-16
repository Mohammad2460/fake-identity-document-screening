import csv
import os
import time
import pytest
from app import pipeline
from app.engines import facewatch
from app.models import ScreeningInput

pytestmark = pytest.mark.skipif(
    not os.path.exists("models/face_detection_yunet_2023mar.onnx"),
    reason="face models not downloaded",
)

FACES_DIR = "data/faces"
GALLERY_FACE = os.path.join(FACES_DIR, "sfhq_05.jpg")   # Nadia Husseini Farah
CLEAN_FACE = os.path.join(FACES_DIR, "sfhq_01.jpg")     # not in any gallery

no_gallery_data = pytest.mark.skipif(
    not os.path.exists(GALLERY_FACE) or not os.path.exists(CLEAN_FACE),
    reason="data/faces crops not present",
)


def _csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "name", "list", "reason"])
        for r in rows:
            w.writerow(r)


@pytest.fixture
def gallery_csv(tmp_path):
    path = str(tmp_path / "face_watchlist.csv")
    _csv(path, [[GALLERY_FACE, "Nadia Husseini Farah", "SDN", "Asset freeze"]])
    return path


@no_gallery_data
def test_document_portrait_match_is_critical(gallery_csv):
    signals = facewatch.run(GALLERY_FACE, None, path=gallery_csv)
    codes = [s.code for s in signals]
    assert "FACE_WL_MATCH" in codes
    hit = [s for s in signals if s.code == "FACE_WL_MATCH"][0]
    assert hit.severity == "critical"
    assert "Nadia Husseini Farah" in hit.message


@no_gallery_data
def test_selfie_only_match_names_selfie_as_source(gallery_csv):
    signals = facewatch.run(CLEAN_FACE, GALLERY_FACE, path=gallery_csv)
    hit = [s for s in signals if s.code == "FACE_WL_MATCH"]
    assert hit
    assert "selfie" in hit[0].message.lower()


@no_gallery_data
def test_both_sources_matching_same_person_is_one_signal(gallery_csv):
    signals = facewatch.run(GALLERY_FACE, GALLERY_FACE, path=gallery_csv)
    hits = [s for s in signals if s.code == "FACE_WL_MATCH"]
    assert len(hits) == 1
    assert "document" in hits[0].message.lower() or "portrait" in hits[0].message.lower()
    assert "selfie" in hits[0].message.lower()


@no_gallery_data
def test_no_match_gives_info_signal(gallery_csv):
    signals = facewatch.run(CLEAN_FACE, CLEAN_FACE, path=gallery_csv)
    assert [s.code for s in signals] == ["FACE_WL_NO_MATCH"]
    assert signals[0].severity == "info"


def test_missing_csv_returns_nothing():
    assert facewatch.run(CLEAN_FACE, None, path="data/does_not_exist.csv") == []


@no_gallery_data
def test_bad_gallery_rows_are_skipped_silently(tmp_path):
    path = str(tmp_path / "face_watchlist.csv")
    blank = tmp_path / "blank.png"
    from PIL import Image
    Image.new("RGB", (320, 320), "white").save(blank)
    _csv(path, [
        ["data/faces/does_not_exist.jpg", "Ghost Person", "SDN", "missing file"],
        [str(blank), "No Face Person", "SDN", "no detectable face"],
        [GALLERY_FACE, "Nadia Husseini Farah", "SDN", "Asset freeze"],
    ])
    signals = facewatch.run(GALLERY_FACE, None, path=path)
    assert "FACE_WL_MATCH" in [s.code for s in signals]


@no_gallery_data
def test_local_overlay_adds_entries(tmp_path):
    path = str(tmp_path / "face_watchlist.csv")
    overlay = str(tmp_path / "face_watchlist.local.csv")
    _csv(path, [])
    _csv(overlay, [[GALLERY_FACE, "Nadia Husseini Farah", "SDN", "Asset freeze"]])
    signals = facewatch.run(GALLERY_FACE, None, path=path)
    assert "FACE_WL_MATCH" in [s.code for s in signals]


def test_missing_overlay_is_not_an_error(tmp_path):
    path = str(tmp_path / "face_watchlist.csv")
    _csv(path, [[GALLERY_FACE, "Nadia Husseini Farah", "SDN", "Asset freeze"]])
    signals = facewatch.run(CLEAN_FACE, None, path=path)
    assert signals is not None


@no_gallery_data
def test_editing_csv_is_picked_up_without_restart(tmp_path):
    path = str(tmp_path / "face_watchlist.csv")
    _csv(path, [])
    signals = facewatch.run(GALLERY_FACE, None, path=path)
    assert [s.code for s in signals] == ["FACE_WL_NO_MATCH"]

    time.sleep(0.01)
    _csv(path, [[GALLERY_FACE, "Nadia Husseini Farah", "SDN", "Asset freeze"]])
    signals2 = facewatch.run(GALLERY_FACE, None, path=path)
    assert "FACE_WL_MATCH" in [s.code for s in signals2]


@no_gallery_data
def test_pipeline_rejects_on_gallery_hit_alone(gallery_csv, tmp_path, monkeypatch):
    monkeypatch.setattr(facewatch, "GALLERY_PATH", gallery_csv)
    db_path = str(tmp_path / "cases.db")
    inp = ScreeningInput(claimed={"full_name": "Someone Else"}, doc_path=GALLERY_FACE)
    result = pipeline.screen(inp, db_path=db_path)
    assert result.band == "REJECT"
    assert result.score >= 65
    assert any(s.code == "FACE_WL_MATCH" for s in result.signals)


@no_gallery_data
def test_engine_failure_becomes_signal_not_exception(gallery_csv, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("embedder exploded")
    monkeypatch.setattr(facewatch, "GALLERY_PATH", gallery_csv)
    monkeypatch.setattr(facewatch, "_embedding", boom)
    db_path = str(tmp_path / "cases.db")
    inp = ScreeningInput(claimed={"full_name": "Someone Else"}, doc_path=GALLERY_FACE)
    result = pipeline.screen(inp, db_path=db_path)
    assert result.band in ("CLEAR", "REVIEW", "REJECT")


# --- What the gallery threshold is actually built on -------------------------

def _all_crops():
    import glob
    return sorted(glob.glob(os.path.join(FACES_DIR, "sfhq_*.jpg")))


@no_gallery_data
def test_no_two_distinct_faces_reach_the_gallery_threshold():
    """Every SFHQ crop is a different non-existent person, so no pair may reach
    FACE_WL_MATCH. This is the measurement the threshold is chosen from: four of
    the 28 pairs score at or above face.SAME_PERSON (0.363), the worst at 0.425,
    which is why the gallery does not use that threshold."""
    import itertools
    embeddings = {p: facewatch._embedding(p) for p in _all_crops()}
    pairs = [(facewatch._score(embeddings[a], embeddings[b]), a, b)
             for a, b in itertools.combinations(sorted(embeddings), 2)
             if embeddings[a] is not None and embeddings[b] is not None]
    assert pairs, "no crops available to measure"
    worst, a, b = max(pairs)
    assert worst < facewatch.FACE_WL_MATCH, (
        f"{a} and {b} are different people but score {worst:.3f}, at or above "
        f"the gallery match threshold {facewatch.FACE_WL_MATCH}")
    assert worst <= facewatch.MEASURED_IMPOSTOR_MAX + 0.01, (
        f"impostor similarity rose to {worst:.3f}; MEASURED_IMPOSTOR_MAX and the "
        f"numbers quoted in README/JUDGE_QA are stale")


@no_gallery_data
def test_gallery_faces_are_not_reused_anywhere_else_in_the_repo():
    """A crop used as a demo holder's portrait must never also sit in the
    gallery: that person's own genuine passport would then self-match and
    REJECT. This happened once during task 23."""
    gallery_files = {row["file"] for row in facewatch.load_gallery()}
    assert gallery_files, "the committed gallery is empty"
    import subprocess
    for path in sorted(gallery_files):
        name = os.path.basename(path)
        hits = subprocess.run(
            ["grep", "-rl", "--include=*.py", "--include=*.csv", "--include=*.md",
             name, "tests", "scripts", "app", "data", "docs"],
            capture_output=True, text=True).stdout.split()
        unexpected = [h for h in hits
                      if h not in ("tests/test_facewatch.py", "data/face_watchlist.csv")]
        assert not unexpected, (
            f"{name} is in the wanted-face gallery but is also used by "
            f"{unexpected} - a demo portrait must never be a gallery face")
