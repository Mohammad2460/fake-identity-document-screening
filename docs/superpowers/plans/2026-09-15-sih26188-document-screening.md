# SIH26188 — AI-Based Fake Identity & Document Screening System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Problem statement (SIH26188, Ministry of Home Affairs), verbatim:**

> Identity documents such as passports, visas etc. can be forged or tampered. Manual verification is time-consuming and can lead to human errors. Forged documents can contain altered photographs, names, DOBs, or visa stamps. High volumes of documents make manual inspection inefficient.

**Goal:** A locally-runnable screening service that ingests a passport or visa image plus claimed applicant details, runs nine independent forensic and rules engines, and returns an explainable 0-100 fraud risk score that names **which field was tampered** and shows it boxed on an annotated evidence image.

**Architecture:** One Python process. FastAPI serves both the JSON API and a static vanilla-JS frontend — no Node, no bundler, no build step, no CORS. Each detection concern is an isolated module under `app/engines/` consuming an input bundle and emitting `list[Signal]`. `app/pipeline.py` fans out to every engine; `app/scoring.py` folds signals into a weighted score and band. Engines degrade gracefully: any engine that raises returns an `ENGINE_ERROR` signal rather than failing the request, so the demo can never hard-crash on a judge's weird upload.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, OpenCV, Pillow, RapidOCR (ONNX — PaddleOCR's models without PaddlePaddle), pypdf, RapidFuzz, SQLite (stdlib), pytest. Frontend: HTML + Tailwind CDN + vanilla JS.

---

## The four attack types named in the PS, and who catches each

| PS says | Owning engine | Method |
|---|---|---|
| altered **photographs** | `fieldforensics` + `face` | per-region ELA on the portrait; selfie-to-portrait biometric match |
| altered **names** | `mrz` + `ocr` + `fieldforensics` | name vs MRZ encoding; name vs printed text; per-field ELA |
| altered **DOBs** | `mrz` + `fieldforensics` | ICAO check digit on the DOB; per-field ELA |
| forged **visa stamps** | `fieldforensics` | per-region ELA on the stamp area |
| **high volumes** | `batch` | CSV bulk screening + dashboard |

## The differentiator — field-level forensics (Task 10)

Everyone else's project outputs *"this document is 78% fake."*
Ours outputs **"the DOB field was altered — here it is, circled in red."**

OCR returns a bounding box per text field. We run ELA **inside each box separately** and find the box whose compression residual is a statistical outlier against its neighbours. That field was retyped after the document was issued. The same method runs on the portrait region and the visa stamp region.

**This is the centerpiece: the innovation claim, the demo moment, and the best visual, in one engine. Protect its schedule.**

---

## Global Constraints

Every task's requirements implicitly include this section.

- **Python 3.13.** Verified working. `.venv` at repo root.
- **Scope is passports and visas.** Border control / Bureau of Immigration. Not Aadhaar, not PAN, not domestic Indian ID. A feature that does not help screen a passport or visa is out of scope.
- **Zero system-level dependencies.** Everything installs via `pip` alone. No PaddlePaddle, no dlib, no tesseract, no cmake, no MySQL server. A teammate's laptop failing an install at hour 20 loses the hackathon.
- **Pinned dependency set** (verified to resolve together on 3.13):
  `fastapi`, `uvicorn`, `python-multipart`, `pillow`, `opencv-python`, `rapidocr-onnxruntime`, `pypdf`, `rapidfuzz`, `pytest`, `httpx`
- **Only `opencv-python`, never `opencv-contrib-python` alongside it.** `rapidocr-onnxruntime` already depends on `opencv-python`; installing contrib as well puts two packages in the same `cv2` namespace, which breaks imports unpredictably. `FaceDetectorYN`, `FaceRecognizerSF` and ORB are all in standard `opencv-python`.
- **Offline-capable.** No network on the request path. No LLM API, no government API. Judging-day wifi must be irrelevant — we switch it off on stage deliberately. ONNX models download once during setup.
- **No real identity documents, ever.** Not scraped, not a teammate's, not your own. Demo data comes from `scripts/make_samples.py`; accuracy numbers come from the SIDTD dataset (1,900 bona fide + 1,900 labelled forgeries, CC BY-SA 3.0). A real document in a git repo is a permanent leak and a judging liability.
- **Every engine degrades, never crashes.** An engine raising an exception must be caught by the pipeline and converted into a signal. A malformed upload returns a scored result, not a 500.
- **Every signal is explainable.** No signal may contribute to the score without a human-readable `message` naming what was checked and what was found. Explainability *is* the product — both the PS and our pitch say so.
- **Risk bands:** `0-29 = CLEAR (green)`, `30-64 = REVIEW (amber)`, `65-100 = REJECT (red)`.
- **Commit after every task.** The history is evidence of process for judges.

---

## Team Roles (6 nominal, built to survive 2 working)

The plan assumes **the Lead plus Claude carries the critical path alone**. Every other role is additive — if that person vanishes, the demo still works. Nothing on the critical path may depend on a teammate showing up.

| # | Role | Owns | Critical path? |
|---|------|------|----------------|
| 1 | **Lead / Driver** | Runs Claude, executes T0-T15, git, demo laptop | **YES — the whole build** |
| 2 | **Forensics Support** | T16 samples, adversarial testing, threshold calibration | No |
| 3 | **Frontend Polish** | T15 visual pass | No |
| 4 | **Data / QA** | SIDTD download + accuracy run, watchlist, test matrix | No |
| 5 | **Pitch / Docs** | Slides, 4-minute script, README, judge Q&A | No (highest non-code score impact) |
| 6 | **Floater** | Backup laptop, screen recording, timekeeping | No |

**If only 2-3 show up:** Lead takes 1+2, second takes 5, third takes 3+4.

---

## Phase Timeline (36h)

| Phase | Hours | Tasks | Exit gate |
|-------|-------|-------|-----------|
| **0 — Foundation** | 0-2 | T0, T1 | `uvicorn` boots, `/health` 200, deps import, pytest runs |
| **1 — Rules core** | 2-8 | T2-T6 | MRZ, identity, watchlist, scoring, storage green. **Demoable product on its own.** |
| **2 — Forensics** | 8-18 | T7-T11 | Field-level forensics localizes a tampered DOB on a real sample |
| **3 — Surface** | 18-24 | T12-T15 | Upload in the browser, see a verdict with the bad field boxed |
| **4 — Demo assets** | 24-29 | T16, T17 | Seven samples spanning CLEAR/REVIEW/REJECT, thresholds calibrated |
| **5 — Harden & rehearse** | 29-34 | T18 | Cold start on another laptop, two dress rehearsals, video backup |
| **Buffer** | 34-36 | — | Build nothing new. Fix only what rehearsal broke. Sleep. |

**Hard rule:** at hour 24, whatever is not working gets cut, not fixed. A polished 6-engine demo beats a broken 9-engine one.

---

## Data

Three sources, all synthetic. Storage is three things, only one of them a database.

| What | Where | Purpose |
|---|---|---|
| Demo samples | `data/samples/*.jpg` — **files on disk**, generated by `scripts/make_samples.py` | The seven scripted demo cases. Full control over what each triggers. |
| Watchlist | `data/watchlist.csv` — **one CSV** | Synthetic sanctions/PEP names to screen against |
| Case history | `cases.db` — **SQLite**, one row per screening | Cross-document and duplicate detection, plus the dashboard |
| Accuracy | **SIDTD** (external, downloaded by Data/QA) | One real, quotable detection rate. Never invent a number. |

**We need zero genuine documents.** Every check is self-contained: MRZ check digits prove the document against itself, and field-level ELA compares each field against the other fields on the same page. This is also why the system runs fully offline with no government API.

---

## File Structure

```
app/
  main.py              FastAPI app: routes, static mount, error handling
  config.py            Signal weights, band thresholds, tunables
  models.py            Signal, ScreeningInput, ScreeningResult dataclasses
  db.py                SQLite schema + case persistence
  pipeline.py          Fan-out orchestrator; catches per-engine failures
  scoring.py           Weighted signal -> score -> band + top reasons
  report.py            Printable analyst case report (optional, T19)
  annotate.py          Draws the evidence image with tampered regions boxed
  engines/
    __init__.py
    mrz.py             MRZ parse + ICAO 9303 check digits
    identity.py        Synthetic-identity heuristics on claimed fields
    watchlist.py       Fuzzy sanctions/PEP name match
    velocity.py        Cross-submission duplicate & burst detection
    metadata.py        EXIF + PDF provenance forensics
    tamper.py          Whole-image ELA, copy-move (ORB), noise inconsistency
    ocr.py             RapidOCR text + bounding boxes, printed-vs-typed check
    fieldforensics.py  Per-region ELA -> which field was altered  ⭐
    face.py            Portrait detection (YuNet), selfie match (SFace)
    crossdoc.py        Passport vs visa vs prior submissions
static/
  index.html           Single page UI
  app.js               Upload, render verdict, show evidence image
  styles.css           Small overrides on Tailwind CDN
data/
  watchlist.csv
  samples/             Generated sample cases
  evidence/            Annotated evidence images (generated per case)
models/                YuNet + SFace ONNX (downloaded by script)
scripts/
  make_samples.py      Generate clean + forged passports and visas
  download_models.py   Fetch face ONNX models
  batch_screen.py      Bulk CSV screening (T17)
tests/                 pytest, one file per engine
```

**Decomposition rule:** one engine per file, one responsibility per engine, identical signature across engines. This is what lets tasks be worked in any order and lets a weak engine be cut at hour 24 by setting one weight to `0.0`.

---

## Task 0: Foundation — deps, skeleton, boot proof

**Why first:** this task exists to fail fast. If `opencv-python` or `rapidocr-onnxruntime` misbehaves on this machine, you learn at hour 0 with 34 hours to re-plan, not at hour 20.

**Files:**
- Create: `requirements.txt`, `.gitignore`, `pytest.ini`, `app/__init__.py`, `app/main.py`, `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing
- Produces: `app.main:app` (FastAPI instance) — every later task mounts onto this

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi
uvicorn
python-multipart
pillow
opencv-python
rapidocr-onnxruntime
pypdf
rapidfuzz
pytest
httpx
```

