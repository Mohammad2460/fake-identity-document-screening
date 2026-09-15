# SIH26188 — Execution Runbook · hour 0 to submission

**Update this file after every task.** Single source of truth for where the team is.
Claude reads it at the start of each session to know what to do next.

Project rules: `CLAUDE.md` · Full plan with code: `docs/superpowers/plans/2026-09-15-sih26188-document-screening.md`

**Status key:** ⬜ not started · 🟡 in progress · ✅ done · ❌ cut

---

**Non-coding teammates: read `docs/TEAM_GUIDE.md` instead of this file.**

## Hour 0 — before any code

- [ ] Everyone reads `CLAUDE.md` (10 min)
- [ ] Demo laptop chosen, charger present, backup laptop identified
- [ ] Shared countdown clock visible to all. Submission deadline: `__________`
- [ ] Roles assigned below — write real names in
- [ ] Non-coders start Phase 5 **immediately**. They do not wait for code.
- [ ] **Say this out loud to the team:** nobody photographs their own ID "just to test." Not once. All data is synthetic.

### Roles

| # | Role | Name | Owns | Critical path? |
|---|------|------|------|----------------|
| 1 | Lead / Driver | ________ | Runs Claude, T0-T15, git, demo laptop | **YES** |
| 2 | Forensics Support | ________ | T16 samples, adversarial testing, threshold calibration | No |
| 3 | Frontend Polish | ________ | T15 visual pass | No |
| 4 | Data / QA | ________ | SIDTD download, watchlist, test matrix | No |
| 5 | Pitch / Docs | ________ | Slides, script, README, judge Q&A | No |
| 6 | Floater | ________ | Backup laptop, recording, timekeeping | No |

**If only 2-3 show up:** Lead takes 1+2. Second takes 5 — pitch is the highest-ROI non-code work. Third takes 3+4.

---

## PHASE 0 — Foundation · h0-2 · Lead

Prove the toolchain works before betting 34 hours on it.

| Task | What | Status |
|---|---|---|
| T0 | Skeleton, deps, `/health` boots, risky imports verified | ✅ |
| T1 | `Signal` model + scoring config | ✅ |

**Gate:**
- [x] `./.venv/bin/pytest -v` green
- [x] `curl localhost:8000/health` → `{"status":"ok"}`
- [x] T0 Step 3 printed `True True` for the OpenCV face API — **if `False False`, mark T11 ❌ now**

---

## PHASE 1 — Rules core · h2-8 · Lead

A complete, demoable screener with **zero image processing**. This is your insurance policy.

| Task | What | Status |
|---|---|---|
| T2 | **MRZ engine** — ICAO 9303 check digits ⭐ | ✅ |
| T3 | Identity engine — synthetic-identity heuristics | ✅ |
| T4 | Watchlist — fuzzy sanctions match | ✅ |
| T5 | Scoring — decaying weights, critical floor | ✅ |
| T6 | SQLite persistence + velocity engine | ✅ |

**Gate:**
- [ ] Full suite green
- [x] T5 hand-check: one `high` → REVIEW, one `critical` → REJECT

If everything after this fails, you can still demo a real product. Nothing later may destabilise it.

---

## PHASE 2 — Forensics · h8-18 · Lead (+ Forensics Support)

The computer vision. **T10 is the centerpiece — protect its time.**

| Task | What | Status |
|---|---|---|
| T7 | Metadata — EXIF / PDF provenance | ✅ |
| T8 | Tamper — whole-image ELA, copy-move, noise | ✅ |
| T9 | OCR — text + **bounding boxes** (T10 depends on the boxes) | ✅ |
| T10 | **Field-level forensics** — which field was altered ⭐⭐ | ✅ |
| T11 | Face — portrait detection + selfie match | ✅ |

**Gate:**
- [ ] Full suite green
- [ ] T10 correctly localizes a tampered DOB on a sample document
- [ ] Annotated evidence image written to disk with the bad field boxed

**Hour-18 decision:** if T11 is unfinished, cut it. `ENGINE_WEIGHTS["face"] = 0.0`, mark ❌, move on. Do not negotiate with yourself.

---

## PHASE 3 — Surface · h18-24 · Lead + Frontend Polish

A judge uses it without you touching the keyboard.

| Task | What | Status |
|---|---|---|
| T12 | Cross-document consistency · *stretch, cut first* | ⬜ |
| T13 | Pipeline orchestrator with per-engine fault isolation | ⬜ |
| T14 | API — `/api/screen`, `/api/cases` | ⬜ |
| T15 | Frontend — verdict, reason cards, **annotated evidence image** | ⬜ |

**Gate — by hand in a browser:**
- [ ] Clean passport → green CLEAR
- [ ] Tampered-MRZ passport → REJECT naming the failed check digit
- [ ] Tampered-DOB passport → **red box drawn on the DOB field**
- [ ] Watchlist name → REJECT

### ⛔ HOUR 24 — HARD FEATURE FREEZE

**No new features past this line.** Broken things get cut, not fixed. A polished 6-engine demo beats a broken 9-engine one. Everything after is calibration, rehearsal, polish.

---

## PHASE 4 — Demo assets & calibration · h24-29 · Lead + Forensics Support

