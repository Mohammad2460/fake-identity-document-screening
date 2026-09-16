import json

from app.models import Signal, ScreeningResult
from app import config

def test_signal_has_required_fields():
    s = Signal(code="MRZ_CHECKSUM_FAIL", engine="mrz", severity="high",
               message="Document number check digit mismatch")
    assert s.code == "MRZ_CHECKSUM_FAIL"
    assert s.severity == "high"
    assert s.evidence == {}

def test_signal_default_plain_is_empty_string():
    s = Signal(code="X", engine="e", severity="info", message="m")
    assert s.plain == ""

def test_signal_to_dict_includes_plain():
    s = Signal(code="X", engine="e", severity="info", message="m", plain="p")
    r = ScreeningResult(case_id="c", score=0, band="CLEAR", signals=[s])
    assert r.to_dict()["signals"][0]["plain"] == "p"

def test_every_signal_over_the_sample_cases_has_a_plain_sentence(tmp_path):
    """Every code across every engine must carry a non-technical explanation.

    Walks the full pipeline over every scripted demo case (task-21 gate): a
    signal with an empty `plain` fails this test, so a new engine code cannot
    ship without plain-language coverage.
    """
    from scripts.check_samples import run_cases

    with open("data/samples/manifest.json") as fh:
        cases = json.load(fh)

    results = run_cases(cases, work_dir=str(tmp_path / "work"))
    empty = []
    for case, result in results:
        for s in result.signals:
            if not s.plain.strip():
                empty.append((case["files"].get("document"), s.code))
    assert not empty, f"signals with no plain-language sentence: {empty}"

def test_every_engine_has_a_weight():
    for engine in config.ENGINE_WEIGHTS:
        assert config.ENGINE_WEIGHTS[engine] >= 0

def test_severity_points_are_ordered():
    p = config.SEVERITY_POINTS
    assert p["info"] < p["low"] < p["medium"] < p["high"] < p["critical"]

def test_result_serialises_evidence_path():
    r = ScreeningResult(case_id="x", score=1, band="CLEAR", evidence_path="data/evidence/a.jpg")
    assert r.to_dict()["evidence_path"] == "data/evidence/a.jpg"
