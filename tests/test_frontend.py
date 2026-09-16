"""Guards for the static frontend. There is no browser test runner, so these
check the contract the page depends on: it is served, it works offline, it
never uses innerHTML, and it carries the design spec's colour tokens."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parent.parent / "static"
FONT_FILES = [
    "IBMPlexSans-Variable-latin.woff2",
    "IBMPlexMono-Regular-latin.woff2",
    "IBMPlexMono-SemiBold-latin.woff2",
    "OFL.txt",
]
COLOUR_TOKENS = {
    "--paper": "#F3F1EA",
    "--surface": "#FBFAF6",
    "--ink": "#16181C",
    "--navy": "#1D3A6E",
    "--altered": "#B3261E",
    "--review": "#955300",
    "--clear": "#1F6B3A",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "fe.db"))
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(config, "EVIDENCE_DIR", str(tmp_path / "evidence"))
    from app.main import app, startup
    startup()
    return TestClient(app)


def test_index_serves_the_screening_form(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert 'id="screen-form"' in html
    for name in ("document", "visa", "selfie"):
        assert re.search(rf'<input[^>]*type="file"[^>]*name="{name}"', html), name
    for name in ("full_name", "dob", "passport_no", "nationality", "email", "phone"):
        assert re.search(rf'<input[^>]*name="{name}"', html), name


@pytest.mark.parametrize("path", ["/static/styles.css", "/static/app.js"]
                         + [f"/static/fonts/{f}" for f in FONT_FILES])
def test_static_assets_are_served(client, path):
    assert client.get(path).status_code == 200


def test_no_network_urls_in_static_files():
    offenders = []
    for p in STATIC.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".css", ".js"):
            text = p.read_text(encoding="utf-8")
            if "http://" in text or "https://" in text:
                offenders.append(str(p.relative_to(STATIC)))
    assert offenders == []


@pytest.mark.parametrize("forbidden", ["innerHTML", "outerHTML", "insertAdjacentHTML",
                                       "document.write", 'HTML"]', "HTML']"])
def test_app_js_never_injects_html(forbidden):
    assert forbidden not in (STATIC / "app.js").read_text(encoding="utf-8")


def test_app_js_counts_checks_from_engines_run():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "engines_run" in js


def test_app_js_validates_evidence_url_before_use():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert r"/^\/evidence\/[0-9a-f]{32}\.jpg$/" in js


def test_app_js_uses_evidence_source_for_exhibit_label():
    """checkpoint-3 ruling 2: the exhibit caption must come from the server's
    evidence_source, not be guessed from scanning signal messages."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "evidence_source" in js
    assert 'evidenceSource === "visa"' in js


def test_app_js_reasons_heading_counts_all_findings():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '"· top "' in js and "nonInfo" in js


def test_index_has_inline_favicon_and_short_nationality_label(client):
    html = client.get("/").text
    assert '<link rel="icon" href="data:,">' in html
    assert re.search(r'<label for="f-nationality"[^>]*>Nationality</label>', html)
    assert 'placeholder="3-letter code, e.g. IND"' in html


@pytest.mark.parametrize("token,hexval", COLOUR_TOKENS.items())
def test_css_defines_colour_tokens(token, hexval):
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert re.search(rf"{re.escape(token)}\s*:\s*{hexval}\s*;", css, re.IGNORECASE), token


# --- T16d Part A: live selfie capture -------------------------------------
# Source-level guards: there is no browser runner, so these assert the
# contract the camera code must keep (no audio, every stream stopped, no
# broken control where getUserMedia does not exist).

def _js() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8")


def test_camera_requests_video_only_never_audio():
    js = _js()
    assert re.search(r"getUserMedia\(\s*\{.{0,200}?audio:\s*false", js, re.S), \
        "getUserMedia must be called with audio: false"
    assert "audio: true" not in js


def test_camera_control_is_created_only_when_mediadevices_exists():
    js = _js()
    guard = js.find("navigator.mediaDevices")
    label = js.find("Use camera")
    assert guard != -1 and label != -1
    assert guard < label, "the mediaDevices guard must come before the camera control"


@pytest.mark.parametrize("path", ["capture", "cancel", "remove", "pagehide"])
def test_every_camera_teardown_path_stops_the_stream(path):
    """Each teardown path is tagged `// teardown(<path>)` and must stop the
    camera within the next few statements. A camera light left on is a bug."""
    js = _js()
    marker = "// teardown(" + path + ")"
    at = js.find(marker)
    assert at != -1, "missing teardown path: " + path
    assert "stopCameraStream()" in js[at:at + 240], path


def test_camera_stop_helper_stops_every_track():
    js = _js()
    assert re.search(r"getTracks\(\)\.forEach\(\s*\(?\s*\w+\s*\)?\s*=>\s*\w+\.stop\(\)", js)


@pytest.mark.parametrize("name", ["NotAllowedError", "NotFoundError", "NotReadableError"])
def test_camera_names_each_permission_failure(name):
    assert name in _js()


def test_camera_capture_makes_a_jpeg_file_for_the_existing_selfie_input():
    js = _js()
    assert '"image/jpeg", 0.92' in js
    assert "DataTransfer" in js
    assert '"selfie.jpg"' in js


def test_css_styles_the_camera_ui():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    for selector in (".camera-stage", ".camera-video", ".camera-actions"):
        assert selector in css, selector


