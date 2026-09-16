"""File-level provenance forensics: EXIF and PDF metadata."""
import hashlib
import os
import re
from PIL import Image
from app.models import Signal


def pdf_date_digits(raw: str) -> str | None:
    """Extract a zero-padded YYYYMMDDHHmmSS digit string from a PDF date.

    Strips an optional "D:" prefix and any trailing timezone/offset. Returns
    None if fewer than 8 digits (a full date, at minimum) are present.
    """
    s = (raw or "")
    if s.startswith("D:"):
        s = s[2:]
    digits = re.match(r"\d*", s).group(0)[:14]
    if len(digits) < 8:
        return None
    return digits.ljust(14, "0")

EDITORS = ("photoshop", "gimp", "canva", "illustrator", "affinity", "pixlr",
           "paint.net", "lightroom", "snapseed", "picsart", "inkscape", "figma")

TAG_SOFTWARE, TAG_MAKE, TAG_MODEL, TAG_DATETIME_ORIG = 305, 271, 272, 36867

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _pdf_signals(path: str) -> list[Signal]:
    from pypdf import PdfReader
    out: list[Signal] = []
    reader = PdfReader(path)
    info = reader.metadata or {}
    producer = str(info.get("/Producer", "") or "")
    creator = str(info.get("/Creator", "") or "")
    blob = f"{producer} {creator}".lower()
    if any(e in blob for e in EDITORS):
        out.append(Signal(
            code="META_EDITING_SOFTWARE", engine="metadata", severity="medium",
            message=f"PDF was produced by image-editing software ({producer or creator}).",
            plain="This PDF was made with image-editing software, not with a "
                  "document scanner or issuing system.",
            evidence={"producer": producer, "creator": creator},
        ))
    c, m = str(info.get("/CreationDate", "")), str(info.get("/ModDate", ""))
    c_digits, m_digits = pdf_date_digits(c), pdf_date_digits(m)
    if c_digits and m_digits and m_digits > c_digits:
        out.append(Signal(
            code="META_PDF_MODIFIED_AFTER_CREATION", engine="metadata", severity="medium",
            message=f"PDF was modified ({m}) after it was created ({c}).",
            plain="This PDF file was edited after it was first created.",
            evidence={"created": c, "modified": m},
        ))
    if not out:
        out.append(Signal(code="META_PDF_CLEAN", engine="metadata", severity="info",
                          message="PDF metadata shows no editing-tool or post-modification traces.",
                          plain="Nothing in the PDF's file history suggests it was edited."))
    return out

def _image_signals(path: str) -> list[Signal]:
    out: list[Signal] = []
    with Image.open(path) as img:
        exif = img.getexif()
        fmt, size = img.format, img.size

    software = str(exif.get(TAG_SOFTWARE, "") or "")
    make = str(exif.get(TAG_MAKE, "") or "")
    model = str(exif.get(TAG_MODEL, "") or "")

    if any(e in software.lower() for e in EDITORS):
        out.append(Signal(
            code="META_EDITING_SOFTWARE", engine="metadata", severity="medium",
            message=f"Image carries an editing-software tag: {software!r}. "
                    f"A genuine capture would name a camera, not an editor.",
            plain="This image's file details say it was made with photo-editing "
                  "software, not photographed or scanned.",
            evidence={"software": software},
        ))

    if not make and not model:
        # Ruling (task-16b item 5): info, not a risk. Scanner output, e-passport chip
        # images, issued visa PDFs rendered to images and messaging-app uploads all
        # lack camera EXIF, so its absence says nothing about forgery - it fired on
        # every genuine demo document. An editing-software tag (above) stays medium:
        # that is positive evidence of an editor, not the absence of a camera.
        out.append(Signal(
            code="META_NO_CAMERA_EXIF", engine="metadata", severity="info",
            message="No camera make/model in EXIF. Normal for a scanned or issued "
                    "document image; recorded for provenance, not scored.",
            plain="This image has no camera details attached, which is normal "
                  "for a scanned or officially issued document.",
            evidence={"format": fmt, "size": list(size)},
        ))
    else:
        out.append(Signal(
            code="META_CAMERA_PRESENT", engine="metadata", severity="info",
            message=f"Camera EXIF present ({make} {model}).".strip(),
            plain=f"This image's file details show it was taken with a camera "
                  f"({make} {model}).".strip(),
            evidence={"make": make, "model": model},
        ))

    if not out:
        out.append(Signal(code="META_CLEAN", engine="metadata", severity="info",
                          message="No metadata anomalies found.",
                          plain="Nothing in the file's hidden details looks unusual."))
    return out

def run(path: str) -> list[Signal]:
    if not path or not os.path.exists(path):
        return [Signal(code="META_UNREADABLE", engine="metadata", severity="low",
                       message="No document file was available for metadata analysis.",
                       plain="No document file was available, so its hidden file "
                             "details could not be checked.")]
    try:
        if path.lower().endswith(".pdf"):
            return _pdf_signals(path)
        return _image_signals(path)
    except Exception as e:
        return [Signal(code="META_UNREADABLE", engine="metadata", severity="low",
                       message=f"Metadata could not be parsed: {type(e).__name__}: {e}",
                       plain="The file's hidden details could not be read on "
                             "this file.")]
