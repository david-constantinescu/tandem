"""validarea uploadurilor: extensie, tip, semnatura fisierului si marime"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import filetype

from app.utils.errors import ValidationFailed

# extension -> canonical MIME type
SUPPORTED_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "txt": "text/plain",
    "html": "text/html",
    "htm": "text/html",
    "eml": "message/rfc822",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
BINARY_SIGNATURES = {
    "application/pdf": {"application/pdf"},
    "image/jpeg": {"image/jpeg"},
    "image/png": {"image/png"},
    "image/webp": {"image/webp"},
    # DOCX is a ZIP container; filetype may report either
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
}
TEXT_TYPES = {"text/plain", "text/html", "message/rfc822"}


@dataclass
class ValidatedFile:
    filename: str
    mime_type: str
    data: bytes


def safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFKC", name or "upload").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip(" .") or "upload"
    return name[:200]


def validate_upload(filename: str, data: bytes, declared_mime: str | None, max_bytes: int) -> ValidatedFile:
    filename = safe_filename(filename)
    if not data:
        raise ValidationFailed(f"{filename} is empty", code="empty_file")
    if len(data) > max_bytes:
        raise ValidationFailed(
            f"{filename} is larger than the {max_bytes // (1024 * 1024)} MB limit", code="file_too_large")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime = SUPPORTED_TYPES.get(ext)
    if mime is None:
        raise ValidationFailed(
            f"{filename}: unsupported file type. Supported: PDF, JPG, PNG, WEBP, TXT, HTML, EML, DOCX",
            code="unsupported_type")
    declared = (declared_mime or "").split(";")[0].strip().lower()
    if declared and declared not in ("application/octet-stream", mime) and not _compatible(declared, mime):
        raise ValidationFailed(f"{filename}: declared type {declared} does not match its extension",
                               code="mime_mismatch")
    if mime in BINARY_SIGNATURES:
        kind = filetype.guess(data)
        if kind is None or kind.mime not in BINARY_SIGNATURES[mime]:
            raise ValidationFailed(f"{filename}: file contents do not match a {ext.upper()} file",
                                   code="signature_mismatch")
        if mime.endswith("wordprocessingml.document") and b"word/" not in data[:20000] and b"[Content_Types].xml" not in data[:20000]:
            raise ValidationFailed(f"{filename}: not a valid Word document", code="signature_mismatch")
    elif mime in TEXT_TYPES:
        if b"\x00" in data[:8192]:
            raise ValidationFailed(f"{filename}: binary content in a text file", code="signature_mismatch")
        if filetype.guess(data) is not None and filetype.guess(data).mime.startswith(("application/", "image/")):
            raise ValidationFailed(f"{filename}: file contents do not match a text file", code="signature_mismatch")
    return ValidatedFile(filename=filename, mime_type=mime, data=data)


def _compatible(declared: str, canonical: str) -> bool:
    aliases = {
        "image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg", "text/x-eml": "message/rfc822",
        "application/x-pdf": "application/pdf", "text/htm": "text/html",
    }
    return aliases.get(declared) == canonical or (declared.startswith("text/") and canonical.startswith("text/"))
