/*
 * Document & Identity Screening — page behaviour.
 *
 * What this file does, top to bottom:
 *   1. Lookup tables (band wording, severity chips, engine names).
 *   2. A tiny helper `el()` that builds DOM elements safely.
 *   3. File drop zones: show the chosen file, "Remove", 15 MB client check.
 *   4. Submitting the form to POST /api/screen.
 *   5. One render function per page state: empty, loading, result, error.
 *
 * SECURITY RULE: never assign HTML strings to an element (the inner-HTML
 * property is banned, and a test enforces it). Signal messages contain whatever the
 * traveller typed, so every server or user string goes in via textContent
 * (which `el()` does for you). Clear elements with replaceChildren().
 */
"use strict";

// ---------------------------------------------------------------------------
// 1. Lookup tables
// ---------------------------------------------------------------------------

const MAX_UPLOAD_BYTES = 15 * 1024 * 1024; // must match config.MAX_UPLOAD_BYTES

const BANDS = {
  CLEAR:  { cls: "band-clear",  label: "CLEAR",
            sentence: "No indicators of forgery or identity fraud were found." },
  REVIEW: { cls: "band-review", label: "MANUAL REVIEW",
            sentence: "Refer to an officer for manual examination before admission." },
  REJECT: { cls: "band-reject", label: "REJECT",
            sentence: "Strong evidence of document forgery or identity fraud." },
};

// Glyph + text on every chip, so severity never depends on colour alone.
const SEVERITIES = {
  critical: { glyph: "■", text: "CRITICAL" },
  high:     { glyph: "▲", text: "HIGH" },
  medium:   { glyph: "◆", text: "MEDIUM" },
  low:      { glyph: "●", text: "LOW" },
  info:     { glyph: "○", text: "INFO" },
};

const ENGINE_NAMES = {
  mrz: "Machine-readable zone",
  fieldforensics: "Field forensics",
  ocr: "Printed text",
  face: "Portrait",
  tamper: "Image integrity",
  metadata: "File metadata",
  crossdoc: "Cross-document",
  watchlist: "Watchlist",
  velocity: "Submission history",
  identity: "Identity details",
  liveness: "Liveness",
};

// Signal codes meaning "this region of the document was altered".
const ALTERED_CODES = ["FF_FIELD_TAMPERED", "FF_PHOTO_TAMPERED", "FF_STAMP_TAMPERED"];

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

// ---------------------------------------------------------------------------
// 2. DOM helper
// ---------------------------------------------------------------------------

/**
 * Build an element. `attrs` may hold `class`, `text` (set as textContent —
 * always safe), or any HTML attribute. `children` are elements or strings.
 *   el("p", { class: "note", text: "Hello" })
 */
function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else node.setAttribute(key, String(value));
  }
  for (const child of children) {
    node.append(child); // append() treats strings as plain text, never HTML
  }
  return node;
}

const $ = (id) => document.getElementById(id);

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  if (bytes >= 1024) return Math.round(bytes / 1024) + " KB";
  return bytes + " B";
}

function plural(n, one, many) {
  return n === 1 ? one : many;
}

// ---------------------------------------------------------------------------
// 3. File drop zones
// ---------------------------------------------------------------------------

const DROPZONE_REST_TEXT = "Choose file or drop here · JPG, PNG or PDF, up to 15 MB";

function setFieldError(fieldName, message) {
  const errorLine = $("e-" + fieldName);
  if (!errorLine) return false;
  errorLine.textContent = message || "";
  errorLine.hidden = !message;
  return true;
}

function clearAllFieldErrors() {
  for (const name of ["document", "visa", "selfie"]) setFieldError(name, "");
}

