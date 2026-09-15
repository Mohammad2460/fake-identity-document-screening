"""Prints per-sample field-forensics output so thresholds can be calibrated.

Run from the repo root: ./.venv/bin/python -m scripts.tune_fields
"""
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
