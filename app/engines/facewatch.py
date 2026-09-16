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
# Both bands clear our worst measured impostor pair (0.425), because a medium
# "possible match" against an innocent traveller is still an accusation with
# points attached. 0.50 sits far below a genuine match (same face, resized and
# re-encoded: 0.9342), so the narrow 0.45-0.50 band is uncertainty, not noise.
FACE_WL_MATCH = 0.50
FACE_WL_POSSIBLE = 0.45

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
    """Rows from the committed gallery plus the gitignored overlay.

    Either may be absent: the overlay is the documented way to screen a
    consenting stand-in, and it must keep working if the committed gallery is
    renamed or removed.
    """
    overlay = local_overlay_path(path)
    if not os.path.exists(path) and not os.path.exists(overlay):
        return tuple()
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
    rows = load_gallery(path)
    if not rows:
        return []

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

    # Best score per gallery row, keeping which source(s) hit it and at what
    # score, so the message can attribute each one honestly.
    best_overall = None                 # (score, row)
    per_person: dict[str, dict] = {}    # name -> {"row", "best", "labels": {label: score}}
    skipped = 0

    for row in rows:
        img_path = row.get("file", "")
        try:
            gallery_emb = _embedding(img_path, cache=True)
        except Exception:
            gallery_emb = None
        if gallery_emb is None:
            # missing file, undecodable, or no detectable face (R6)
            skipped += 1
            continue

        scored = [(label, _score(emb, gallery_emb)) for label, emb in source_embeddings]
        row_best = max(score for _, score in scored)
        if best_overall is None or row_best > best_overall[0]:
            best_overall = (row_best, row)

        hits = {label: score for label, score in scored if score >= FACE_WL_POSSIBLE}
        if not hits:
            continue
        name = (row.get("name") or "").strip()
        if not name:
            skipped += 1
            continue

        entry = per_person.get(name)
        if entry is None or row_best > entry["best"]:
            # Keep the row that actually scored best: two rows can share a name
            # while naming different lists, and the signal must not attribute
            # the match to the wrong one.
            entry = {"row": row, "best": row_best, "labels": {}}
            per_person[name] = entry
        for label, score in hits.items():
            if score > entry["labels"].get(label, 0.0):
                entry["labels"][label] = score

    # A gallery whose every row failed to load must not read as a clean screen:
    # a relative path resolved from the wrong working directory, or a typo in
    # the hand-authored overlay, would clear every traveller silently.
    if rows and skipped == len(rows):
        return [Signal(
            code="FACE_WL_UNAVAILABLE", engine="facewatch", severity="low",
            message=(f"The wanted-face gallery could not be read: all "
                     f"{len(rows)} entries failed to load. No face screening "
                     f"was performed."),
            plain="The wanted-face list could not be loaded, so the photograph "
                  "was not checked against it.",
            evidence={"rows": len(rows), "skipped": skipped})]

    if not per_person:
        closest = ("" if best_overall is None
                   else f" (closest similarity {best_overall[0]:.2f})")
        return [Signal(code="FACE_WL_NO_MATCH", engine="facewatch", severity="info",
                       message=f"The gallery of wanted faces was screened; no "
                               f"match found{closest}.",
                       plain="The photograph does not resemble anyone on the "
                             "wanted-face list.")]

    signals: list[Signal] = []
    for name, info in per_person.items():
        row = info["row"]
        labels = sorted(info["labels"], key=info["labels"].get, reverse=True)
        best = info["labels"][labels[0]]
        listed = (row.get("list") or "unspecified").strip() or "unspecified"
        # Name each source with its own score: a 0.92 document portrait and a
        # 0.46 selfie must not both read as 0.92.
        source_phrase = " and ".join(f"{l} ({info['labels'][l]:.2f})" for l in labels)
        ev = {"similarity": round(best, 3), "threshold": FACE_WL_MATCH,
              "list": listed, "sources": {l: round(sc, 3)
                                          for l, sc in info["labels"].items()}}

        if best >= FACE_WL_MATCH:
            signals.append(Signal(
                code="FACE_WL_MATCH", engine="facewatch", severity="critical",
                message=(f"{source_phrase} matches {name!r} on the {listed} "
                         f"wanted-face list ({row.get('reason', '')}) at similarity "
                         f"{best:.2f} (threshold {FACE_WL_MATCH})."),
                plain=(f"The face in {_plain_sources(labels)} is on the wanted "
                       f"list as {name}."),
                evidence=ev,
            ))
        else:
            signals.append(Signal(
                code="FACE_WL_POSSIBLE", engine="facewatch", severity="medium",
                message=(f"{source_phrase} looks similar to {name!r} on "
                         f"the {listed} wanted-face list, below the {FACE_WL_MATCH} "
                         f"match threshold. Manual review required."),
                plain=(f"The face in {_plain_sources(labels)} looks similar to "
                       f"{name} on the wanted list, but not close enough to be "
                       f"sure. An officer should check."),
                evidence=ev,
            ))

    return signals