- [ ] **Step 2: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
data/samples/*
!data/samples/.gitkeep
models/*.onnx
cases.db
.pytest_cache/
```

- [ ] **Step 2b: Write `pytest.ini`**

Without this, pytest puts `tests/` on the import path instead of the repo root, and every `from app...` in every test fails.

```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 3: Install and verify the risky imports**

Run:
```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -c "import cv2, rapidocr_onnxruntime, PIL, pypdf, rapidfuzz, fastapi; print(cv2.__version__); print(hasattr(cv2,'FaceDetectorYN'), hasattr(cv2,'FaceRecognizerSF'))"
```
Expected: an OpenCV version string, then `True True`.

**If the second line prints `False False`:** the face engine (Task 10) is cut. Delete it from the plan, redistribute its 12 weight points to `tamper` and `ocr` in `config.py`, and move on. Do not spend more than 15 minutes here.

- [ ] **Step 4: Write the smoke test**

```python
# tests/test_smoke.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] **Step 5: Run it to watch it fail**

Run: `./.venv/bin/pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 6: Write the minimal app**

```python
# app/main.py
from fastapi import FastAPI

app = FastAPI(title="Fake Identity & Document Screening System")

@app.get("/health")
def health():
    return {"status": "ok"}
```

Also create an empty `app/__init__.py` and `app/engines/__init__.py`.

- [ ] **Step 7: Run the test to verify it passes**

Run: `./.venv/bin/pytest tests/test_smoke.py -v`
Expected: PASS, 1 passed

- [ ] **Step 8: Prove it boots for real**

Run: `./.venv/bin/uvicorn app.main:app --reload --port 8000`
Then in another terminal: `curl localhost:8000/health`
Expected: `{"status":"ok"}`

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: project skeleton with health endpoint and verified deps"
```

---

## Task 1: Domain model and scoring config

**Files:**
- Create: `app/models.py`, `app/config.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `Signal(code: str, engine: str, severity: str, message: str, weight_override: float | None = None, evidence: dict | None = None)` — `severity` is one of `"info" | "low" | "medium" | "high" | "critical"`
  - `ScreeningInput(claimed: dict, doc_path: str | None, visa_path: str | None, selfie_path: str | None)`
  - `ScreeningResult(case_id: str, score: int, band: str, signals: list[Signal], engine_errors: list[str], evidence_path: str | None)`
  - `config.SEVERITY_POINTS: dict[str, float]`, `config.ENGINE_WEIGHTS: dict[str, float]`, `config.BANDS`, `config.EVIDENCE_DIR`

**Design note:** severity carries the points, engine weight scales them. This means an engine can be tuned or cut without touching any signal definition — critical at hour 22 when you need to silence a noisy engine in one line.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from app.models import Signal, ScreeningResult
from app import config

def test_signal_has_required_fields():
    s = Signal(code="MRZ_CHECKSUM_FAIL", engine="mrz", severity="high",
               message="Document number check digit mismatch")
    assert s.code == "MRZ_CHECKSUM_FAIL"
    assert s.severity == "high"
    assert s.evidence == {}

def test_every_engine_has_a_weight():
    for engine in config.ENGINE_WEIGHTS:
        assert config.ENGINE_WEIGHTS[engine] >= 0

def test_severity_points_are_ordered():
    p = config.SEVERITY_POINTS
    assert p["info"] < p["low"] < p["medium"] < p["high"] < p["critical"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: Write `app/models.py`**

```python
from dataclasses import dataclass, field

SEVERITIES = ("info", "low", "medium", "high", "critical")

@dataclass
class Signal:
    code: str
    engine: str
    severity: str
    message: str
    weight_override: float | None = None
    evidence: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.severity not in SEVERITIES:
            raise ValueError(f"bad severity {self.severity!r}")

@dataclass
class ScreeningInput:
    claimed: dict = field(default_factory=dict)
    doc_path: str | None = None
    visa_path: str | None = None
    selfie_path: str | None = None

@dataclass
class ScreeningResult:
    case_id: str
    score: int
    band: str
    signals: list[Signal] = field(default_factory=list)
    engine_errors: list[str] = field(default_factory=list)
    evidence_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "score": self.score,
            "band": self.band,
            "engine_errors": self.engine_errors,
            "evidence_path": self.evidence_path,
            "signals": [
                {"code": s.code, "engine": s.engine, "severity": s.severity,
                 "message": s.message, "evidence": s.evidence}
                for s in self.signals
            ],
        }
```

- [ ] **Step 4: Write `app/config.py`**

```python
SEVERITY_POINTS = {
    "info": 0.0,
    "low": 6.0,
    "medium": 15.0,
    "high": 30.0,
    "critical": 60.0,
}

# Scales every signal an engine emits. Set to 0.0 to cut an engine instantly.
ENGINE_WEIGHTS = {
    "mrz": 1.0,
    "fieldforensics": 1.0,   # the centerpiece
    "identity": 1.0,
    "watchlist": 1.0,
    "velocity": 0.8,
    "metadata": 0.9,
    "tamper": 1.0,
    "ocr": 0.9,
    "face": 1.0,
    "crossdoc": 1.0,
}

BANDS = [(30, "CLEAR"), (65, "REVIEW"), (101, "REJECT")]

MAX_SCORE = 100
UPLOAD_DIR = "data/uploads"
EVIDENCE_DIR = "data/evidence"
DB_PATH = "cases.db"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_models.py -v`
Expected: PASS, 3 passed

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/config.py tests/test_models.py
git commit -m "feat: signal domain model and scoring configuration"
```

---

## Task 2: MRZ engine — parse and ICAO 9303 check digits

**Why this task is the demo centerpiece:** MRZ check digits are real, published, verifiable cryptographic-ish arithmetic. When a judge asks "is this actually detecting anything or is it a mock?", you change one character in an MRZ string on screen and the verdict flips to REJECT. Nothing else in the build is this convincing per line of code.

**Files:**
- Create: `app/engines/mrz.py`, `tests/test_mrz.py`

**Interfaces:**
- Consumes: `Signal` from `app.models`
- Produces:
  - `check_digit(s: str) -> int`
  - `parse_td3(line1: str, line2: str) -> dict` — returns keys `surname, given_names, doc_number, nationality, dob, sex, expiry, country`
  - `run(mrz_lines: list[str], claimed: dict) -> list[Signal]`

**Reference — ICAO 9303 check digit:** weights cycle `7,3,1`. `<` = 0, digits = value, `A`-`Z` = 10-35 (i.e. `ord(c) - 55`). Sum, mod 10.

**Verified test vectors** (these are the published ICAO Doc 9303 examples — confirmed correct, do not change them):
- `check_digit("L898902C3") == 6`
- `check_digit("740812") == 2`
- `check_digit("120415") == 9`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mrz.py
import pytest
from app.engines import mrz

# Canonical ICAO Doc 9303 TD3 specimen
L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"

def test_check_digit_matches_icao_examples():
    assert mrz.check_digit("L898902C3") == 6
    assert mrz.check_digit("740812") == 2
    assert mrz.check_digit("120415") == 9

def test_check_digit_treats_filler_as_zero():
    assert mrz.check_digit("<<<") == 0

def test_parse_td3_extracts_fields():
    f = mrz.parse_td3(L1, L2)
    assert f["surname"] == "ERIKSSON"
    assert f["given_names"] == "ANNA MARIA"
    assert f["doc_number"] == "L898902C3"
    assert f["nationality"] == "UTO"
    assert f["dob"] == "740812"
    assert f["sex"] == "F"
    assert f["expiry"] == "120415"

def test_clean_mrz_emits_no_high_signals():
    signals = mrz.run([L1, L2], {"full_name": "ANNA MARIA ERIKSSON"})
    assert not [s for s in signals if s.severity in ("high", "critical")]

def test_tampered_document_number_is_detected():
    bad_l2 = "L898902C96UTO7408122F1204159ZE184226B<<<<<10"
    signals = mrz.run([L1, bad_l2], {})
    codes = [s.code for s in signals]
    assert "MRZ_DOCNUM_CHECKSUM_FAIL" in codes

def test_name_mismatch_against_claimed_identity():
    signals = mrz.run([L1, L2], {"full_name": "JOHN SMITH"})
    assert "MRZ_NAME_MISMATCH" in [s.code for s in signals]

def test_malformed_input_does_not_raise():
    signals = mrz.run(["garbage"], {})
    assert "MRZ_MALFORMED" in [s.code for s in signals]
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_mrz.py -v`
Expected: FAIL — `ImportError: cannot import name 'mrz'`

- [ ] **Step 3: Write `app/engines/mrz.py`**

```python
"""ICAO Doc 9303 machine-readable zone parsing and validation."""
from app.models import Signal

FILLER = "<"

def _char_value(c: str) -> int:
    if c == FILLER:
        return 0
    if c.isdigit():
        return int(c)
    if "A" <= c <= "Z":
        return ord(c) - 55
    raise ValueError(f"invalid MRZ character {c!r}")

def check_digit(s: str) -> int:
    weights = (7, 3, 1)
    return sum(_char_value(c) * weights[i % 3] for i, c in enumerate(s)) % 10

def _names(line1: str) -> tuple[str, str]:
    body = line1[5:]
    surname, _, given = body.partition("<<")
    clean = lambda x: " ".join(p for p in x.split(FILLER) if p)
    return clean(surname), clean(given)

def parse_td3(line1: str, line2: str) -> dict:
    surname, given = _names(line1)
    return {
        "country": line1[2:5].replace(FILLER, ""),
        "surname": surname,
        "given_names": given,
        "doc_number_raw": line2[0:9],
        "dob_raw": line2[13:19],
        "expiry_raw": line2[21:27],
        "doc_number": line2[0:9].replace(FILLER, ""),
        "doc_number_cd": line2[9],
        "nationality": line2[10:13].replace(FILLER, ""),
        "dob": line2[13:19],
        "dob_cd": line2[19],
        "sex": line2[20],
        "expiry": line2[21:27],
        "expiry_cd": line2[27],
        "personal_number": line2[28:42],
        "personal_number_cd": line2[42],
        "final_cd": line2[43],
    }

_FIELD_CHECKS = [
    ("doc_number_raw", "doc_number_cd", "MRZ_DOCNUM_CHECKSUM_FAIL", "document number"),
    ("dob_raw", "dob_cd", "MRZ_DOB_CHECKSUM_FAIL", "date of birth"),
    ("expiry_raw", "expiry_cd", "MRZ_EXPIRY_CHECKSUM_FAIL", "expiry date"),
]

def run(mrz_lines: list[str], claimed: dict) -> list[Signal]:
    signals: list[Signal] = []

    if len(mrz_lines) < 2 or len(mrz_lines[0]) < 44 or len(mrz_lines[1]) < 44:
        return [Signal(
            code="MRZ_MALFORMED", engine="mrz", severity="medium",
            message="Machine-readable zone is missing or not a valid 2x44 TD3 block.",
            evidence={"lines": mrz_lines},
        )]

    try:
        f = parse_td3(mrz_lines[0], mrz_lines[1])
    except ValueError as e:
        return [Signal(code="MRZ_MALFORMED", engine="mrz", severity="medium",
                       message=f"MRZ contains invalid characters: {e}")]

    for raw_key, cd_key, code, label in _FIELD_CHECKS:
        raw = f[raw_key]
        expected = check_digit(raw)
        actual = f[cd_key]
        if not actual.isdigit() or int(actual) != expected:
            signals.append(Signal(
                code=code, engine="mrz", severity="high",
                message=(f"MRZ {label} check digit is {actual}, but the printed value "
                         f"{raw!r} computes to {expected}. Field was altered."),
                evidence={"field": raw, "expected": expected, "found": actual},
            ))

    claimed_name = (claimed.get("full_name") or "").strip().upper()
    if claimed_name:
        mrz_name = f"{f['given_names']} {f['surname']}".strip()
        if set(claimed_name.split()) != set(mrz_name.split()):
            signals.append(Signal(
                code="MRZ_NAME_MISMATCH", engine="mrz", severity="high",
                message=(f"Claimed name {claimed_name!r} does not match the name "
                         f"encoded in the MRZ ({mrz_name!r})."),
                evidence={"claimed": claimed_name, "mrz": mrz_name},
            ))

    if not signals:
        signals.append(Signal(
            code="MRZ_ALL_CHECKS_PASS", engine="mrz", severity="info",
            message="All MRZ check digits are valid and the name matches the claim.",
            evidence={"doc_number": f["doc_number"], "nationality": f["nationality"]},
        ))
    return signals
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_mrz.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add app/engines/mrz.py tests/test_mrz.py
git commit -m "feat: MRZ engine with ICAO 9303 check digit validation"
```

---

## Task 3: Identity engine — synthetic-identity heuristics

**Scope note:** the PS title is "Fake **Identity** & Document Screening". This engine screens the *claimed person*, not the document — a fabricated applicant who has never existed. Passport/visa context, so no Aadhaar or PAN validators.

**Files:**
- Create: `app/engines/identity.py`, `tests/test_identity.py`

**Interfaces:**
- Consumes: `Signal`
- Produces:
  - `passport_number_plausible(num: str) -> bool`
  - `run(claimed: dict) -> list[Signal]` — `claimed` keys: `full_name, dob, passport_no, nationality, email, phone, address`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_identity.py
from app.engines import identity

def test_passport_number_format():
    assert identity.passport_number_plausible("L898902C3") is True
    assert identity.passport_number_plausible("AB1") is False
    assert identity.passport_number_plausible("!!!!###") is False

def test_clean_identity_produces_no_high_signals():
    signals = identity.run({
        "full_name": "Anna Maria Eriksson", "dob": "1974-08-12",
        "passport_no": "L898902C3", "nationality": "UTO",
        "email": "anna.eriksson@gmail.com", "phone": "9845012763",
    })
    assert not [s for s in signals if s.severity in ("high", "critical")]

def test_disposable_email_flagged():
    signals = identity.run({"email": "throwaway@mailinator.com"})
    assert "ID_DISPOSABLE_EMAIL" in [s.code for s in signals]

def test_implausible_dob_flagged():
    assert "ID_DOB_IMPLAUSIBLE" in [s.code for s in identity.run({"dob": "2025-01-01"})]
    assert "ID_DOB_IMPLAUSIBLE" in [s.code for s in identity.run({"dob": "1890-01-01"})]

def test_unparseable_dob_flagged():
    assert "ID_DOB_UNPARSEABLE" in [s.code for s in identity.run({"dob": "not a date"})]

def test_keyboard_pattern_name_flagged():
    signals = identity.run({"full_name": "Asdf Qwerty"})
    assert "ID_NAME_SUSPICIOUS" in [s.code for s in signals]

def test_single_token_name_is_low_severity():
    signals = identity.run({"full_name": "Madonna"})
    assert "ID_NAME_SINGLE_TOKEN" in [s.code for s in signals]

def test_sequential_phone_flagged():
    signals = identity.run({"phone": "1234567890"})
    assert "ID_PHONE_SEQUENTIAL" in [s.code for s in signals]

def test_descending_phone_flagged():
    signals = identity.run({"phone": "9876543210"})
    assert "ID_PHONE_SEQUENTIAL" in [s.code for s in signals]

def test_realistic_phone_not_flagged():
    signals = identity.run({"phone": "9845012763"})
    assert "ID_PHONE_SEQUENTIAL" not in [s.code for s in signals]

def test_repeated_digit_phone_flagged():
    signals = identity.run({"phone": "9999999999"})
    assert "ID_PHONE_SEQUENTIAL" in [s.code for s in signals]

def test_email_name_divergence_flagged():
    signals = identity.run({"full_name": "Anna Eriksson", "email": "xk92mzq7@gmail.com"})
    assert "ID_EMAIL_NAME_DIVERGENCE" in [s.code for s in signals]

def test_malformed_passport_number_flagged():
    signals = identity.run({"passport_no": "!!"})
    assert "ID_PASSPORT_FORMAT_ODD" in [s.code for s in signals]
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_identity.py -v`
Expected: FAIL — `ImportError: cannot import name 'identity'`

- [ ] **Step 3: Write `app/engines/identity.py`**

```python
"""Screens the claimed person for signs of a fabricated identity."""
import re
from datetime import date, datetime
from app.models import Signal

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "throwawaymail.com", "yopmail.com", "trashmail.com", "sharklasers.com",
    "getnada.com", "temp-mail.org", "fakeinbox.com", "dispostable.com",
}

_KEYBOARD_RUNS = ("qwerty", "asdf", "zxcv", "qazwsx", "hjkl", "wasd", "poiuy")
_PASSPORT_RE = re.compile(r"^[A-Z0-9<]{6,12}$")

def passport_number_plausible(num: str) -> bool:
    return bool(_PASSPORT_RE.match((num or "").strip().upper()))

def _looks_like_keyboard_mash(text: str) -> bool:
    t = re.sub(r"[^a-z]", "", (text or "").lower())
    return any(run in t for run in _KEYBOARD_RUNS)

def _is_sequential(digits: str) -> bool:
    if len(digits) < 6:
        return False
    # mod 10 so keypad order wraps: 1234567890 and 0987654321 both count as runs
    asc = all((int(digits[i + 1]) - int(digits[i])) % 10 == 1 for i in range(len(digits) - 1))
    desc = all((int(digits[i]) - int(digits[i + 1])) % 10 == 1 for i in range(len(digits) - 1))
    return asc or desc or len(set(digits)) == 1

def _parse_dob(dob: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(dob.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None

def run(claimed: dict) -> list[Signal]:
    s: list[Signal] = []
    name = (claimed.get("full_name") or "").strip()
    email = (claimed.get("email") or "").strip().lower()
    phone = re.sub(r"\D", "", claimed.get("phone") or "")
    passport_no = (claimed.get("passport_no") or "").strip()
    dob = (claimed.get("dob") or "").strip()

    if passport_no and not passport_number_plausible(passport_no):
        s.append(Signal(
            code="ID_PASSPORT_FORMAT_ODD", engine="identity", severity="medium",
            message=f"Passport number {passport_no!r} does not match the 6-12 "
                    f"alphanumeric structure used by ICAO travel documents.",
            evidence={"passport_no": passport_no},
        ))

    if email:
        domain = email.rpartition("@")[2]
        if domain in DISPOSABLE_DOMAINS:
            s.append(Signal(
                code="ID_DISPOSABLE_EMAIL", engine="identity", severity="high",
                message=f"Email uses known disposable provider {domain!r}.",
                evidence={"domain": domain},
            ))
        local = email.partition("@")[0]
        digits = sum(c.isdigit() for c in local)
        if name and len(local) >= 6:
            parts = [p.lower() for p in re.split(r"\s+", name) if len(p) > 2]
            if not any(p[:4] in local for p in parts) and digits >= 3:
                s.append(Signal(
                    code="ID_EMAIL_NAME_DIVERGENCE", engine="identity", severity="medium",
                    message=(f"Email local-part {local!r} shares nothing with the claimed "
                             f"name and is digit-heavy — typical of bulk-generated accounts."),
                    evidence={"local_part": local},
                ))

    if phone:
        if len(phone) < 10:
            s.append(Signal(code="ID_PHONE_TOO_SHORT", engine="identity", severity="medium",
                            message=f"Phone number has only {len(phone)} digits."))
        elif _is_sequential(phone):
            s.append(Signal(
                code="ID_PHONE_SEQUENTIAL", engine="identity", severity="high",
                message=f"Phone number {phone!r} is a sequential or repeated digit run.",
                evidence={"phone": phone},
            ))

    if name:
        if _looks_like_keyboard_mash(name):
            s.append(Signal(
                code="ID_NAME_SUSPICIOUS", engine="identity", severity="high",
                message=f"Name {name!r} contains a keyboard-run pattern, not a real name.",
                evidence={"name": name},
            ))
        elif len(name.split()) < 2:
            s.append(Signal(code="ID_NAME_SINGLE_TOKEN", engine="identity", severity="low",
                            message="Only one name token supplied; full legal name expected."))

    if dob:
        d = _parse_dob(dob)
        if d is None:
            s.append(Signal(code="ID_DOB_UNPARSEABLE", engine="identity", severity="medium",
                            message=f"Date of birth {dob!r} is not a recognised date format."))
        else:
            age = (date.today() - d).days / 365.25
            if age < 18 or age > 110:
                s.append(Signal(
                    code="ID_DOB_IMPLAUSIBLE", engine="identity", severity="high",
                    message=f"Date of birth implies an age of {age:.0f}, outside 18-110.",
                    evidence={"dob": dob, "age": round(age, 1)},
                ))
    return s
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_identity.py -v`
Expected: PASS, 13 passed

- [ ] **Step 5: Commit**

```bash
git add app/engines/identity.py tests/test_identity.py
git commit -m "feat: synthetic-identity heuristics engine"
```

---

## Task 4: Watchlist engine — fuzzy sanctions matching

**Files:**
- Create: `app/engines/watchlist.py`, `data/watchlist.csv`, `tests/test_watchlist.py`

**Interfaces:**
- Consumes: `Signal`, `rapidfuzz`
- Produces: `load_watchlist(path: str) -> list[dict]`, `run(claimed: dict, path: str = "data/watchlist.csv") -> list[Signal]`

**Design note:** exact matching is useless against fraud — real evaders transliterate and reorder. `token_sort_ratio` handles reordering ("Eriksson Anna" vs "Anna Eriksson") and minor spelling drift in one call. Threshold 88 for a hit, 78-88 for a near-miss worth analyst review.

- [ ] **Step 1: Write `data/watchlist.csv`** (synthetic — no real sanctioned persons)

```csv
name,list,country,reason
Viktor Anatolyevich Petrov,SDN,RU,Financial sanctions
Anna Maria Eriksdotter,PEP,SE,Politically exposed person
Mohammed Al-Rashid,SDN,SY,Asset freeze
Chen Wei Lin,INTERPOL,CN,Wanted notice
Dmitri Sokolov,SDN,RU,Financial sanctions
Fatima Nasser Khoury,PEP,LB,Politically exposed person
Rajesh Kumar Sharma,INTERPOL,IN,Wanted notice
Olena Kovalenko,PEP,UA,Politically exposed person
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_watchlist.py
from app.engines import watchlist

def test_exact_match_is_flagged():
    signals = watchlist.run({"full_name": "Viktor Anatolyevich Petrov"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_reordered_name_still_matches():
    signals = watchlist.run({"full_name": "Petrov Viktor Anatolyevich"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_minor_misspelling_matches():
    signals = watchlist.run({"full_name": "Dmitri Sokolovv"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_near_miss_is_review_not_match():
    signals = watchlist.run({"full_name": "Anna Maria Eriksson"})
    codes = [s.code for s in signals]
    assert "WL_NEAR_MATCH" in codes and "WL_MATCH" not in codes

def test_unrelated_name_is_clear():
    signals = watchlist.run({"full_name": "Jonathan Michael Brewster"})
    assert [s.code for s in signals] == ["WL_NO_MATCH"]

def test_missing_name_is_handled():
    assert watchlist.run({}) == []
```

- [ ] **Step 3: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_watchlist.py -v`
Expected: FAIL — `ImportError: cannot import name 'watchlist'`

- [ ] **Step 4: Write `app/engines/watchlist.py`**

```python
"""Fuzzy screening of the claimed name against a sanctions / PEP list."""
import csv
import functools
from rapidfuzz import fuzz, process
from app.models import Signal

MATCH_THRESHOLD = 88
REVIEW_THRESHOLD = 78

@functools.lru_cache(maxsize=4)
def load_watchlist(path: str = "data/watchlist.csv") -> tuple:
    with open(path, newline="", encoding="utf-8") as fh:
        return tuple(dict(row) for row in csv.DictReader(fh))

def run(claimed: dict, path: str = "data/watchlist.csv") -> list[Signal]:
    name = (claimed.get("full_name") or "").strip()
    if not name:
        return []

    entries = load_watchlist(path)
    names = [e["name"] for e in entries]
    best = process.extractOne(name, names, scorer=fuzz.token_sort_ratio)
    if best is None:
        return [Signal(code="WL_NO_MATCH", engine="watchlist", severity="info",
                       message="No sanctions or PEP list entry resembles this name.")]

    matched_name, score, idx = best
    entry = entries[idx]
    ev = {"matched": matched_name, "score": round(score, 1),
          "list": entry["list"], "country": entry["country"], "reason": entry["reason"]}

    if score >= MATCH_THRESHOLD:
        return [Signal(
            code="WL_MATCH", engine="watchlist", severity="critical",
            message=(f"Claimed name matches {matched_name!r} on the {entry['list']} list "
                     f"({entry['reason']}, {entry['country']}) at {score:.0f}% similarity."),
            evidence=ev,
        )]
    if score >= REVIEW_THRESHOLD:
        return [Signal(
            code="WL_NEAR_MATCH", engine="watchlist", severity="medium",
            message=(f"Claimed name is a partial match ({score:.0f}%) to {matched_name!r} "
                     f"on the {entry['list']} list. Manual analyst review required."),
            evidence=ev,
        )]
    return [Signal(code="WL_NO_MATCH", engine="watchlist", severity="info",
                   message=f"No watchlist entry above {REVIEW_THRESHOLD}% similarity "
                           f"(closest: {matched_name!r} at {score:.0f}%).", evidence=ev)]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_watchlist.py -v`
Expected: PASS, 6 passed

**If `test_near_miss_is_review_not_match` fails** because "Anna Maria Eriksson" vs "Anna Maria Eriksdotter" scores above 88: lower nothing, instead change the test fixture name. Do not tune thresholds to satisfy one test.

- [ ] **Step 6: Commit**

```bash
git add app/engines/watchlist.py data/watchlist.csv tests/test_watchlist.py
git commit -m "feat: fuzzy watchlist screening engine"
```

---

## Task 5: Scoring engine — signals to explainable verdict

**Files:**
- Create: `app/scoring.py`, `tests/test_scoring.py`

**Interfaces:**
- Consumes: `Signal`, `config.SEVERITY_POINTS`, `config.ENGINE_WEIGHTS`, `config.BANDS`
- Produces: `score_signals(signals: list[Signal]) -> tuple[int, str]`, `band_for(score: int) -> str`, `top_reasons(signals, limit=5) -> list[Signal]`

**Design note — why not a plain sum:** a document with six `low` signals is not more fraudulent than one with a failed MRZ checksum. Raw summation lets noise outvote proof. Instead: take the single highest-weighted signal at full value, and add each remaining signal at a decaying fraction. A real fraud indicator dominates; corroborating weak signals nudge upward without ever swamping it. Any `critical` signal floors the score into REJECT regardless of arithmetic.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scoring.py
from app.models import Signal
from app import scoring

def sig(sev, engine="identity", code="X"):
    return Signal(code=code, engine=engine, severity=sev, message="m")

def test_no_signals_is_zero_and_clear():
    assert scoring.score_signals([]) == (0, "CLEAR")

def test_only_info_signals_stay_clear():
    score, band = scoring.score_signals([sig("info"), sig("info")])
    assert score == 0 and band == "CLEAR"

def test_single_high_signal_lands_in_review():
    score, band = scoring.score_signals([sig("high")])
    assert band == "REVIEW"

def test_critical_signal_forces_reject():
    score, band = scoring.score_signals([sig("critical", engine="watchlist")])
    assert band == "REJECT" and score >= 65

def test_many_low_signals_do_not_outweigh_one_high():
    many_low = scoring.score_signals([sig("low") for _ in range(8)])[0]
    one_high = scoring.score_signals([sig("high")])[0]
    assert one_high > many_low

def test_score_is_capped_at_100():
    score, _ = scoring.score_signals([sig("critical") for _ in range(10)])
    assert score == 100

def test_engine_weight_zero_silences_engine(monkeypatch):
    monkeypatch.setitem(scoring.config.ENGINE_WEIGHTS, "tamper", 0.0)
    score, _ = scoring.score_signals([sig("critical", engine="tamper")])
    assert score == 0

def test_top_reasons_are_ordered_by_severity():
    signals = [sig("low", code="L"), sig("critical", code="C"), sig("medium", code="M")]
    assert [s.code for s in scoring.top_reasons(signals)] == ["C", "M", "L"]

def test_top_reasons_excludes_info():
    signals = [sig("info", code="I"), sig("high", code="H")]
    assert [s.code for s in scoring.top_reasons(signals)] == ["H"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.scoring'`

- [ ] **Step 3: Write `app/scoring.py`**

```python
"""Folds weighted signals into a 0-100 risk score with an explainable ordering."""
from app import config
from app.models import Signal

DECAY = 0.45          # each additional corroborating signal counts for less
CRITICAL_FLOOR = 65   # any surviving critical signal cannot score below REJECT

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

def _points(s: Signal) -> float:
    base = config.SEVERITY_POINTS.get(s.severity, 0.0)
    if s.weight_override is not None:
        base = s.weight_override
    return base * config.ENGINE_WEIGHTS.get(s.engine, 1.0)

def band_for(score: int) -> str:
    for ceiling, name in config.BANDS:
        if score < ceiling:
            return name
    return config.BANDS[-1][1]

def score_signals(signals: list[Signal]) -> tuple[int, str]:
    scored = sorted((p for p in (_points(s) for s in signals) if p > 0), reverse=True)
    if not scored:
        return 0, band_for(0)

    total = scored[0]
    for i, pts in enumerate(scored[1:], start=1):
        total += pts * (DECAY ** i)

    score = min(config.MAX_SCORE, int(round(total)))

    has_live_critical = any(
        s.severity == "critical" and _points(s) > 0 for s in signals
    )
    if has_live_critical:
        score = max(score, CRITICAL_FLOOR)

    return score, band_for(score)

def top_reasons(signals: list[Signal], limit: int = 5) -> list[Signal]:
    meaningful = [s for s in signals if s.severity != "info" and _points(s) > 0]
    meaningful.sort(key=lambda s: (_SEVERITY_ORDER[s.severity], -_points(s)))
    return meaningful[:limit]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_scoring.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Sanity-check the band boundaries by hand**

Run:
```bash
./.venv/bin/python -c "
from app.models import Signal
from app import scoring
for sev in ['low','medium','high','critical']:
    print(sev, scoring.score_signals([Signal(code='X',engine='identity',severity=sev,message='m')]))
"
```
Expected: `low` → CLEAR, `medium` → CLEAR, `high` → REVIEW, `critical` → REJECT.
If `high` lands in CLEAR, raise `SEVERITY_POINTS["high"]` until a single high signal reaches REVIEW. A forged document must never score CLEAR.

- [ ] **Step 6: Commit**

```bash
git add app/scoring.py tests/test_scoring.py
git commit -m "feat: decaying weighted risk scoring with critical floor"
```

---

## Task 6: Persistence and velocity engine

**Files:**
- Create: `app/db.py`, `app/engines/velocity.py`, `tests/test_velocity.py`

**Interfaces:**
- Consumes: `Signal`, stdlib `sqlite3`
- Produces:
  - `db.init_db(path) -> None`, `db.save_case(path, case_id, claimed, score, band, signals) -> None`
  - `db.find_prior(path, *, passport_no=None, email=None, phone=None, doc_hash=None) -> list[dict]`
  - `db.recent_count(path, minutes=10) -> int`
  - `velocity.run(claimed: dict, doc_hash: str | None, db_path: str) -> list[Signal]`

**Why this engine wins points:** every other engine looks at one submission in isolation. This one catches the pattern no single-document check can — the same passport number submitted under three different names, or twenty applications in four minutes. Judges recognise it as the difference between a toy checker and a screening *system*.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_velocity.py
import pytest
from app import db
from app.engines import velocity

@pytest.fixture
def dbfile(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    return p

def test_first_submission_is_clean(dbfile):
    signals = velocity.run({"passport_no": "L898902C3", "email": "a@b.com"}, None, dbfile)
    assert [s.severity for s in signals] == ["info"]

def test_same_id_different_name_is_flagged(dbfile):
    db.save_case(dbfile, "c1", {"passport_no": "L898902C3", "full_name": "Anna Eriksson"},
                 10, "CLEAR", [])
    signals = velocity.run({"passport_no": "L898902C3", "full_name": "John Smith"}, None, dbfile)
    assert "VEL_ID_REUSED_NEW_NAME" in [s.code for s in signals]

def test_same_id_same_name_is_only_informational(dbfile):
    db.save_case(dbfile, "c1", {"passport_no": "L898902C3", "full_name": "Anna Eriksson"},
                 10, "CLEAR", [])
    signals = velocity.run({"passport_no": "L898902C3", "full_name": "Anna Eriksson"}, None, dbfile)
    assert "VEL_ID_REUSED_NEW_NAME" not in [s.code for s in signals]

def test_identical_document_hash_is_flagged(dbfile):
    db.save_case(dbfile, "c1", {"full_name": "A"}, 10, "CLEAR", [], doc_hash="deadbeef")
    signals = velocity.run({"full_name": "B"}, "deadbeef", dbfile)
    assert "VEL_DUPLICATE_DOCUMENT" in [s.code for s in signals]

def test_burst_of_submissions_is_flagged(dbfile):
    for i in range(6):
        db.save_case(dbfile, f"c{i}", {"email": f"u{i}@x.com"}, 10, "CLEAR", [])
    signals = velocity.run({"email": "u99@x.com"}, None, dbfile)
    assert "VEL_SUBMISSION_BURST" in [s.code for s in signals]
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_velocity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 3: Write `app/db.py`**

```python
"""SQLite persistence for screening cases."""
import json
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id    TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    full_name  TEXT,
    passport_no TEXT,
    nationality TEXT,
    email      TEXT,
    phone      TEXT,
    doc_hash   TEXT,
    score      INTEGER,
    band       TEXT,
    payload    TEXT
);
CREATE INDEX IF NOT EXISTS idx_passport ON cases(passport_no);
CREATE INDEX IF NOT EXISTS idx_email    ON cases(email);
CREATE INDEX IF NOT EXISTS idx_doc_hash ON cases(doc_hash);
"""

@contextmanager
def _conn(path: str):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_db(path: str) -> None:
    with _conn(path) as con:
        con.executescript(SCHEMA)

def save_case(path, case_id, claimed, score, band, signals, doc_hash=None) -> None:
    payload = json.dumps({
        "claimed": claimed,
        "signals": [{"code": s.code, "engine": s.engine, "severity": s.severity,
                     "message": s.message} for s in signals],
    })
    with _conn(path) as con:
        con.execute(
            "INSERT OR REPLACE INTO cases "
            "(case_id, full_name, passport_no, nationality, email, phone, doc_hash, score, band, payload) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (case_id, claimed.get("full_name"), claimed.get("passport_no"),
             claimed.get("nationality"), claimed.get("email"), claimed.get("phone"),
             doc_hash, score, band, payload),
        )

def find_prior(path, *, passport_no=None, email=None, phone=None, doc_hash=None) -> list[dict]:
    clauses, params = [], []
    for col, val in (("passport_no", passport_no), ("email", email),
                     ("phone", phone), ("doc_hash", doc_hash)):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val)
    if not clauses:
        return []
    sql = f"SELECT * FROM cases WHERE {' OR '.join(clauses)} ORDER BY created_at DESC LIMIT 50"
    with _conn(path) as con:
        return [dict(r) for r in con.execute(sql, params)]

def recent_count(path: str, minutes: int = 10) -> int:
    with _conn(path) as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM cases "
            "WHERE created_at >= datetime('now', ?)", (f"-{minutes} minutes",)
        ).fetchone()
        return row["n"]

def all_cases(path: str, limit: int = 100) -> list[dict]:
    with _conn(path) as con:
        return [dict(r) for r in con.execute(
            "SELECT case_id, created_at, full_name, score, band FROM cases "
            "ORDER BY created_at DESC LIMIT ?", (limit,))]
```

- [ ] **Step 4: Write `app/engines/velocity.py`**

```python
"""Cross-submission fraud patterns: identity reuse, duplicate docs, bursts."""
from app import db
from app.models import Signal

BURST_WINDOW_MINUTES = 10
BURST_THRESHOLD = 5

def run(claimed: dict, doc_hash: str | None, db_path: str) -> list[Signal]:
    signals: list[Signal] = []
    name = (claimed.get("full_name") or "").strip().lower()

    prior = db.find_prior(
        db_path,
        passport_no=claimed.get("passport_no"),
        email=claimed.get("email"),
        phone=claimed.get("phone"),
        doc_hash=doc_hash,
    )

    if doc_hash:
        dupes = [p for p in prior if p["doc_hash"] == doc_hash]
        if dupes:
            signals.append(Signal(
                code="VEL_DUPLICATE_DOCUMENT", engine="velocity", severity="critical",
                message=(f"This exact document image was already submitted in case "
                         f"{dupes[0]['case_id']} under the name "
                         f"{dupes[0]['full_name']!r}."),
                evidence={"prior_case": dupes[0]["case_id"]},
            ))

    if claimed.get("passport_no"):
        conflicting = {
            p["full_name"] for p in prior
            if p["passport_no"] == claimed["passport_no"] and p["full_name"]
            and p["full_name"].strip().lower() != name
        }
        if conflicting:
            signals.append(Signal(
                code="VEL_ID_REUSED_NEW_NAME", engine="velocity", severity="critical",
                message=(f"The same passport number has previously been submitted under "
                         f"{len(conflicting)} different name(s): "
                         f"{', '.join(sorted(conflicting))}."),
                evidence={"conflicting_names": sorted(conflicting)},
            ))

    if db.recent_count(db_path, BURST_WINDOW_MINUTES) >= BURST_THRESHOLD:
        signals.append(Signal(
            code="VEL_SUBMISSION_BURST", engine="velocity", severity="medium",
            message=(f"{db.recent_count(db_path, BURST_WINDOW_MINUTES)} applications "
                     f"received in the last {BURST_WINDOW_MINUTES} minutes — "
                     f"consistent with automated bulk submission."),
        ))

    if not signals:
        signals.append(Signal(code="VEL_NO_PRIOR_HISTORY", engine="velocity", severity="info",
                              message="No prior submission matches this identity or document."))
    return signals
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_velocity.py -v`
Expected: PASS, 5 passed

- [ ] **Step 6: Commit**

```bash
git add app/db.py app/engines/velocity.py tests/test_velocity.py
git commit -m "feat: case persistence and cross-submission velocity engine"
```

---

## PHASE 1 GATE — hour 8

Run the whole suite: `./.venv/bin/pytest -v`
Expected: all tests from Tasks 0-6 pass.

**You now have a working fraud screener with zero image processing.** If everything after this point fails, you can still demo: identity validation, watchlist screening, velocity detection, explainable scoring. Do not proceed until this gate is green — the forensics tasks are strictly additive and must never be allowed to destabilise this core.

---

## Task 7: Metadata forensics engine

**Files:**
- Create: `app/engines/metadata.py`, `tests/test_metadata.py`

**Interfaces:**
- Consumes: `Signal`, `PIL.Image`, `pypdf`
- Produces: `run(path: str) -> list[Signal]`, `file_sha256(path: str) -> str`

**What it detects:** a genuine phone photo of a document carries camera EXIF (Make, Model, DateTimeOriginal). A document exported from Photoshop, GIMP, or Canva carries editing-software tags and no camera data. A PDF regenerated after editing has a `/Producer` that names the tool and a `ModDate` later than `CreationDate`. None of this is conclusive alone — which is exactly why it emits `medium`, not `critical`.

- [ ] **Step 1: Write the failing test**

No extra dependency is required — Pillow's built-in `Image.getexif()` covers every tag used here.

```python
# tests/test_metadata.py
from PIL import Image
from app.engines import metadata

def _make_jpeg(tmp_path, name="x.jpg", **save_kwargs):
    p = tmp_path / name
    Image.new("RGB", (64, 64), (128, 128, 128)).save(p, "JPEG", **save_kwargs)
    return str(p)

def test_sha256_is_stable_and_differs_between_files(tmp_path):
    a = _make_jpeg(tmp_path, "a.jpg")
    b = _make_jpeg(tmp_path, "b.jpg", quality=50)
    assert metadata.file_sha256(a) == metadata.file_sha256(a)
    assert metadata.file_sha256(a) != metadata.file_sha256(b)

def test_image_without_camera_exif_is_flagged(tmp_path):
    p = _make_jpeg(tmp_path)
    codes = [s.code for s in metadata.run(p)]
    assert "META_NO_CAMERA_EXIF" in codes

def test_editing_software_tag_is_flagged(tmp_path):
    p = tmp_path / "edited.jpg"
    img = Image.new("RGB", (64, 64), (10, 10, 10))
    exif = img.getexif()
    exif[305] = "Adobe Photoshop 25.0"   # 305 = Software
    img.save(p, "JPEG", exif=exif)
    codes = [s.code for s in metadata.run(str(p))]
    assert "META_EDITING_SOFTWARE" in codes

def test_missing_file_does_not_raise():
    signals = metadata.run("/nonexistent/file.jpg")
    assert "META_UNREADABLE" in [s.code for s in signals]

def test_unknown_extension_is_handled(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"not an image")
    assert metadata.run(str(p))  # returns signals, does not raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_metadata.py -v`
Expected: FAIL — `ImportError: cannot import name 'metadata'`

- [ ] **Step 3: Write `app/engines/metadata.py`**

```python
"""File-level provenance forensics: EXIF and PDF metadata."""
import hashlib
import os
from PIL import Image, ExifTags
from app.models import Signal

EDITORS = ("photoshop", "gimp", "canva", "illustrator", "affinity", "pixlr",
           "paint.net", "lightroom", "snapseed", "picsart", "inkscape", "figma")

TAG_SOFTWARE, TAG_MAKE, TAG_MODEL, TAG_DATETIME_ORIG = 305, 271, 272, 36867

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _pdf_signals(path: str) -> list[Signal]:
    from pypdf import PdfReader
    out: list[Signal] = []
    reader = PdfReader(path)
    info = reader.metadata or {}
    producer = str(info.get("/Producer", "") or "")
    creator = str(info.get("/Creator", "") or "")
    blob = f"{producer} {creator}".lower()
    if any(e in blob for e in EDITORS):
        out.append(Signal(
            code="META_EDITING_SOFTWARE", engine="metadata", severity="medium",
            message=f"PDF was produced by image-editing software ({producer or creator}).",
            evidence={"producer": producer, "creator": creator},
        ))
    c, m = str(info.get("/CreationDate", "")), str(info.get("/ModDate", ""))
    if c and m and m > c:
        out.append(Signal(
            code="META_PDF_MODIFIED_AFTER_CREATION", engine="metadata", severity="medium",
            message=f"PDF was modified ({m}) after it was created ({c}).",
            evidence={"created": c, "modified": m},
        ))
    if not out:
        out.append(Signal(code="META_PDF_CLEAN", engine="metadata", severity="info",
                          message="PDF metadata shows no editing-tool or post-modification traces."))
    return out

def _image_signals(path: str) -> list[Signal]:
    out: list[Signal] = []
    with Image.open(path) as img:
        exif = img.getexif()
        fmt, size = img.format, img.size

    software = str(exif.get(TAG_SOFTWARE, "") or "")
    make = str(exif.get(TAG_MAKE, "") or "")
    model = str(exif.get(TAG_MODEL, "") or "")

    if any(e in software.lower() for e in EDITORS):
        out.append(Signal(
            code="META_EDITING_SOFTWARE", engine="metadata", severity="medium",
            message=f"Image carries an editing-software tag: {software!r}. "
                    f"A genuine capture would name a camera, not an editor.",
            evidence={"software": software},
        ))

    if not make and not model:
        out.append(Signal(
            code="META_NO_CAMERA_EXIF", engine="metadata", severity="medium",
            message="No camera make/model in EXIF. The file was re-saved, screenshotted, "
                    "or synthesised rather than photographed.",
            evidence={"format": fmt, "size": list(size)},
        ))
    else:
        out.append(Signal(
            code="META_CAMERA_PRESENT", engine="metadata", severity="info",
            message=f"Camera EXIF present ({make} {model}).".strip(),
            evidence={"make": make, "model": model},
        ))

    if not out:
        out.append(Signal(code="META_CLEAN", engine="metadata", severity="info",
                          message="No metadata anomalies found."))
    return out

def run(path: str) -> list[Signal]:
    if not path or not os.path.exists(path):
        return [Signal(code="META_UNREADABLE", engine="metadata", severity="low",
                       message="No document file was available for metadata analysis.")]
    try:
        if path.lower().endswith(".pdf"):
            return _pdf_signals(path)
        return _image_signals(path)
    except Exception as e:
        return [Signal(code="META_UNREADABLE", engine="metadata", severity="low",
                       message=f"Metadata could not be parsed: {type(e).__name__}: {e}")]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_metadata.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/engines/metadata.py tests/test_metadata.py
git commit -m "feat: EXIF and PDF metadata forensics engine"
```

---

## Task 8: Tamper forensics engine — ELA, copy-move, noise

**Files:**
- Create: `app/engines/tamper.py`, `tests/test_tamper.py`

**Interfaces:**
- Consumes: `Signal`, `cv2`, `numpy`, `PIL.Image`
- Produces:
  - `ela_map(path: str, quality: int = 90) -> np.ndarray`
  - `ela_score(path: str) -> float`
  - `copy_move_score(path: str) -> tuple[float, int]`
  - `run(path: str) -> list[Signal]`

**How each check works — you must be able to say this to a judge:**

- **ELA (Error Level Analysis).** Re-save the image at a known JPEG quality and subtract it from the original. Regions that have already been compressed many times barely change; a freshly pasted region changes a lot. A spliced name or photo therefore lights up brighter than its surroundings. We measure the *ratio* of the brightest 1% of the residual to the median — a uniform image scores near 1, a spliced one scores well above it.
- **Copy-move.** ORB keypoints are matched against *the same image*. Genuine images have no strong self-matches at a distance. A cloned region — a digit copied over another digit, a stamp duplicated — produces many high-quality matches with a consistent spatial offset.
- **Noise inconsistency.** Real sensor noise is statistically uniform across a photo. A pasted region comes from a different source with different noise. We tile the image and compare per-tile Laplacian variance; a large spread means mixed provenance.

**Honest limitation to state out loud in the demo:** these are heuristics, not proof. ELA in particular produces false positives on high-contrast text and on images that were never JPEG. That is precisely why tamper signals cap at `high` and never `critical`, and why the system outputs a *review* verdict rather than an accusation. Saying this before a judge asks converts your weakest engine into evidence of engineering maturity.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tamper.py
import numpy as np
import pytest
from PIL import Image
from app.engines import tamper

@pytest.fixture
def photo_like(tmp_path):
    """A noisy gradient — stands in for a real photograph."""
    rng = np.random.default_rng(0)
    base = np.linspace(40, 200, 256, dtype=np.uint8)
    img = np.tile(base, (256, 1))
    img = np.clip(img + rng.normal(0, 6, img.shape), 0, 255).astype(np.uint8)
    p = tmp_path / "clean.jpg"
    Image.fromarray(img).convert("RGB").save(p, "JPEG", quality=85)
    return str(p)

@pytest.fixture
def spliced(tmp_path, photo_like):
    """Same image with a hard-pasted uncompressed block."""
    arr = np.array(Image.open(photo_like))
    arr[80:150, 80:150] = np.random.default_rng(1).integers(0, 255, (70, 70, 3))
    p = tmp_path / "spliced.jpg"
    Image.fromarray(arr).save(p, "JPEG", quality=95)
    return str(p)

def test_ela_map_matches_image_shape(photo_like):
    m = tamper.ela_map(photo_like)
    assert m.shape[:2] == (256, 256)

def test_spliced_region_raises_ela_score(photo_like, spliced):
    assert tamper.ela_score(spliced) > tamper.ela_score(photo_like)

def test_cloned_region_is_detected(tmp_path, photo_like):
    arr = np.array(Image.open(photo_like))
    arr[10:70, 10:70] = arr[150:210, 150:210]   # clone a patch
    p = tmp_path / "cloned.jpg"
    Image.fromarray(arr).save(p, "JPEG", quality=95)
    score, matches = tamper.copy_move_score(str(p))
    assert matches >= 0        # engine runs and reports

def test_run_returns_signals_for_valid_image(photo_like):
    signals = tamper.run(photo_like)
    assert signals and all(s.engine == "tamper" for s in signals)

def test_run_never_raises_on_garbage(tmp_path):
    p = tmp_path / "bad.jpg"
    p.write_bytes(b"not an image at all")
    signals = tamper.run(str(p))
    assert "TAMPER_UNREADABLE" in [s.code for s in signals]

def test_run_handles_missing_file():
    assert "TAMPER_UNREADABLE" in [s.code for s in tamper.run("/nope.jpg")]

def test_no_tamper_signal_exceeds_high(photo_like, spliced):
    for p in (photo_like, spliced):
        assert all(s.severity != "critical" for s in tamper.run(p))
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_tamper.py -v`
Expected: FAIL — `ImportError: cannot import name 'tamper'`

- [ ] **Step 3: Write `app/engines/tamper.py`**

```python
"""Pixel-level tamper heuristics: ELA, copy-move cloning, noise inconsistency."""
import os
import tempfile
import cv2
import numpy as np
from PIL import Image
from app.models import Signal

ELA_SUSPICIOUS = 6.0      # brightest-1% to median residual ratio
CLONE_MATCH_MIN = 12      # self-matches with consistent offset
NOISE_SPREAD_MAX = 4.5    # ratio of loudest tile variance to median tile variance

def _load_bgr(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("image could not be decoded")
    if max(img.shape[:2]) > 1400:                 # keep the demo fast
        scale = 1400 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img

def ela_map(path: str, quality: int = 90) -> np.ndarray:
    with Image.open(path) as im:
        original = im.convert("RGB")
        fd, tmp = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            original.save(tmp, "JPEG", quality=quality)
            with Image.open(tmp) as resaved:
                diff = np.abs(np.asarray(original, np.int16)
                              - np.asarray(resaved.convert("RGB"), np.int16))
        finally:
            os.unlink(tmp)
    return diff.max(axis=2).astype(np.float32)

def ela_score(path: str) -> float:
    m = ela_map(path)
    hot = float(np.percentile(m, 99))
    med = float(np.median(m))
    return hot / max(med, 0.5)

def copy_move_score(path: str) -> tuple[float, int]:
    img = _load_bgr(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=2000)
    kp, desc = orb.detectAndCompute(gray, None)
    if desc is None or len(kp) < 20:
        return 0.0, 0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    knn = matcher.knnMatch(desc, desc, k=3)

    offsets = []
    for group in knn:
        for m in group[1:]:                       # skip self-match at index 0
            p1 = np.array(kp[m.queryIdx].pt)
            p2 = np.array(kp[m.trainIdx].pt)
            dist = np.linalg.norm(p1 - p2)
            if dist > 40 and m.distance < 40:     # far apart but visually identical
                offsets.append(tuple(np.round((p1 - p2) / 8).astype(int)))

    if not offsets:
        return 0.0, 0
    counts = {}
    for o in offsets:
        counts[o] = counts.get(o, 0) + 1
    best = max(counts.values())
    return best / max(len(kp), 1) * 100, best

def noise_spread(path: str) -> float:
    img = _load_bgr(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    th, tw = h // 6, w // 6
    variances = []
    for r in range(6):
        for c in range(6):
            tile = gray[r * th:(r + 1) * th, c * tw:(c + 1) * tw]
            if tile.size:
                variances.append(float(cv2.Laplacian(tile, cv2.CV_64F).var()))
    variances = [v for v in variances if v > 0]
    if len(variances) < 4:
        return 1.0
    return float(np.percentile(variances, 95)) / max(float(np.median(variances)), 0.5)

def run(path: str) -> list[Signal]:
    if not path or not os.path.exists(path) or path.lower().endswith(".pdf"):
        return [Signal(code="TAMPER_UNREADABLE", engine="tamper", severity="low",
                       message="No raster image available for pixel-level analysis.")]
    try:
        ela = ela_score(path)
        clone_pct, clone_matches = copy_move_score(path)
        spread = noise_spread(path)
    except Exception as e:
        return [Signal(code="TAMPER_UNREADABLE", engine="tamper", severity="low",
                       message=f"Image could not be analysed: {type(e).__name__}: {e}")]

    signals: list[Signal] = []

    if ela > ELA_SUSPICIOUS:
        signals.append(Signal(
            code="TAMPER_ELA_ANOMALY", engine="tamper", severity="high",
            message=(f"Error Level Analysis ratio is {ela:.1f} (threshold {ELA_SUSPICIOUS}). "
                     f"Part of this image has a different compression history from the rest, "
                     f"which is what splicing looks like."),
            evidence={"ela_ratio": round(ela, 2)},
        ))

    if clone_matches >= CLONE_MATCH_MIN:
        signals.append(Signal(
            code="TAMPER_COPY_MOVE", engine="tamper", severity="high",
            message=(f"{clone_matches} keypoints match another region of the same image "
                     f"at a consistent offset — a cloned or duplicated region."),
            evidence={"matches": clone_matches, "score": round(clone_pct, 2)},
        ))

    if spread > NOISE_SPREAD_MAX:
        signals.append(Signal(
            code="TAMPER_NOISE_INCONSISTENT", engine="tamper", severity="medium",
            message=(f"Sensor-noise variance differs {spread:.1f}x across the image. "
                     f"A single-capture photograph has near-uniform noise."),
            evidence={"noise_spread": round(spread, 2)},
        ))

    if not signals:
        signals.append(Signal(
            code="TAMPER_NONE_DETECTED", engine="tamper", severity="info",
            message=(f"No splicing, cloning or noise anomalies detected "
                     f"(ELA {ela:.1f}, clone matches {clone_matches}, noise {spread:.1f}x)."),
            evidence={"ela_ratio": round(ela, 2), "clone_matches": clone_matches,
                      "noise_spread": round(spread, 2)},
        ))
    return signals
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_tamper.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Calibrate the thresholds against your own sample images**

Run:
```bash
./.venv/bin/python -c "
from app.engines import tamper
import sys
for p in sys.argv[1:]:
    print(p, 'ela=%.2f' % tamper.ela_score(p), 'clone=%s' % (tamper.copy_move_score(p)[1],), 'noise=%.2f' % tamper.noise_spread(p))
" data/samples/*.jpg
```

Adjust `ELA_SUSPICIOUS`, `CLONE_MATCH_MIN` and `NOISE_SPREAD_MAX` so your clean samples sit below threshold and your forged samples sit above. **Do this after Task 16 generates the samples** — come back to this step. Record the chosen numbers in the README so you can justify them to a judge.

- [ ] **Step 6: Commit**

```bash
git add app/engines/tamper.py tests/test_tamper.py
git commit -m "feat: ELA, copy-move and noise tamper forensics"
```

---

## Task 9: OCR engine — text, bounding boxes, and printed-vs-typed cross-check

**Files:**
- Create: `app/engines/ocr.py`, `tests/test_ocr.py`

**Interfaces:**
- Consumes: `Signal`, `rapidocr_onnxruntime.RapidOCR`
- Produces:
  - `extract_boxes(path: str) -> list[dict]` — each `{"text": str, "confidence": float, "box": (x, y, w, h)}`
  - `find_mrz_lines(lines: list[str]) -> list[str]`
  - `run(path: str, claimed: dict) -> tuple[list[Signal], list[str], list[dict]]` — signals, MRZ lines, **and the boxes Task 10 needs**

**Why boxes matter:** this is the only engine that knows *where* each field sits on the page. Task 10 — the centerpiece — cannot exist without them. Returning boxes is not optional polish.

**Why the cross-check matters:** the highest-value OCR signal is not "what does the document say" but "does what the document says match what the applicant typed". An applicant whose name appears nowhere on their own uploaded passport is the strongest non-forensic fraud indicator in the system.

**Severity note:** `OCR_NAME_NOT_ON_DOCUMENT` is `high`, deliberately **not** `critical`. OCR misreads genuine documents often enough that an automatic REJECT on this signal alone would reject a valid applicant live on stage. It is also suppressed when OCR confidence is poor — a blurred scan is not evidence of fraud.

**Performance note:** RapidOCR loads ~15MB of ONNX models on first call, taking 2-4 seconds. It is cached at module level as a singleton — never construct it per request, or the demo will feel broken.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ocr.py
import pytest
from PIL import Image, ImageDraw, ImageFont
from app.engines import ocr

def _font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()

@pytest.fixture
def text_image(tmp_path):
    img = Image.new("RGB", (800, 260), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 50), "ANNA MARIA ERIKSSON", fill="black", font=_font(44))
    d.text((30, 140), "DOB 1974-08-12", fill="black", font=_font(44))
    p = tmp_path / "doc.png"
    img.save(p)
    return str(p)

def test_find_mrz_lines_picks_out_chevron_rows():
    lines = [
        "REPUBLIC OF UTOPIA",
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
        "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
    ]
    assert ocr.find_mrz_lines(lines) == lines[1:]

def test_find_mrz_lines_returns_empty_when_absent():
    assert ocr.find_mrz_lines(["JUST A NAME", "AND A DATE"]) == []

def test_extract_boxes_returns_text_and_geometry(text_image):
    boxes = ocr.extract_boxes(text_image)
    assert boxes, "OCR found no text at all"
    joined = " ".join(b["text"] for b in boxes).upper()
    assert "ERIKSSON" in joined or "ANNA" in joined
    for b in boxes:
        x, y, w, h = b["box"]
        assert w > 0 and h > 0
        assert x >= 0 and y >= 0

def test_run_returns_signals_mrz_and_boxes(text_image):
    signals, mrz_lines, boxes = ocr.run(text_image, {"full_name": "Anna Maria Eriksson"})
    assert isinstance(signals, list) and isinstance(mrz_lines, list)
    assert boxes and "box" in boxes[0]

def test_name_present_on_document_is_not_flagged(text_image):
    signals, _, _ = ocr.run(text_image, {"full_name": "Anna Maria Eriksson"})
    assert "OCR_NAME_NOT_ON_DOCUMENT" not in [s.code for s in signals]

def test_name_absent_from_document_is_flagged(text_image):
    signals, _, _ = ocr.run(text_image, {"full_name": "Bartholomew Cubbins"})
    assert "OCR_NAME_NOT_ON_DOCUMENT" in [s.code for s in signals]

def test_name_mismatch_is_high_not_critical(text_image):
    signals, _, _ = ocr.run(text_image, {"full_name": "Bartholomew Cubbins"})
    hit = [s for s in signals if s.code == "OCR_NAME_NOT_ON_DOCUMENT"][0]
    assert hit.severity == "high"

def test_run_handles_missing_file():
    signals, mrz, boxes = ocr.run("/nope.png", {})
    assert "OCR_UNREADABLE" in [s.code for s in signals]
    assert mrz == [] and boxes == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_ocr.py -v`
Expected: FAIL — `ImportError: cannot import name 'ocr'`

- [ ] **Step 3: Write `app/engines/ocr.py`**

```python
"""OCR extraction with geometry, and cross-validation of printed vs claimed fields."""
import functools
import os
import re
from rapidfuzz import fuzz
from app.models import Signal

MRZ_RE = re.compile(r"^[A-Z0-9<]{25,}$")
NAME_MATCH_THRESHOLD = 80
MIN_CONFIDENCE_TO_JUDGE = 0.45   # below this, a miss is illegible text, not fraud

@functools.lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()

def _poly_to_box(poly) -> tuple[int, int, int, int]:
    xs = [float(pt[0]) for pt in poly]
    ys = [float(pt[1]) for pt in poly]
    x, y = int(min(xs)), int(min(ys))
    return x, y, int(max(xs)) - x, int(max(ys)) - y

def extract_boxes(path: str) -> list[dict]:
    result, _ = _engine()(path)
    if not result:
        return []
    out = []
    for item in result:
        poly, text, score = item[0], item[1], item[2]
        out.append({"text": text, "confidence": float(score), "box": _poly_to_box(poly)})
    return out

def find_mrz_lines(lines: list[str]) -> list[str]:
    candidates = [ln.strip().upper().replace(" ", "") for ln in lines if ln and "<" in ln]
    return [ln for ln in candidates if MRZ_RE.match(ln)]

def run(path: str, claimed: dict) -> tuple[list[Signal], list[str], list[dict]]:
    if not path or not os.path.exists(path):
        return ([Signal(code="OCR_UNREADABLE", engine="ocr", severity="low",
                        message="No document image available for text extraction.")], [], [])
    try:
        boxes = extract_boxes(path)
    except Exception as e:
        return ([Signal(code="OCR_UNREADABLE", engine="ocr", severity="low",
                        message=f"OCR failed: {type(e).__name__}: {e}")], [], [])

    if not boxes:
        return ([Signal(code="OCR_NO_TEXT_FOUND", engine="ocr", severity="medium",
                        message="No readable text found on the document. Genuine travel "
                                "documents always carry printed text.")], [], [])

    texts = [b["text"] for b in boxes]
    mrz_lines = find_mrz_lines(texts)
    blob = " ".join(texts).upper()
    avg_conf = sum(b["confidence"] for b in boxes) / len(boxes)
    signals: list[Signal] = []

    if avg_conf < 0.55:
        signals.append(Signal(
            code="OCR_LOW_CONFIDENCE", engine="ocr", severity="low",
            message=f"Average OCR confidence is {avg_conf:.0%}; the document is blurred, "
                    f"low resolution, or a photograph of a screen.",
            evidence={"avg_confidence": round(avg_conf, 3)},
        ))

    name = (claimed.get("full_name") or "").strip()
    if name and avg_conf >= MIN_CONFIDENCE_TO_JUDGE:
        best = max((fuzz.partial_ratio(part.upper(), blob)
                    for part in name.split() if len(part) > 2), default=0)
        if best < NAME_MATCH_THRESHOLD:
            signals.append(Signal(
                code="OCR_NAME_NOT_ON_DOCUMENT", engine="ocr", severity="high",
                message=(f"The claimed name {name!r} does not appear in the text printed "
                         f"on the uploaded document (best match {best:.0f}%). The applicant "
                         f"may be presenting another person's document."),
                evidence={"claimed_name": name, "best_match_pct": round(best, 1)},
            ))
        else:
            signals.append(Signal(
                code="OCR_NAME_CONFIRMED", engine="ocr", severity="info",
                message=f"Claimed name is printed on the document ({best:.0f}% match)."))

    if avg_conf >= MIN_CONFIDENCE_TO_JUDGE:
        flat = re.sub(r"[\s\-/]", "", blob)
        for field, code, label in (("dob", "OCR_DOB_NOT_ON_DOCUMENT", "date of birth"),
                                   ("passport_no", "OCR_NUMBER_NOT_ON_DOCUMENT",
                                    "passport number")):
            value = re.sub(r"[\s\-/]", "", (claimed.get(field) or "")).upper()
            if value and len(value) >= 6 and fuzz.partial_ratio(value, flat) < 80:
                signals.append(Signal(
                    code=code, engine="ocr", severity="medium",
                    message=f"The claimed {label} is not printed on the uploaded document.",
                    evidence={field: value},
                ))

    if mrz_lines:
        signals.append(Signal(
            code="OCR_MRZ_FOUND", engine="ocr", severity="info",
            message=f"Located {len(mrz_lines)} machine-readable zone line(s); "
                    f"passed to MRZ validation.",
            evidence={"lines": mrz_lines}))

    return signals, mrz_lines, boxes
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_ocr.py -v`
Expected: PASS, 8 passed. First run is slow (model download and load).

- [ ] **Step 5: Commit**

```bash
git add app/engines/ocr.py tests/test_ocr.py
git commit -m "feat: OCR engine returning geometry plus claimed-vs-printed cross-check"
```

---

## Task 10: Field-level forensics — WHICH field was altered · CENTERPIECE

**This is the innovation claim, the best visual, and the answer to three of the four attack types named in the problem statement. If you are behind schedule, cut anything else first.**

**Files:**
- Create: `app/engines/fieldforensics.py`, `app/annotate.py`, `scripts/tune_fields.py`, `tests/test_fieldforensics.py`

**Interfaces:**
- Consumes: `Signal`, `tamper.ela_map`, OCR boxes from Task 9, optional portrait box from Task 11
- Produces:
  - `region_scores(ela: np.ndarray, boxes: list[tuple]) -> list[float]`
  - `outlier_indices(values: list[float], z_threshold: float = 3.5) -> list[int]`
  - `stamp_regions(path: str) -> list[tuple]`
  - `run(path, ocr_boxes, portrait_box=None) -> tuple[list[Signal], list[dict]]`
  - `annotate.draw_evidence(path, regions, out_dir) -> str | None`

**The method, in the words you will use on stage:**

> Error Level Analysis measures how much a region changes when the image is re-compressed. A region that went through the original capture pipeline changes very little. A region pasted or retyped afterwards has a different compression history and changes much more. We run this **per field** rather than over the whole page, then ask which field is a statistical outlier against its own neighbours. Because each field is compared against the other fields on the same document, we need no reference database and no genuine passport to compare against.

**Why median + MAD, not mean + standard deviation:** a tampered field is itself an extreme value, so it drags a mean and a standard deviation toward itself — hiding the very thing you are hunting. Median and median-absolute-deviation are robust to outliers, so the tampered field stays visible. Use the modified z-score, `0.6745 * (x - median) / MAD`.

**Honest limitation to say out loud:** ELA false-positives on high-contrast text and on images that were never JPEG. This is why field signals cap at `high`, never `critical`, and why the system recommends review rather than issuing an accusation.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fieldforensics.py
import numpy as np
import pytest
from PIL import Image
from app.engines import fieldforensics as ff

@pytest.fixture
def doc_with_tampered_field(tmp_path):
    """Five identical text-ish strips; strip 2 is repasted at a different quality."""
    rng = np.random.default_rng(0)
    canvas = np.full((400, 600, 3), 235, np.uint8)
    boxes = []
    for i in range(5):
        y = 30 + i * 70
        strip = rng.integers(60, 90, (40, 500, 3)).astype(np.uint8)
        canvas[y:y + 40, 50:550] = strip
        boxes.append((50, y, 500, 40))

    p_clean = tmp_path / "clean.jpg"
    Image.fromarray(canvas).save(p_clean, "JPEG", quality=60)

    # Reload the compressed version, then paste fresh uncompressed content into box 2
    arr = np.array(Image.open(p_clean))
    x, y, w, h = boxes[2]
    arr[y:y + h, x:x + w] = rng.integers(0, 255, (h, w, 3)).astype(np.uint8)
    p_bad = tmp_path / "tampered.jpg"
    Image.fromarray(arr).save(p_bad, "JPEG", quality=98)
    return str(p_bad), boxes, 2

def test_outlier_indices_finds_the_extreme_value():
    assert ff.outlier_indices([10.0, 10.2, 9.8, 10.1, 80.0]) == [4]

def test_outlier_indices_empty_when_uniform():
    assert ff.outlier_indices([10.0, 10.1, 9.9, 10.05]) == []

def test_outlier_indices_handles_tiny_input():
    assert ff.outlier_indices([1.0]) == []
    assert ff.outlier_indices([]) == []

def test_region_scores_one_value_per_box(doc_with_tampered_field):
    path, boxes, _ = doc_with_tampered_field
    from app.engines.tamper import ela_map
    scores = ff.region_scores(ela_map(path), boxes)
    assert len(scores) == len(boxes)
    assert all(s >= 0 for s in scores)

def test_tampered_field_scores_highest(doc_with_tampered_field):
    path, boxes, bad_idx = doc_with_tampered_field
    from app.engines.tamper import ela_map
    scores = ff.region_scores(ela_map(path), boxes)
    assert scores.index(max(scores)) == bad_idx

def test_run_names_the_tampered_field(doc_with_tampered_field):
    path, boxes, bad_idx = doc_with_tampered_field
    ocr_boxes = [{"text": f"FIELD {i}", "confidence": 0.95, "box": b}
                 for i, b in enumerate(boxes)]
    signals, regions = ff.run(path, ocr_boxes)
    assert "FF_FIELD_TAMPERED" in [s.code for s in signals]
    flagged = [r for r in regions if r["suspect"]]
    assert flagged and flagged[0]["label"] == f"FIELD {bad_idx}"

def test_run_with_no_boxes_is_graceful(tmp_path):
    p = tmp_path / "x.jpg"
    Image.new("RGB", (64, 64), "white").save(p, "JPEG")
    signals, regions = ff.run(str(p), [])
    assert "FF_NO_REGIONS" in [s.code for s in signals]
    assert regions == []

def test_run_never_raises_on_garbage(tmp_path):
    p = tmp_path / "bad.jpg"
    p.write_bytes(b"not an image")
    signals, regions = ff.run(str(p), [{"text": "A", "confidence": 1.0, "box": (0, 0, 50, 50)}])
    assert "FF_UNREADABLE" in [s.code for s in signals] or \
           "FF_NO_REGIONS" in [s.code for s in signals]

def test_no_field_signal_is_critical(doc_with_tampered_field):
    path, boxes, _ = doc_with_tampered_field
    ocr_boxes = [{"text": f"F{i}", "confidence": 0.9, "box": b} for i, b in enumerate(boxes)]
    signals, _ = ff.run(path, ocr_boxes)
    assert all(s.severity != "critical" for s in signals)

def test_annotate_writes_an_image(tmp_path, doc_with_tampered_field):
    from app import annotate
    path, boxes, bad_idx = doc_with_tampered_field
    regions = [{"box": b, "label": f"F{i}", "suspect": i == bad_idx, "score": 1.0}
               for i, b in enumerate(boxes)]
    out = annotate.draw_evidence(path, regions, str(tmp_path / "ev"))
    assert out and Image.open(out).size == Image.open(path).size
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_fieldforensics.py -v`
Expected: FAIL — `ImportError: cannot import name 'fieldforensics'`

- [ ] **Step 3: Write `app/engines/fieldforensics.py`**

```python
"""Per-field tamper localization: which field on this document was altered."""
import os
import cv2
import numpy as np
from app.engines.tamper import ela_map
from app.models import Signal

Z_THRESHOLD = 3.5      # modified z-score above which a field is an outlier
MIN_REGIONS = 3        # fewer than this and "outlier" is meaningless
MIN_AREA = 200         # ignore specks

def region_scores(ela: np.ndarray, boxes: list[tuple]) -> list[float]:
    h, w = ela.shape[:2]
    out: list[float] = []
    for (x, y, bw, bh) in boxes:
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(w, int(x + bw)), min(h, int(y + bh))
        patch = ela[y0:y1, x0:x1]
        out.append(float(patch.mean()) if patch.size else 0.0)
    return out

def outlier_indices(values: list[float], z_threshold: float = Z_THRESHOLD) -> list[int]:
    if len(values) < MIN_REGIONS:
        return []
    arr = np.asarray(values, dtype=np.float64)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    if mad < 1e-6:
        spread = float(arr.std())
        if spread < 1e-6:
            return []
        z = (arr - median) / spread
    else:
        z = 0.6745 * (arr - median) / mad
    return [i for i in range(len(arr)) if z[i] > z_threshold]

def stamp_regions(path: str) -> list[tuple]:
    """Saturated colour blobs - visa stamps, seals and inked impressions."""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return []
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 90, 40), (179, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h >= MIN_AREA * 4 and 0.2 <= w / max(h, 1) <= 6.0:
            out.append((x, y, w, h))
    return sorted(out, key=lambda b: b[2] * b[3], reverse=True)[:6]

def run(path: str, ocr_boxes: list[dict],
        portrait_box: tuple | None = None) -> tuple[list[Signal], list[dict]]:
    if not path or not os.path.exists(path):
        return ([Signal(code="FF_UNREADABLE", engine="fieldforensics", severity="low",
                        message="No document image available for field-level analysis.")], [])

    regions: list[dict] = []
    for b in ocr_boxes:
        x, y, w, h = b["box"]
        if w * h >= MIN_AREA:
            regions.append({"box": (x, y, w, h), "label": b["text"][:32],
                            "kind": "text", "suspect": False, "score": 0.0})
    if portrait_box:
        regions.append({"box": tuple(portrait_box), "label": "PHOTOGRAPH",
                        "kind": "portrait", "suspect": False, "score": 0.0})

    try:
        for sb in stamp_regions(path):
            regions.append({"box": sb, "label": "STAMP", "kind": "stamp",
                            "suspect": False, "score": 0.0})
    except Exception:
        pass   # stamps are a bonus; never let them break the engine

    if len(regions) < MIN_REGIONS:
        return ([Signal(
            code="FF_NO_REGIONS", engine="fieldforensics", severity="low",
            message=(f"Only {len(regions)} analysable region(s) found; field-level "
                     f"comparison needs at least {MIN_REGIONS}."))], [])

    try:
        ela = ela_map(path)
        scores = region_scores(ela, [r["box"] for r in regions])
    except Exception as e:
        return ([Signal(code="FF_UNREADABLE", engine="fieldforensics", severity="low",
                        message=f"Field analysis failed: {type(e).__name__}: {e}")], [])

    for r, sc in zip(regions, scores):
        r["score"] = round(float(sc), 2)

    bad = outlier_indices(scores)
    for i in bad:
        regions[i]["suspect"] = True

    signals: list[Signal] = []
    median = float(np.median(scores))

    for i in bad:
        r = regions[i]
        if r["kind"] == "portrait":
            signals.append(Signal(
                code="FF_PHOTO_TAMPERED", engine="fieldforensics", severity="high",
                message=(f"The photograph region has a compression residual of "
                         f"{r['score']} against a document median of {median:.2f}. "
                         f"The portrait was pasted in after the document was produced."),
                evidence={"box": list(r["box"]), "score": r["score"],
                          "document_median": round(median, 2)}))
        elif r["kind"] == "stamp":
            signals.append(Signal(
                code="FF_STAMP_TAMPERED", engine="fieldforensics", severity="high",
                message=(f"A stamp or seal region has a compression residual of "
                         f"{r['score']} against a document median of {median:.2f}. "
                         f"The stamp was added or altered after issue."),
                evidence={"box": list(r["box"]), "score": r["score"],
                          "document_median": round(median, 2)}))
        else:
            signals.append(Signal(
                code="FF_FIELD_TAMPERED", engine="fieldforensics", severity="high",
                message=(f"The field reading {r['label']!r} has a compression residual of "
                         f"{r['score']} against a document median of {median:.2f} - it was "
                         f"edited after the rest of the document was produced."),
                evidence={"field_text": r["label"], "box": list(r["box"]),
                          "score": r["score"], "document_median": round(median, 2)}))

    if not signals:
        signals.append(Signal(
            code="FF_ALL_FIELDS_CONSISTENT", engine="fieldforensics", severity="info",
            message=(f"All {len(regions)} analysed regions share a consistent compression "
                     f"history (median residual {median:.2f}). No single field stands out "
                     f"as edited."),
            evidence={"regions_analysed": len(regions),
                      "document_median": round(median, 2)}))
    return signals, regions
```

- [ ] **Step 4: Write `app/annotate.py`**

```python
"""Draws the annotated evidence image: suspect regions boxed in red."""
import os
import uuid
import cv2

RED = (0, 0, 220)
GREEN = (90, 170, 90)

def draw_evidence(path: str, regions: list[dict], out_dir: str) -> str | None:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return None
    os.makedirs(out_dir, exist_ok=True)

    for r in regions:
        x, y, w, h = [int(v) for v in r["box"]]
        suspect = bool(r.get("suspect"))
        colour = RED if suspect else GREEN
        cv2.rectangle(img, (x, y), (x + w, y + h), colour, 3 if suspect else 1)
        if suspect:
            label = f"ALTERED: {r.get('label', '')}"[:40]
            ty = max(18, y - 8)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(img, (x, ty - th - 6), (x + tw + 8, ty + 4), RED, -1)
            cv2.putText(img, label, (x + 4, ty), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (255, 255, 255), 2, cv2.LINE_AA)

    dest = os.path.join(out_dir, f"{uuid.uuid4().hex}.jpg")
    cv2.imwrite(dest, img)
    return dest
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_fieldforensics.py -v`
Expected: PASS, 10 passed

**If `test_tampered_field_scores_highest` fails**, the fixture's repaste is not producing a strong enough compression difference. Widen the gap further — clean at `quality=50`, tampered at `quality=99`. Do not weaken the assertion; this behaviour is the entire product.

- [ ] **Step 6: Write `scripts/tune_fields.py`**

```python
"""Prints per-sample field-forensics output so thresholds can be calibrated."""
import glob
from app.engines import ocr
from app.engines import fieldforensics as ff

def main() -> None:
    for path in sorted(glob.glob("data/samples/*.jpg")):
        _, _, boxes = ocr.run(path, {})
        signals, regions = ff.run(path, boxes)
        flagged = [r["label"] for r in regions if r["suspect"]]
        print(f"{path:46s} regions={len(regions):3d} flagged={flagged}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Tune `Z_THRESHOLD` against real samples — return here after Task 16**

Run: `./.venv/bin/python -m scripts.tune_fields`

Clean samples must flag **nothing**. Tampered samples must flag the field you actually tampered. Raise `Z_THRESHOLD` if clean documents flag; lower it if forgeries slip through. Record the final value in the README with your justification.

- [ ] **Step 8: Commit**

```bash
git add app/engines/fieldforensics.py app/annotate.py scripts/tune_fields.py tests/test_fieldforensics.py
git commit -m "feat: field-level tamper localization with annotated evidence output"
```

---

## Task 11: Face engine — portrait detection and selfie match

**Cut this task without hesitation if Task 0 Step 3 printed `False False`, or if you are behind schedule at hour 16.** It is the most impressive engine and the most expendable one.

**Files:**
- Create: `scripts/download_models.py`, `app/engines/face.py`, `tests/test_face.py`

**Interfaces:**
- Consumes: `Signal`, `cv2.FaceDetectorYN`, `cv2.FaceRecognizerSF`
- Produces:
  - `detect_faces(path: str) -> list[dict]` — each `{"box": [x,y,w,h], "confidence": float, "raw": np.ndarray}`
  - `match_score(doc_path: str, selfie_path: str) -> float | None` — cosine similarity, higher is more similar
  - `run(doc_path: str, selfie_path: str | None) -> list[Signal]`

**Thresholds:** OpenCV's SFace documentation gives cosine similarity `>= 0.363` as the same-person threshold. We treat `< 0.25` as a definite mismatch (critical) and `0.25-0.363` as inconclusive (medium).

- [ ] **Step 1: Write `scripts/download_models.py`**

```python
"""One-time download of the face ONNX models. Requires network; run during setup only."""
import os
import urllib.request

MODELS = {
    "face_detection_yunet_2023mar.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
}

def main() -> None:
    os.makedirs("models", exist_ok=True)
    for name, url in MODELS.items():
        dest = os.path.join("models", name)
        if os.path.exists(dest):
            print(f"[skip] {name}")
            continue
        print(f"[get ] {name}")
        urllib.request.urlretrieve(url, dest)
        print(f"[ok  ] {name} ({os.path.getsize(dest) // 1024} KB)")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it and confirm both models land**

Run: `./.venv/bin/python -m scripts.download_models && ls -la models/`
Expected: two `.onnx` files, roughly 230 KB and 38 MB.

**If the download fails, cut Task 10 now.** Do not debug a GitHub raw URL during a hackathon.

- [ ] **Step 3: Write the failing test**

```python
# tests/test_face.py
import os
import numpy as np
import pytest
from PIL import Image
from app.engines import face

pytestmark = pytest.mark.skipif(
    not os.path.exists("models/face_detection_yunet_2023mar.onnx"),
    reason="face models not downloaded",
)

@pytest.fixture
def blank(tmp_path):
    p = tmp_path / "blank.png"
    Image.new("RGB", (320, 320), "white").save(p)
    return str(p)

def test_no_face_in_blank_image(blank):
    assert face.detect_faces(blank) == []

def test_missing_portrait_on_document_is_flagged(blank):
    signals = face.run(blank, None)
    assert "FACE_NO_PORTRAIT_ON_DOC" in [s.code for s in signals]

def test_run_without_selfie_does_not_emit_match_signals(blank):
    codes = [s.code for s in face.run(blank, None)]
    assert "FACE_MISMATCH" not in codes and "FACE_MATCH" not in codes

def test_run_handles_missing_files():
    signals = face.run("/nope.png", "/also-nope.png")
    assert "FACE_UNREADABLE" in [s.code for s in signals]
```

- [ ] **Step 4: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_face.py -v`
Expected: FAIL — `ImportError: cannot import name 'face'`

- [ ] **Step 5: Write `app/engines/face.py`**

```python
"""Portrait detection on the document and biometric match against a selfie."""
import functools
import os
import cv2
import numpy as np
from app.models import Signal

DETECTOR_PATH = "models/face_detection_yunet_2023mar.onnx"
RECOGNIZER_PATH = "models/face_recognition_sface_2021dec.onnx"

SAME_PERSON = 0.363     # OpenCV SFace documented cosine threshold
DEFINITE_MISMATCH = 0.25

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
    det = _detector()
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    if faces is None:
        return []
    return [{"box": [int(v) for v in f[:4]], "confidence": float(f[-1]), "raw": f}
            for f in faces]

def _embedding(path: str, face_row: np.ndarray) -> np.ndarray:
    img = _read(path)
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_face.py -v`
Expected: PASS, 4 passed

- [ ] **Step 7: Commit**

```bash
git add scripts/download_models.py app/engines/face.py tests/test_face.py
git commit -m "feat: face detection and selfie-to-portrait biometric match"
```

---

## Task 12: Cross-document consistency · stretch, cut first

**Why:** the PS asks us to verify "the document to the selfies and other documents". A traveller presents a passport **and** a visa. Each can be internally flawless and still contradict the other — the visa names a different passport number, or the DOB differs by a digit. Prior submissions for the same passport number are a third source to compare against.

**Files:**
- Create: `app/engines/crossdoc.py`, `tests/test_crossdoc.py`

**Interfaces:**
- Consumes: `Signal`, `rapidfuzz`
- Produces: `run(sources: list[dict]) -> list[Signal]` — each source is `{"source": str, "full_name": str, "dob": str, "passport_no": str, "nationality": str}`; any key may be missing or empty. `source` is a label such as `"passport MRZ"`, `"visa MRZ"`, `"claimed"`, `"prior case a3f9c2"`.

**Design note:** a pure function over a list of field dictionaries. It knows nothing about images, OCR or the database — the pipeline assembles the sources. This keeps it trivially testable, and it means adding a fourth document type later costs zero changes here.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_crossdoc.py
from app.engines import crossdoc

PASSPORT = {"source": "passport MRZ", "full_name": "ANNA MARIA ERIKSSON",
            "dob": "740812", "passport_no": "L898902C3", "nationality": "UTO"}

def test_consistent_documents_are_clean():
    visa = dict(PASSPORT, source="visa MRZ")
    signals = crossdoc.run([PASSPORT, visa])
    assert [s.code for s in signals] == ["XDOC_CONSISTENT"]

def test_passport_number_disagreement_is_critical():
    visa = dict(PASSPORT, source="visa MRZ", passport_no="X12345678")
    signals = crossdoc.run([PASSPORT, visa])
    hit = [s for s in signals if s.code == "XDOC_PASSPORT_NO_MISMATCH"]
    assert hit and hit[0].severity == "critical"

def test_dob_disagreement_is_flagged():
    visa = dict(PASSPORT, source="visa MRZ", dob="740813")
    assert "XDOC_DOB_MISMATCH" in [s.code for s in crossdoc.run([PASSPORT, visa])]

def test_name_order_and_case_do_not_count_as_mismatch():
    visa = dict(PASSPORT, source="visa MRZ", full_name="eriksson anna maria")
    assert "XDOC_NAME_MISMATCH" not in [s.code for s in crossdoc.run([PASSPORT, visa])]

def test_genuinely_different_name_is_flagged():
    visa = dict(PASSPORT, source="visa MRZ", full_name="JOHN PETER SMITH")
    assert "XDOC_NAME_MISMATCH" in [s.code for s in crossdoc.run([PASSPORT, visa])]

def test_missing_fields_are_not_treated_as_disagreement():
    sparse = {"source": "claimed", "full_name": "Anna Maria Eriksson"}
    codes = [s.code for s in crossdoc.run([PASSPORT, sparse])]
    assert "XDOC_DOB_MISMATCH" not in codes
    assert "XDOC_PASSPORT_NO_MISMATCH" not in codes

def test_single_source_emits_nothing():
    assert crossdoc.run([PASSPORT]) == []

def test_message_names_both_sources():
    visa = dict(PASSPORT, source="visa MRZ", dob="740813")
    hit = [s for s in crossdoc.run([PASSPORT, visa]) if s.code == "XDOC_DOB_MISMATCH"][0]
    assert "passport MRZ" in hit.message and "visa MRZ" in hit.message
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_crossdoc.py -v`
Expected: FAIL — `ImportError: cannot import name 'crossdoc'`

- [ ] **Step 3: Write `app/engines/crossdoc.py`**

```python
"""Compares identity fields across passport, visa, claim and prior submissions."""
import re
from itertools import combinations
from rapidfuzz import fuzz
from app.models import Signal

NAME_AGREE = 85

def _norm(v: str | None) -> str:
    return re.sub(r"[\s<\-/]", "", (v or "").upper())

def _names_agree(a: str, b: str) -> bool:
    return fuzz.token_sort_ratio(a.upper(), b.upper()) >= NAME_AGREE

_FIELDS = [
    ("passport_no", "XDOC_PASSPORT_NO_MISMATCH", "passport number", "critical"),
    ("dob",         "XDOC_DOB_MISMATCH",         "date of birth",   "high"),
    ("nationality", "XDOC_NATIONALITY_MISMATCH", "nationality",     "high"),
]

def run(sources: list[dict]) -> list[Signal]:
    usable = [src for src in sources if src]
    if len(usable) < 2:
        return []

    signals: list[Signal] = []
    seen: set[tuple] = set()

    for a, b in combinations(usable, 2):
        for key, code, label, severity in _FIELDS:
            va, vb = _norm(a.get(key)), _norm(b.get(key))
            if va and vb and va != vb and (code, key) not in seen:
                seen.add((code, key))
                signals.append(Signal(
                    code=code, engine="crossdoc", severity=severity,
                    message=(f"The {label} disagrees between documents: "
                             f"{a['source']} says {a.get(key)!r}, "
                             f"{b['source']} says {b.get(key)!r}."),
                    evidence={a["source"]: a.get(key), b["source"]: b.get(key)},
                ))

        na, nb = (a.get("full_name") or "").strip(), (b.get("full_name") or "").strip()
        if na and nb and not _names_agree(na, nb) and ("XDOC_NAME_MISMATCH",) not in seen:
            seen.add(("XDOC_NAME_MISMATCH",))
            signals.append(Signal(
                code="XDOC_NAME_MISMATCH", engine="crossdoc", severity="high",
                message=(f"The holder's name disagrees between documents: "
                         f"{a['source']} says {na!r}, {b['source']} says {nb!r}."),
                evidence={a["source"]: na, b["source"]: nb},
            ))

    if not signals:
        signals.append(Signal(
            code="XDOC_CONSISTENT", engine="crossdoc", severity="info",
            message=(f"Name, date of birth, passport number and nationality agree across "
                     f"all {len(usable)} sources ({', '.join(x['source'] for x in usable)})."),
        ))
    return signals
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_crossdoc.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add app/engines/crossdoc.py tests/test_crossdoc.py
git commit -m "feat: cross-document consistency across passport, visa and prior cases"
```

---

## Task 13: Pipeline orchestrator

**Files:**
- Create: `app/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: every engine module, `scoring`, `db`, `annotate.draw_evidence`, `metadata.file_sha256`
- Produces: `screen(inp: ScreeningInput, db_path: str = config.DB_PATH) -> ScreeningResult`

**The single most important property of this module:** no engine may ever break the request. Each is called inside its own `try`, and a raised exception becomes an `ENGINE_ERROR` signal plus an entry in `result.engine_errors`. A judge uploading a corrupt file must still see a verdict screen.

**Ordering matters:** OCR runs first, because it discovers both the MRZ lines that `mrz` validates and the field boxes that `fieldforensics` analyses. Face detection runs before `fieldforensics` so the portrait region can be included in the per-field comparison.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
import pytest
from app import db, pipeline
from app.models import ScreeningInput

@pytest.fixture
def dbfile(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    return p

def test_clean_identity_without_document_scores_low(dbfile):
    inp = ScreeningInput(claimed={
        "full_name": "Jonathan Michael Brewster", "dob": "1988-03-14",
        "passport_no": "L898902C3", "nationality": "UTO",
        "email": "jonathan.brewster@gmail.com", "phone": "9845012763",
    })
    result = pipeline.screen(inp, dbfile)
    assert result.band in ("CLEAR", "REVIEW")
    assert result.case_id

def test_watchlist_hit_forces_reject(dbfile):
    inp = ScreeningInput(claimed={"full_name": "Viktor Anatolyevich Petrov"})
    result = pipeline.screen(inp, dbfile)
    assert result.band == "REJECT"

def test_broken_document_path_does_not_crash(dbfile):
    inp = ScreeningInput(claimed={"full_name": "A B"}, doc_path="/does/not/exist.jpg")
    result = pipeline.screen(inp, dbfile)
    assert isinstance(result.score, int)

def test_engine_exception_is_captured_not_raised(dbfile, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("engine exploded")
    monkeypatch.setattr(pipeline.identity, "run", boom)
    result = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}), dbfile)
    assert any("identity" in e for e in result.engine_errors)
    assert "ENGINE_ERROR" in [s.code for s in result.signals]

def test_case_is_persisted_and_second_submission_sees_it(dbfile):
    claimed = {"full_name": "Anna Eriksson", "passport_no": "L898902C3"}
    pipeline.screen(ScreeningInput(claimed=claimed), dbfile)
    second = pipeline.screen(
        ScreeningInput(claimed={"full_name": "Different Person",
                                "passport_no": "L898902C3"}), dbfile)
    assert "VEL_ID_REUSED_NEW_NAME" in [s.code for s in second.signals]

def test_result_serialises_to_dict(dbfile):
    r = pipeline.screen(ScreeningInput(claimed={"full_name": "A B"}), dbfile)
    d = r.to_dict()
    assert set(d) >= {"case_id", "score", "band", "signals", "engine_errors"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipeline'`

- [ ] **Step 3: Write `app/pipeline.py`**

```python
"""Fans a screening request out across every engine and folds the result."""
import os
import uuid
from app import annotate, config, db, scoring
from app.engines import (crossdoc, face, fieldforensics, identity, metadata, mrz,
                         ocr, tamper, velocity, watchlist)
from app.models import ScreeningInput, ScreeningResult, Signal

def _safe(engine_name: str, fn, *args, **kwargs):
    """Run an engine; convert any failure into a signal instead of an exception."""
    try:
        return fn(*args, **kwargs), None
    except Exception as e:
        err = f"{engine_name}: {type(e).__name__}: {e}"
        sig = Signal(code="ENGINE_ERROR", engine=engine_name, severity="low",
                     message=f"The {engine_name} engine could not complete: {e}")
        return [sig], err

def _ocr_document(path: str, claimed: dict, label: str, signals: list, errors: list):
    """OCR one document. Returns (mrz_lines, boxes); never raises."""
    try:
        sigs, mrz_lines, boxes = ocr.run(path, claimed)
        for sg in sigs:
            if label != "passport":
                sg.message = f"[{label}] {sg.message}"
        signals.extend(sigs)
        return mrz_lines, boxes
    except Exception as e:
        errors.append(f"ocr[{label}]: {type(e).__name__}: {e}")
        signals.append(Signal(code="ENGINE_ERROR", engine="ocr", severity="low",
                              message=f"OCR could not read the {label}: {e}"))
        return [], []

def _mrz_fields(lines: list[str], label: str) -> dict | None:
    if len(lines) < 2:
        return None
    try:
        f = mrz.parse_td3(lines[0], lines[1])
    except Exception:
        return None
    return {"source": f"{label} MRZ", "full_name": f"{f['given_names']} {f['surname']}",
            "dob": f["dob"], "passport_no": f["doc_number"], "nationality": f["nationality"]}

def _largest_face_box(path: str) -> tuple | None:
    try:
        faces = face.detect_faces(path)
    except Exception:
        return None
    if not faces:
        return None
    return tuple(max(faces, key=lambda f: f["box"][2] * f["box"][3])["box"])

def screen(inp: ScreeningInput, db_path: str = config.DB_PATH) -> ScreeningResult:
    case_id = uuid.uuid4().hex[:12]
    signals: list[Signal] = []
    errors: list[str] = []
    doc_hash = None
    evidence_path = None

    has_doc = bool(inp.doc_path and os.path.exists(inp.doc_path))
    has_visa = bool(inp.visa_path and os.path.exists(inp.visa_path))

    if has_doc:
        try:
            doc_hash = metadata.file_sha256(inp.doc_path)
        except Exception as e:
            errors.append(f"hash: {e}")

    # 1. Text first. OCR discovers the MRZ lines and the field boxes everything else needs.
    mrz_lines, boxes = ([], [])
    if has_doc:
        mrz_lines, boxes = _ocr_document(inp.doc_path, inp.claimed, "passport", signals, errors)

    visa_mrz: list[str] = []
    visa_boxes: list[dict] = []
    if has_visa:
        visa_mrz, visa_boxes = _ocr_document(inp.visa_path, {}, "visa", signals, errors)

    # 2. MRZ check digits - the self-proving arithmetic.
    if mrz_lines:
        out, err = _safe("mrz", mrz.run, mrz_lines, inp.claimed)
        signals += out
        if err:
            errors.append(err)

    # 3. Rules engines that need no image.
    for name, fn, args in (
        ("identity",  identity.run,  (inp.claimed,)),
        ("watchlist", watchlist.run, (inp.claimed,)),
        ("velocity",  velocity.run,  (inp.claimed, doc_hash, db_path)),
    ):
        out, err = _safe(name, fn, *args)
        signals += out
        if err:
            errors.append(err)

    # 4. Cross-document: passport MRZ vs visa MRZ vs the applicant's own claim.
    sources = [src for src in (
        _mrz_fields(mrz_lines, "passport"),
        _mrz_fields(visa_mrz, "visa"),
        {"source": "claimed", **{k: inp.claimed.get(k) for k in
                                 ("full_name", "dob", "passport_no", "nationality")}},
    ) if src]
    out, err = _safe("crossdoc", crossdoc.run, sources)
    signals += out
    if err:
        errors.append(err)

    # 5. Pixel forensics on the passport image.
    if has_doc:
        portrait_box = _largest_face_box(inp.doc_path)

        for name, fn, args in (
            ("metadata", metadata.run, (inp.doc_path,)),
            ("tamper",   tamper.run,   (inp.doc_path,)),
            ("face",     face.run,     (inp.doc_path, inp.selfie_path)),
        ):
            out, err = _safe(name, fn, *args)
            signals += out
            if err:
                errors.append(err)

        # 6. The centerpiece: which field was altered, drawn onto an evidence image.
        try:
            ff_signals, regions = fieldforensics.run(inp.doc_path, boxes, portrait_box)
            signals += ff_signals
            if regions:
                evidence_path = annotate.draw_evidence(inp.doc_path, regions,
                                                       config.EVIDENCE_DIR)
        except Exception as e:
            errors.append(f"fieldforensics: {type(e).__name__}: {e}")
            signals.append(Signal(code="ENGINE_ERROR", engine="fieldforensics",
                                  severity="low",
                                  message=f"Field-level analysis could not complete: {e}"))

    # 7. Same analysis on the visa - this is what catches a forged entry stamp.
    if has_visa:
        try:
            v_signals, v_regions = fieldforensics.run(inp.visa_path, visa_boxes,
                                                      _largest_face_box(inp.visa_path))
            for sg in v_signals:
                sg.message = f"[visa] {sg.message}"
            signals += [sg for sg in v_signals if sg.severity != "info"]
            if any(r["suspect"] for r in v_regions):
                evidence_path = annotate.draw_evidence(inp.visa_path, v_regions,
                                                       config.EVIDENCE_DIR)
        except Exception as e:
            errors.append(f"fieldforensics[visa]: {type(e).__name__}: {e}")

    score, band = scoring.score_signals(signals)
    result = ScreeningResult(case_id=case_id, score=score, band=band, signals=signals,
                             engine_errors=errors, evidence_path=evidence_path)

    try:
        db.save_case(db_path, case_id, inp.claimed, score, band, signals, doc_hash)
    except Exception as e:
        result.engine_errors.append(f"persistence: {e}")
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_pipeline.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Run the entire suite — nothing may have regressed**

Run: `./.venv/bin/pytest -v`
Expected: every test from Tasks 0-11 passes.

- [ ] **Step 6: Commit**

```bash
git add app/pipeline.py tests/test_pipeline.py
git commit -m "feat: screening pipeline with per-engine fault isolation"
```

---

## Task 14: HTTP API

**Files:**
- Modify: `app/main.py` (replace the Task 0 contents entirely)
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `pipeline.screen`, `db.all_cases`, `report`
- Produces:
  - `POST /api/screen` — multipart: optional `document` (passport), optional `visa`, optional `selfie`, plus form fields `full_name, dob, passport_no, nationality, email, phone, address`. Returns the `ScreeningResult` dict plus `top_reasons` and `evidence_url`.
  - `GET /evidence/<file>` — annotated evidence images
  - `GET /api/cases` — recent case list for the dashboard
  - `GET /health`
  - `GET /` — serves `static/index.html`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api.py
import io
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(config, "EVIDENCE_DIR", str(tmp_path / "evidence"))
    from app.main import app, startup
    startup()
    return TestClient(app)

def test_health(client):
    assert client.get("/health").json()["status"] == "ok"

def test_screen_fields_only(client):
    r = client.post("/api/screen", data={"full_name": "Jonathan Brewster",
                                         "passport_no": "L898902C3"})
    assert r.status_code == 200
    body = r.json()
    assert body["band"] in ("CLEAR", "REVIEW", "REJECT")
    assert isinstance(body["signals"], list)
    assert "top_reasons" in body

def test_screen_flags_watchlist_name(client):
    r = client.post("/api/screen", data={"full_name": "Viktor Anatolyevich Petrov"})
    assert r.json()["band"] == "REJECT"

def test_screen_accepts_an_upload(client):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    buf.seek(0)
    r = client.post("/api/screen",
                    data={"full_name": "Jonathan Brewster"},
                    files={"document": ("id.png", buf, "image/png")})
    assert r.status_code == 200
    assert r.json()["case_id"]

def test_screen_with_no_input_still_returns_a_verdict(client):
    r = client.post("/api/screen", data={})
    assert r.status_code == 200
    assert r.json()["band"] == "CLEAR"

def test_cases_listing_grows(client):
    client.post("/api/screen", data={"full_name": "Aaa Bbb"})
    r = client.get("/api/cases")
    assert r.status_code == 200
    assert len(r.json()["cases"]) >= 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_api.py -v`
Expected: FAIL — `ImportError: cannot import name 'startup' from 'app.main'`

- [ ] **Step 3: Replace `app/main.py`**

```python
"""HTTP surface for the screening system."""
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from app import config, db, report, scoring
from app.models import ScreeningInput
from app.pipeline import screen

def startup() -> None:
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    os.makedirs(config.EVIDENCE_DIR, exist_ok=True)
    db.init_db(config.DB_PATH)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Starlette 1.x removed startup event handlers; lifespan is the supported hook.
    startup()
    yield

app = FastAPI(title="Fake Identity & Document Screening System", lifespan=lifespan)

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

def _save_upload(upload: UploadFile | None) -> str | None:
    if upload is None or not upload.filename:
        return None
    ext = os.path.splitext(upload.filename)[1].lower() or ".bin"
    dest = os.path.join(config.UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    with open(dest, "wb") as fh:
        shutil.copyfileobj(upload.file, fh)
    return dest

@app.post("/api/screen")
async def api_screen(
    document: UploadFile | None = File(default=None),
    visa: UploadFile | None = File(default=None),
    selfie: UploadFile | None = File(default=None),
    full_name: str = Form(default=""),
    dob: str = Form(default=""),
    passport_no: str = Form(default=""),
    nationality: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    address: str = Form(default=""),
) -> dict:
    inp = ScreeningInput(
        claimed={"full_name": full_name, "dob": dob, "passport_no": passport_no,
                 "nationality": nationality, "email": email, "phone": phone,
                 "address": address},
        doc_path=_save_upload(document),
        visa_path=_save_upload(visa),
        selfie_path=_save_upload(selfie),
    )
    result = screen(inp, config.DB_PATH)
    body = result.to_dict()
    body["top_reasons"] = [
        {"code": s.code, "engine": s.engine, "severity": s.severity, "message": s.message}
        for s in scoring.top_reasons(result.signals)
    ]
    body["evidence_url"] = (f"/evidence/{os.path.basename(result.evidence_path)}"
                            if result.evidence_path else None)
    return body

@app.get("/api/cases")
def api_cases() -> dict:
    return {"cases": db.all_cases(config.DB_PATH)}

@app.get("/api/report/{case_id}", response_class=HTMLResponse)
def api_report(case_id: str) -> str:
    return report.render_case_html(config.DB_PATH, case_id)

@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")

os.makedirs(config.EVIDENCE_DIR, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=config.EVIDENCE_DIR), name="evidence")
app.mount("/static", StaticFiles(directory="static"), name="static")
```

**Note:** `app/report.py` does not exist until Task 19. To keep this task independently testable, create a one-line stub now and fill it in at Task 19:

```python
# app/report.py  (stub — completed in Task 19)
def render_case_html(db_path: str, case_id: str) -> str:
    return "<h1>Report pending</h1>"
```

You also need `static/index.html` to exist for `GET /` — create an empty placeholder file now; Task 15 writes the real one.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_api.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Verify by hand**

Run: `./.venv/bin/uvicorn app.main:app --reload --port 8000`
Then:
```bash
curl -s -X POST localhost:8000/api/screen -F "full_name=Viktor Anatolyevich Petrov" | head -40
```
Expected: JSON with `"band": "REJECT"` and a `WL_MATCH` signal.

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/report.py static/index.html tests/test_api.py
git commit -m "feat: screening API with multipart upload and case listing"
```

---

## Task 15: Frontend

**Files:**
- Create: `static/index.html` (replacing the Task 12 placeholder), `static/app.js`, `static/styles.css`

**Interfaces:**
- Consumes: `POST /api/screen`, `GET /api/cases`
- Produces: the thing the judges actually look at

**Design direction — four rules, because a hackathon UI fails in predictable ways:**
0. **The evidence image is the hero.** The passport with the altered field boxed in red is the single image judges will remember. It sits directly under the verdict, full width.
1. **The verdict is the page.** A large score number and a colour-coded band, readable from across a room on a projector. Everything else is secondary.
2. **Every signal shows its reasoning.** A list of reason cards, each with severity chip, engine name, and the full human-readable message. This is the "explainable AI" story — do not truncate the messages.
3. **No framework, no build.** Tailwind via CDN, one `fetch`, `innerHTML` rendering. A build step that breaks at hour 30 is an unforced loss.

- [ ] **Step 1: Write `static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Identity &amp; Document Screening</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
  <header class="border-b border-slate-800 px-6 py-4">
    <h1 class="text-xl font-semibold">Fake Identity &amp; Document Screening System</h1>
    <p class="text-sm text-slate-400">Multi-engine forensic and rules-based fraud detection</p>
  </header>

  <main class="grid gap-6 p-6 lg:grid-cols-2 max-w-7xl mx-auto">
    <section class="bg-slate-900 rounded-xl p-5 border border-slate-800">
      <h2 class="font-semibold mb-4">Applicant submission</h2>
      <form id="screen-form" class="space-y-3">
        <input name="full_name" placeholder="Full name" class="inp">
        <div class="grid grid-cols-2 gap-3">
          <input name="dob" placeholder="DOB (YYYY-MM-DD)" class="inp">
          <input name="phone" placeholder="Phone" class="inp">
        </div>
        <div class="grid grid-cols-2 gap-3">
          <input name="passport_no" placeholder="Passport number" class="inp">
          <input name="nationality" placeholder="Nationality (e.g. IND)" class="inp">
        </div>
        <input name="email" placeholder="Email" class="inp">
        <label class="block text-sm text-slate-400">Passport image
          <input type="file" name="document" accept="image/*,.pdf" class="inp mt-1">
        </label>
        <label class="block text-sm text-slate-400">Visa image (optional)
          <input type="file" name="visa" accept="image/*" class="inp mt-1">
        </label>
        <label class="block text-sm text-slate-400">Selfie (optional)
          <input type="file" name="selfie" accept="image/*" class="inp mt-1">
        </label>
        <button type="submit" id="submit-btn"
                class="w-full bg-sky-600 hover:bg-sky-500 rounded-lg py-2.5 font-medium">
          Screen applicant
        </button>
      </form>
    </section>

    <section class="space-y-4">
      <div id="verdict" class="hidden bg-slate-900 rounded-xl p-6 border-2 text-center">
        <div id="score" class="text-6xl font-bold"></div>
        <div id="band" class="text-2xl font-semibold mt-1"></div>
        <div id="case-id" class="text-xs text-slate-500 mt-2"></div>
      </div>
      <figure id="evidence-wrap" class="hidden bg-slate-900 rounded-xl p-3 border border-slate-800">
        <figcaption class="text-sm text-slate-400 mb-2">
          Evidence — altered regions boxed in red
        </figcaption>
        <img id="evidence" alt="Annotated evidence image" class="w-full rounded-lg">
      </figure>
      <div id="reasons" class="space-y-2"></div>
      <details id="all-signals-wrap" class="hidden bg-slate-900 rounded-xl border border-slate-800 p-4">
        <summary class="cursor-pointer text-sm text-slate-400">All engine output</summary>
        <div id="all-signals" class="mt-3 space-y-2"></div>
      </details>
    </section>
  </main>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `static/styles.css`**

```css
.inp {
  width: 100%;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 0.5rem;
  padding: 0.55rem 0.75rem;
  color: #e2e8f0;
  font-size: 0.9rem;
}
.inp::placeholder { color: #64748b; }
.inp:focus { outline: 2px solid #0284c7; outline-offset: -1px; }
.chip {
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em;
  padding: 0.15rem 0.5rem; border-radius: 999px; font-weight: 600;
}
```

- [ ] **Step 3: Write `static/app.js`**

```javascript
const BAND_STYLE = {
  CLEAR:  { border: "#16a34a", text: "#4ade80", label: "CLEAR" },
  REVIEW: { border: "#d97706", text: "#fbbf24", label: "MANUAL REVIEW" },
  REJECT: { border: "#dc2626", text: "#f87171", label: "REJECT" },
};

const SEVERITY_STYLE = {
  critical: "background:#7f1d1d;color:#fecaca",
  high:     "background:#7c2d12;color:#fed7aa",
  medium:   "background:#713f12;color:#fde68a",
  low:      "background:#1e3a5f;color:#bfdbfe",
  info:     "background:#1e293b;color:#94a3b8",
};

function signalCard(s) {
  return `
    <div class="bg-slate-900 border border-slate-800 rounded-lg p-3">
      <div class="flex items-center gap-2 mb-1">
        <span class="chip" style="${SEVERITY_STYLE[s.severity] || SEVERITY_STYLE.info}">
          ${s.severity}
        </span>
        <span class="text-xs text-slate-500">${s.engine}</span>
        <span class="text-xs text-slate-600 font-mono ml-auto">${s.code}</span>
      </div>
      <p class="text-sm text-slate-300 leading-relaxed">${s.message}</p>
    </div>`;
}

document.getElementById("screen-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("submit-btn");
  btn.disabled = true;
  btn.textContent = "Screening…";

  try {
    const res = await fetch("/api/screen", {
      method: "POST",
      body: new FormData(e.target),
    });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    render(await res.json());
  } catch (err) {
    document.getElementById("reasons").innerHTML =
      `<div class="bg-red-950 border border-red-800 rounded-lg p-3 text-sm">
         Screening failed: ${err.message}
       </div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Screen applicant";
  }
});

function render(data) {
  const style = BAND_STYLE[data.band] || BAND_STYLE.REVIEW;
  const verdict = document.getElementById("verdict");
  verdict.classList.remove("hidden");
  verdict.style.borderColor = style.border;
  document.getElementById("score").textContent = data.score;
  document.getElementById("score").style.color = style.text;
  const band = document.getElementById("band");
  band.textContent = style.label;
  band.style.color = style.text;
  document.getElementById("case-id").textContent = `Case ${data.case_id}`;

  const evWrap = document.getElementById("evidence-wrap");
  if (data.evidence_url) {
    document.getElementById("evidence").src = `${data.evidence_url}?t=${Date.now()}`;
    evWrap.classList.remove("hidden");
  } else {
    evWrap.classList.add("hidden");
  }

  const reasons = data.top_reasons || [];
  document.getElementById("reasons").innerHTML = reasons.length
    ? reasons.map(signalCard).join("")
    : `<div class="bg-slate-900 border border-slate-800 rounded-lg p-3 text-sm text-slate-400">
         No risk indicators were raised by any engine.
       </div>`;

  document.getElementById("all-signals-wrap").classList.remove("hidden");
  document.getElementById("all-signals").innerHTML =
    (data.signals || []).map(signalCard).join("");
}
```

- [ ] **Step 4: Verify in a browser**

Run: `./.venv/bin/uvicorn app.main:app --reload --port 8000`, open `http://localhost:8000`.

Check all three by hand:
1. Submit `Viktor Anatolyevich Petrov` with nothing else → red REJECT, watchlist reason card.
2. Submit `Jonathan Brewster` + passport no `L898902C3` → green CLEAR.
3. Submit `Asdf Qwerty` + email `x@mailinator.com` + phone `1234567890` → amber or red with three distinct reason cards.
4. After Task 16: upload `03_dob_retyped.jpg` → **the evidence image appears with the DOB field boxed in red.**

- [ ] **Step 5: Commit**

```bash
git add static/
git commit -m "feat: screening UI with verdict display and per-signal reasoning"
```

---

## Task 16: Sample case generator — passports and visas

**Files:**
- Create: `scripts/make_samples.py`, `data/samples/.gitkeep`

**Interfaces:**
- Consumes: `PIL`, `app.engines.mrz.check_digit`
- Produces: seven images in `data/samples/` plus `data/samples/manifest.json` recording each case's expected verdict and the story to tell

**This task is worth far more than it looks.** A demo without prepared, deterministic cases becomes live improvisation in front of judges. Seven files that each cleanly exercise one attack named in the PS is what turns "here is a form" into "watch it catch every forgery in your problem statement".

**Every sample is drawn from scratch. Never a real document.**

**How the field tamper is simulated — this matters for honesty on stage:** the generator saves the genuine document as JPEG (its "issued" compression history), reloads it, paints over one field and re-types a new value, then saves again at a different quality. That is precisely the physical process a forger follows in an image editor, and it is exactly the compression discontinuity `fieldforensics` hunts.

| # | File | PS attack | Expected |
|---|---|---|---|
| 1 | `01_clean_passport.jpg` | — | CLEAR |
| 2 | `02_mrz_tampered.jpg` | altered number | REVIEW/REJECT — MRZ check digit |
| 3 | `03_dob_retyped.jpg` | **altered DOB** | REVIEW — **DOB boxed red** ⭐ |
| 4 | `04_photo_substituted.jpg` | **altered photograph** | REVIEW — portrait boxed red |
| 5 | `05_name_retyped.jpg` | **altered name** | REVIEW/REJECT — name boxed + MRZ name mismatch |
| 6 | `06_visa_forged_stamp.jpg` | **forged visa stamp** | REVIEW — stamp boxed red |
| 7 | `07_visa_mismatch.jpg` + `01` | cross-document | REJECT — visa names a different passport |

- [ ] **Step 1: Write `scripts/make_samples.py`**

```python
"""Generates synthetic clean and forged passports and visas for the SIH26188 demo."""
import io
import json
import os
import random
from PIL import Image, ImageDraw, ImageFont
from app.engines.mrz import check_digit

OUT = "data/samples"
W, H = 1000, 640

def _font(size: int):
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def _mono(size: int):
    for path in ("/System/Library/Fonts/Menlo.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                 "C:/Windows/Fonts/consola.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def build_mrz(doc_type: str, surname: str, given: str, doc_no: str, nat: str,
              dob: str, sex: str, expiry: str) -> tuple[str, str]:
    name_field = f"{surname}<<{given.replace(' ', '<')}".ljust(39, "<")[:39]
    l1 = f"{doc_type}<{nat}{name_field}"
    doc = doc_no.ljust(9, "<")[:9]
    personal = "<" * 14
    body = (f"{doc}{check_digit(doc)}{nat}{dob}{check_digit(dob)}{sex}"
            f"{expiry}{check_digit(expiry)}{personal}{check_digit(personal)}")
    composite = (doc + str(check_digit(doc)) + dob + str(check_digit(dob)) +
                 expiry + str(check_digit(expiry)) + personal + str(check_digit(personal)))
    return l1, (body + str(check_digit(composite))).ljust(44, "<")[:44]

def _noise(img: Image.Image, seed: int = 7) -> None:
    px = img.load()
    rng = random.Random(seed)
    for _ in range(img.width * img.height // 10):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        r, g, b = px[x, y]
        j = rng.randint(-8, 8)
        px[x, y] = (max(0, min(255, r + j)), max(0, min(255, g + j)), max(0, min(255, b + j)))

# Field layout shared by drawing and tampering, so a retyped field lands exactly in place.
FIELD_X, FIELD_Y0, FIELD_STEP = 300, 120, 58
FIELDS = ["Surname", "Given names", "Passport No.", "Nationality",
          "Date of birth", "Sex", "Date of expiry"]

def field_value_box(index: int) -> tuple[int, int, int, int]:
    y = FIELD_Y0 + index * FIELD_STEP + 18
    return FIELD_X - 4, y - 2, 420, 34

def _draw_portrait(d: ImageDraw.ImageDraw, skin=(222, 190, 165), bg=(205, 205, 200)):
    d.rectangle([50, 120, 250, 380], fill=bg)
    d.ellipse([85, 150, 215, 320], fill=skin)
    d.ellipse([115, 210, 137, 226], fill=(40, 30, 25))
    d.ellipse([163, 210, 185, 226], fill=(40, 30, 25))
    d.arc([125, 250, 175, 285], start=10, end=170, fill=(120, 70, 60), width=4)

def draw_passport(p: dict, mrz_override=None) -> Image.Image:
    img = Image.new("RGB", (W, H), (236, 234, 224))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 80], fill=(22, 52, 96))
    d.text((28, 22), "REPUBLIC OF UTOPIA   ·   PASSPORT", font=_font(30), fill="white")
    values = [p["surname"], p["given"], p["doc_no"], p["nat"],
              f"{p['dob'][4:6]}/{p['dob'][2:4]}/19{p['dob'][0:2]}", p["sex"],
              f"{p['expiry'][4:6]}/{p['expiry'][2:4]}/20{p['expiry'][0:2]}"]
    for i, (label, value) in enumerate(zip(FIELDS, values)):
        y = FIELD_Y0 + i * FIELD_STEP
        d.text((FIELD_X, y), label.upper(), font=_font(14), fill=(110, 110, 110))
        d.text((FIELD_X, y + 18), str(value), font=_font(26), fill=(15, 15, 15))
    _draw_portrait(d)
    l1, l2 = mrz_override or build_mrz("P", p["surname"], p["given"], p["doc_no"],
                                       p["nat"], p["dob"], p["sex"], p["expiry"])
    d.rectangle([0, H - 110, W, H], fill=(250, 250, 246))
    d.text((28, H - 94), l1, font=_mono(24), fill=(10, 10, 10))
    d.text((28, H - 52), l2, font=_mono(24), fill=(10, 10, 10))
    _noise(img)
    return img

def draw_visa(p: dict, *, visa_passport_no: str | None = None,
              stamp: bool = True) -> Image.Image:
    img = Image.new("RGB", (W, H), (242, 238, 226))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 80], fill=(96, 30, 44))
    d.text((28, 22), "REPUBLIC OF UTOPIA   ·   ENTRY VISA", font=_font(30), fill="white")
    doc_no = visa_passport_no or p["doc_no"]
    rows = [("Holder", f"{p['given']} {p['surname']}"), ("Passport No.", doc_no),
            ("Nationality", p["nat"]), ("Visa type", "TOURIST - SINGLE ENTRY"),
            ("Valid until", "31/12/2030")]
    for i, (label, value) in enumerate(rows):
        y = FIELD_Y0 + i * 64
        d.text((FIELD_X, y), label.upper(), font=_font(14), fill=(110, 110, 110))
        d.text((FIELD_X, y + 18), value, font=_font(26), fill=(15, 15, 15))
    _draw_portrait(d)
    if stamp:
        d.ellipse([720, 330, 930, 470], outline=(30, 60, 170), width=6)
        d.text((752, 382), "ENTRY  2026", font=_font(26), fill=(30, 60, 170))
    l1, l2 = build_mrz("V", p["surname"], p["given"], doc_no, p["nat"],
                       p["dob"], p["sex"], p["expiry"])
    d.rectangle([0, H - 110, W, H], fill=(250, 250, 246))
    d.text((28, H - 94), l1, font=_mono(24), fill=(10, 10, 10))
    d.text((28, H - 52), l2, font=_mono(24), fill=(10, 10, 10))
    _noise(img, seed=11)
    return img

def save_issued(img: Image.Image, path: str, quality: int = 70) -> None:
    """The genuine document's compression history."""
    img.save(path, "JPEG", quality=quality)

def reload(path: str) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGB").copy()

def retype_field(img: Image.Image, index: int, new_value: str) -> Image.Image:
    """What a forger does in an image editor: paint over a field, type a new value."""
    d = ImageDraw.Draw(img)
    x, y, w, h = field_value_box(index)
    d.rectangle([x, y, x + w, y + h], fill=(236, 234, 224))
    d.text((FIELD_X, y + 2), new_value, font=_font(26), fill=(15, 15, 15))
    return img

BASE = dict(surname="ERIKSSON", given="ANNA MARIA", doc_no="L898902C3",
            nat="UTO", dob="740812", sex="F", expiry="301231")
ANNA = {"full_name": "Anna Maria Eriksson", "dob": "1974-08-12",
        "passport_no": "L898902C3", "nationality": "UTO",
        "email": "anna.eriksson@gmail.com", "phone": "9845012763"}

def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    m = []

    # 1. Genuine passport
    save_issued(draw_passport(BASE), f"{OUT}/01_clean_passport.jpg")
    m.append({"files": {"document": "01_clean_passport.jpg"}, "claimed": ANNA,
              "expect": "CLEAR", "attack": "none",
              "story": "Genuine passport, applicant details match."})

    # 2. MRZ digit altered - the check digit no longer agrees
    l1, l2 = build_mrz("P", **{k: BASE[k] for k in ("surname", "given", "doc_no",
                                                     "nat", "dob", "sex", "expiry")})
    bad = l2[:3] + ("9" if l2[3] != "9" else "7") + l2[4:]
    save_issued(draw_passport(BASE, mrz_override=(l1, bad)), f"{OUT}/02_mrz_tampered.jpg")
    m.append({"files": {"document": "02_mrz_tampered.jpg"}, "claimed": ANNA,
              "expect": "REVIEW/REJECT", "attack": "altered passport number",
              "story": "One digit of the passport number changed. ICAO check digit fails."})

    # 3. DOB retyped - the centerpiece case
    path = f"{OUT}/03_dob_retyped.jpg"
    save_issued(draw_passport(BASE), path)
    retype_field(reload(path), FIELDS.index("Date of birth"), "12/08/1994") \
        .save(path, "JPEG", quality=97)
    m.append({"files": {"document": "03_dob_retyped.jpg"},
              "claimed": dict(ANNA, dob="1994-08-12"),
              "expect": "REVIEW", "attack": "altered DOB",
              "story": "Applicant made themself 20 years younger. The DOB field has a "
                       "different compression history from every other field - boxed red. "
                       "The MRZ still encodes the true 1974 DOB."})

    # 4. Photograph substituted
    path = f"{OUT}/04_photo_substituted.jpg"
    save_issued(draw_passport(BASE), path)
    img = reload(path)
    _draw_portrait(ImageDraw.Draw(img), skin=(200, 160, 130), bg=(190, 198, 214))
    img.save(path, "JPEG", quality=97)
    m.append({"files": {"document": "04_photo_substituted.jpg"}, "claimed": ANNA,
              "expect": "REVIEW", "attack": "altered photograph",
              "story": "Portrait replaced after issue. Photo region is a compression outlier."})

    # 5. Name retyped
    path = f"{OUT}/05_name_retyped.jpg"
    save_issued(draw_passport(BASE), path)
    retype_field(reload(path), FIELDS.index("Surname"), "SHARMA") \
        .save(path, "JPEG", quality=97)
    m.append({"files": {"document": "05_name_retyped.jpg"},
              "claimed": dict(ANNA, full_name="Anna Maria Sharma"),
              "expect": "REVIEW/REJECT", "attack": "altered name",
              "story": "Surname retyped. Field boxed red, and the MRZ still says ERIKSSON."})

    # 6. Visa with forged stamp
    path = f"{OUT}/06_visa_forged_stamp.jpg"
    save_issued(draw_visa(BASE, stamp=False), path)
    img = reload(path)
    d = ImageDraw.Draw(img)
    d.ellipse([720, 330, 930, 470], outline=(30, 60, 170), width=6)
    d.text((752, 382), "ENTRY  2026", font=_font(26), fill=(30, 60, 170))
    img.save(path, "JPEG", quality=97)
    save_issued(draw_passport(BASE), f"{OUT}/06_passport_for_visa.jpg")
    m.append({"files": {"document": "06_passport_for_visa.jpg",
                        "visa": "06_visa_forged_stamp.jpg"},
              "claimed": ANNA, "expect": "REVIEW", "attack": "forged visa stamp",
              "story": "Entry stamp added to the visa after issue. Stamp region boxed red."})

    # 7. Visa issued against a different passport
    save_issued(draw_visa(BASE, visa_passport_no="X47281956"), f"{OUT}/07_visa_mismatch.jpg")
    m.append({"files": {"document": "01_clean_passport.jpg",
                        "visa": "07_visa_mismatch.jpg"},
              "claimed": ANNA, "expect": "REJECT", "attack": "cross-document mismatch",
              "story": "Both documents are individually flawless. The visa was issued "
                       "against passport X47281956; the passport presented is L898902C3."})

    with open(f"{OUT}/manifest.json", "w") as fh:
        json.dump(m, fh, indent=2)
    print(f"Wrote {len(m)} cases to {OUT}/")

if __name__ == "__main__":
    main()
```

**Note on case 6:** the pipeline runs `fieldforensics` on the visa as well as the passport (Task 13, step 7), and when the visa has a suspect region its annotated image becomes the evidence shown in the UI. That is what surfaces the forged stamp.

- [ ] **Step 2: Generate and eyeball the output**

Run: `./.venv/bin/python -m scripts.make_samples && ls data/samples/`
Expected: image files plus `manifest.json`. **Open every image.** They must look like plausible documents on a projector. If they look like grey placeholder boxes, spend twenty minutes on `draw_passport` — judges see these images before they see your code.

- [ ] **Step 3: Write `scripts/check_samples.py` and run every case**

```python
"""Runs every manifest case through the pipeline and prints verdict vs expectation."""
import json
import os
from app import config, db
from app.models import ScreeningInput
from app.pipeline import screen

def main() -> None:
    db_path = "samples_check.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db.init_db(db_path)
    for case in json.load(open("data/samples/manifest.json")):
        f = case["files"]
        inp = ScreeningInput(
            claimed=case["claimed"],
            doc_path=f"data/samples/{f['document']}",
            visa_path=f"data/samples/{f['visa']}" if "visa" in f else None,
        )
        r = screen(inp, db_path)
        name = f.get("visa", f["document"])
        print(f"{name:30s} got={r.band:7s} score={r.score:3d}  expect={case['expect']}")
        for s in r.signals:
            if s.severity in ("medium", "high", "critical"):
                print(f"      [{s.severity:8s}] {s.code}")
        if r.evidence_path:
            print(f"      evidence -> {r.evidence_path}")
    os.remove(db_path)

if __name__ == "__main__":
    main()
```

Run: `./.venv/bin/python -m scripts.check_samples`

**This is the calibration loop, and the most important step in Phase 4.**

- `01_clean_passport.jpg` **must** come out CLEAR. If your own clean document flags, the demo dies on stage — fix that before anything else.
- `03_dob_retyped.jpg` **must** produce `FF_FIELD_TAMPERED`, and opening its evidence image must show the DOB boxed red. This is the demo.
- Every other case should land on or adjacent to its `expect`.

If they don't, return to Task 8 Step 5 and Task 10 Step 7 and retune thresholds using the numbers these samples produce. Record final values in the README.

- [ ] **Step 4: Commit**

```bash
git add scripts/make_samples.py scripts/check_samples.py data/samples/.gitkeep
git commit -m "feat: passport and visa sample generator covering every PS attack type"
```

---

## Task 17: Batch screening for high volumes · stretch, cut second

**Why:** the PS states "high volumes of documents make manual inspection inefficient." A single-document UI doesn't answer that line. A batch run that screens a folder and ranks the results — highest risk first, so an officer reads the ten worst instead of all thousand — does.

**Files:**
- Create: `scripts/batch_screen.py`, `tests/test_batch.py`
- Modify: `app/db.py` (add `stats`), `app/main.py` (add `GET /api/stats`)

**Interfaces:**
- Consumes: `pipeline.screen`, `db`
- Produces:
  - `batch_screen.screen_manifest(rows: list[dict], sample_dir: str, db_path: str) -> list[dict]` — one result row per input, sorted by descending score
  - `db.stats(path: str) -> dict` — `{"total": int, "CLEAR": int, "REVIEW": int, "REJECT": int}`
  - `GET /api/stats`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_batch.py
import pytest
from app import db
from scripts import batch_screen

@pytest.fixture
def dbfile(tmp_path):
    p = str(tmp_path / "b.db")
    db.init_db(p)
    return p

def test_results_are_sorted_highest_risk_first(dbfile, tmp_path):
    rows = [
        {"claimed": {"full_name": "Jonathan Brewster"}, "files": {}},
        {"claimed": {"full_name": "Viktor Anatolyevich Petrov"}, "files": {}},
        {"claimed": {"full_name": "Asdf Qwerty", "email": "x@mailinator.com"}, "files": {}},
    ]
    out = batch_screen.screen_manifest(rows, str(tmp_path), dbfile)
    scores = [r["score"] for r in out]
    assert scores == sorted(scores, reverse=True)
    assert out[0]["band"] == "REJECT"

def test_every_input_produces_one_row(dbfile, tmp_path):
    rows = [{"claimed": {"full_name": f"Person Number{i}"}, "files": {}} for i in range(4)]
    assert len(batch_screen.screen_manifest(rows, str(tmp_path), dbfile)) == 4

def test_stats_counts_bands(dbfile, tmp_path):
    rows = [{"claimed": {"full_name": "Viktor Anatolyevich Petrov"}, "files": {}},
            {"claimed": {"full_name": "Jonathan Brewster"}, "files": {}}]
    batch_screen.screen_manifest(rows, str(tmp_path), dbfile)
    st = db.stats(dbfile)
    assert st["total"] == 2 and st["REJECT"] >= 1
```

Also create an empty `scripts/__init__.py` so `from scripts import batch_screen` resolves.

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_batch.py -v`
Expected: FAIL — `ImportError: cannot import name 'batch_screen'`

- [ ] **Step 3: Add `stats` to `app/db.py`**

```python
def stats(path: str) -> dict:
    out = {"total": 0, "CLEAR": 0, "REVIEW": 0, "REJECT": 0}
    with _conn(path) as con:
        for row in con.execute("SELECT band, COUNT(*) AS n FROM cases GROUP BY band"):
            out[row["band"]] = row["n"]
            out["total"] += row["n"]
    return out
```

- [ ] **Step 4: Write `scripts/batch_screen.py`**

```python
"""Screens many applications at once and ranks them highest-risk first.

Usage: python -m scripts.batch_screen data/samples/manifest.json   (run from the repo root)
"""
import csv
import json
import os
import sys
import time
from app import config, db
from app.models import ScreeningInput
from app.pipeline import screen

def screen_manifest(rows: list[dict], sample_dir: str, db_path: str) -> list[dict]:
    results = []
    for row in rows:
        files = row.get("files", {})
        path = lambda key: os.path.join(sample_dir, files[key]) if key in files else None
        r = screen(ScreeningInput(claimed=row.get("claimed", {}),
                                  doc_path=path("document"), visa_path=path("visa")),
                   db_path)
        top = next((s for s in r.signals if s.severity in ("critical", "high")), None)
        results.append({
            "case_id": r.case_id,
            "applicant": row.get("claimed", {}).get("full_name", ""),
            "score": r.score,
            "band": r.band,
            "top_reason": top.message if top else "",
        })
    return sorted(results, key=lambda x: x["score"], reverse=True)

def main() -> None:
    manifest = sys.argv[1] if len(sys.argv) > 1 else "data/samples/manifest.json"
    db.init_db(config.DB_PATH)
    rows = json.load(open(manifest))
    started = time.perf_counter()
    results = screen_manifest(rows, os.path.dirname(manifest), config.DB_PATH)
    elapsed = time.perf_counter() - started

    out = "batch_results.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    print(f"Screened {len(results)} applications in {elapsed:.1f}s "
          f"({elapsed / len(results):.2f}s each). Ranked results -> {out}")
    for r in results[:10]:
        print(f"  {r['score']:3d}  {r['band']:7s}  {r['applicant']}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Add `GET /api/stats` to `app/main.py`**

```python
@app.get("/api/stats")
def api_stats() -> dict:
    return db.stats(config.DB_PATH)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_batch.py -v`
Expected: PASS, 3 passed

- [ ] **Step 7: Measure throughput — you will be asked**

Run: `./.venv/bin/python -m scripts.batch_screen`
Write the "seconds per document" figure into the README and onto a slide. "Screens a passport in N seconds on a laptop, fully offline" is a concrete, defensible claim that directly answers the PS's volume line.

- [ ] **Step 8: Commit**

```bash
git add scripts/__init__.py scripts/batch_screen.py app/db.py app/main.py tests/test_batch.py
git commit -m "feat: batch screening ranked by risk, with band statistics endpoint"
```

---

## Task 19 (optional): Case report

**Files:**
- Modify: `app/report.py` (replacing the Task 12 stub)
- Create: `tests/test_report.py`

**Interfaces:**
- Consumes: `db`, stdlib `json`
- Produces: `render_case_html(db_path: str, case_id: str) -> str`

**Why bother:** "we produce an auditable analyst case file" is a different claim from "we show a score". It is one small function and it closes the loop on the product story. Browser print-to-PDF gives you PDF export for free — do not add a PDF library.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report.py
import pytest
from app import db, report
from app.models import Signal

@pytest.fixture
def dbfile(tmp_path):
    p = str(tmp_path / "r.db")
    db.init_db(p)
    db.save_case(p, "abc123", {"full_name": "Anna Eriksson", "email": "a@b.com"},
                 72, "REJECT",
                 [Signal(code="WL_MATCH", engine="watchlist", severity="critical",
                         message="Matched sanctions list.")])
    return p

def test_report_contains_case_details(dbfile):
    html = report.render_case_html(dbfile, "abc123")
    assert "abc123" in html
    assert "Anna Eriksson" in html
    assert "REJECT" in html
    assert "Matched sanctions list." in html

def test_unknown_case_returns_not_found(dbfile):
    assert "not found" in report.render_case_html(dbfile, "nope").lower()

def test_report_escapes_injected_markup(dbfile):
    db.save_case(dbfile, "xss1", {"full_name": "<script>alert(1)</script>"},
                 10, "CLEAR", [])
    html = report.render_case_html(dbfile, "xss1")
    assert "<script>alert(1)</script>" not in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest tests/test_report.py -v`
Expected: FAIL — the stub returns `"<h1>Report pending</h1>"`, so the first assertion fails.

- [ ] **Step 3: Write `app/report.py`**

```python
"""Renders an auditable analyst case file for a completed screening."""
import html
import json
import sqlite3

SEVERITY_COLOR = {
    "critical": "#dc2626", "high": "#ea580c", "medium": "#d97706",
    "low": "#0284c7", "info": "#64748b",
}

def render_case_html(db_path: str, case_id: str) -> str:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    finally:
        con.close()

    if row is None:
        return f"<h1>Case {html.escape(case_id)} not found</h1>"

    payload = json.loads(row["payload"] or "{}")
    claimed = payload.get("claimed", {})
    signals = payload.get("signals", [])

    fields = "".join(
        f"<tr><th>{html.escape(str(k).replace('_', ' ').title())}</th>"
        f"<td>{html.escape(str(v))}</td></tr>"
        for k, v in claimed.items() if v
    )

    rows = "".join(
        f"<tr>"
        f"<td><span class='sev' style='background:{SEVERITY_COLOR.get(s['severity'], '#64748b')}'>"
        f"{html.escape(s['severity'])}</span></td>"
        f"<td>{html.escape(s['engine'])}</td>"
        f"<td><code>{html.escape(s['code'])}</code></td>"
        f"<td>{html.escape(s['message'])}</td>"
        f"</tr>"
        for s in signals
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Case {html.escape(case_id)}</title>
<style>
 body {{ font-family: -apple-system, system-ui, sans-serif; margin: 40px auto;
         max-width: 900px; color: #0f172a; }}
 h1 {{ margin-bottom: 4px; }}
 .meta {{ color: #64748b; font-size: 14px; margin-bottom: 24px; }}
 .verdict {{ font-size: 40px; font-weight: 700; }}
 table {{ border-collapse: collapse; width: 100%; margin-bottom: 28px; font-size: 14px; }}
 th, td {{ border: 1px solid #e2e8f0; padding: 8px 10px; text-align: left;
           vertical-align: top; }}
 th {{ background: #f8fafc; width: 160px; }}
 .sev {{ color: white; padding: 2px 8px; border-radius: 999px;
         font-size: 11px; text-transform: uppercase; }}
 code {{ font-size: 12px; color: #475569; }}
 @media print {{ body {{ margin: 0; }} }}
</style></head>
<body>
  <h1>Screening Case Report</h1>
  <div class="meta">Case <strong>{html.escape(case_id)}</strong> ·
       Screened {html.escape(str(row['created_at']))}</div>
  <p class="verdict" style="color:{'#dc2626' if row['band'] == 'REJECT'
       else '#d97706' if row['band'] == 'REVIEW' else '#16a34a'}">
     {html.escape(str(row['band']))} — risk score {row['score']}/100</p>
  <h2>Claimed identity</h2>
  <table>{fields or '<tr><td>No fields supplied</td></tr>'}</table>
  <h2>Engine findings ({len(signals)})</h2>
  <table>
    <tr><th>Severity</th><th>Engine</th><th>Code</th><th>Finding</th></tr>
    {rows or '<tr><td colspan="4">No findings</td></tr>'}
  </table>
</body></html>"""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest tests/test_report.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: View one in the browser**

Screen an applicant through the UI, copy the case id, then open
`http://localhost:8000/api/report/<case_id>`. Print-to-PDF should produce a clean one-page file.

- [ ] **Step 6: Commit**

```bash
git add app/report.py tests/test_report.py
git commit -m "feat: printable analyst case report"
```

---

## Task 18: Harden and rehearse

**Files:**
- Create: `README.md`, `run.sh`, `docs/DEMO_SCRIPT.md`, `docs/JUDGE_QA.md`

**This task is not optional and it is not busywork.** Teams lose hackathons at the demo, not at the keyboard. Budget the full four hours.

- [ ] **Step 1: Write `run.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "==> Creating virtualenv"
  python3 -m venv .venv
fi

echo "==> Installing dependencies"
./.venv/bin/pip install -q -r requirements.txt

if [ ! -f models/face_detection_yunet_2023mar.onnx ]; then
  echo "==> Downloading face models (one time, needs network)"
  ./.venv/bin/python -m scripts.download_models || \
    echo "!! Face models unavailable — the face engine will degrade gracefully."
fi

if [ ! -f data/samples/manifest.json ]; then
  echo "==> Generating sample documents"
  ./.venv/bin/python -m scripts.make_samples
fi

echo "==> Starting on http://localhost:8000"
exec ./.venv/bin/uvicorn app.main:app --port 8000
```

Run: `chmod +x run.sh`

- [ ] **Step 2: Verify the cold-start path on a second machine**

On a teammate's laptop: clone the repo, run `./run.sh`, open `localhost:8000`, screen one applicant.
**If this fails, your demo laptop is a single point of failure.** Fix it now — this is exactly the failure that ends hackathon runs.

- [ ] **Step 3: Write `docs/DEMO_SCRIPT.md`**

Structure the demo to 4 minutes, in this order. The ordering is deliberate: open with the strongest visual, close with the strongest engineering.

```markdown
# Demo Script — SIH26188 (4 minutes)

## 0:00 — The problem, in their words (20s)
"Your problem statement names four forgeries: altered photographs, altered
names, altered dates of birth, and forged visa stamps. And it names the real
problem — volume. An officer can't inspect a thousand passports by eye.
We'll catch all four, and show you exactly where each one is."

## 0:20 — Case 1: genuine passport (20s)
Upload `01_clean_passport.jpg` with matching details.
-> Green, CLEAR. "This is what a genuine traveller looks like."

## 0:40 — Case 3: the altered DOB (70s)  <- THE MOMENT
Upload `03_dob_retyped.jpg`.
-> Evidence image appears. **The date-of-birth field is boxed in red.**
Pause. Let the judges look at it.
"Most systems tell you a document is suspicious. Ours tells you *which field*
was changed. Every field on this page went through the same printing and
compression. This one didn't — it was retyped afterwards. We compare each
field against its own neighbours, so we need no database of genuine passports."
Then point at the MRZ reason: "And the machine-readable zone still encodes
the real 1974 birth date. The forger changed what a human reads, not what
the machine reads."

## 1:50 — Case 2: the MRZ check digit (40s)
Upload `02_mrz_tampered.jpg`.
-> REJECT, MRZ_DOCNUM_CHECKSUM_FAIL. Read the reason aloud.
"This isn't a guess. It's ICAO Doc 9303 arithmetic — the same check every
border control system runs."

## 2:30 — Cases 4 and 6: photograph and visa stamp (40s)
Upload `04_photo_substituted.jpg` -> portrait boxed red.
Upload `06` passport + forged-stamp visa -> stamp boxed red.
"Photographs and visa stamps — the other two attacks in your statement.
Same method, same explanation."

## 3:10 — Case 7: two perfect documents that disagree (30s)
Upload `01` passport with `07_visa_mismatch.jpg`.
-> REJECT, XDOC_PASSPORT_NO_MISMATCH.
"Each document alone is flawless. Together they're impossible — this visa
was issued to a different passport."

## 3:40 — Volume (15s)
Show the batch output ranked by risk. "N seconds a document, offline, on a
laptop. The officer reads the top ten, not all thousand."

## 3:55 — Close (5s)
"Every decision explainable. Every forgery located. No internet required."
```

- [ ] **Step 4: Write `docs/JUDGE_QA.md`**

Prepare honest answers. Judges reward calibration and punish bluffing.

```markdown
# Judge Q&A Prep

**"Is this real AI or just if-statements?"**
Both, deliberately. Computer vision (ELA, ORB copy-move, noise analysis),
neural OCR and neural face recognition (ONNX models) do the perception.
Deterministic rules do the adjudication. We chose explainable adjudication
over a black-box classifier because a fraud decision a bank cannot explain
is a fraud decision a bank cannot use.

**"What's your accuracy?"**
We won't quote a number we can't defend. There is no public labelled forged-ID
dataset we could ethically train or validate against in 24 hours. What we can
show: every engine is unit-tested against known-correct vectors, and the ICAO
check-digit engine is exactly correct by construction, not statistically correct.
For the forensic engines we quote our measured detection rate on SIDTD
(1,900 genuine + 1,900 forged documents) - and only that number.

**"Couldn't ELA false-positive on a genuine document?"**
Yes, and it does — on high-contrast text and non-JPEG sources. That's why
tamper signals cap at 'high' and never 'critical', why one signal alone
lands in REVIEW rather than REJECT, and why the output is a triage
recommendation for a human analyst, not an automated rejection.

**"What happens when an engine crashes on a weird upload?"**
Every engine runs fault-isolated. A failure becomes a low-severity signal
and a logged error; the applicant still gets a verdict. Try to break it —
hand us any file you like.

**"How does field-level detection actually work?"**
Error Level Analysis per region. Re-compress the image and measure how much
each field changes. Fields that went through the original production pipeline
change little; a retyped field changes more. We use a median-based outlier test
so the tampered field can't hide by skewing the average. No reference passport
needed - each field is judged against its own neighbours.

**"Why not train a deep learning model?"**
We do use neural networks - OCR, face detection and face recognition all run
pretrained models. We chose not to *train* a forgery classifier in 36 hours
because there is no labelled Indian passport forgery dataset we could ethically
use, and a border officer can't act on a verdict nobody can explain. Training on
SIDTD is our clear next step.

**"Where does your data come from?"**
Never real documents. Our demo samples are generated from scratch. Validation
uses SIDTD and MIDV-2020, the standard public research datasets of synthetic
identity documents, built specifically because real ID data can't be shared.

**"What would you build next?"**
A classifier trained on SIDTD alongside the explainable engines, liveness
detection on the selfie, template matching against issuing-authority layouts,
and integration with immigration case-management systems.

**"Why no LLM?"**
It runs fully offline with no API dependency. For a compliance system, that's
a feature: no customer PII leaves the machine, and there's no vendor outage
between an applicant and a decision.
```

- [ ] **Step 5: Write `README.md`**

Cover: one-paragraph pitch, `./run.sh` quickstart, the eight engines in a table with what each detects, the scoring model, the tuned threshold values with justification, architecture diagram (ASCII is fine), team roles, and an explicit "synthetic data only, no real PII" statement.

- [ ] **Step 6: Full dress rehearsal, twice**

Close every editor. Run `./run.sh` from cold. Perform the entire demo script aloud, timed, on the actual projector if you can get to it.

Rehearsal one finds the bugs. **Rehearsal two is the one that matters** — do not skip it because the first went well.

- [ ] **Step 7: Record the backup video**

Screen-record a clean 4-minute run. If the laptop dies, the wifi dies, or the projector refuses your resolution, you still have a demo. Put it on a phone and a USB stick.

- [ ] **Step 8: Final commit**

```bash
git add -A
git commit -m "docs: demo script, judge Q&A, README, and one-command runner"
```

---

## Self-Review

**Spec coverage against SIH26188.** Every attack named in the problem statement has an owning engine and a scripted demo case:

| PS text | Engines | Demo case |
|---|---|---|
| "altered photographs" | T10 fieldforensics (portrait), T11 face | `04_photo_substituted` |
| "altered names" | T2 mrz, T9 ocr, T10 fieldforensics | `05_name_retyped` |
| "altered DOBs" | T2 mrz, T10 fieldforensics | `03_dob_retyped` ⭐ |
| "visa stamps" | T10 fieldforensics (stamp regions) | `06_visa_forged_stamp` |
| "manual verification time-consuming / human error" | T5 scoring, T15 explainable UI | every case |
| "high volumes" | T17 batch + stats | batch run |
| pitch: "matches the document holder's face" | T11 face | selfie upload |
| pitch: "cross-document" | T12 crossdoc | `07_visa_mismatch` |
| pitch: "evidence-backed report" | T10 annotate, T19 report | evidence image |

**Interface consistency, checked across tasks.**
- `ocr.run` returns a **3-tuple** `(signals, mrz_lines, boxes)`. Every consumer unpacks three: `pipeline._ocr_document`, the pipeline's visa branch, `scripts/tune_fields.py`, and every `tests/test_ocr.py` call.
- `fieldforensics.run(path, ocr_boxes, portrait_box)` returns `(signals, regions)`; each region is `{"box", "label", "kind", "suspect", "score"}`, which is exactly what `annotate.draw_evidence` reads.
- `ScreeningInput` has `visa_path`; `ScreeningResult` has `evidence_path` and serialises it. The API turns it into `evidence_url`; the frontend reads `evidence_url`.
- Claimed-field keys are `full_name, dob, passport_no, nationality, email, phone, address` in the model, API form, frontend form, DB columns, velocity, crossdoc, samples and batch. No `aadhaar` or `pan` remains.
- `config.ENGINE_WEIGHTS` has a key for every `engine=` string emitted, including `fieldforensics` and `crossdoc`.

**Known soft spots, stated rather than hidden.**
- Tamper and field thresholds are estimates until Task 16 Step 3 calibrates them on real samples. Task 8 Step 5 and Task 10 Step 7 exist to close this, and are explicitly deferred rather than forgotten.
- `test_cloned_region_is_detected` asserts only that copy-move runs, not that it fires. Asserting detection on a synthetic gradient would be flaky and burn hackathon hours; real calibration happens against the samples.
- Synthetic drawn portraits may not trip YuNet, which is trained on photographs. If `FACE_NO_PORTRAIT_ON_DOC` fires on every sample, either composite a public-domain photographic face into the template, or set `ENGINE_WEIGHTS["face"] = 0.0` and drop face from the narrative. Decide at Task 16, never on stage. **Field-level portrait forensics does not depend on this** — if no face is detected, the portrait region simply isn't added, and text-field and stamp analysis continue.
- RapidOCR may split or merge fields differently from the drawn layout. `fieldforensics` works on whatever boxes OCR returns, so this changes labels, not correctness — but check the evidence image by eye at Task 16.

**Cut order, if behind.** T12 crossdoc → T17 batch → T11 face → T19 report → T9's secondary DOB/number cross-checks. **Never cut** T2 mrz, T10 fieldforensics, T5 scoring, or T18 rehearsal.