function setupDropzone(wrapper) {
  const fieldName = wrapper.dataset.fileField;
  const zone = wrapper.querySelector(".dropzone");
  const input = wrapper.querySelector('input[type="file"]');
  const text = wrapper.querySelector(".dropzone-text");
  const removeBtn = wrapper.querySelector(".remove-btn");

  function showCurrentFile() {
    const file = input.files && input.files[0];
    if (!file) {
      text.textContent = DROPZONE_REST_TEXT;
      zone.classList.remove("has-file");
      removeBtn.hidden = true;
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      // Reject before upload, and say exactly why.
      input.value = "";
      showCurrentFile();
      setFieldError(fieldName,
        "This file is " + formatBytes(file.size) + ". The limit is 15 MB.");
      return;
    }
    setFieldError(fieldName, "");
    text.textContent = file.name + " · " + formatBytes(file.size);
    zone.classList.add("has-file");
    removeBtn.hidden = false;
  }

  input.addEventListener("change", showCurrentFile);

  removeBtn.addEventListener("click", () => {
    input.value = "";
    setFieldError(fieldName, "");
    showCurrentFile();
    input.focus();
  });

  // Purely visual hint while a file is dragged over; the browser's own file
  // input handles the actual drop because it covers the zone.
  input.addEventListener("dragenter", () => zone.classList.add("is-dragover"));
  input.addEventListener("dragleave", () => zone.classList.remove("is-dragover"));
  input.addEventListener("drop", () => zone.classList.remove("is-dragover"));
}

document.querySelectorAll("[data-file-field]").forEach(setupDropzone);

// ---------------------------------------------------------------------------
// 3b. Live selfie capture
//
// A camera control is added beside the selfie drop zone ONLY when the browser
// exposes getUserMedia (needs a secure context: localhost counts, a plain
// LAN IP address does not). Where it is missing there is no button at all and
// file upload is the only path — never a control that cannot work.
//
// The captured frame is put into the existing selfie file input via a
// DataTransfer, so submitting is completely unchanged. Nothing is uploaded
// until the officer presses "Screen traveller".
//
// The camera stream MUST be stopped on every exit path. Each one is tagged
// `// teardown(<name>)` and a test asserts the stop call is there.
// ---------------------------------------------------------------------------

const CAMERA_ERRORS = {
  NotAllowedError: "Camera permission was refused. Allow camera access in the browser, or choose a photo file instead.",
  NotFoundError: "No camera was found on this device. Choose a photo file instead.",
  NotReadableError: "The camera is already in use by another app. Close it and try again, or choose a photo file instead.",
  OverconstrainedError: "This camera cannot provide a usable picture. Choose a photo file instead.",
  SecurityError: "The browser blocks the camera on this address. Open the page on this laptop at localhost, or choose a photo file instead.",
};
const CAMERA_ERROR_FALLBACK = "The camera could not be started. Choose a photo file instead.";

// --- Liveness challenge ----------------------------------------------------
// A printed photograph has no nose depth, so turning it moves nothing. We ask
// the traveller to turn their head and send the frames with the normal submit;
// app/engines/liveness.py measures how far the nose moved off the eye midpoint.
// Frames are captured from the SAME stream and the SAME teardown rules apply.
const LIVENESS_FRAMES = 8;          // must be <= config.MAX_LIVENESS_FRAMES
const LIVENESS_FRAME_MS = 380;      // ~3 s of turning
const LIVENESS_SETTLE_MS = 1200;    // "look straight at the camera" first
const LIVENESS_DIRECTION = "left";  // the traveller's own left

let cameraStream = null;
let livenessFrames = [];
let livenessTimer = null;
let livenessAborted = false;

/** The one place a stream is released. Safe to call when nothing is running. */
function stopCameraStream() {
  if (!cameraStream) return;
  cameraStream.getTracks().forEach((track) => track.stop());
  cameraStream = null;
}

/** Drop any frames already captured — the selfie they belong to is gone. */
function clearLivenessFrames() {
  livenessFrames = [];
}

/** Stop a challenge in flight: no pending timer may survive a teardown. */
function cancelLivenessChallenge() {
  livenessAborted = true;
  if (livenessTimer !== null) {
    clearTimeout(livenessTimer);
    livenessTimer = null;
  }
}

function livenessWait(ms) {
  return new Promise((resolve) => {
    livenessTimer = setTimeout(() => {
      livenessTimer = null;
      resolve();
    }, ms);
  });
}

/** Attach the captured challenge frames to a submission. No frames, no field. */
function attachLivenessFrames(formData) {
  if (!livenessFrames.length) return formData;
  formData.set("liveness_direction", LIVENESS_DIRECTION);
  livenessFrames.forEach((blob, i) => {
    formData.append("selfie_frames", blob, "frame" + i + ".jpg");
  });
  return formData;
}

