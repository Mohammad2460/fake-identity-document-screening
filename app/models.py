from dataclasses import dataclass, field

SEVERITIES = ("info", "low", "medium", "high", "critical")

@dataclass
class Signal:
    code: str
    engine: str
    severity: str
    message: str
    weight_override: float | None = None
    evidence: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.severity not in SEVERITIES:
            raise ValueError(f"bad severity {self.severity!r}")

@dataclass
class ScreeningInput:
    claimed: dict = field(default_factory=dict)
    doc_path: str | None = None
    visa_path: str | None = None
    selfie_path: str | None = None

@dataclass
class ScreeningResult:
    case_id: str
    score: int
    band: str
    signals: list[Signal] = field(default_factory=list)
    engine_errors: list[str] = field(default_factory=list)
    evidence_path: str | None = None
    evidence_source: str | None = None
    engines_run: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "score": self.score,
            "band": self.band,
            "engine_errors": self.engine_errors,
            "evidence_path": self.evidence_path,
            "evidence_source": self.evidence_source,
            "engines_run": self.engines_run,
            "signals": [
                {"code": s.code, "engine": s.engine, "severity": s.severity,
                 "message": s.message, "evidence": s.evidence}
                for s in self.signals
            ],
        }
