# SIH26188 — AI-Based Fake Identity & Document Screening System

Smart India Hackathon · Ministry of Home Affairs. An explainable AI system that verifies
passports and visas, detects forgery and tampering, matches the document holder's face,
and produces an evidence-backed risk score in seconds — fully offline.

Start with `CLAUDE.md` and `docs/PROGRESS.md` for the full project context.

## Quick start

```bash
./run.sh                                      # cold start: venv, deps, models, samples, server
```

`run.sh` is idempotent: it creates `.venv` if missing, installs `requirements.txt`,
downloads the face ONNX models and the SFHQ demo faces once (needs network the first time
only — everything after is offline), generates the 7 scripted sample documents if absent,
then serves the app at `http://localhost:8000`. Re-running it is safe and fast.

```bash
./.venv/bin/pytest -v                         # full test suite
./.venv/bin/python -m scripts.make_samples    # (re)generate the synthetic demo documents
./.venv/bin/python -m scripts.check_samples   # print verdict + score per demo case
./.venv/bin/uvicorn app.main:app --reload --port 8000   # dev server, no cold-start steps
```

See `docs/DEMO_SCRIPT.md` for the stage runbook and `docs/JUDGE_QA.md` for prepared
technical answers.

## Architecture

One Python process. FastAPI serves both the JSON API and the static frontend — no Node, no
bundler, no CORS. Each detection concern is an isolated module in `app/engines/`, taking an
input bundle and returning a `list[Signal]`. `app/pipeline.py` fans out to every engine
inside a per-engine `try/except`, so one engine raising becomes a low-severity
`ENGINE_ERROR` signal instead of a failed request. `app/scoring.py` folds every signal into
a 0-100 risk score and a `CLEAR` (0-29) / `REVIEW` (30-64) / `REJECT` (65-100) band. Storage
is three things, only one a database: sample images are files on disk, the watchlist is one
CSV (`data/watchlist.csv`), and `cases.db` is SQLite holding one row per screening — the
case history that makes cross-document and duplicate-submission detection possible.

## The engines

| Engine | Catches | Key signal codes |
|---|---|---|
| `mrz` | Altered passport fields — ICAO 9303 check-digit arithmetic, self-proving | `MRZ_DOCNUM_CHECKSUM_FAIL`, `MRZ_COMPOSITE_CHECKSUM_FAIL`, `MRZ_NAME_MISMATCH` |
| `fieldforensics` ⭐ | **Which field** was tampered — per-region ELA on OCR text boxes, the portrait region, and visa stamp regions | `FF_FIELD_TAMPERED`, `FF_PHOTO_TAMPERED`, `FF_STAMP_TAMPERED` |
| `ocr` | Claimed name/DOB/number not printed on the uploaded document; supplies the bounding boxes `fieldforensics` needs | — |
| `face` | Missing/duplicate portrait; live selfie-to-portrait match | face cosine similarity vs. `SAME_PERSON`/`DEFINITE_MISMATCH` |
| `liveness` | Printed photo or screen held up to the camera instead of a live head | head-turn yaw-proxy delta vs. `YAW_DELTA_THRESHOLD` |
| `tamper` | Whole-image splicing (ELA), cloning (ORB copy-move), noise inconsistency | `TAMPER_ELA_ANOMALY`, `TAMPER_COPY_MOVE`, `TAMPER_NOISE_INCONSISTENT` |
| `metadata` | EXIF/PDF provenance — editor tags, missing camera data | `META_NO_CAMERA_EXIF` |
| `crossdoc` | Passport vs. visa vs. prior submissions — same person, contradictory details | `XDOC_DOB_MISMATCH`, `XDOC_NAME_MISMATCH`, `XDOC_PASSPORT_NO_MISMATCH` |
| `watchlist` | Sanctions/PEP name matches, fuzzy so transliteration doesn't evade | `WL_MATCH`, `WL_NEAR_MATCH` |
| `facewatch` | Document portrait and selfie vs. a gallery of wanted faces — catches a wanted traveller under a clean forged name, which the text-only name watchlist cannot | `FACE_WL_MATCH`, `FACE_WL_POSSIBLE` |
| `velocity` | Same document under different names, duplicates, bulk bursts | — |

Cut an engine instantly by setting its weight to `0.0` in `app/config.py`'s
`ENGINE_WEIGHTS`. Add one by writing a file in `app/engines/` plus one registry line.

## Synthetic data only — no real identity documents

Every image this repo ships or generates is synthetic. `scripts/make_samples.py` renders
the 7 scripted demo documents from scratch with invented names, numbers and computed (not
copied) MRZ check digits. `data/faces/` holds StyleGAN-generated SFHQ crops — faces of
people who do not exist (MIT licence). The only real photograph ever used is a
**consenting teammate's own live selfie**, captured for the on-stage demo via
`scripts/make_demo_passport.py`; it is written to `data/demo/`, which is gitignored, and is
deleted after the hackathon. Accuracy claims, where made, are measured only against our own
synthetic corpus or the public SIDTD/MIDV-2020 research datasets — never invented, and
never against real documents.