function setupSelfieCamera() {
  const wrapper = document.querySelector('[data-file-field="selfie"]');
  if (!wrapper) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;

  const input = wrapper.querySelector('input[type="file"]');
  const removeBtn = wrapper.querySelector(".remove-btn");

  const openBtn = el("button", { type: "button", class: "btn-secondary camera-btn",
                                 text: "Use camera" });
  const status = el("p", { class: "camera-status t-label", role: "status",
                           "aria-live": "polite" });
  const video = el("video", { class: "camera-video", playsinline: "", muted: "",
                              autoplay: "", "aria-label": "Live camera preview" });
  video.muted = true;
  const canvas = el("canvas", { class: "camera-still", role: "img",
                                "aria-label": "Captured selfie" });
  canvas.hidden = true;
  const captureBtn = el("button", { type: "button", class: "btn-primary camera-capture",
                                    text: "Capture" });
  const cancelBtn = el("button", { type: "button", class: "remove-btn camera-cancel",
                                   text: "Cancel" });
  const retakeBtn = el("button", { type: "button", class: "btn-secondary camera-retake",
                                   text: "Retake" });
  retakeBtn.hidden = true;
  const challengeBtn = el("button", { type: "button", class: "btn-secondary camera-challenge",
                                      text: "Check liveness" });
  const prompt = el("p", { class: "camera-prompt", role: "status", "aria-live": "assertive" });
  prompt.hidden = true;
  const actions = el("div", { class: "camera-actions" },
                     [captureBtn, challengeBtn, retakeBtn, cancelBtn]);
  const stage = el("div", { class: "camera-stage" }, [video, canvas, prompt, actions]);
  stage.hidden = true;

  const block = el("div", { class: "camera" }, [
    openBtn,
    status,
    stage,
    el("p", { class: "camera-note t-label",
              text: "The camera runs on this device. Nothing is sent until you screen the traveller." }),
  ]);
  wrapper.insertBefore(block, $("e-selfie"));

  function setChallengeRunning(running) {
    captureBtn.disabled = running;
    challengeBtn.disabled = running;
    retakeBtn.disabled = running;
    prompt.hidden = !running;
    if (!running) prompt.textContent = "";
  }

  function closeStage() {
    cancelLivenessChallenge();
    setChallengeRunning(false);
    stage.hidden = true;
    openBtn.hidden = false;
    video.hidden = false;
    canvas.hidden = true;
    captureBtn.hidden = false;
    challengeBtn.hidden = false;
    retakeBtn.hidden = true;
    video.srcObject = null;
  }

  async function openCamera() {
    setFieldError("selfie", "");
    cancelLivenessChallenge();
    clearLivenessFrames();
    stopCameraStream();   // never hold two streams at once
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 } },
        audio: false,
      });
    } catch (err) {
      // teardown(error): getUserMedia may have half-opened a device.
      stopCameraStream();
      closeStage();
      status.textContent = "";
      setFieldError("selfie", CAMERA_ERRORS[err && err.name] || CAMERA_ERROR_FALLBACK);
      openBtn.focus();
      return;
    }
    video.srcObject = cameraStream;
    const playing = video.play();
    if (playing && typeof playing.catch === "function") playing.catch(() => {});
    openBtn.hidden = true;
    stage.hidden = false;
    video.hidden = false;
    canvas.hidden = true;
    captureBtn.hidden = false;
    challengeBtn.hidden = false;
    retakeBtn.hidden = true;
    setChallengeRunning(false);
    status.textContent = "Camera on. Press Capture when the face is centred, "
      + "or Check liveness to run the head-turn challenge.";
    captureBtn.focus();
  }

  /** Paint the current video frame onto a canvas at the camera's own size. */
  function drawFrame(target) {
    target.width = video.videoWidth || 640;
    target.height = video.videoHeight || 480;
    target.getContext("2d").drawImage(video, 0, 0, target.width, target.height);
    return target;
  }

  /** Put the still on `canvas` into the existing selfie file input. */
  function publishSelfie() {
    canvas.toBlob((blob) => {
      if (!blob) {
        setFieldError("selfie", CAMERA_ERROR_FALLBACK);
        return;
      }
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], "selfie.jpg", { type: "image/jpeg" }));
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }, "image/jpeg", 0.92);
  }

  function showStill() {
    video.srcObject = null;
    video.hidden = true;
    canvas.hidden = false;
    captureBtn.hidden = true;
    challengeBtn.hidden = true;
    retakeBtn.hidden = false;
  }

  function capture() {
    clearLivenessFrames();   // a plain still carries no challenge evidence
    drawFrame(canvas);
    // teardown(capture): the still is on the canvas; the camera is done.
    stopCameraStream();
    showStill();
    publishSelfie();
    status.textContent = "Selfie captured. Retake it, or screen the traveller.";
    retakeBtn.focus();
  }

  const frameCanvas = document.createElement("canvas");

  /** One challenge frame as a JPEG blob, off-screen so the preview is untouched. */
  function grabFrame() {
    return new Promise((resolve) => {
      drawFrame(frameCanvas).toBlob(resolve, "image/jpeg", 0.85);
    });
  }

  async function runChallenge() {
    livenessAborted = false;
    clearLivenessFrames();
    setChallengeRunning(true);
    status.textContent = "Liveness challenge running.";

    prompt.textContent = "Look straight at the camera…";
    await livenessWait(LIVENESS_SETTLE_MS);
    if (livenessAborted || !cameraStream) return;

    // The frontal frame is both the still selfie and the challenge baseline.
    drawFrame(canvas);
    publishSelfie();

    prompt.textContent = "Now slowly turn your head to your LEFT.";
    for (let i = 0; i < LIVENESS_FRAMES; i += 1) {
      const blob = await grabFrame();
      if (livenessAborted || !cameraStream) return;
      if (blob) livenessFrames.push(blob);
      await livenessWait(LIVENESS_FRAME_MS);
      if (livenessAborted || !cameraStream) return;
    }

    // teardown(challenge): every frame is captured; the camera is done.
    stopCameraStream();
    setChallengeRunning(false);
    showStill();
    status.textContent = "Liveness challenge recorded (" + livenessFrames.length
      + " frames). Screen the traveller to see the result.";
    retakeBtn.focus();
  }

  openBtn.addEventListener("click", openCamera);
  captureBtn.addEventListener("click", capture);
  challengeBtn.addEventListener("click", () => { runChallenge(); });
  retakeBtn.addEventListener("click", openCamera);

  cancelBtn.addEventListener("click", () => {
    // teardown(cancel): the officer backed out of the preview.
    cancelLivenessChallenge();
    clearLivenessFrames();
    stopCameraStream();
    closeStage();
    status.textContent = "Camera off.";
    openBtn.focus();
  });

  if (removeBtn) {
    removeBtn.addEventListener("click", () => {
      // teardown(remove): the selfie was removed, so the camera closes too.
      cancelLivenessChallenge();
      clearLivenessFrames();
      stopCameraStream();
      closeStage();
      status.textContent = "";
    });
  }

  // teardown(pagehide): tab closed, navigated away or backgrounded.
  window.addEventListener("pagehide", () => {
    cancelLivenessChallenge();
    stopCameraStream();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      cancelLivenessChallenge();
      clearLivenessFrames();
      stopCameraStream();
      closeStage();
    }
  });
}

