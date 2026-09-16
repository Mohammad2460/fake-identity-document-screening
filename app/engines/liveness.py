"""Challenge-response liveness: did the face in front of the camera actually turn?

This is NOT anti-spoofing. It defeats the cheapest attack — a printed photograph
or a phone screen held up to the webcam — and nothing more. A video replay of the
right person turning their head, or a photo bent around a curve, will pass.
Passive anti-spoofing (a dedicated model) is named as future work.

How it works, with no new model and no new dependency. YuNet already returns five
landmarks per face: both eyes, the nose tip and both mouth corners. A real head is
three-dimensional — the nose sticks out in front of the eye plane — so turning it
moves the nose tip sideways relative to the midpoint between the eyes. A flat
photograph has no nose depth, so tilting or shifting it moves nothing.

    yaw proxy = (nose_x - eye_midpoint_x) / inter-eye distance

Dividing by the inter-eye distance makes it scale-invariant: moving a photograph
toward the camera changes the inter-eye distance but leaves the proxy alone.
We never use the absolute proxy (it is non-zero for a resting face and differs
per person); we use how far it MOVES across the challenge sequence, measured as
the median of the last third minus the median of the first third — medians so
that one bad landmark frame cannot carry the verdict.

The threshold is calibrated in scripts/tune_liveness.py; see README's
Calibration section for the measured numbers.
"""
import math
import os

from app.config import MAX_LIVENESS_FRAMES
from app.models import Signal

# Calibrated in scripts/tune_liveness.py over synthetic sequences built from the
# committed SFHQ crops (see README). Measured there:
#   synthetic head turn (7 faces) : +0.065 .. +0.120
#   flat photo rotated on its axis: -0.068 .. -0.014   (always the wrong way)
#   static photo, shifted/rescaled: -0.035 .. +0.016
# 0.045 sits ~2.8x above the worst photograph and ~1.4x below the weakest turn.
YAW_DELTA_THRESHOLD = 0.045

MIN_FRAMES = 3     # fewer usable frames than this proves nothing
MAX_FRAMES = MAX_LIVENESS_FRAMES    # a flood of frames must not stall a screening
MIN_USABLE_FRACTION = 0.6   # below this, too many frames were unreadable to judge fairly

# A liveness failure must land a clean case in MANUAL REVIEW on its own, but must
# never be enough for REJECT by itself. The severity stays "medium" (the cap this
# engine may never exceed); the score override lifts it over the CLEAR/REVIEW
# boundary at 30 while staying well under the REJECT floor at 65.
FAILED_SCORE = 35.0

DIRECTIONS = {"left": 1.0, "right": -1.0}
DEFAULT_DIRECTION = "left"


