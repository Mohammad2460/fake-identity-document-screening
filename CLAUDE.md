# CLAUDE.md — read this first, every session

Project: **AI-Based Fake Identity & Document Screening System** (hackathon, 24-36h).

**The implementation plan is `docs/superpowers/plans/2026-09-14-fake-identity-screening.md`.**
It contains 17 tasks with complete code. Do not re-derive anything it already specifies.
To execute it, use the `superpowers:subagent-driven-development` skill (one fresh subagent per task).

## Where we are

Track progress in `docs/PROGRESS.md`. Read it before starting work; update it after every task.

## Hard rules

1. **No system-level dependencies.** Everything installs via `pip` alone. No brew, no tesseract, no dlib, no cmake. A teammate's laptop failing an install at hour 20 loses the hackathon.
2. **No network on the request path.** No LLM API, no remote watchlist. Judging-day wifi must be irrelevant. Models download once during setup only.
3. **Every engine degrades, never crashes.** An engine that raises must become an `ENGINE_ERROR` signal, not a 500. A judge uploading a corrupt file still sees a verdict.
4. **Every signal carries a human-readable `message`** naming what was checked and what was found. Explainability is the product, not a feature.
5. **Synthetic data only.** Never a real ID document, including your own. All samples come from `scripts/make_samples.py`.
6. **Commit after every task.** Small commits; the history is evidence of process.
7. **TDD.** Test first, watch it fail, implement minimally, watch it pass, commit.

## Architecture in one paragraph

One Python process. FastAPI serves both the JSON API and a static vanilla-JS frontend — no Node, no bundler, no build step, no CORS. Each detection concern is an isolated module in `app/engines/` that takes an input bundle and returns `list[Signal]`. `app/pipeline.py` fans out to all eight engines inside per-engine try/except; `app/scoring.py` folds the signals into a 0-100 score and a CLEAR/REVIEW/REJECT band. Adding an engine means adding one file and one registry line. Cutting an engine means setting its weight to `0.0` in `app/config.py`.

## The eight engines

| Engine | Catches |
|---|---|
| `mrz` | Altered passport fields — ICAO 9303 check-digit arithmetic |
| `identity` | Invalid Aadhaar/PAN, impossible DOB, disposable email, fabricated names |
| `watchlist` | Sanctions / PEP name matches, fuzzy so transliteration doesn't evade |
| `velocity` | Same ID under different names, duplicate documents, bulk bursts |
| `metadata` | EXIF/PDF provenance — editor tags, missing camera data |
| `tamper` | Splicing (ELA), cloning (ORB copy-move), noise inconsistency |
| `ocr` | Claimed name/DOB/ID not printed on the uploaded document |
| `face` | Missing or duplicate portrait, selfie-to-document mismatch |

## Commands

```bash
./run.sh                      # cold start: venv, deps, models, samples, server
./.venv/bin/pytest -v         # full suite
./.venv/bin/uvicorn app.main:app --reload --port 8000
./.venv/bin/python scripts/make_samples.py
```

## Judgment calls already made — do not relitigate

- **No LLM.** Offline operation is a compliance feature and removes demo-day network risk.
- **No trained classifier.** No ethically usable labelled forged-ID dataset exists within the time budget. Deterministic, explainable checks beat an unvalidated model.
- **Decaying score, not a sum.** Six weak signals must not outvote one proven forgery. See `app/scoring.py`.
- **Tamper signals cap at `high`, never `critical`.** ELA false-positives on high-contrast text. Say this out loud in the demo.

## Cut order if behind schedule

`face` → `report` → OCR's secondary DOB/ID cross-checks. **Never cut** `mrz`, `identity`, `scoring`, or the Task 16 rehearsal.

At hour 22, whatever is not working gets cut, not fixed.