## Calibration

Measured on synthetic documents only (`scripts/make_samples.py`: the 7 demo cases plus
extra genuine identities rendered at JPEG quality 60/70/80/90/95). Each check compares
like with like; thresholds sit above the worst genuine value measured.

| Check | Measure | Genuine (worst) | Forged | Threshold |
|---|---|---|---|---|
| `TAMPER_ELA_ANOMALY` | luma ELA per unit edge energy, 16px textured blocks, vs document median (floor 0.005) | 6.5 (q95) | substituted photo 15.9, 3 contiguous blocks | > 8.0 in >= 2 contiguous blocks |
| `TAMPER_COPY_MOVE` | ORB self-matches at one offset, inside one 96px window, 2D-compact (>= 24px both axes) | 14 (axis-aligned; text row/column coincidences) | cloned texture patch 13 (off-axis); pure vertical/horizontal clone 31 | >= 12 off-axis, >= 20 axis-aligned |
| `TAMPER_NOISE_INCONSISTENT` | p95 / median of MAD noise sigma on smooth (non-print) pixels, 6x6 tiles, floor 0.5 | 1.2 (was 12.6 with Laplacian variance) | pasted noisy camera photo 7.9; noisy splice on photo 4.1 | > 3.0 |
| `FF_FIELD_TAMPERED` | per-field luma ELA, modified z within peer group (background shade; MRZ lines separate) | data fields z <= 1.6 | retyped DOB z 8.1, retyped surname z 8.1 | z > 3.5 (unchanged) |
| `FF_STAMP_TAMPERED` | stamp judged on its OCR lettering, same measure as fields | genuine stamp lettering 0.63 (fields ~0.65) | added stamp lettering 2.42, z 10.8 | z > 3.5 (unchanged) |
| `META_NO_CAMERA_EXIF` | absence of camera make/model | — | — | info only (scanned/issued images have none) |

Limits: whole-image ELA does not catch a single retyped field (DOB peak 4.3);
`fieldforensics` owns that.

All contact details (`email`, `phone`, `address`) on every scripted demo case and the
stage specimen are invented; email addresses use `@example.com` (RFC 2606) so none is
even plausibly a real address. `phone` keeps a valid-shaped number for the identity
checks but is not a real number either.

`face` (SFace cosine similarity, `SAME_PERSON = 0.363`, `DEFINITE_MISMATCH = 0.25`), measured
on the committed SFHQ synthetic crops in `data/faces/`:

| Comparison | Cosine similarity |
|---|---|
| Same synthetic face vs. itself resized + re-saved as JPEG q80 | 0.934 |
| Two different synthetic faces (`sfhq_01` vs `sfhq_02`) | 0.163 (below `DEFINITE_MISMATCH`) |

`facewatch` reuses these same thresholds (`FACE_WL_MATCH = SAME_PERSON = 0.363`,
`FACE_WL_POSSIBLE = 0.30`) against a small gallery of SFHQ crops (`data/face_watchlist.csv`:
`sfhq_05`, `sfhq_06`). Measured cross-similarities among the gallery faces and the other
committed SFHQ crops used elsewhere (samples, demo builder, liveness) were all well below
0.30 (highest observed 0.207), so nothing already in the repo accidentally triggers the
gallery.

`liveness` (challenge-response head turn, `YAW_DELTA_THRESHOLD = 0.045`). The measure is the
yaw proxy — `(nose_x − eye_midpoint_x) / inter-eye distance`, so it is scale-invariant — and
how far its median moves between the first and last third of the challenge frames.

Reproduce with `./.venv/bin/python -m scripts.tune_liveness`. **These sequences are synthetic
warps of the committed SFHQ crops, not recorded humans** — no real person's face may enter
this repo. A real person on camera is the operator's check, not a measured number here.

| Sequence (8 frames, built from `data/faces/`) | Yaw-proxy movement | Verdict |
|---|---|---|
| Synthetic head turn, 0→28°, nose depth 0.45 × face width (7 crops) | +0.065 … +0.120 | `LIVENESS_PASS` |
| Flat photo rotated about its own vertical axis, 0→28° | −0.068 … −0.014 (always the wrong way) | `LIVENESS_FAILED` |
| Static photo, shifted ±5 px and rescaled ±6% | −0.035 … +0.016 | `LIVENESS_FAILED` |

`0.045` sits ~2.8× above the worst photograph and ~1.4× below the weakest synthetic turn.
Geometry puts a real 25° turn near `0.16` (nose protrusion ≈ 0.32 × inter-eye distance ×
tan θ), so a genuine turn should clear it comfortably. One crop (`sfhq_07`) does not move
under the synthetic warp at all — a synthesis artefact, reported by the script and excluded
from the live set.