| Task | What | Status |
|---|---|---|
| T16 | Sample generator — passport + visa, 7 fraud types | ⬜ |
| T16.0 | ⚠️ Demo portraits must be **photo-realistic AI-generated faces of people who don't exist** (licence allows use). The face detector ignores drawn cartoon faces. Never a real person's photo. | ⬜ |
| T16.1 | ⚠️ Add tests that a real (AI-generated) face IS detected and matched — only the "no face" paths are tested today. | ⬜ |
| T16.3 | **Calibration loop** — run all samples, retune T8/T10 thresholds | ⬜ |
| T16.4 | ⚠️ **BLOCKING: rework T8 tamper for documents** — it currently raises 2 high + 1 medium alarms on a *genuine* passport (copy-move matches repeated letters; noise check reads flat background as tampering). Clean passport must come out CLEAR. | ⬜ |
| T17 | Batch CSV screening + dashboard · *stretch, cut second* | ⬜ |

**Gate:**
- [ ] `01_clean.jpg` comes out **CLEAR** — if your own clean document flags, the demo dies on stage
- [ ] Every sample lands on or adjacent to its expected band
- [ ] Samples look plausible on a projector, not like grey placeholder boxes
- [ ] Final threshold values recorded in README with justification

---

## PHASE 5 — Pitch & docs · h0-30 · Pitch/Docs · RUNS IN PARALLEL

**Start hour 0. Do not wait for working code.** Write against the plan document.

- [ ] Slides: problem → four attack types from the PS → our approach → architecture → demo → limitations → future work
- [ ] `README.md` — pitch, quickstart, engine table, scoring model, thresholds + justification, architecture, data sources, roles
- [ ] `docs/DEMO_SCRIPT.md` — timed 4-minute script
- [ ] `docs/JUDGE_QA.md` — honest prepared answers
- [ ] **Accuracy run on SIDTD** (Data/QA) — one real number to quote. Never invent one.
- [ ] Rehearse narration aloud before the build is even finished

---

## PHASE 6 — Harden & rehearse · h29-34 · EVERYONE

Hackathons are lost at the demo, not at the keyboard. Budget the full five hours.

| Step | What | Status |
|---|---|---|
| T18.1 | `run.sh` one-command cold start | ⬜ |
| T18.2 | **Cold start on a teammate's laptop** — clone, `./run.sh`, screen a document | ⬜ |
| T18.3 | Dress rehearsal #1 — full script, aloud, timed | ⬜ |
| T18.4 | **Dress rehearsal #2** — the one that matters. Do not skip it. | ⬜ |
| T18.5 | Record 4-minute backup video → phone **and** USB stick | ⬜ |

**Adversarial pass (Forensics Support + QA), in parallel:**
- [ ] Corrupt file → still returns a verdict, no 500
- [ ] 20MB image → doesn't hang
- [ ] `.txt` renamed `.jpg` → graceful
- [ ] Empty form → CLEAR, no crash
- [ ] Same passport twice under different names → velocity fires
- [ ] Submit 10× fast → no duplicate-case corruption

**Gate:**
- [ ] Cold start works on a machine that is not the Lead's
- [ ] Both rehearsals done, under time
- [ ] Backup video in two physical places

---

## PHASE 7 — Buffer · h34-36 · Lead

- [ ] **Build nothing new.** Fix only what rehearsal broke.
- [ ] Final commit, push, confirm submission accepted
- [ ] Charge every device
- [ ] Sleep. A rested presenter outscores a marginal extra feature.

---

## Demo-day checklist — print this

- [ ] Laptop charged + charger in bag
- [ ] `./run.sh` already running before you walk up, browser open at `localhost:8000`
- [ ] Sample files open in a window, ready to drag
- [ ] Backup video on phone and USB
- [ ] **Wifi off** — proves it runs offline, and removes the risk
- [ ] Do Not Disturb on, notifications off
- [ ] Resolution tested on the actual projector
- [ ] Whoever answers questions has read `docs/JUDGE_QA.md`
- [ ] Everyone can answer "what did you actually build?" in one sentence

---

## Running log

Append one line per completed task: `hh:mm — T<n> done — note`

```
2026-09-15 — Work happens on git branch `build` (not master).
2026-09-15 — Deps installed (opencv-python 5.0, face API present). T0-T6: 45/45 tests pass. Fixed plan bug: phone 1234567890 was not detected as fake.
2026-09-15 — Subagent execution ledger: `.superpowers/sdd/2026-09-15-sih26188-document-screening/progress.md` (git-ignored; detailed per-task record).
2026-09-15 — ✅ PHASE 0 + PHASE 1 COMPLETE. T0-T6 reviewed and approved. Demoable rules-core screener exists.
2026-09-15 — T7 metadata ✅, T8 tamper ✅ (57/57 tests). Checkpoint: code-review skill + first push to private GitHub repo `fake-identity-document-screening`.
2026-09-15 — Code review found 9 bugs (worst: capitalised sanctioned names bypassed watchlist; bad OCR character crashed MRZ; composite check digit unchecked). All 9 fixed, re-reviewed, 72/72 tests. Pushed to GitHub.
2026-09-15 — Added `docs/TEAM_GUIDE.md`: plain-language roles for teammates who don't use Claude.
2026-09-15 — Session 2: T9 OCR ✅, T10 field-level forensics (red box) ✅, T11 face ✅. 103/103 tests. Visual check found & fixed header false positive in T10. Found T8 false-alarms on genuine passports (blocking before T16).
```

### Resume instructions for a new session
1. `git checkout build`
2. Read the first 🟡 or ⬜ row above — that is the next task.
3. `./.venv/bin/pytest -v` to see what currently passes.
