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
    "facewatch": 1.0,
    "crossdoc": 1.0,
    "liveness": 1.0,
}

BANDS = [(30, "CLEAR"), (65, "REVIEW"), (101, "REJECT")]

MAX_SCORE = 100
UPLOAD_DIR = "data/uploads"
EVIDENCE_DIR = "data/evidence"
DB_PATH = "cases.db"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
# checkpoint-4 R5: MAX_UPLOAD_BYTES caps each of document/visa/selfie alone, but
# nothing capped the WHOLE request (three big files plus a burst of liveness
# frames could still add up). A smaller per-frame cap too, since a frame is a
# single webcam snapshot, not a full-page scan.
MAX_TOTAL_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_FRAME_UPLOAD_BYTES = 2 * 1024 * 1024
# Challenge frames per screening. The client sends ~8; anything past this
# is dropped unread so a scripted flood cannot stall the screening lock.
MAX_LIVENESS_FRAMES = 12
