from app.models import Signal
from app import scoring

def sig(sev, engine="identity", code="X"):
    return Signal(code=code, engine=engine, severity=sev, message="m")

def test_no_signals_is_zero_and_clear():
    assert scoring.score_signals([]) == (0, "CLEAR")

def test_only_info_signals_stay_clear():
    score, band = scoring.score_signals([sig("info"), sig("info")])
    assert score == 0 and band == "CLEAR"

def test_single_high_signal_lands_in_review():
    score, band = scoring.score_signals([sig("high")])
    assert band == "REVIEW"

def test_critical_signal_forces_reject():
    score, band = scoring.score_signals([sig("critical", engine="watchlist")])
    assert band == "REJECT" and score >= 65

def test_many_low_signals_do_not_outweigh_one_high():
    many_low = scoring.score_signals([sig("low") for _ in range(8)])[0]
    one_high = scoring.score_signals([sig("high")])[0]
    assert one_high > many_low

def test_score_is_capped_at_100():
    score, _ = scoring.score_signals([sig("critical") for _ in range(10)])
    assert score == 100

def test_engine_weight_zero_silences_engine(monkeypatch):
    monkeypatch.setitem(scoring.config.ENGINE_WEIGHTS, "tamper", 0.0)
    score, _ = scoring.score_signals([sig("critical", engine="tamper")])
    assert score == 0

def test_top_reasons_are_ordered_by_severity():
    signals = [sig("low", code="L"), sig("critical", code="C"), sig("medium", code="M")]
    assert [s.code for s in scoring.top_reasons(signals)] == ["C", "M", "L"]

def test_top_reasons_excludes_info():
    signals = [sig("info", code="I"), sig("high", code="H")]
    assert [s.code for s in scoring.top_reasons(signals)] == ["H"]
