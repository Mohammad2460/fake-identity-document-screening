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
// 4. Submitting
// ---------------------------------------------------------------------------

const form = $("screen-form");
const submitBtn = $("submit-btn");
let lastFormData = null;   // kept so "Try again" can resend the same submission
let lastResult = null;     // the last verdict shown, restored after a 413

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runScreening(new FormData(form));
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
  renderExhibit(data.evidence_url, signals);
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

function renderExhibit(evidenceUrl, signals) {
  const exhibit = $("exhibit");
  exhibit.replaceChildren();
  // Only ever load an evidence image the server names in its own format.
  const validUrl = typeof evidenceUrl === "string"
    && /^\/evidence\/[0-9a-f]{32}\.jpg$/.test(evidenceUrl);
  if (!validUrl) {
    exhibit.hidden = true;
    return;
  }

  const altered = signals.filter((s) => ALTERED_CODES.includes(s.code));
  const onVisa = altered.some((s) => String(s.message || "").startsWith("[visa]"));
  const docLabel = onVisa ? "VISA" : "PASSPORT";
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
