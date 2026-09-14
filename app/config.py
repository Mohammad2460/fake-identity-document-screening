SEVERITY_POINTS = {
    "info": 0.0,
    "low": 6.0,
    "medium": 15.0,
    "high": 30.0,
    "critical": 60.0,
}

# Scales every signal an engine emits. Set to 0.0 to cut an engine instantly.
ENGINE_WEIGHTS = {
    "mrz": 1.0,
    "fieldforensics": 1.0,   # the centerpiece
    "identity": 1.0,
    "watchlist": 1.0,
    "velocity": 0.8,
    "metadata": 0.9,
    "tamper": 1.0,
    "ocr": 0.9,
    "face": 1.0,
    "crossdoc": 1.0,
}

BANDS = [(30, "CLEAR"), (65, "REVIEW"), (101, "REJECT")]

MAX_SCORE = 100
UPLOAD_DIR = "data/uploads"
EVIDENCE_DIR = "data/evidence"
DB_PATH = "cases.db"
