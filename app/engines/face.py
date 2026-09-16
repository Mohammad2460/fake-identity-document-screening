"""Portrait detection on the document and biometric match against a selfie."""
import functools
import os
import threading
import cv2
import numpy as np
from app.models import Signal

DETECTOR_PATH = "models/face_detection_yunet_2023mar.onnx"
RECOGNIZER_PATH = "models/face_recognition_sface_2021dec.onnx"

SAME_PERSON = 0.363     # OpenCV SFace documented cosine threshold
DEFINITE_MISMATCH = 0.25
GHOST_AREA_RATIO = 0.4  # a second face smaller than this fraction of the largest
                        # is a printed "ghost" portrait, not a pasted-over photo

# The detector/recognizer are cached singletons shared across requests; setInputSize+detect
# (and alignCrop+feature) are not atomic, so concurrent calls with differently-sized images
# could race and corrupt results. Serialize access to the models themselves.
_MODEL_LOCK = threading.Lock()

@functools.lru_cache(maxsize=1)
def _detector():
    return cv2.FaceDetectorYN.create(DETECTOR_PATH, "", (320, 320), 0.8, 0.3, 5000)

@functools.lru_cache(maxsize=1)
def _recognizer():
    return cv2.FaceRecognizerSF.create(RECOGNIZER_PATH, "")

def _read(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"cannot decode {path}")
    return img

def detect_faces(path: str) -> list[dict]:
    img = _read(path)
    h, w = img.shape[:2]
    with _MODEL_LOCK:
        det = _detector()
        det.setInputSize((w, h))
        _, faces = det.detect(img)
    if faces is None:
        return []
    return [{"box": [int(v) for v in f[:4]], "confidence": float(f[-1]), "raw": f}
            for f in faces]

def classify_portraits(faces: list[dict]) -> tuple[str, dict | None, list[dict]]:
    """Classify a document's detected faces.

    Returns (kind, primary, extras):
    - "none": no faces.
    - "single": exactly one face.
    - "ghost": 2+ faces, every non-primary face's area is < GHOST_AREA_RATIO of
      the largest — a primary portrait plus modern-passport ghost image(s).
    - "multiple": 2+ faces where at least one other face is >= GHOST_AREA_RATIO
      of the largest — consistent with a pasted-over portrait.
    `primary` is the largest face (or None for "none"); `extras` are the rest.
    """
    if not faces:
        return "none", None, []
    ordered = sorted(faces, key=lambda f: f["box"][2] * f["box"][3], reverse=True)
    primary, extras = ordered[0], ordered[1:]
    if not extras:
        return "single", primary, []
    primary_area = primary["box"][2] * primary["box"][3]
    if all((f["box"][2] * f["box"][3]) < GHOST_AREA_RATIO * primary_area for f in extras):
        return "ghost", primary, extras
    return "multiple", primary, extras

def _embedding(path: str, face_row: np.ndarray) -> np.ndarray:
    img = _read(path)
    with _MODEL_LOCK:
        aligned = _recognizer().alignCrop(img, face_row)
        return _recognizer().feature(aligned)

def match_score(doc_path: str, selfie_path: str) -> float | None:
    doc_faces = detect_faces(doc_path)
    selfie_faces = detect_faces(selfie_path)
    if not doc_faces or not selfie_faces:
        return None
    biggest = lambda fs: max(fs, key=lambda f: f["box"][2] * f["box"][3])
    a = _embedding(doc_path, biggest(doc_faces)["raw"])
    b = _embedding(selfie_path, biggest(selfie_faces)["raw"])
    return float(_recognizer().match(a, b, cv2.FaceRecognizerSF_FR_COSINE))

