"""HTTP surface for the screening system."""
import os
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config, db, report, scoring
from app.models import ScreeningInput
from app.pipeline import screen

_EXT_RE = re.compile(r"^\.[a-z0-9]{1,5}$")
_CHUNK_SIZE = 1024 * 1024


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _safe_ext(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return ext if _EXT_RE.fullmatch(ext) else ".bin"


class UploadTooLarge(Exception):
    def __init__(self, field: str):
        self.field = field


def _save_upload(upload: UploadFile | None, field: str) -> str | None:
    """Stream an upload to disk under a random name. Raises UploadTooLarge over
    config.MAX_UPLOAD_BYTES, deleting the partial file first."""
    if upload is None or not upload.filename:
        return None
    ext = _safe_ext(upload.filename)
    dest = os.path.join(config.UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    total = 0
    with open(dest, "wb") as fh:
        while True:
            chunk = upload.file.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > config.MAX_UPLOAD_BYTES:
                fh.close()
                os.remove(dest)
                raise UploadTooLarge(field)
            fh.write(chunk)
    return dest


@app.post("/api/screen")
async def api_screen(
    document: UploadFile | None = File(default=None),
    visa: UploadFile | None = File(default=None),
    selfie: UploadFile | None = File(default=None),
    full_name: str = Form(default=""),
    dob: str = Form(default=""),
    passport_no: str = Form(default=""),
    nationality: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    address: str = Form(default=""),
):
    try:
        doc_path = _save_upload(document, "document")
        visa_path = _save_upload(visa, "visa")
        selfie_path = _save_upload(selfie, "selfie")
    except UploadTooLarge as e:
        return JSONResponse(
            status_code=413,
            content={"error": f"{e.field} exceeds the 15 MB upload limit"},
        )

    inp = ScreeningInput(
        claimed={"full_name": full_name, "dob": dob, "passport_no": passport_no,
                 "nationality": nationality, "email": email, "phone": phone,
                 "address": address},
        doc_path=doc_path,
        visa_path=visa_path,
        selfie_path=selfie_path,
    )
    result = screen(inp, config.DB_PATH)
    body = result.to_dict()
    body["top_reasons"] = [
        {"code": s.code, "engine": s.engine, "severity": s.severity, "message": s.message}
        for s in scoring.top_reasons(result.signals)
    ]
    body["evidence_url"] = (f"/evidence/{os.path.basename(result.evidence_path)}"
                            if result.evidence_path else None)
    return body


@app.get("/api/cases")
def api_cases() -> dict:
    return {"cases": db.all_cases(config.DB_PATH)}


@app.get("/api/report/{case_id}", response_class=HTMLResponse)
def api_report(case_id: str) -> str:
    return report.render_case_html(config.DB_PATH, case_id)


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")


os.makedirs(config.EVIDENCE_DIR, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=config.EVIDENCE_DIR), name="evidence")
app.mount("/static", StaticFiles(directory="static"), name="static")
