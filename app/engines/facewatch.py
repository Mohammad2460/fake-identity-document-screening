"""Face watchlist: screens the document portrait and the live selfie against a
gallery of wanted people's faces.

The name watchlist (`app/engines/watchlist.py`) screens text a forger controls -
the typed name, the passport MRZ name, the visa MRZ name. A face cannot be
retyped. A wanted traveller with a cleanly forged passport in a name that was
never on any list still has their own face, so this engine catches what the
name watchlist structurally cannot (task-23).
"""
import csv
import functools
import os
from app.engines import face
from app.engines.watchlist import local_overlay_path
from app.models import Signal

GALLERY_PATH = "data/face_watchlist.csv"

# Stricter than face.SAME_PERSON (0.363), and deliberately so.
#
# That threshold is published for 1:1 verification - one claimed identity, one
# comparison. A gallery is 1:N identification: every extra entry is another
# chance to match the wrong person, so the false-match probability grows with
# the gallery while the threshold does not. Standard biometric practice is a
# stricter operating point for identification than for verification.
#
# We also measured it. Across the 28 pairs of our 8 SFHQ crops - every pair a
# DIFFERENT non-existent person - four scored at or above 0.363, the highest at
# 0.425 (see tests/test_facewatch.py::test_no_two_distinct_faces_reach_the_
# gallery_threshold). These are StyleGAN faces from one generator and are more
# alike than a random sample of real people would be, but the measurement is
# ours and it says 0.363 is not a safe operating point for a gallery.
#
# 0.50 clears our worst measured impostor pair by a wide margin and sits far
# below a genuine match (same face, resized and re-encoded: 0.9342).
FACE_WL_MATCH = 0.50
FACE_WL_POSSIBLE = 0.40

# The highest similarity we have measured between two different people. Tests
# assert the gallery keeps clear of it; quoted in README and JUDGE_QA.
MEASURED_IMPOSTOR_MAX = 0.425

# Gallery embeddings only. A traveller's document and selfie are uploaded to
# uuid-named files that are deleted after the screening, so caching them would
# grow this dict once per screening and never release it.
_GALLERY_EMBED_CACHE: dict[tuple, object] = {}
_GALLERY_EMBED_CACHE_MAX = 256


