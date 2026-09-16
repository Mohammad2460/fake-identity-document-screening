"""Liveness challenge-response over synthesised frame sequences.

There is no recorded human here (hard rule 1). "Live" frames are a committed
SFHQ crop warped as a turning head; "photo" frames are the same crop shifted
and rescaled, which is what a printed photograph held to a webcam does.
"""
import os

import pytest
from PIL import Image

from app.engines import liveness

pytestmark = pytest.mark.skipif(
    not os.path.exists("models/face_detection_yunet_2023mar.onnx"),
    reason="face models not downloaded",
)

FACES_DIR = "data/faces"
FACE_A = os.path.join(FACES_DIR, "sfhq_00.jpg")
FACE_B = os.path.join(FACES_DIR, "sfhq_02.jpg")

no_face_data = pytest.mark.skipif(
    not os.path.exists(FACE_A), reason="data/faces crops not present")


def codes(signals):
    return [s.code for s in signals]


@pytest.fixture
def blank(tmp_path):
    p = tmp_path / "blank.png"
    Image.new("RGB", (320, 320), "white").save(p)
    return str(p)


# --- no frames: file-upload demos must be untouched ------------------------

def test_no_frames_emits_no_signal_at_all():
    assert liveness.run([]) == []


def test_none_frames_emits_no_signal_at_all():
    assert liveness.run(None) == []


# --- too few / unusable frames --------------------------------------------

def test_two_frames_are_inconclusive(blank):
    signals = liveness.run([blank, blank])
    assert codes(signals) == ["LIVENESS_INCONCLUSIVE"]
    assert signals[0].severity == "low"


def test_frames_without_a_face_are_inconclusive(blank):
    signals = liveness.run([blank] * 6)
    assert codes(signals) == ["LIVENESS_INCONCLUSIVE"]
    assert signals[0].severity == "low"


@no_face_data
def test_face_lost_mid_sequence_is_inconclusive(tmp_path, blank):
    from scripts.tune_liveness import live_sequence
    frames = live_sequence(FACE_A, str(tmp_path), "l")
    frames[3] = blank        # the traveller stepped out of shot
    signals = liveness.run(frames)
    assert codes(signals) == ["LIVENESS_INCONCLUSIVE"]


def test_unreadable_frames_do_not_raise(tmp_path):
    bad = tmp_path / "broken.jpg"
    bad.write_bytes(b"not an image")
    signals = liveness.run([str(bad)] * 5)
    assert codes(signals) == ["LIVENESS_INCONCLUSIVE"]


# --- the two verdicts ------------------------------------------------------

@no_face_data
@pytest.mark.parametrize("name", [f"sfhq_0{i}.jpg" for i in range(7)])
def test_a_turning_head_passes(tmp_path, name):
    from scripts.tune_liveness import live_sequence
    src = os.path.join(FACES_DIR, name)
    if not os.path.exists(src):
        pytest.skip("crop missing")
    frames = live_sequence(src, str(tmp_path), "l")
    signals = liveness.run(frames)
    assert codes(signals) == ["LIVENESS_PASS"], signals[0].message
    assert signals[0].severity == "info"
    assert signals[0].evidence["yaw_delta"] >= liveness.YAW_DELTA_THRESHOLD


@no_face_data
@pytest.mark.parametrize("name", [f"sfhq_0{i}.jpg" for i in range(8)])
def test_a_static_photograph_fails(tmp_path, name):
    from scripts.tune_liveness import photo_sequence
    src = os.path.join(FACES_DIR, name)
    if not os.path.exists(src):
        pytest.skip("crop missing")
    frames = photo_sequence(src, str(tmp_path), "s")
    signals = liveness.run(frames)
    assert codes(signals) == ["LIVENESS_FAILED"], signals[0].message
    assert signals[0].severity == "medium"


@no_face_data
@pytest.mark.parametrize("name", [f"sfhq_0{i}.jpg" for i in range(8)])
def test_a_flat_photo_rotated_about_its_own_axis_fails(tmp_path, name):
    """Perspective on a flat plane is not a head turn: the nose does not move
    off the eye midpoint, so this must not pass."""
    from scripts.tune_liveness import plane_sequence
    src = os.path.join(FACES_DIR, name)
    if not os.path.exists(src):
        pytest.skip("crop missing")
    signals = liveness.run(plane_sequence(src, str(tmp_path), "p"))
    assert codes(signals) == ["LIVENESS_FAILED"], signals[0].message


# --- explainability and safety limits --------------------------------------

@no_face_data
def test_failure_message_names_the_measurement(tmp_path):
    from scripts.tune_liveness import photo_sequence
    signals = liveness.run(photo_sequence(FACE_A, str(tmp_path), "s"))
    msg = signals[0].message
    assert str(liveness.YAW_DELTA_THRESHOLD) in msg
    assert "photograph" in msg.lower()


@no_face_data
def test_no_liveness_signal_is_ever_above_medium(tmp_path):
    from scripts.tune_liveness import live_sequence, photo_sequence
    for frames in (live_sequence(FACE_A, str(tmp_path), "l"),
                   photo_sequence(FACE_A, str(tmp_path), "s")):
        for s in liveness.run(frames):
            assert s.severity in ("info", "low", "medium")


@no_face_data
def test_direction_is_respected(tmp_path):
    """The same turn, asked for in the other direction, is not a pass."""
    from scripts.tune_liveness import live_sequence
    frames = live_sequence(FACE_A, str(tmp_path), "l")
    left = liveness.run(frames, direction="left")
    right = liveness.run(frames, direction="right")
    assert codes(left) == ["LIVENESS_PASS"]
    assert codes(right) == ["LIVENESS_FAILED"]


def test_unknown_direction_falls_back_without_raising(blank):
    signals = liveness.run([blank] * 5, direction="sideways")
    assert codes(signals) == ["LIVENESS_INCONCLUSIVE"]


@no_face_data
def test_frames_are_capped_so_a_flood_cannot_stall_a_screening(tmp_path):
    from scripts.tune_liveness import photo_sequence
    frames = photo_sequence(FACE_A, str(tmp_path), "s") * 20
    signals = liveness.run(frames)
    assert signals[0].evidence["frames_used"] <= liveness.MAX_FRAMES
