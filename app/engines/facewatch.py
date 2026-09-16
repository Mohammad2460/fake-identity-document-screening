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

FACE_WL_MATCH = face.SAME_PERSON      # 0.363, OpenCV's published SFace cosine threshold
FACE_WL_POSSIBLE = 0.30

_EMBED_CACHE: dict[tuple, "np.ndarray"] = {}


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


def _embedding(image_path: str):
    """One face embedding for an image, or None if it can't be produced.
    Cached on (path, mtime) so repeated screenings against the same gallery
    row don't re-run the recognizer every time."""
    key = (image_path, _mtime(image_path))
    if key in _EMBED_CACHE:
        return _EMBED_CACHE[key]
    faces = face.detect_faces(image_path)
    if not faces:
        _EMBED_CACHE[key] = None
        return None
    biggest = max(faces, key=lambda f: f["box"][2] * f["box"][3])
    emb = face._embedding(image_path, biggest["raw"])
    _EMBED_CACHE[key] = emb
    return emb


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
            gallery_emb = _embedding(img_path)
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
            name = row["name"]
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
                plain=(f"The person in the passport photograph appears on the "
                       f"wanted list as {name}."),
                evidence=ev,
            ))
        else:
            signals.append(Signal(
                code="FACE_WL_POSSIBLE", engine="facewatch", severity="medium",
                message=(f"{source_phrase} looks similar ({best:.2f}) to {name!r} on "
                         f"the {row['list']} wanted-face list, below the {FACE_WL_MATCH} "
                         f"same-person threshold. Manual review required."),
                plain=(f"The photograph looks similar to {name} on the wanted "
                       f"list. An officer should check."),
                evidence=ev,
            ))

    return signals
