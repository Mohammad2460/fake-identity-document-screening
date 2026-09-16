# Demo Script — SIH26188 (4 minutes)

All verdicts below are measured, not aspirational — reproduce with
`./.venv/bin/python -m scripts.check_samples` any time before you go on stage.

## Pre-demo checklist (do this 15 minutes before you walk up)

- [ ] Wifi **off** — proves the system runs offline, removes the one risk you don't control
- [ ] Camera permission for the browser pre-granted (open the page once, click "Use camera",
      allow it, so the permission prompt never appears live on stage)
- [ ] Regenerate samples fresh: `./.venv/bin/python -m scripts.make_samples`
- [ ] Clear prior state so the run is clean:
      `rm -rf data/uploads data/evidence cases.db && mkdir -p data/uploads data/evidence`
- [ ] Server already running (`./run.sh`), browser open at `http://localhost:8000`
- [ ] Browser zoom set for the projector (`Cmd/Ctrl` + `+` two or three times — test on the
      actual projector beforehand; text and the evidence image must read from the back row)
- [ ] Sample files visible in a Finder window, ready to drag: `data/samples/01_clean_passport.jpg`,
      `03_dob_retyped.jpg`, `06_passport_for_visa.jpg` + `06_visa_forged_stamp.jpg`
- [ ] `data/demo/demo_passport.jpg` (or your prepared specimen) ready for Act 4
- [ ] Backup video on the phone and on a USB stick (see Act "if it breaks")

---

## 0:00 — The problem, in their words (15s)

"Your problem statement names four forgeries: altered photographs, altered names,
altered dates of birth, and forged visa stamps — and it names the real bottleneck:
volume. An officer can't inspect a thousand passports by eye. We catch all four,
and we show exactly where each one is."

## 0:15 — Act 1: genuine passport (20s)

Upload `data/samples/01_clean_passport.jpg` with its own claimed details (see
`data/samples/manifest.json`).

**Expected: CLEAR, score 0.**

"This is a genuine traveller. Every check passes — no forced positives."

## 0:35 — Act 2: the altered DOB (65s) — THE MOMENT

Upload `data/samples/03_dob_retyped.jpg`. Type DOB `1994-08-12` in the form (the
claimed value the forger typed — the printed and MRZ dates still say 1974).

**Expected: REVIEW, score 44. `FF_FIELD_TAMPERED` (high) and `XDOC_DOB_MISMATCH`
(high) fire. The evidence image boxes the DOB field in red.**

Pause on the evidence image. Let the judges look.

"Most systems tell you a document is suspicious. Ours tells you *which field*.
Every field on this page went through the same print-and-scan pipeline — except
this one. We re-compress the image and measure how much each field's pixels shift.
The DOB field shifts far more than its neighbours, so it was edited afterwards.
We need no database of genuine passports — each field is judged against the
other fields on the same page."

## 1:40 — Act 3: the forged visa stamp (35s)

Upload `data/samples/06_passport_for_visa.jpg` as the passport and
`data/samples/06_visa_forged_stamp.jpg` as the visa.

**Expected: REVIEW, score 30. `FF_STAMP_TAMPERED` (high) fires; the stamp region
is boxed red.**

"Same method, applied to the visa stamp region. Photographs, text fields, and
stamps — every attack in your problem statement, one field-level technique."

## 2:15 — Act 4: live face match (55s)

Upload the prepared specimen (`data/demo/demo_passport.jpg`, built with
`scripts/make_demo_passport.py`, see below) with its claimed details from
`data/demo/demo_claimed.json`. Click **Use camera** next to the selfie field,
**Capture** your own live selfie, then screen.

**Expected: CLEAR — the live selfie matches the specimen portrait.**

Then re-screen the same specimen but have a teammate whose face does not match
sit in for the selfie capture.

**Expected: REJECT, score 65 — face mismatch.**

"The system doesn't just read the document — it checks the person standing in
front of it matches the photograph, live, on the spot."

## 3:10 — Act 5: liveness (30s)