def run(doc_path: str, selfie_path: str | None) -> list[Signal]:
    if not doc_path or not os.path.exists(doc_path):
        return [Signal(code="FACE_UNREADABLE", engine="face", severity="low",
                       message="No document image available for portrait analysis.",
                       plain="No document photo was available, so the portrait "
                             "could not be checked.")]
    try:
        doc_faces = detect_faces(doc_path)
    except Exception as e:
        return [Signal(code="FACE_UNREADABLE", engine="face", severity="low",
                       message=f"Face analysis failed: {type(e).__name__}: {e}",
                       plain="The portrait check could not run on this file.")]

    signals: list[Signal] = []

    kind, primary, extras = classify_portraits(doc_faces)
    has_single_primary_portrait = False

    if kind == "none":
        signals.append(Signal(
            code="FACE_NO_PORTRAIT_ON_DOC", engine="face", severity="medium",
            message="No portrait photograph was detected on the document. "
                    "Every genuine photo ID carries one.",
            plain="No photograph of the holder was found on the document. "
                  "A genuine passport or visa always has one.",
        ))
    elif kind == "multiple":
        signals.append(Signal(
            code="FACE_MULTIPLE_PORTRAITS", engine="face", severity="high",
            message=f"{len(doc_faces)} faces detected on a single ID document — "
                    f"consistent with a photo pasted over the original portrait.",
            plain="More than one face was found in the photograph area, which "
                  "is what happens when a new photo is glued or pasted over "
                  "the original.",
            evidence={"count": len(doc_faces)},
        ))
    elif kind == "ghost":
        signals.append(Signal(
            code="FACE_GHOST_IMAGE_PRESENT", engine="face", severity="info",
            message="Primary portrait plus smaller ghost image(s), as printed on "
                    "modern passports.",
            plain="A main photo plus a smaller security image was found, which "
                  "is normal on modern passports.",
            evidence={"count": len(doc_faces)},
        ))
        has_single_primary_portrait = True
    else:  # "single"
        signals.append(Signal(code="FACE_PORTRAIT_PRESENT", engine="face", severity="info",
                              message="A single portrait was detected on the document.",
                              plain="A single photograph of the holder was found on "
                                    "the document, as expected.",
                              evidence={"box": doc_faces[0]["box"],
                                        "confidence": round(doc_faces[0]["confidence"], 3)}))
        has_single_primary_portrait = True

    if not has_single_primary_portrait:
        return signals

    if not selfie_path or not os.path.exists(selfie_path):
        return signals

    try:
        score = match_score(doc_path, selfie_path)
    except Exception as e:
        signals.append(Signal(code="FACE_UNREADABLE", engine="face", severity="low",
                              message=f"Selfie comparison failed: {type(e).__name__}: {e}",
                              plain="The selfie could not be compared with the "
                                    "document photo."))
        return signals

    if score is None:
        signals.append(Signal(
            code="FACE_NO_SELFIE_FACE", engine="face", severity="medium",
            message="No face could be located in the submitted selfie.",
            plain="No face could be found in the selfie, so it could not be "
                  "compared with the document photo."))
    elif score < DEFINITE_MISMATCH:
        signals.append(Signal(
            code="FACE_MISMATCH", engine="face", severity="critical",
            message=(f"The selfie does not match the portrait on the document "
                     f"(similarity {score:.2f}, same-person threshold {SAME_PERSON}). "
                     f"The document belongs to a different person."),
            plain="The person in the selfie is not the person in the passport "
                  "photograph.",
            evidence={"similarity": round(score, 3), "threshold": SAME_PERSON}))
    elif score < SAME_PERSON:
        signals.append(Signal(
            code="FACE_MATCH_INCONCLUSIVE", engine="face", severity="medium",
            message=(f"Selfie-to-portrait similarity is {score:.2f}, below the "
                     f"{SAME_PERSON} same-person threshold but not a clear mismatch. "
                     f"Manual review required."),
            plain="The selfie and the document photo look similar but not close "
                  "enough to be certain. An officer should take a look.",
            evidence={"similarity": round(score, 3)}))
    else:
        signals.append(Signal(
            code="FACE_MATCH", engine="face", severity="info",
            message=f"Selfie matches the document portrait (similarity {score:.2f}).",
            plain="The selfie matches the photograph on the document.",
            evidence={"similarity": round(score, 3)}))
    return signals
