"""extrage textul local, fara retea: pdf + ocr, poze, docx, html, eml, text"""
from __future__ import annotations

import email
import io
import logging
import re
import shutil
from dataclasses import dataclass, field
from email import policy
from email.utils import parsedate_to_datetime

log = logging.getLogger("tandem.ingestion")

MIN_PAGE_TEXT = 40  # characters below which a PDF page is treated as scanned
MAX_PDF_PAGES = 40
MAX_IMAGE_EDGE = 3072


@dataclass
class PageText:
    page: int
    text: str
    method: str  # embedded | ocr | none


@dataclass
class Attachment:
    filename: str
    mime_type: str
    data: bytes


@dataclass
class ExtractedContent:
    text: str
    pages: list[PageText] = field(default_factory=list)
    page_count: int | None = None
    images: list[tuple[bytes, str]] = field(default_factory=list)  # (png/jpeg bytes, mime) for vision models
    attachments: list[Attachment] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    methods: list[str] = field(default_factory=list)

    @property
    def needs_vision(self) -> bool:
        return any(p.method != "embedded" for p in self.pages) or (not self.text.strip() and bool(self.images))


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_image(img) -> str:
    if not ocr_available():
        return ""
    try:
        import pytesseract

        return pytesseract.image_to_string(img, lang="eng", timeout=60) or ""
    except Exception as exc:  # noqa: BLE001
        log.warning("OCR failed: %s", type(exc).__name__)
        return ""


def extract(data: bytes, mime_type: str) -> ExtractedContent:
    if mime_type == "application/pdf":
        return extract_pdf(data)
    if mime_type.startswith("image/"):
        return extract_image(data, mime_type)
    if mime_type.endswith("wordprocessingml.document"):
        return extract_docx(data)
    if mime_type == "text/html":
        return extract_html(data.decode("utf-8", errors="replace"))
    if mime_type == "message/rfc822":
        return extract_eml(data)
    return ExtractedContent(text=data.decode("utf-8", errors="replace"), methods=["plain_text"])


def extract_pdf(data: bytes) -> ExtractedContent:
    import fitz  # PyMuPDF
    from PIL import Image

    doc = fitz.open(stream=data, filetype="pdf")
    if doc.needs_pass:
        raise ValueError("PDF is password protected")
    pages: list[PageText] = []
    images: list[tuple[bytes, str]] = []
    methods = {"pdf_text"}
    for index, page in enumerate(doc):
        if index >= MAX_PDF_PAGES:
            break
        text = page.get_text("text") or ""
        if len(text.strip()) >= MIN_PAGE_TEXT:
            pages.append(PageText(index + 1, text, "embedded"))
            continue
        pix = page.get_pixmap(dpi=200)
        png = pix.tobytes("png")
        images.append((png, "image/png"))
        ocr = ocr_image(Image.open(io.BytesIO(png)))
        methods.add("ocr" if ocr.strip() else "rendered_page")
        pages.append(PageText(index + 1, ocr, "ocr" if ocr.strip() else "none"))
    full = "\n\n".join(f"[Page {p.page}]\n{p.text.strip()}" for p in pages if p.text.strip())
    return ExtractedContent(text=full, pages=pages, page_count=doc.page_count, images=images,
                            metadata={"title": (doc.metadata or {}).get("title")}, methods=sorted(methods))


def normalise_image(data: bytes) -> tuple[bytes, str, object]:
    """fix EXIF orientation and bound size without destructive compression"""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > MAX_IMAGE_EDGE:
        img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    png = out.getvalue()
    if len(png) > 4.5 * 1024 * 1024:  # keep under common provider image limits
        out = io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=92)
        return out.getvalue(), "image/jpeg", img
    return png, "image/png", img


def extract_image(data: bytes, mime_type: str) -> ExtractedContent:
    norm, norm_mime, img = normalise_image(data)
    text = ocr_image(img)
    return ExtractedContent(text=text, pages=[PageText(1, text, "ocr" if text.strip() else "none")], page_count=1,
                            images=[(norm, norm_mime)], methods=["ocr" if text.strip() else "image_only"])


def extract_docx(data: bytes) -> ExtractedContent:
    import docx

    document = docx.Document(io.BytesIO(data))
    lines = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return ExtractedContent(text="\n".join(lines), methods=["docx_text"])


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "iframe", "svg", "head"]):
        tag.decompose()
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    text = soup.get_text("\n")
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def sanitize_html(html: str) -> str:
    """sanitised HTML for previews: no scripts, styles, event handlers or remote resources"""
    import nh3

    return nh3.clean(html, tags={"p", "br", "b", "strong", "i", "em", "ul", "ol", "li", "table", "thead", "tbody",
                                 "tr", "td", "th", "h1", "h2", "h3", "h4", "span", "div", "a"},
                     attributes={"a": {"href"}}, url_schemes={"https", "mailto"}, link_rel="noopener noreferrer nofollow")


def extract_html(html: str) -> ExtractedContent:
    return ExtractedContent(text=html_to_text(html), methods=["html_text"])


def extract_eml(data: bytes) -> ExtractedContent:
    msg = email.message_from_bytes(data, policy=policy.default)
    subject = str(msg.get("subject", "") or "")
    sender = str(msg.get("from", "") or "")
    date_raw = msg.get("date")
    try:
        sent = parsedate_to_datetime(str(date_raw)).isoformat() if date_raw else None
    except (TypeError, ValueError):
        sent = None
    body = ""
    plain = msg.get_body(preferencelist=("plain",))
    html = msg.get_body(preferencelist=("html",))
    if plain is not None:
        body = plain.get_content()
    elif html is not None:
        body = html_to_text(html.get_content())
    attachments: list[Attachment] = []
    for part in msg.iter_attachments():
        filename = part.get_filename() or "attachment"
        payload = part.get_payload(decode=True) or b""
        if payload:
            attachments.append(Attachment(filename=filename, mime_type=part.get_content_type(), data=payload))
    # "Sent:" (not "Date:") so the email's send time is never mistaken for a booking date
    header = f"Subject: {subject}\nFrom: {sender}\nSent: {date_raw or ''}\n\n"
    return ExtractedContent(text=header + body.strip(), attachments=attachments,
                            metadata={"subject": subject, "from": sender, "sent_at": sent},
                            methods=["email_text"])