setupSelfieCamera();

// ---------------------------------------------------------------------------
// 4. Submitting
// ---------------------------------------------------------------------------

const form = $("screen-form");
const submitBtn = $("submit-btn");
let lastFormData = null;   // kept so "Try again" can resend the same submission
let lastResult = null;     // the last verdict shown, restored after a 413

form.addEventListener("submit", (event) => {
  event.preventDefault();
  // Challenge frames are not form inputs; they ride along on the same submit.
  runScreening(attachLivenessFrames(new FormData(form)));
});

async function runScreening(formData) {
  lastFormData = formData;
  clearAllFieldErrors();
  renderLoading();

  let response;
  let body = null;
  try {
    response = await fetch("/api/screen", { method: "POST", body: formData });
    body = await response.json().catch(() => null);
  } catch (networkError) {
    renderError();
    return;
  }

  if (response.status === 413) {
    renderTooLarge(body && body.error);
    return;
  }
  if (!response.ok || !body || typeof body.score !== "number") {
    renderError();
    return;
  }
  renderResult(body);
}

// ---------------------------------------------------------------------------
// 5. Rendering — one function per state
// ---------------------------------------------------------------------------

function setBusy(isBusy) {
  submitBtn.disabled = isBusy;
  submitBtn.textContent = isBusy ? "Screening…" : "Screen traveller";
  $("verdict").closest("section").setAttribute("aria-busy", isBusy ? "true" : "false");
}

/** Put a new look and new content into the verdict panel. */
function setVerdict(stateClass, children) {
  const verdict = $("verdict");
  verdict.className = "verdict " + stateClass;
  verdict.replaceChildren(...children);
}

