# Execution Runbook — phase by phase, hour 0 to submission

**Update this file after every task.** It is the single source of truth for where the team is.
Claude reads it at the start of each session to know what to do next.

Plan with full code: `docs/superpowers/plans/2026-09-14-fake-identity-screening.md`
Project rules: `CLAUDE.md`

**Status key:** ⬜ not started · 🟡 in progress · ✅ done · ❌ cut

---

## Hour 0 — before any code

- [ ] Whole team reads this file and `CLAUDE.md` (10 min, everyone)
- [ ] Lead confirms: demo laptop chosen, charger present, backup laptop identified
- [ ] Set a shared countdown clock everyone can see. Write the submission deadline here: `__________`
- [ ] Assign roles from the table below. Write real names in.
- [ ] Non-coders start immediately on Phase 5 work — they do **not** wait for code.

### Role assignment

| # | Role | Name | Owns | Critical path? |
|---|------|------|------|----------------|
| 1 | Lead / Driver | ________ | Runs Claude, Tasks 0-13, git, demo laptop | **YES** |
| 2 | Forensics Support | ________ | Task 14 samples, adversarial testing | No |
| 3 | Frontend Polish | ________ | Task 13 visual pass | No |
| 4 | Data / QA | ________ | Watchlist, fixtures, full test matrix | No |
| 5 | Pitch / Docs | ________ | Slides, script, README, judge Q&A | No |
| 6 | Floater | ________ | Backup laptop, recording, timekeeping | No |

**If only 2-3 show up:** Lead takes 1+2. Second person takes 5 — pitch is the highest-ROI non-code work. Third takes 3+4.

---

## PHASE 0 — Foundation · hours 0-2 · Lead

Goal: prove the toolchain works before betting 34 hours on it.

| Task | What | Status |
|---|---|---|
| T0 | Repo skeleton, deps, `/health` boots, risky imports verified | ⬜ |
| T1 | `Signal` model + scoring config | ⬜ |

**Gate — do not pass until all true:**
- [ ] `./.venv/bin/pytest -v` green
- [ ] `curl localhost:8000/health` returns `{"status":"ok"}`
- [ ] T0 Step 3 printed `True True` for the OpenCV face API — **if it printed `False False`, mark Task 10 ❌ now** and move its 12 weight points to `tamper` and `ocr`

---

## PHASE 1 — Rules core · hours 2-8 · Lead

Goal: a complete, demoable fraud screener with **zero image processing**.

| Task | What | Status |
|---|---|---|
| T2 | MRZ engine — ICAO 9303 check digits | ⬜ |
| T3 | Identity engine — Verhoeff/PAN/email/DOB/synthetic heuristics | ⬜ |
| T4 | Watchlist engine — fuzzy sanctions match | ⬜ |
| T5 | Scoring engine — decaying weights, critical floor | ⬜ |
| T6 | SQLite persistence + velocity engine | ⬜ |

**Gate:**
- [ ] `./.venv/bin/pytest -v` fully green
- [ ] T5 Step 5 hand-check: `high` → REVIEW, `critical` → REJECT

**This is your insurance policy.** If everything after this fails, you can still demo a real product. Nothing later is allowed to destabilise it.

---

## PHASE 2 — Forensics · hours 8-16 · Lead (+ Forensics Support)

Goal: the computer-vision engines that make it "AI-based".

| Task | What | Status |
|---|---|---|
| T7 | Metadata forensics — EXIF / PDF provenance | ⬜ |
| T8 | Tamper forensics — ELA, copy-move, noise | ⬜ |
| T9 | OCR — text extraction + claimed-vs-printed cross-check | ⬜ |
| T10 | Face — portrait detection + selfie match · **first to cut** | ⬜ |

**Gate:**
- [ ] Full suite green
- [ ] Each engine returns real signals on a real image, not just on test fixtures

**Hour-16 decision point:** if T10 is unfinished, cut it. Set `ENGINE_WEIGHTS["face"] = 0.0`, mark ❌, move on. Do not negotiate with yourself.

---

## PHASE 3 — Surface · hours 16-22 · Lead + Frontend Polish

Goal: a judge can use it without you touching the keyboard.

| Task | What | Status |
|---|---|---|
| T11 | Pipeline orchestrator with per-engine fault isolation | ⬜ |
| T12 | HTTP API — `/api/screen`, `/api/cases` | ⬜ |
| T13 | Frontend — verdict display + reason cards | ⬜ |

