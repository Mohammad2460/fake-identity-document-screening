# Judge Q&A Prep — SIH26188

Honest, specific answers. Judges reward calibration and punish bluffing — every
number here is measured (see README's Calibration section and
`./.venv/bin/python -m scripts.check_samples` / `scripts.tune_liveness`), never invented.

## How each attack in the problem statement is caught

| PS attack | Engine(s) | Signal codes |
|---|---|---|
| Altered photograph | `fieldforensics` (portrait region ELA), `face` (selfie match), `facewatch` (wanted-face gallery) | `FF_PHOTO_TAMPERED` |
| Altered name | `mrz` (name vs MRZ), `ocr` (claimed vs printed), `fieldforensics` | `MRZ_NAME_MISMATCH`, `XDOC_NAME_MISMATCH`, `FF_FIELD_TAMPERED` |
| Altered DOB | `mrz` (ICAO check-digit arithmetic), `fieldforensics` (per-field ELA) | `MRZ_DOCNUM_CHECKSUM_FAIL`, `MRZ_COMPOSITE_CHECKSUM_FAIL`, `XDOC_DOB_MISMATCH`, `FF_FIELD_TAMPERED` |
| Forged visa stamp | `fieldforensics` (stamp region ELA) | `FF_STAMP_TAMPERED` |
| High volume | batch/`check_samples`-style bulk run + dashboard | — |

## "How do you make findings understandable to a non-technical officer?"

Every finding is shown in plain language first — one or two short sentences
naming what was checked and what it means for this traveller, no jargon, no
internal numbers. The precise forensic sentence (compression residuals, check
digits, cosine similarity) is still there, one click away behind a
"Technical detail" toggle, so the evidence is never hidden — it is just not
the first thing an officer has to parse. This is the explainability claim,
made concrete: `Signal.plain` and `Signal.message` are two separate,
independently-tested fields on every signal (`app/models.py`).

## "What stops a wanted person just using a different name?"