def yaw_proxy(path: str) -> tuple[float, float] | None:
    """(yaw proxy, inter-eye distance in pixels) for the largest face, or None.

    Positive proxy = the nose sits right of the eye midpoint in the image. In an
    unmirrored camera frame the traveller's own LEFT is the image's right, so
    turning the head left drives the proxy up.
    """
    # Imported here so a missing face model degrades this engine alone.
    from app.engines import face

    try:
        faces = face.detect_faces(path)
    except Exception:
        return None
    if not faces:
        return None
    row = max(faces, key=lambda f: f["box"][2] * f["box"][3])["raw"]
    if row is None or len(row) < 10:
        return None
    right_eye_x, right_eye_y, left_eye_x, left_eye_y, nose_x = (float(v) for v in row[4:9])
    eye_distance = math.hypot(left_eye_x - right_eye_x, left_eye_y - right_eye_y)
    if eye_distance < 1.0:
        return None
    midpoint_x = (right_eye_x + left_eye_x) / 2.0
    return (nose_x - midpoint_x) / eye_distance, eye_distance


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def yaw_delta(paths: list[str]) -> float:
    """Signed movement of the yaw proxy across a sequence. 0.0 when unusable."""
    proxies = [p[0] for p in (yaw_proxy(path) for path in paths[:MAX_FRAMES]) if p]
    if len(proxies) < MIN_FRAMES:
        return 0.0
    k = max(1, len(proxies) // 3)
    return _median(proxies[-k:]) - _median(proxies[:k])


def run(frame_paths: list[str] | None, direction: str = DEFAULT_DIRECTION) -> list[Signal]:
    """Adjudicate one challenge sequence. No frames means no opinion at all —
    an officer uploading a passport file must never see a liveness signal."""
    paths = [p for p in (frame_paths or []) if p and os.path.exists(p)]
    if not paths:
        return []

    used = paths[:MAX_FRAMES]
    measured = [yaw_proxy(path) for path in used]
    usable = [m for m in measured if m]
    n_usable, n_total = len(usable), len(used)

    # checkpoint-4 R2: requiring EVERY frame usable let a spoofer downgrade a
    # FAILED (35) to an unscored INCONCLUSIVE just by losing one frame, and cost
    # genuine head turns their extreme frames where the face partly left the
    # camera. A face in most (>=60%) frames, with at least MIN_FRAMES usable,
    # is now judged. When enough frames were even supplied to judge
    # (n_total >= MIN_FRAMES) and it still can't be, that is as suspicious as a
    # clean failure, so INCONCLUSIVE carries the same weight_override as FAILED.
    if n_usable < MIN_FRAMES or n_usable < MIN_USABLE_FRACTION * n_total:
        weight_override = FAILED_SCORE if n_total >= MIN_FRAMES else None
        return [Signal(
            code="LIVENESS_INCONCLUSIVE", engine="liveness", severity="low",
            weight_override=weight_override,
            message=(f"The liveness challenge could not be judged: a face was "
                     f"found in only {n_usable} of {n_total} camera frames "
                     f"(at least {MIN_FRAMES}, and at least "
                     f"{MIN_USABLE_FRACTION:.0%}, are needed). "
                     f"Ask the traveller to face the camera and repeat it."),
            plain="The camera could not see the traveller's face clearly enough "
                  "during the head-turn check. Ask them to repeat it, facing "
                  "the camera directly.",
            evidence={"frames_used": n_total, "frames_with_face": n_usable})]

    proxies = [m[0] for m in usable]
    eye_distances = [m[1] for m in usable]
    k = max(1, n_usable // 3)
    signed = _median(proxies[-k:]) - _median(proxies[:k])
    sign = DIRECTIONS.get(direction, DIRECTIONS[DEFAULT_DIRECTION])
    towards = "their left" if sign > 0 else "their right"
    delta = signed * sign
    scale_change = (max(eye_distances) - min(eye_distances)) / max(eye_distances)
    evidence = {
        "yaw_delta": round(delta, 4),
        "threshold": YAW_DELTA_THRESHOLD,
        "direction": direction if direction in DIRECTIONS else DEFAULT_DIRECTION,
        "frames_used": n_total,
        "frames_with_face": n_usable,
        "eye_distance_change": round(scale_change, 3),
    }

    if delta >= YAW_DELTA_THRESHOLD:
        return [Signal(
            code="LIVENESS_PASS", engine="liveness", severity="info",
            message=(f"Liveness challenge passed: asked to turn their head to "
                     f"{towards}, the face rotated by {delta:.3f} of an eye width "
                     f"across {n_usable} frames (at least {YAW_DELTA_THRESHOLD} "
                     f"required). A flat photograph cannot do this."),
            plain="The traveller's head visibly turned when asked, which a "
                  "printed photo or phone screen cannot do.",
            evidence=evidence)]

    return [Signal(
        code="LIVENESS_FAILED", engine="liveness", severity="medium",
        weight_override=FAILED_SCORE,
        message=(f"Liveness challenge failed: asked to turn their head to "
                 f"{towards}, the face rotated by only {delta:.3f} of an eye "
                 f"width across {n_usable} frames, where at least "
                 f"{YAW_DELTA_THRESHOLD} is expected — consistent with a "
                 f"photograph held up to the camera "
                 f"(apparent size changed by {scale_change * 100:.0f}% over the "
                 f"same frames). Confirm the traveller in person."),
        plain="The head did not move when asked, which is what happens when "
              "someone holds a photograph up to the camera.",
        evidence=evidence)]
