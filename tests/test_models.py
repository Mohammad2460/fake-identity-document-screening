from app.models import Signal, ScreeningResult
from app import config

def test_signal_has_required_fields():
    s = Signal(code="MRZ_CHECKSUM_FAIL", engine="mrz", severity="high",
               message="Document number check digit mismatch")
    assert s.code == "MRZ_CHECKSUM_FAIL"
    assert s.severity == "high"
    assert s.evidence == {}

def test_every_engine_has_a_weight():
    for engine in config.ENGINE_WEIGHTS:
        assert config.ENGINE_WEIGHTS[engine] >= 0

def test_severity_points_are_ordered():
    p = config.SEVERITY_POINTS
    assert p["info"] < p["low"] < p["medium"] < p["high"] < p["critical"]

def test_result_serialises_evidence_path():
    r = ScreeningResult(case_id="x", score=1, band="CLEAR", evidence_path="data/evidence/a.jpg")
    assert r.to_dict()["evidence_path"] == "data/evidence/a.jpg"
