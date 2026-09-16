# SIH26188 — AI-Based Fake Identity & Document Screening System

Explainable passport and visa screening. Start with `CLAUDE.md` and `docs/PROGRESS.md`.

```bash
./run.sh                                      # cold start
./.venv/bin/pytest -q                         # tests
./.venv/bin/python -m scripts.make_samples    # synthetic demo documents
./.venv/bin/python -m scripts.check_samples   # verdict per demo case
```

## Calibration

Measured on synthetic documents only (`scripts/make_samples.py`: the 7 demo cases plus
extra genuine identities rendered at JPEG quality 60/70/80/90/95). Each check compares
like with like; thresholds sit above the worst genuine value measured.

| Check | Measure | Genuine (worst) | Forged | Threshold |
|---|---|---|---|---|
| `TAMPER_ELA_ANOMALY` | luma ELA per unit edge energy, 16px textured blocks, vs document median (floor 0.005) | 6.5 (q95) | substituted photo 15.9, 3 contiguous blocks | > 8.0 in >= 2 contiguous blocks |
| `TAMPER_COPY_MOVE` | ORB self-matches at one offset, off-axis (> 12px both axes), inside one 96px window spanning >= 24px both axes | 0 (was 15-25 before the layout filter) | cloned texture patch 13 | >= 12 |
| `TAMPER_NOISE_INCONSISTENT` | p95 / median of MAD noise sigma on smooth (non-print) pixels, 6x6 tiles, floor 0.5 | 1.2 (was 12.6 with Laplacian variance) | pasted noisy camera photo 7.9; noisy splice on photo 4.1 | > 3.0 |
| `FF_FIELD_TAMPERED` | per-field luma ELA, modified z within peer group (background shade; MRZ lines separate) | data fields z <= 1.6 | retyped DOB z 8.1, retyped surname z 8.1 | z > 3.5 (unchanged) |
| `FF_STAMP_TAMPERED` | stamp judged on its OCR lettering, same measure as fields | genuine stamp lettering 0.63 (fields ~0.65) | added stamp lettering 2.42, z 10.8 | z > 3.5 (unchanged) |
| `META_NO_CAMERA_EXIF` | absence of camera make/model | — | — | info only (scanned/issued images have none) |

Limits: a clone moved purely along a row or column (within 12px of an axis) is not reported
by `TAMPER_COPY_MOVE` — typeset layout repeats exactly that way. Whole-image ELA does not
catch a single retyped field (DOB peak 4.3); `fieldforensics` owns that.

`face` (SFace cosine similarity, `SAME_PERSON = 0.363`, `DEFINITE_MISMATCH = 0.25`), measured
on the committed SFHQ synthetic crops in `data/faces/`:

| Comparison | Cosine similarity |
|---|---|
| Same synthetic face vs. itself resized + re-saved as JPEG q80 | 0.934 |
| Two different synthetic faces (`sfhq_01` vs `sfhq_02`) | 0.163 (below `DEFINITE_MISMATCH`) |

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
