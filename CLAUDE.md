# CLAUDE.md — read this first, every session

**SIH26188 — AI-Based Fake Identity & Document Screening System**
Smart India Hackathon · Ministry of Home Affairs · 36-hour build.

## The problem statement, verbatim

> Identity documents such as passports, visas etc. can be forged or tampered.
> Manual verification is time-consuming and can lead to human errors.
> Forged documents can contain altered photographs, names, DOBs, or visa stamps.
> High volumes of documents make manual inspection inefficient.

**Scope is passports and visas** — border control / Bureau of Immigration. Not Aadhaar, not PAN, not domestic Indian ID. If a feature does not help screen a passport or a visa, it is out of scope.

The PS names four attack types. Every one has an owning engine:

| Attack named in the PS | Engine that catches it |
|---|---|
| altered photographs | `fieldforensics` (portrait region) + `face` + `facewatch` |
| altered names | `mrz` (name vs MRZ) + `ocr` (name vs printed) + `fieldforensics` |
| altered DOBs | `mrz` (check digit) + `fieldforensics` (per-field ELA) |
| forged visa stamps | `fieldforensics` (stamp region) |
| high volumes | `batch` mode + dashboard |

## Our one-line pitch

> An explainable AI system that verifies identity documents, detects forgery and tampering, matches the document holder's face, and produces an evidence-backed risk score in seconds.

## The differentiator — field-level forensics

Everyone else's project says *"this document is 78% fake."*
Ours says **"the DOB field was altered — here it is, circled in red."**

OCR returns a bounding box per text field. We run ELA **inside each box separately** and find the box whose compression history differs from its neighbours. That field was retyped. Same method on the portrait region and the visa stamp region.

**This is the centerpiece. Protect it. It is the demo, the innovation claim, and the best visual, all in one.**

## Team

Non-coding teammates follow `docs/TEAM_GUIDE.md` (plain-language, one page per role). Only the Lead uses Claude. Keep the guide accurate when features change — it holds the pitch, the judge Q&A answers and the honest limitations.

## Where we are

`docs/PROGRESS.md` is the phase-by-phase runbook and the single source of truth. Read it before starting; update it after every task.
Full plan with complete code: `docs/superpowers/plans/2026-09-15-sih26188-document-screening.md`
To execute: use the `superpowers:subagent-driven-development` skill, one fresh subagent per task.

## Hard rules

1. **No real identity documents. Ever.** Not scraped, not a teammate's, not your own. Demo data comes from `scripts/make_samples.py`; accuracy numbers come from the SIDTD dataset (1,900 genuine + 1,900 labelled forgeries). A real document in a git repo is a permanent leak and a judging liability.
2. **No system-level dependencies.** `pip` only. No PaddlePaddle, no dlib, no tesseract, no cmake, no MySQL server. A teammate's laptop failing an install at hour 20 loses the hackathon.
3. **No network on the request path.** No LLM API, no government API. Demo-day wifi must be irrelevant — we turn it off on stage deliberately. Models download once at setup.
4. **Every engine degrades, never crashes.** An engine that raises becomes an `ENGINE_ERROR` signal, not a 500. A judge uploading a corrupt file still sees a verdict.
5. **Every signal carries a human-readable `message`** naming what was checked and what was found. Explainability *is* the product — the PS and our pitch both say so.
6. **No frontend build step.** Vanilla HTML + plain CSS + self-hosted IBM Plex fonts (no CDN) + plain JS. Nobody on the team knows React or JS; Claude writes all of it. Adding a bundler adds a way to lose.
7. **TDD.** Test first → watch it fail → minimal implementation → watch it pass → commit.
8. **Commit after every task.** The history is evidence of process.

## Architecture in one paragraph

One Python process. FastAPI serves both the JSON API and the static frontend — no Node, no bundler, no CORS. Each detection concern is an isolated module in `app/engines/` taking an input bundle and returning `list[Signal]`. `app/pipeline.py` fans out to every engine inside per-engine try/except; `app/scoring.py` folds signals into a 0-100 score and a CLEAR/REVIEW/REJECT band. Add an engine = one file plus one registry line. Cut an engine = set its weight to `0.0` in `app/config.py`.

## The engines

| Engine | Catches |
|---|---|
| `mrz` | Altered passport fields — ICAO 9303 check-digit arithmetic. Self-proving, needs no reference database. |
| `fieldforensics` | **Which field** was tampered — per-region ELA on OCR boxes, portrait, stamps. ⭐ centerpiece |
| `ocr` | Claimed name/DOB/number not printed on the uploaded document |
| `face` | Missing or duplicate portrait; selfie-to-portrait mismatch |
| `liveness` | A printed photo held to the webcam — challenge-response head turn on YuNet landmarks |
| `tamper` | Whole-image splicing (ELA), cloning (ORB copy-move), noise inconsistency |
| `metadata` | EXIF/PDF provenance — editor tags, missing camera data |
| `crossdoc` | Passport vs visa vs prior submissions — same person, contradictory details |
| `watchlist` | Sanctions / PEP name matches, fuzzy so transliteration doesn't evade — screens the typed name, the passport MRZ name, and the visa MRZ name |
| `facewatch` | A wanted traveller under a clean forged name — screens the document portrait and the live selfie against a gallery of wanted faces, catching what the (text-only) name watchlist structurally cannot |
| `velocity` | Same document under different names, duplicates, bulk bursts |