**Gate — all three by hand in a browser:**
- [ ] `Viktor Anatolyevich Petrov` → red REJECT with watchlist reason
- [ ] `Jonathan Brewster` + aadhaar `234567890124` → green CLEAR
- [ ] `Asdf Qwerty` + `999999999999` + `x@mailinator.com` → amber/red, three distinct reasons

### ⛔ HOUR 22 — HARD FEATURE FREEZE

**No new features after this line.** Whatever is broken gets cut, not fixed. A polished 5-engine demo beats a broken 8-engine one. Everything from here is calibration, rehearsal, and polish.

---

## PHASE 4 — Demo assets & calibration · hours 22-28 · Lead + Forensics Support

Goal: six deterministic sample cases that each catch a different fraud.

| Task | What | Status |
|---|---|---|
| T14 | Sample generator — 6 fraud types + manifest | ⬜ |
| T14.3 | **Calibration loop** — run all samples, retune T8 thresholds | ⬜ |
| T15 | Printable analyst case report · second to cut | ⬜ |

**Gate:**
- [ ] `01_clean.jpg` comes out **CLEAR** — if your own clean document flags, the demo dies on stage
- [ ] Every other sample lands on or adjacent to its expected band
- [ ] Sample images look plausible on a projector, not like grey placeholder boxes
- [ ] Final threshold values recorded in README with justification

---

## PHASE 5 — Pitch & docs · hours 0-30 · Pitch/Docs · RUNS IN PARALLEL

**Start at hour 0. Do not wait for working code.** Write against the plan document.

- [ ] Slides: problem → the three fraud shapes → our approach → architecture → demo → what's next
- [ ] `README.md` — pitch, quickstart, engine table, scoring model, thresholds + why, architecture, roles, "synthetic data only" statement
- [ ] `docs/DEMO_SCRIPT.md` — the timed 4-minute script (full text in plan Task 16 Step 3)
- [ ] `docs/JUDGE_QA.md` — honest prepared answers (full text in plan Task 16 Step 4)
- [ ] Rehearse narration aloud against the plan's screenshots before the build is even done

---

## PHASE 6 — Harden & rehearse · hours 28-34 · EVERYONE

This is where hackathons are won and lost. Budget the full six hours.

| Step | What | Status |
|---|---|---|
| T16.1 | `run.sh` one-command cold start | ⬜ |
| T16.2 | **Cold-start on a teammate's laptop** — clone, `./run.sh`, screen someone | ⬜ |
| T16.6a | Dress rehearsal #1 — full script, aloud, timed | ⬜ |
| T16.6b | **Dress rehearsal #2** — the one that matters. Do not skip it. | ⬜ |
| T16.7 | Record 4-minute backup video → phone **and** USB stick | ⬜ |

**Adversarial pass (Forensics Support + QA), while rehearsals run:**
- [ ] Upload a corrupt file → still returns a verdict, no 500
- [ ] Upload a 20MB image → doesn't hang
- [ ] Upload a `.txt` renamed `.jpg` → graceful
- [ ] Submit an empty form → returns CLEAR, no crash
- [ ] Submit the same ID twice under different names → velocity fires
- [ ] Click submit 10× fast → no duplicate-case corruption

**Gate:**
- [ ] Cold start works on a machine that is not the Lead's
- [ ] Both rehearsals completed, under time
- [ ] Backup video exists in two physical places

---

## PHASE 7 — Buffer · hours 34-36 · Lead

- [ ] **Build nothing new.** Fix only what rehearsal broke.
- [ ] Final `git commit`, push, confirm submission form accepted
- [ ] Charge every device
- [ ] Sleep. A rested presenter outscores a marginal extra feature.

---

## Demo-day checklist — print this

- [ ] Laptop charged + charger in bag
- [ ] `./run.sh` already running before you walk up; browser open at `localhost:8000`
- [ ] Sample files open in a finder window, ready to drag
- [ ] Backup video on phone and USB
- [ ] Wifi **off** — prove it runs offline, and remove the risk
- [ ] Notifications off, Do Not Disturb on
- [ ] Screen resolution tested on the actual projector
- [ ] `docs/JUDGE_QA.md` read by whoever answers questions
- [ ] Know your one-sentence answer to "what did you actually build?"

---

## Running log

Append one line per completed task: `hh:mm — T<n> done — note`.

```
```
