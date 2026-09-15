"""Runs every manifest case through the pipeline and prints verdict vs expectation."""
import json
import os
import shutil
import tempfile
from app import config, db
from app.models import ScreeningInput
from app.pipeline import screen


def run_cases(cases: list[dict], samples_dir: str = "data/samples",
              work_dir: str | None = None) -> list[tuple[dict, object]]:
    """Screen each case against its OWN fresh, empty case database.

    The manifest's cases share one synthetic identity, so a shared DB would make
    velocity fire on repeat submissions - an artefact of the script, not a finding.
    """
    work = work_dir or tempfile.mkdtemp(prefix="check_samples_")
    os.makedirs(work, exist_ok=True)
    results = []
    try:
        for i, case in enumerate(cases):
            db_path = os.path.join(work, f"case_{i:02d}.db")
            if os.path.exists(db_path):
                os.remove(db_path)
            db.init_db(db_path)
            f = case["files"]
            inp = ScreeningInput(
                claimed=case["claimed"],
                doc_path=os.path.join(samples_dir, f["document"]),
                visa_path=os.path.join(samples_dir, f["visa"]) if "visa" in f else None,
            )
            try:
                results.append((case, screen(inp, db_path)))
            finally:
                os.remove(db_path)
    finally:
        if work_dir is None:
            shutil.rmtree(work, ignore_errors=True)
    return results


def main() -> None:
    # Keep generated evidence images out of the tracked data/evidence directory.
    evidence_dir = "data/samples/_evidence"
    if os.path.exists(evidence_dir):
        shutil.rmtree(evidence_dir)
    os.makedirs(evidence_dir, exist_ok=True)
    config.EVIDENCE_DIR = evidence_dir

    with open("data/samples/manifest.json") as fh:
        cases = json.load(fh)
    for case, r in run_cases(cases):
        f = case["files"]
        name = f.get("visa", f["document"])
        print(f"{name:30s} got={r.band:7s} score={r.score:3d}  expect={case['expect']}")
        for s in r.signals:
            if s.severity in ("medium", "high", "critical"):
                print(f"      [{s.severity:8s}] {s.code}")
        if r.evidence_path:
            print(f"      evidence -> {r.evidence_path}")


if __name__ == "__main__":
    main()
