from __future__ import annotations

from dataclasses import dataclass

import fitz


PDF_MAGIC = b"%PDF-"
JPEG_MAGIC_PREFIX = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class UploadValidationError(ValueError):
    pass


class UploadTooLargeError(UploadValidationError):
    pass


@dataclass(frozen=True)
class ValidatedUpload:
    document_type: str
    media_type: str
    pages: int
    suffix: str


def identify_magic(data: bytes) -> tuple[str, str, str]:
    if data.startswith(PDF_MAGIC):
        return "pdf", "application/pdf", ".pdf"
    if data.startswith(JPEG_MAGIC_PREFIX):
        return "image", "image/jpeg", ".jpg"
    if data.startswith(PNG_MAGIC):
        return "image", "image/png", ".png"
    raise UploadValidationError("Unsupported file: expected a PDF, JPG, or PNG signature")


def validate_upload(data: bytes, max_bytes: int, max_pages: int) -> ValidatedUpload:
    if not data:
        raise UploadValidationError("The upload is empty")
    if len(data) > max_bytes:
        raise UploadTooLargeError(f"The upload exceeds the {max_bytes // (1024 * 1024)} MB limit")
    document_type, media_type, suffix = identify_magic(data)
    if document_type == "pdf":
        try:
            with fitz.open(stream=data, filetype="pdf") as document:
                pages = document.page_count
        except Exception as exc:  # PyMuPDF raises several format-specific exceptions.
            raise UploadValidationError("The PDF signature is present, but the PDF cannot be opened") from exc
        if pages < 1:
            raise UploadValidationError("The PDF has no pages")
        if pages > max_pages:
            raise UploadValidationError(f"The document exceeds the {max_pages}-page limit")
        return ValidatedUpload(document_type, media_type, pages, suffix)

    try:
        from PIL import Image

        with Image.open(__import__("io").BytesIO(data)) as image:
            image.verify()
    except Exception as exc:
        raise UploadValidationError("The image signature is present, but the image cannot be opened") from exc
    return ValidatedUpload(document_type, media_type, 1, suffix)