def _read(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


@functools.lru_cache(maxsize=8)
def _load_rows(path: str, path_mtime, overlay: str, overlay_mtime) -> tuple:
    """Cache key includes both files' mtimes (R7) so editing the gallery on
    disk takes effect on the next call without restarting the server."""
    entries = _read(path) if path_mtime is not None else []
    if overlay_mtime is not None:
        entries += _read(overlay)
    return tuple(entries)


def load_gallery(path: str = GALLERY_PATH) -> tuple:
    if not os.path.exists(path):
        return tuple()
    overlay = local_overlay_path(path)
    return _load_rows(path, _mtime(path), overlay, _mtime(overlay))


def _embedding(image_path: str, cache: bool = False):
    """One face embedding for an image, or None if it can't be produced.

    Gallery rows pass cache=True and are keyed on (path, mtime), so editing a
    gallery image is picked up and repeated screenings don't re-run the
    recognizer over the whole gallery every time.
    """
    key = (image_path, _mtime(image_path))
    if cache and key in _GALLERY_EMBED_CACHE:
        return _GALLERY_EMBED_CACHE[key]
    faces = face.detect_faces(image_path)
    if not faces:
        emb = None
    else:
        biggest = max(faces, key=lambda f: f["box"][2] * f["box"][3])
        emb = face._embedding(image_path, biggest["raw"])
    if cache:
        if len(_GALLERY_EMBED_CACHE) >= _GALLERY_EMBED_CACHE_MAX:
            _GALLERY_EMBED_CACHE.clear()
        _GALLERY_EMBED_CACHE[key] = emb
    return emb


_PLAIN_SOURCE = {"the document portrait": "the photograph on the document",
                 "the selfie": "the live selfie"}


def _plain_sources(labels: list[str]) -> str:
    """Plain-language phrase naming which picture(s) matched."""
    worded = [_PLAIN_SOURCE.get(l, l) for l in labels]
    return worded[0] if len(worded) == 1 else " and ".join(worded)


def _score(a, b) -> float:
    return float(face._recognizer().match(a, b, face.cv2.FaceRecognizerSF_FR_COSINE))


def run(doc_path: str | None, selfie_path: str | None,
        path: str = GALLERY_PATH) -> list[Signal]:
    if not os.path.exists(path):
        return []

    rows = load_gallery(path)

    sources = []
    if doc_path and os.path.exists(doc_path):
        sources.append(("the document portrait", doc_path))
    if selfie_path and os.path.exists(selfie_path):
        sources.append(("the selfie", selfie_path))
    if not sources:
        return []

    source_embeddings = []
    for label, p in sources:
        try:
            emb = _embedding(p)
        except Exception:
            emb = None
        if emb is not None:
            source_embeddings.append((label, emb))
    if not source_embeddings:
        return []

    # Best score per gallery row, keeping which source(s) hit it.
    best_overall = None  # (score, row)
    per_person: dict[str, dict] = {}  # name -> {"row":..., "best": score, "labels": []}

    for row in rows:
        img_path = row.get("file", "")
        try:
            gallery_emb = _embedding(img_path, cache=True)
        except Exception:
            gallery_emb = None
        if gallery_emb is None:
            continue  # missing file, undecodable, or no detectable face - skip silently (R6)

        row_best = None
        row_labels = []
        for label, emb in source_embeddings:
            score = _score(emb, gallery_emb)
            if row_best is None or score > row_best:
                row_best = score
            if score >= FACE_WL_POSSIBLE:
                row_labels.append((label, score))

        if row_best is None:
            continue
        if best_overall is None or row_best > best_overall[0]:
            best_overall = (row_best, row)

        if row_labels:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            entry = per_person.setdefault(name, {"row": row, "best": 0.0, "labels": []})
            for label, score in row_labels:
                if label not in [l for l, _ in entry["labels"]]:
                    entry["labels"].append((label, score))
                if score > entry["best"]:
                    entry["best"] = score

    if not per_person:
        if best_overall is None:
            return [Signal(code="FACE_WL_NO_MATCH", engine="facewatch", severity="info",
                           message="The gallery of wanted faces was screened; no match found.",
                           plain="The photograph does not resemble anyone on the "
                                 "wanted-face list.")]
        return [Signal(code="FACE_WL_NO_MATCH", engine="facewatch", severity="info",
                       message=(f"The gallery of wanted faces was screened; no match "
                                f"found (closest similarity {best_overall[0]:.2f})."),
                       plain="The photograph does not resemble anyone on the "
                             "wanted-face list.")]

    signals: list[Signal] = []
    for name, info in per_person.items():
        row = info["row"]
        best = info["best"]
        labels = [l for l, _ in info["labels"]]
        source_phrase = " and ".join(labels)
        ev = {"similarity": round(best, 3), "threshold": FACE_WL_MATCH,
              "list": row["list"], "sources": labels}

        if best >= FACE_WL_MATCH:
            signals.append(Signal(
                code="FACE_WL_MATCH", engine="facewatch", severity="critical",
                message=(f"{source_phrase} matches {name!r} on the {row['list']} "
                         f"wanted-face list ({row.get('reason', '')}) at similarity "
                         f"{best:.2f} (threshold {FACE_WL_MATCH})."),
                plain=(f"The face in {_plain_sources(labels)} is on the wanted "
                       f"list as {name}."),
                evidence=ev,
            ))
        else:
            signals.append(Signal(
                code="FACE_WL_POSSIBLE", engine="facewatch", severity="medium",
                message=(f"{source_phrase} looks similar ({best:.2f}) to {name!r} on "
                         f"the {row['list']} wanted-face list, below the {FACE_WL_MATCH} "
                         f"match threshold. Manual review required."),
                plain=(f"The face in {_plain_sources(labels)} looks similar to "
                       f"{name} on the wanted list, but not close enough to be "
                       f"sure. An officer should check."),
                evidence=ev,
            ))

    return signals
