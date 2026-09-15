"""Runs every manifest case through the pipeline and prints verdict vs expectation."""
import json
import os
import shutil
from app import config, db
from app.models import ScreeningInput
from app.pipeline import screen

def main() -> None:
    db_path = "samples_check.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db.init_db(db_path)

    # Keep generated evidence images out of the tracked data/evidence directory.
    # data/samples/* is gitignored, so a subdirectory there is safe to leave
    # around for the controller to open, and we clear it first for a clean run.
    evidence_dir = "data/samples/_evidence"
    if os.path.exists(evidence_dir):
        shutil.rmtree(evidence_dir)
    os.makedirs(evidence_dir, exist_ok=True)
    config.EVIDENCE_DIR = evidence_dir

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