function hideDetailSections() {
  for (const id of ["exhibit", "reasons", "all-output"]) {
    $(id).replaceChildren();
    $(id).hidden = true;
  }
}

function verdictHeading(text, extraClass) {
  return el("h2", { id: "verdict-heading", class: extraClass, tabindex: "-1", text });
}

/* --- Empty: before anything has been screened --- */
function renderEmpty() {
  setBusy(false);
  $("layout").classList.remove("has-result");
  hideDetailSections();
  setVerdict("is-empty", [
    verdictHeading("No traveller screened yet", "t-h2 verdict-title"),
    el("p", { class: "verdict-sentence",
              text: "Submit a passport to see the verdict, the altered fields marked on the document, and every check that ran." }),
  ]);
}

/* --- Loading: request in flight --- */
function renderLoading() {
  setBusy(true);
  hideDetailSections();
  setVerdict("is-loading", [
    verdictHeading("Examining documents", "t-h2 verdict-title"),
    el("p", { class: "verdict-sentence",
              text: "Reading the machine-readable zone, checking every field for alteration, and comparing the portrait. This takes a few seconds." }),
  ]);
}

/* --- Error: server down, network failure, or unreadable response --- */
function renderError() {
  setBusy(false);
  hideDetailSections();
  const retry = el("button", { type: "button", class: "btn-secondary", text: "Try again" });
  retry.addEventListener("click", () => {
    if (lastFormData) runScreening(lastFormData);
  });
  setVerdict("is-error", [
    verdictHeading("Screening could not finish", "t-h2 verdict-title"),
    el("p", { class: "verdict-sentence",
              text: "The screening service did not respond. Check that the server is running, then try again." }),
    retry,
  ]);
  $("verdict-heading").focus();
}

/* --- 413: a file was over the limit. Say so under that file field. --- */
function renderTooLarge(message) {
  const text = message || "A file exceeds the 15 MB upload limit.";
  // The API's message starts with the field name: "visa exceeds the 15 MB ..."
  const fieldName = text.split(" ")[0];
  const shownInline = ["document", "visa", "selfie"].includes(fieldName)
    && setFieldError(fieldName, text);

  if (!shownInline) {
    renderError();
    $("verdict").querySelector(".verdict-sentence").textContent = text;
    return;
  }
  // Put the page back how it was before this attempt.
  if (lastResult) renderResult(lastResult, { moveFocus: false });
  else renderEmpty();
  const input = $("f-" + fieldName);
  if (input) input.focus();
}

/* --- Result: the verdict, the exhibit, the reasons, all output --- */
function renderResult(data, options = { moveFocus: true }) {
  lastResult = data;
  setBusy(false);
  const signals = Array.isArray(data.signals) ? data.signals : [];

  renderVerdict(data, signals);
  renderExhibit(data.evidence_url, data.evidence_source, signals);
  renderReasons(Array.isArray(data.top_reasons) ? data.top_reasons : [], signals);
  renderAllOutput(signals, Array.isArray(data.engine_errors) ? data.engine_errors : []);

  // Below 1100px the verdict moves above the form (CSS reads this class).
  $("layout").classList.add("has-result");
  if (options.moveFocus) {
    const heading = $("verdict-heading");
    heading.focus({ preventScroll: true });
    heading.closest(".verdict").scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }
}

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function renderVerdict(data, signals) {
  const band = BANDS[data.band] || BANDS.REVIEW;
  const checksRun = Array.isArray(data.engines_run) ? data.engines_run.length : 0;

  const caseStrip = [
    "CASE " + String(data.case_id || "").toUpperCase(),
    "SCREENED " + formatTimestamp(new Date()),
    checksRun + " " + plural(checksRun, "CHECK", "CHECKS") + " RUN",
  ].join(" · ");

  setVerdict("is-result " + band.cls, [
    el("div", { class: "score-row" }, [
      el("span", { class: "score", text: data.score }),
      el("span", { class: "t-h2 score-out-of", text: "/100" }),
    ]),
    // The band label is the heading focus moves to: it is the answer.
    verdictHeading(band.label, "band-label verdict-title"),
    el("p", { class: "verdict-sentence", text: band.sentence }),
    el("p", { class: "t-mono-sm case-strip", text: caseStrip }),
  ]);
}

/** "15 SEP 2026 15:04" in the officer's local time. */
function formatTimestamp(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return pad(d.getDate()) + " " + MONTHS[d.getMonth()] + " " + d.getFullYear()
    + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
}

