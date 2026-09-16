"""HTTP surface for the screening system."""
import os
import re
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config, db, report, scoring
from app.models import ScreeningInput
from app.pipeline import screen

_EXT_RE = re.compile(r"^\.[a-z0-9]{1,5}$")
_CHUNK_SIZE = 1024 * 1024
_EVIDENCE_NAME_RE = re.compile(r"^[0-9a-f]{32}\.jpg$")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def startup() -> None:
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    os.makedirs(config.EVIDENCE_DIR, exist_ok=True)
    db.init_db(config.DB_PATH)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Starlette 1.x removed startup event handlers; lifespan is the supported hook.
    startup()
    yield


app = FastAPI(title="Fake Identity & Document Screening System", lifespan=lifespan)

# RapidOCR's thread-safety is unverified, so screenings are serialised - one at a
# time - while api_screen itself runs in FastAPI's threadpool (it is a plain def,
# not a coroutine) so other endpoints (/, static, /api/cases, /evidence) stay
# responsive during a screening (checkpoint-3 ruling 3).
_screen_lock = threading.Lock()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _safe_ext(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return ext if _EXT_RE.fullmatch(ext) else ".bin"


class UploadTooLarge(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message


def _save_upload(upload: UploadFile | None, field: str, limit: int = None,
                  budget: dict | None = None) -> str | None:
    """Stream an upload to disk under a random name.

    Raises UploadTooLarge, deleting the partial file first, over either this
    file's own `limit` (config.MAX_UPLOAD_BYTES by default) or the whole
    request's shared `budget` (checkpoint-4 R5) - a dict {"used": int, "max":
    int} the caller passes in and this function updates across every file in
    one request.
    """
    if upload is None or not upload.filename:
        return None
    limit = config.MAX_UPLOAD_BYTES if limit is None else limit
    ext = _safe_ext(upload.filename)
    # The directory can vanish between startup and a request (a cleanup step
    # before a demo, a cleared temp dir); recreate it rather than 500.
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(config.UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    total = 0
    with open(dest, "wb") as fh:
        while True:
            chunk = upload.file.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if budget is not None:
                budget["used"] += len(chunk)
            if total > limit:
                fh.close()
                os.remove(dest)
                raise UploadTooLarge(field, f"{field} exceeds the "
                                     f"{limit // (1024 * 1024)} MB upload limit")
            if budget is not None and budget["used"] > budget["max"]:
                fh.close()
                os.remove(dest)
                raise UploadTooLarge(field, f"total upload size exceeds the "
                                     f"{budget['max'] // (1024 * 1024)} MB request limit")
            fh.write(chunk)
    return dest


def _cleanup(*paths: str | None) -> None:
    for p in paths:
        if p and os.path.exists(p):
            os.remove(p)


@app.post("/api/screen")
def api_screen(
    document: UploadFile | None = File(default=None),
    visa: UploadFile | None = File(default=None),
    selfie: UploadFile | None = File(default=None),
    selfie_frames: list[UploadFile] = File(default=[]),
    liveness_direction: str = Form(default="left"),
    full_name: str = Form(default=""),
    dob: str = Form(default=""),
    passport_no: str = Form(default=""),
    nationality: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    address: str = Form(default=""),
):
    # Plain def: FastAPI runs this in its threadpool, so /, /static, /api/cases
    # and /evidence stay responsive while a screening is in progress.
    doc_path = visa_path = selfie_path = None
    frame_paths: list[str] = []
    # checkpoint-4 R5: one shared budget across every file in the request, on
    # top of each file's own cap; R6: an identity image must never survive on
    # disk after ANY failure in this block, not only an over-size one.
    budget = {"used": 0, "max": config.MAX_TOTAL_UPLOAD_BYTES}
    try:
        doc_path = _save_upload(document, "document", budget=budget)
        visa_path = _save_upload(visa, "visa", budget=budget)
        selfie_path = _save_upload(selfie, "selfie", budget=budget)
        # Liveness challenge frames. Anything past the cap is dropped unread, so
        # a scripted flood cannot hold the screening lock open.
        for frame in (selfie_frames or [])[:config.MAX_LIVENESS_FRAMES]:
            saved = _save_upload(frame, "selfie_frames",
                                  limit=config.MAX_FRAME_UPLOAD_BYTES, budget=budget)
            if saved:
                frame_paths.append(saved)
    except UploadTooLarge as e:
        # The failed field's own partial file is already removed by _save_upload;
        # clean up anything saved earlier in this same request.
        _cleanup(doc_path, visa_path, selfie_path, *frame_paths)
        return JSONResponse(status_code=413, content={"error": e.message})
    except Exception as e:
        # Any other failure while saving (disk full, a malformed multipart
        # part, ...) must still leave nothing behind (checkpoint-4 R6).
        _cleanup(doc_path, visa_path, selfie_path, *frame_paths)
        return JSONResponse(
            status_code=500,
            content={"error": f"upload failed: {type(e).__name__}: {e}"},
        )

    try:
        inp = ScreeningInput(
            claimed={"full_name": full_name, "dob": dob, "passport_no": passport_no,
                     "nationality": nationality, "email": email, "phone": phone,
                     "address": address},
            doc_path=doc_path,
            visa_path=visa_path,
            selfie_path=selfie_path,
            selfie_frames=frame_paths,
            liveness_direction=liveness_direction,
        )
        with _screen_lock:
            result = screen(inp, config.DB_PATH)
        body = result.to_dict()
        body["top_reasons"] = [
            {"code": s.code, "engine": s.engine, "severity": s.severity,
             "message": s.message, "plain": s.plain}
            for s in scoring.top_reasons(result.signals)
        ]
        body["evidence_url"] = (f"/evidence/{os.path.basename(result.evidence_path)}"
                                if result.evidence_path else None)
        return body
    finally:
        # Uploaded identity documents must not accumulate on disk (checkpoint-3
        # ruling 4). The evidence image is a separate copy under EVIDENCE_DIR and
        # is left alone.
        _cleanup(doc_path, visa_path, selfie_path, *frame_paths)


@app.get("/api/cases")
def api_cases() -> dict:
    return {"cases": db.all_cases(config.DB_PATH)}


@app.get("/api/report/{case_id}", response_class=HTMLResponse)
def api_report(case_id: str) -> str:
    return report.render_case_html(config.DB_PATH, case_id)


@app.get("/evidence/{name}")
def evidence(name: str):
    # Resolve config.EVIDENCE_DIR at request time (not import time) so runtime
    # config changes (and test monkeypatches) take effect. Only annotate.py's
    # own naming scheme (uuid4().hex + ".jpg") is servable.
    if not _EVIDENCE_NAME_RE.fullmatch(name):
        return JSONResponse(status_code=404, content={"error": "not found"})
    path = os.path.join(config.EVIDENCE_DIR, name)
    if not os.path.isfile(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FileResponse(path, media_type="image/jpeg")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