# --- T16e: liveness challenge ---------------------------------------------
# Source-level guards again: the challenge must keep 16d's teardown discipline,
# must not fire without the camera, and must never build HTML from strings.

def test_liveness_button_exists_and_is_a_real_button():
    js = _js()
    assert '"Check liveness"' in js
    assert re.search(r'el\("button",\s*\{[^}]*text:\s*"Check liveness"', js)


def test_liveness_prompts_name_the_direction_asked_for():
    js = _js()
    assert "Look straight at the camera" in js
    assert re.search(r"turn your head[^\"]*LEFT", js, re.I)


def test_liveness_challenge_tears_down_the_camera():
    js = _js()
    at = js.find("// teardown(challenge)")
    assert at != -1, "the challenge must be a tagged teardown path"
    assert "stopCameraStream()" in js[at:at + 240]


def test_cancelling_mid_challenge_clears_the_pending_timer():
    js = _js()
    assert "clearTimeout" in js
    assert "cancelLivenessChallenge" in js


def test_frames_are_sent_as_repeated_selfie_frames_with_the_direction():
    js = _js()
    assert '"selfie_frames"' in js
    assert '"liveness_direction"' in js


def test_frame_count_and_cap_match_the_server():
    js = _js()
    assert re.search(r"LIVENESS_FRAMES\s*=\s*(8|9|10)\b", js)
    from app import config
    count = int(re.search(r"LIVENESS_FRAMES\s*=\s*(\d+)", js).group(1))
    assert count <= config.MAX_LIVENESS_FRAMES


def test_frames_are_cleared_when_the_selfie_is_cleared():
    js = _js()
    assert "clearLivenessFrames" in js


def test_camera_status_line_is_actually_in_the_page():
    """T16d created the aria-live status paragraph but never inserted it, so
    every prompt was invisible. The challenge depends on those prompts."""
    js = _js()
    assert re.search(r'el\("div",\s*\{\s*class:\s*"camera"\s*\}\s*,\s*\[\s*openBtn,\s*status', js)


def test_liveness_engine_has_a_plain_english_name():
    js = _js()
    assert re.search(r'liveness:\s*"[^"]+"', js)


def test_css_styles_the_liveness_prompt():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert ".camera-prompt" in css


# --- checkpoint-4 F3: the getUserMedia-pending state must not look broken ---
def test_open_camera_hides_use_camera_button_before_awaiting_permission():
    js = _js()
    at = js.find("async function openCamera")
    assert at != -1
    body = js[at:js.find("\n  }", at)]
    hide_at = body.find("openBtn.hidden = true")
    await_at = body.find("await navigator.mediaDevices.getUserMedia")
    assert hide_at != -1 and await_at != -1 and hide_at < await_at


def test_open_camera_sets_a_pending_status_before_awaiting_permission():
    js = _js()
    at = js.find("async function openCamera")
    body = js[at:js.find("\n  }", at)]
    status_at = body.find('status.textContent = "Starting camera')
    await_at = body.find("await navigator.mediaDevices.getUserMedia")
    assert status_at != -1 and status_at < await_at


def test_open_camera_disables_capture_before_awaiting_permission():
    js = _js()
    at = js.find("async function openCamera")
    body = js[at:js.find("\n  }", at)]
    running_at = body.find("setChallengeRunning(true)")
    await_at = body.find("await navigator.mediaDevices.getUserMedia")
    assert running_at != -1 and running_at < await_at


def test_open_camera_error_path_restores_the_use_camera_button():
    js = _js()
    at = js.find("async function openCamera")
    body = js[at:js.find("\n  }", at)]
    catch_at = body.find("catch (err)")
    assert catch_at != -1
    assert "closeStage()" in body[catch_at:]   # closeStage restores openBtn.hidden = false


# --- checkpoint-4 R9: cancelLivenessChallenge must wake a pending livenessWait ---
def test_cancel_liveness_challenge_resolves_the_pending_wait():
    js = _js()
    at = js.find("function cancelLivenessChallenge")
    body = js[at:js.find("\n}", at)]
    assert "livenessResolve" in body and "resolve()" in body


def test_liveness_wait_stores_its_resolver_for_cancellation():
    js = _js()
    at = js.find("function livenessWait")
    body = js[at:js.find("\n}", at)]
    assert "livenessResolve = resolve" in body


# --- checkpoint-4 R1: stale liveness frames must not ride along on a later screening ---
def test_run_screening_completion_clears_liveness_frames():
    js = _js()
    at = js.find("function runScreening")
    assert at != -1
    end = js.find("\nfunction ", at + 10)
    body = js[at:end if end != -1 else len(js)]
    assert "clearLivenessFrames()" in body


def test_selfie_input_change_clears_frames_when_not_from_the_camera():
    js = _js()
    setup_at = js.find("function setupSelfieCamera")
    assert setup_at != -1
    at = js.find('input.addEventListener("change"', setup_at)
    assert at != -1, "the selfie file input's own change handler must be present"
    body = js[at:js.find("});", at) + 3]
    assert "clearLivenessFrames" in body
    assert "_fromCamera" in body


def test_publish_selfie_marks_its_own_dispatch_as_from_camera():
    js = _js()
    at = js.find("function publishSelfie")
    body = js[at:js.find("\n  }", at)]
    mark_at = body.find("input._fromCamera = true")
    dispatch_at = body.find("input.dispatchEvent")
    assert mark_at != -1 and mark_at < dispatch_at