function renderExhibit(evidenceUrl, evidenceSource, signals) {
  const exhibit = $("exhibit");
  exhibit.replaceChildren();
  // Only ever load an evidence image the server names in its own format.
  const validUrl = typeof evidenceUrl === "string"
    && /^\/evidence\/[0-9a-f]{32}\.jpg$/.test(evidenceUrl);
  if (!validUrl) {
    exhibit.hidden = true;
    return;
  }

  // The exhibit image and its caption must describe the same document, so the
  // label comes from the server's evidence_source, not from scanning messages.
  const onVisa = evidenceSource === "visa";
  const docLabel = onVisa ? "VISA" : "PASSPORT";
  const altered = signals.filter((s) => ALTERED_CODES.includes(s.code)
    && (onVisa === String(s.message || "").startsWith("[visa]")));
  const countText = altered.length === 0
    ? "NO FIELD ALTERED"
    : altered.length + " " + plural(altered.length, "FIELD", "FIELDS") + " ALTERED";

  const img = el("img", {
    class: "exhibit-img",
    src: evidenceUrl,
    alt: "Document image with altered regions outlined in red and checked regions outlined in green.",
  });

  exhibit.append(
    el("p", { class: "t-mono-sm exhibit-caption", text: "EXHIBIT A · " + docLabel + " · " + countText }),
    el("div", { class: "exhibit-frame" }, [
      el("div", { class: "exhibit-marks" }, [img]),
      el("div", { class: "t-label legend" }, [
        el("span", { class: "legend-item" }, [
          el("span", { class: "legend-swatch", "aria-hidden": "true" }), "Altered region",
        ]),
        el("span", { class: "legend-item" }, [
          el("span", { class: "legend-swatch is-checked", "aria-hidden": "true" }), "Region checked, consistent",
        ]),
      ]),
    ]),
  );
  exhibit.hidden = false;
}

/** One signal as a card: severity chip, engine name, code, full message. */
function signalCard(signal) {
  const sev = SEVERITIES[signal.severity] || SEVERITIES.info;
  const sevKey = SEVERITIES[signal.severity] ? signal.severity : "info";
  const engineName = ENGINE_NAMES[signal.engine] || String(signal.engine || "");

  return el("li", { class: "card" }, [
    el("div", { class: "card-top" }, [
      el("span", { class: "t-label chip chip-" + sevKey }, [
        el("span", { "aria-hidden": "true", text: sev.glyph }),
        sev.text,
      ]),
      el("span", { class: "t-label card-engine", text: engineName }),
      el("span", { class: "t-mono-sm card-code", text: signal.code }),
    ]),
    el("p", { class: "card-message", text: signal.message }),
  ]);
}

function cardList(signals) {
  return el("ul", { class: "card-list", role: "list" },
    signals.map(signalCard));
}

function renderReasons(reasons, signals) {
  const section = $("reasons");
  // Count every finding (non-info signal), not just the capped top reasons.
  const nonInfo = signals.filter((s) => s.severity !== "info").length;
  const findings = nonInfo + " " + plural(nonInfo, "finding", "findings");
  const countText = nonInfo > reasons.length
    ? "· top " + reasons.length + " of " + findings
    : "· " + findings;
  const heading = el("h2", { class: "t-h2 section-heading" }, [
    "Why ",
    el("span", { class: "count", text: countText }),
  ]);

  const body = reasons.length
    ? cardList(reasons)
    : el("p", { class: "card is-none", text: "No check raised a concern." });

  section.replaceChildren(heading, body);
  section.hidden = false;
}

function renderAllOutput(signals, engineErrors) {
  const section = $("all-output");
  const inner = [];

  if (engineErrors.length) {
    const n = engineErrors.length;
    inner.push(el("div", { class: "engine-errors" }, [
      el("p", { text: n + " " + plural(n, "check", "checks")
                      + " could not complete. The verdict uses the checks that did." }),
      el("ul", { class: "t-mono-sm" }, engineErrors.map((line) => el("li", { text: line }))),
    ]));
  }
  inner.push(cardList(signals));

  const details = el("details", { class: "all-output" }, [
    el("summary", { class: "t-label", text: "All check results · " + signals.length }),
    el("div", { class: "all-output-body" }, inner),
  ]);

  section.replaceChildren(details);
  section.hidden = false;
}