## Data — three sources, all synthetic

| Source | Purpose |
|---|---|
| `scripts/make_samples.py` | The six scripted demo cases. We control exactly what each triggers. |
| **SIDTD** (1,900 bona fide + 1,900 forged, CC BY-SA 3.0) | Real accuracy numbers, legally |
| **MIDV-2020** (1,000 mock IDs, 72,409 images) | ID-document analysis validation |

Storage is three things, only one of them a database: sample images are **files on disk**; the watchlist is **one CSV**; `cases.db` is **SQLite**, holding one row per screening. The case DB is what makes cross-document and duplicate detection possible — it is the only reason we can catch the same passport submitted twice under different names.

**We need zero genuine documents.** Every check is self-contained: MRZ check digits prove the document against itself, and field-level ELA compares each field against the other fields on the same page.

## Stack decisions — settled, do not relitigate

| Chose | Over | Why |
|---|---|---|
| RapidOCR | PaddleOCR | RapidOCR *is* PaddleOCR's models in ONNX. Same accuracy, pip-only, no PaddlePaddle. Slides may honestly say "PaddleOCR models". |
| OpenCV YuNet + SFace | `face_recognition` / dlib | No compiler, no cmake. ONNX, pip-only. |
| ONNX Runtime | PyTorch | No time and no labelled data to train. We *run* pretrained neural nets; we don't train one. Defensible and honest. |
| SQLite | MySQL | Zero config, one file, nothing to fail on demo day. "Swaps to MySQL in production" — one line. |
| Vanilla + plain CSS + self-hosted fonts, no CDN | React / Tailwind CDN | Nobody knows React. No build step = no build failure at hour 30. No CDN keeps the demo working with wifi off. |
| Deterministic rules for adjudication | Black-box classifier | A fraud decision a border officer cannot explain is one they cannot use. |

**Yes, we use AI.** RapidOCR, YuNet and SFace are neural networks. We run pretrained models via ONNX Runtime and do the *adjudication* with explainable rules. That is the design, not a shortcut.

## Known limitations — state them before a judge finds them

- ELA false-positives on high-contrast text and on non-JPEG sources. This is why tamper signals cap at `high`, never `critical`, and why one signal alone lands in REVIEW rather than REJECT.
- OCR models are English-script. Non-Latin document text is out of scope.
- Liveness is a **challenge-response head turn**, not anti-spoofing: it defeats a printed photo or a
  phone screen held to the webcam, and nothing more. A video replay of the right person turning, or a
  photo bent around a curve, passes. Its threshold is calibrated on synthetic warps, not recorded humans.
- No passive/bank-grade anti-spoofing, no deepfake/GAN-face detection, no live government API
  integration. All named as future work.
- `facewatch` matches at 0.50, stricter than SFace's published 0.363 same-person threshold,
  because a gallery is 1:N identification and because we measured four pairs of *different*
  SFHQ faces at or above 0.363 (worst 0.425). That measurement is on 8 StyleGAN faces from one
  generator, not on real people. The committed gallery is a handful of synthetic faces — it
  demonstrates the mechanism, not a measured detection rate.
- The same measurement is a caution about `face`'s selfie matching, which still uses 0.363: on
  our synthetic set, two different people can exceed it. Not changed, because we have no
  measurement of genuine selfie-to-portrait pairs to move it against — recorded here so nobody
  quotes 0.363 to a judge as if it were validated.
- Accuracy is quoted only against SIDTD, never invented.

## Git and GitHub

- Private repo: `Mohammad2460/fake-identity-document-screening`. Push with the `gh` CLI / `git push`.
- Code work happens on branch `build`; `master` holds the planning docs.
- **Push only reviewed work.** After a batch of tasks passes its task reviews, run the `code-review` skill over the branch, fix what matters, then push. Never push red tests.
- Update `docs/PROGRESS.md` in the same push, so a teammate pulling the repo sees exactly where the build stands.
- Never change the repo to public without the team lead saying so.

## Commands

```bash
./run.sh                      # cold start: venv, deps, models, samples, server
./.venv/bin/pytest -v         # full suite
./.venv/bin/uvicorn app.main:app --reload --port 8000
./.venv/bin/python -m scripts.make_samples   # always -m, from repo root
```

## Cut order if behind schedule

`crossdoc` → `batch` → `face` → OCR's secondary cross-checks.
**Never cut:** `mrz`, `fieldforensics`, `scoring`, or the Phase 6 rehearsal.

At hour 22, whatever is not working gets cut, not fixed.
