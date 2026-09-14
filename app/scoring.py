"""Folds weighted signals into a 0-100 risk score with an explainable ordering."""
from app import config
from app.models import Signal

DECAY = 0.45          # each additional corroborating signal counts for less
CRITICAL_FLOOR = 65   # any surviving critical signal cannot score below REJECT

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

def _points(s: Signal) -> float:
    base = config.SEVERITY_POINTS.get(s.severity, 0.0)
    if s.weight_override is not None:
        base = s.weight_override
    return base * config.ENGINE_WEIGHTS.get(s.engine, 1.0)

def band_for(score: int) -> str:
    for ceiling, name in config.BANDS:
        if score < ceiling:
            return name
    return config.BANDS[-1][1]

def score_signals(signals: list[Signal]) -> tuple[int, str]:
    scored = sorted((p for p in (_points(s) for s in signals) if p > 0), reverse=True)
    if not scored:
        return 0, band_for(0)

    total = scored[0]
    for i, pts in enumerate(scored[1:], start=1):
        total += pts * (DECAY ** i)

    score = min(config.MAX_SCORE, int(round(total)))

    has_live_critical = any(
        s.severity == "critical" and _points(s) > 0 for s in signals
    )
    if has_live_critical:
        score = max(score, CRITICAL_FLOOR)

    return score, band_for(score)

def top_reasons(signals: list[Signal], limit: int = 5) -> list[Signal]:
    meaningful = [s for s in signals if s.severity != "info" and _points(s) > 0]
    meaningful.sort(key=lambda s: (_SEVERITY_ORDER[s.severity], -_points(s)))
    return meaningful[:limit]
