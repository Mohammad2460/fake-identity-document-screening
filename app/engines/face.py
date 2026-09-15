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
                       message="No document image available for portrait analysis.")]
    try:
        doc_faces = detect_faces(doc_path)
    except Exception as e:
        return [Signal(code="FACE_UNREADABLE", engine="face", severity="low",
                       message=f"Face analysis failed: {type(e).__name__}: {e}")]

    signals: list[Signal] = []

    if not doc_faces:
        signals.append(Signal(
            code="FACE_NO_PORTRAIT_ON_DOC", engine="face", severity="medium",
            message="No portrait photograph was detected on the document. "
                    "Every genuine photo ID carries one.",
        ))
    elif len(doc_faces) > 1:
        signals.append(Signal(
            code="FACE_MULTIPLE_PORTRAITS", engine="face", severity="high",
            message=f"{len(doc_faces)} faces detected on a single ID document — "
                    f"consistent with a photo pasted over the original portrait.",
            evidence={"count": len(doc_faces)},
        ))
    else:
        signals.append(Signal(code="FACE_PORTRAIT_PRESENT", engine="face", severity="info",
                              message="A single portrait was detected on the document.",
                              evidence={"box": doc_faces[0]["box"],
                                        "confidence": round(doc_faces[0]["confidence"], 3)}))

    if not selfie_path or not os.path.exists(selfie_path):
        return signals

    try:
        score = match_score(doc_path, selfie_path)
    except Exception as e:
        signals.append(Signal(code="FACE_UNREADABLE", engine="face", severity="low",
                              message=f"Selfie comparison failed: {type(e).__name__}: {e}"))
        return signals

    if score is None:
        signals.append(Signal(
            code="FACE_NO_SELFIE_FACE", engine="face", severity="medium",
            message="No face could be located in the submitted selfie."))
    elif score < DEFINITE_MISMATCH:
        signals.append(Signal(
            code="FACE_MISMATCH", engine="face", severity="critical",
            message=(f"The selfie does not match the portrait on the document "
                     f"(similarity {score:.2f}, same-person threshold {SAME_PERSON}). "
                     f"The document belongs to a different person."),
            evidence={"similarity": round(score, 3), "threshold": SAME_PERSON}))
    elif score < SAME_PERSON:
        signals.append(Signal(
            code="FACE_MATCH_INCONCLUSIVE", engine="face", severity="medium",
            message=(f"Selfie-to-portrait similarity is {score:.2f}, below the "
                     f"{SAME_PERSON} same-person threshold but not a clear mismatch. "
                     f"Manual review required."),
            evidence={"similarity": round(score, 3)}))
    else:
        signals.append(Signal(
            code="FACE_MATCH", engine="face", severity="info",
            message=f"Selfie matches the document portrait (similarity {score:.2f}).",
            evidence={"similarity": round(score, 3)}))
    return signals