Nothing about the *name* watchlist — every name source it screens (the typed name, the
passport MRZ, the visa MRZ) is text a forger controls, and a cleanly forged passport in a
name that was never listed passes all three. A face is different: it cannot be retyped.
`app/engines/facewatch.py` compares the document portrait and the live selfie separately
against a gallery of wanted people's faces (`data/face_watchlist.csv`), reusing the same
SFace cosine threshold as the selfie-match engine (critical at 0.363, a "possible match —
officer should check" band at 0.30). A document with a genuine page, a perfect MRZ, and a
name on no list still comes back REJECT if the face is a match. The committed gallery is
two SFHQ synthetic crops (`sfhq_05`, `sfhq_06`) — the mechanism is real, the gallery is a
demonstration, not a production watchlist. A real deployment points `facewatch` at an
actual wanted-persons face database the same way `data/watchlist.csv` stands in for a
production sanctions feed.

## "Is this real AI or just if-statements?"

Both, deliberately. Perception is neural: RapidOCR (PaddleOCR's models, ONNX),
OpenCV YuNet (face detection) and SFace (face recognition) are pretrained
neural networks run through ONNX Runtime. Adjudication — turning perception
into a verdict — is deterministic rules. We chose explainable adjudication
over a black-box classifier because a fraud decision a border officer can't
explain is one they can't act on.

## "What's your accuracy?"

We quote numbers only where we measured them, and only against the source we
measured them on:

- **MRZ check digits** are exactly correct by construction (ICAO Doc 9303
  arithmetic), not statistically correct.
- **Field-forensics / tamper thresholds** are calibrated against our own
  synthetic demo corpus (`scripts/make_samples.py`: 7 scripted cases at JPEG
  quality 60/70/80/90/95) — see the Calibration table in `README.md` for the
  exact genuine-vs-forged values and thresholds. These are **not** validated
  against SIDTD; that is named as a limitation below.
- We do not, and will not, quote an invented accuracy percentage. Where we
  have not measured a number, we say so.

## "Couldn't ELA false-positive on a genuine document?"

Yes, and it does — on high-contrast text and on non-JPEG sources. That's why
`tamper` and `fieldforensics` signals cap at `high` severity and never
`critical`, and why one signal alone lands a case in REVIEW (score 30-64), not
REJECT (65+). The output is a triage recommendation for a human analyst, not
an automated rejection — see `app/config.py`: `BANDS = [(30, CLEAR), (65,
REVIEW), (101, REJECT)]`.

## "What happens on a corrupt, huge, or empty upload?"

- **Corrupt / unreadable file**: each engine runs inside its own try/except in
  `app/pipeline.py`. A failing engine produces an `ENGINE_ERROR` signal
  (severity `low`) instead of crashing the request — the applicant still gets
  a verdict from every engine that succeeded.
- **Oversized upload**: `app/config.py` caps each file
  (`MAX_UPLOAD_BYTES` = 15 MB), the whole request
  (`MAX_TOTAL_UPLOAD_BYTES` = 40 MB), and each liveness camera frame
  (`MAX_FRAME_UPLOAD_BYTES` = 2 MB, `MAX_LIVENESS_FRAMES` = 12 frames). Going
  over any limit returns HTTP 413 and cleans up any partial upload —
  `app/main.py`'s `_save_upload`/`_cleanup`.
- **Empty form**: no crash; missing claimed fields simply mean the checks that
  need them (name/DOB/number cross-checks) have nothing to compare and are
  skipped or note the absence.

Offer this to a skeptical judge directly: "upload anything you like."

## "How does field-level detection actually work?"

Error Level Analysis, run separately inside each OCR-returned bounding box
(and the portrait and stamp regions). We re-compress the image and measure how
much each region's pixels change. A field that went through the document's
original print/scan pipeline changes little; a field retyped afterwards has a
different, fresher compression history and changes more. We use a
median-based outlier test (z-score within the peer group of fields on the same
page, threshold `z > 3.5`) so one tampered field can't hide by skewing the
average, and so **no reference database of genuine passports is needed** —
each field is judged only against its neighbours on the same page.

## "Why not train a deep-learning forgery classifier?"

We do use neural networks — OCR, face detection and face recognition all run
pretrained ONNX models. We chose not to *train* a forgery classifier in 36
hours because there is no ethically usable labelled forged-passport dataset we
could touch on that timeline, and a verdict nobody can explain is a verdict a
border officer can't use. Training a classifier on SIDTD alongside the
explainable engines is named as future work.

## "Where does your data come from? Any real documents?"

Never. `scripts/make_samples.py` renders every demo document from scratch —
invented names, invented numbers, computed (not copied) MRZ check digits. The
only real-world image content anywhere in the repo is the SFHQ face crops in
`data/faces/` — StyleGAN-generated synthetic faces of people who do not exist
(MIT licence, github.com/SelfishGene/SFHQ-dataset) — used for the demo
portraits and the live-selfie/liveness acts, where a **consenting teammate's
own live photo** is used instead and never committed (`data/demo/` is
gitignored; see `scripts/make_demo_passport.py`'s `CONSENT_NOTICE`). Validation
data referenced (not shipped, not scraped) is SIDTD (1,900 genuine + 1,900
forged) and MIDV-2020 — standard public research corpora, built precisely
because real ID data can't be shared.

## Face-match numbers (measured, `data/faces/` SFHQ crops, `scripts/tune_liveness.py`/README)

| Comparison | Cosine similarity |
|---|---|
| Same synthetic face vs. itself, resized + re-saved JPEG q80 | 0.9342 |
| Two different synthetic faces | 0.1630 |

Threshold: `SAME_PERSON = 0.363` (OpenCV's own published SFace threshold) —
**we did not independently validate this number**; we inherit it from the
model's publisher and state that plainly. `DEFINITE_MISMATCH = 0.25`.

## Liveness (measured, `scripts/tune_liveness.py`)

Challenge-response head-turn using YuNet's 5-point landmarks: yaw proxy =
`(nose_x - eye_midpoint_x) / inter-eye distance`, measured as the shift between
the first and last third of the challenge frames. `YAW_DELTA_THRESHOLD =
0.045`. Measured ranges: synthetic head turn +0.065 to +0.120; flat photo
rotated on its axis -0.068 to -0.014 (always the wrong direction); static
photo shifted/rescaled -0.035 to +0.016. The threshold sits roughly 2.8x above
the worst photograph reading and 1.4x below the weakest genuine turn.

## Known limitations — say these before a judge finds them

- **Liveness is challenge-response, not anti-spoofing.** It defeats a printed
  photo or a phone screen held up to the camera. A **video replay of the real
  person turning their head defeats it** — this is stated in
  `app/engines/liveness.py`'s own docstring and is not hidden.
- **ELA false-positives** on high-contrast text and non-JPEG sources — this is
  why tamper/field signals cap at `high`, never `critical`.
- **OCR is English-script only.** Non-Latin document text is out of scope.
- **MRZ check digits can be recomputed by a capable forger** who edits the MRZ
  to match a changed field — that's exactly why we added the independent
  field-level ELA check as a second, harder-to-defeat method.
- **Thresholds are calibrated on our own synthetic renders, not on SIDTD** —
  the calibration table in the README is measured against
  `scripts/make_samples.py` output at multiple JPEG qualities, not against the
  SIDTD forged/genuine corpus. Validating against SIDTD is the clear next step.
- **The copy-move axis-aligned heuristic is calibrated, not principled** — a
  2D-compact clone needs 12 off-axis ORB self-matches to fire, but a purely
  axis-aligned clone (common on printed text rows/columns) needs 20, because
  axis-aligned coincidences happen naturally in genuine documents. This
  threshold was tuned to stop `01_clean_passport.jpg` from falsely alarming,
  not derived from first principles.
- **No live government API or watchlist integration** — `data/watchlist.csv`
  is a static, invented demo list. Screening runs against every name source we
  have for the case — the officer's typed entry, the passport MRZ name, and
  the visa MRZ name — so a wanted traveller can't pass by typing a different
  name than the one printed on their document.
- **No deepfake/GAN-face detection.**

## "Why no LLM / cloud API?"

The system runs fully offline — models download once at setup, then the
request path never touches the network (`CLAUDE.md` hard rule 3). For a
document-screening system that's a feature, not a limitation: no applicant PII
leaves the machine, and there's no vendor outage between an applicant and a
decision. We turn wifi off on stage on purpose.

## "What would you build next?"

A classifier trained on SIDTD run alongside the explainable engines, passive
anti-spoofing on the selfie (not just the head-turn challenge), template
matching against issuing-authority layouts, and integration with an
immigration case-management system for live watchlist data.
