from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import fitz
from PIL import Image, ImageOps

from .ocr import OcrRun, run_ocr


@dataclass(frozen=True)
class WordBox:
    text: str
    bbox: tuple[float, float, float, float]
    page: int
    line_id: tuple[int, int]
    source: str
    confidence: float = 1.0


@dataclass
class PageContent:
    page: int
    width: float
    height: float
    words: list[WordBox] = field(default_factory=list)
    rendered: Image.Image | None = None


@dataclass
class DocumentContent:
    document_type: str
    media_type: str
    pages: list[PageContent]
    ocr_requested: bool
    ocr_available: bool
    ocr_used: bool
    ocr_message: str | None
    warnings: list[str]


def _pixmap_image(page: fitz.Page) -> Image.Image:
    # PDF points are 1/72 inch; 200 DPI is a practical OCR target for scans.
    dpi_scale = 200 / 72
    pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale), alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _ocr_words_for_page(page_number: int, image: Image.Image, width: float, height: float) -> tuple[list[WordBox], OcrRun]:
    result = run_ocr(image)
    if not result.used:
        return [], result
    scale_x = width / image.width
    scale_y = height / image.height
    words = [
        WordBox(
            text=word.text,
            bbox=(word.left * scale_x, word.top * scale_y, word.right * scale_x, word.bottom * scale_y),
            page=page_number,
            line_id=word.line_id,
            source="ocr",
            confidence=word.confidence,
        )
        for word in result.words
    ]
    return words, result


def _extract_pdf(data: bytes, use_ocr: bool) -> DocumentContent:
    pages: list[PageContent] = []
    warnings: list[str] = []
    ocr_available = False
    ocr_used = False
    ocr_message: str | None = None
    with fitz.open(stream=data, filetype="pdf") as document:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_number = page_index + 1
            page_content = PageContent(page_number, float(page.rect.width), float(page.rect.height))
            raw_words = page.get_text("words")
            page_content.words = [
                WordBox(
                    text=str(item[4]),
                    bbox=(float(item[0]), float(item[1]), float(item[2]), float(item[3])),
                    page=page_number,
                    line_id=(int(item[5]), int(item[6])),
                    source="text",
                )
                for item in raw_words
                if str(item[4]).strip()
            ]
            # Render all pages so optional QR/face detection can work. OCR is only needed
            # for pages without an extractable text layer.
            page_content.rendered = _pixmap_image(page)
            if use_ocr and not page_content.words:
                ocr_words, result = _ocr_words_for_page(page_number, page_content.rendered, page_content.width, page_content.height)
                page_content.words = ocr_words
                ocr_available = ocr_available or result.available
                ocr_used = ocr_used or result.used
                if result.message:
                    ocr_message = result.message
            pages.append(page_content)
    if use_ocr and not ocr_available and not ocr_used:
        warnings.append(ocr_message or "OCR unavailable: install the optional pytesseract package and Tesseract executable")
    elif use_ocr and ocr_message:
        warnings.append(ocr_message)
    return DocumentContent("pdf", "application/pdf", pages, use_ocr, ocr_available, ocr_used, ocr_message, warnings)


def _extract_image(data: bytes, media_type: str, use_ocr: bool) -> DocumentContent:
    with Image.open(io.BytesIO(data)) as source_image:
        image = ImageOps.exif_transpose(source_image).convert("RGB")
    width, height = image.size
    words: list[WordBox] = []
    warnings: list[str] = []
    ocr_available = False
    ocr_used = False
    ocr_message: str | None = None
    if use_ocr:
        words, result = _ocr_words_for_page(1, image, float(width), float(height))
        ocr_available = result.available
        ocr_used = result.used
        ocr_message = result.message
        if result.message:
            warnings.append(result.message)
    return DocumentContent(
        "image",
        media_type,
        [PageContent(1, float(width), float(height), words, image)],
        use_ocr,
        ocr_available,
        ocr_used,
        ocr_message,
        warnings,
    )


def extract_document(data: bytes, document_type: str, media_type: str, use_ocr: bool) -> DocumentContent:
    if document_type == "pdf":
        return _extract_pdf(data, use_ocr)
    return _extract_image(data, media_type, use_ocr)