Click **Check liveness**, hold a printed photo (or a phone showing a photo) up
to the camera instead of a live face, and turn it as instructed.

**Expected: the head-turn challenge fails — liveness signal fires, case lands
in REVIEW.**

"We ask the traveller to turn their head. A real head has depth — the nose
moves sideways relative to the eyes as it turns. A flat photo has no depth, so
nothing moves, and we catch that. To be honest with you: this defeats a printed
photo, not a video replay of the real person turning their head. That's a
named limitation, not a hidden one."

## 3:40 — Act 6: watchlist (15s)

Upload any clean document with claimed name **VIKTOR ANATOLYEVICH PETROV**
(already in `data/watchlist.csv` as an SDN sanctions entry).

**Expected: REJECT, score 65, `WL_MATCH` (critical) — fuzzy match, so
transliteration doesn't evade it.**

## 3:55 — Close (5s)

"Every decision explainable. Every forgery located. No internet required."

---

## Timing budget

| Act | Duration | Running total |
|---|---|---|
| Problem | 0:15 | 0:15 |
| Act 1 — genuine | 0:20 | 0:35 |
| Act 2 — DOB (the moment) | 1:05 | 1:40 |
| Act 3 — visa stamp | 0:35 | 2:15 |
| Act 4 — live face match | 0:55 | 3:10 |
| Act 5 — liveness | 0:30 | 3:40 |
| Act 6 — watchlist | 0:15 | 3:55 |
| Close | 0:05 | 4:00 |

If running long, cut Act 5 (liveness) first, then Act 6 (watchlist) — Acts 1-4
are the core narrative and must never be cut.

## Building the demo documents

Run once, before the hackathon, with a **consenting** teammate's photo (never
committed, deleted after the event — see `scripts/make_demo_passport.py`):

```bash
./.venv/bin/python -m scripts.make_demo_passport --consent \
    --photo path/to/teammate.jpg --name "RAHUL SHARMA"
```

One run writes the genuine pair and one forgery per attack, into `data/demo/`:

| File | Attack | What the system says |
|---|---|---|
| `demo_passport.jpg` + `demo_visa.jpg` | none | CLEAR |
| `demo_passport_dob_altered.jpg` | DOB retyped | the DOB field boxed red |
| `demo_passport_name_altered.jpg` | surname retyped | field boxed red **and** an MRZ name mismatch |
| `demo_passport_mrz_altered.jpg` | one MRZ digit changed | ICAO check digit fails |
| `demo_visa_stamp_forged.jpg` | entry stamp added after issue | the stamp boxed red |
| `demo_visa_wrong_passport.jpg` | visa issued against another passport | cross-document mismatch |

Add `--forge-photo path/to/other_teammate.jpg` for a swapped-photo passport too,
and `--out data/demo_someone` to build a second person's set alongside the first.

`data/demo/demo_claimed.json` holds what to type into the form, keyed by
document: `genuine` for every file, except `dob_altered` and `name_altered`,
which carry the forged value — an officer types what the document shows them.

**Screen the genuine pair first.** Five screenings inside ten minutes trip the
velocity engine's bulk-submission rule, which would add an unrelated finding to
every later case. Delete `cases.db` between rehearsals.

`data/demo/` and `data/demo_*/` are gitignored. Delete them and the source
photos after the hackathon.

## If it breaks — fallback plan

- **Camera won't start / permission dialog blocks the flow live:** abandon the
  live capture, choose a pre-saved selfie file from disk instead (`Choose file`
  on the selfie field) — the match result is identical, just not captured live.
- **Server crashes or hangs:** restart with `./run.sh`; while it restarts, narrate
  from the backup video instead of standing silently.
- **Wifi/projector/laptop fails entirely:** play the recorded 4-minute backup
  video from the phone or USB stick and narrate over it exactly as scripted above.
- **A judge uploads their own file and it errors:** it shouldn't — every engine
  degrades to an `ENGINE_ERROR` signal rather than crashing (see
  `docs/JUDGE_QA.md`). If the whole request fails anyway, say so honestly and
  move on; don't debug live on stage.
