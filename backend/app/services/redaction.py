from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Iterable

import fitz
from PIL import Image, ImageDraw

from .detectors import Detection
from .ocr import run_ocr


@dataclass(frozen=True)
class Verification:
    passed: bool
    text_absent: bool
    raw_bytes_absent: bool
    metadata_clean: bool
    annotations_clean: bool
    ocr: str
    failures: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "text_absent": self.text_absent,
            "raw_bytes_absent": self.raw_bytes_absent,
            "metadata_clean": self.metadata_clean,
            "annotations_clean": self.annotations_clean,
            "ocr": self.ocr,
            "failures": list(self.failures),
        }


def _clean_document_metadata(document: fitz.Document) -> None:
    document.set_metadata(
        {
            "format": "",
            "title": "",
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "",
            "producer": "",
            "creationDate": "",
            "modDate": "",
            "trapped": "",
        }
    )
    try:
        document.set_xml_metadata("")
    except Exception:
        pass
    try:
        for name in list(document.embfile_names()):
            document.embfile_del(name)
    except Exception:
        pass


def _strip_page_features(page: fitz.Page) -> None:
    try:
        page.delete_links()
    except Exception:
        pass
    try:
        annotations = list(page.annots() or [])
        for annotation in annotations:
            page.delete_annot(annotation)
    except Exception:
        pass
    try:
        widgets = list(page.widgets() or [])
        for widget in widgets:
            page.delete_widget(widget)
    except Exception:
        pass


def _save_pdf(document: fitz.Document) -> bytes:
    output = io.BytesIO()
    document.save(output, garbage=4, clean=True, deflate=True, deflate_images=True, deflate_fonts=True)
    return output.getvalue()


def _apply_page_redactions(page: fitz.Page, findings: Iterable[Detection]) -> None:
    for finding in findings:
        x0, y0, x1, y1 = finding.bbox
        rect = fitz.Rect(max(0.0, x0), max(0.0, y0), max(0.0, x1), max(0.0, y1))
        if rect.width <= 0 or rect.height <= 0:
            continue
        page.add_redact_annot(rect, fill=(0, 0, 0))
    if list(page.annots() or []):
        try:
            page.apply_redactions(images=getattr(fitz, "PDF_REDACT_IMAGE_PIXELS", 2))
        except TypeError:
            page.apply_redactions()


def redact_pdf(data: bytes, findings: Iterable[Detection], flatten_to_image: bool = False) -> bytes:
    findings_by_page: dict[int, list[Detection]] = {}
    for finding in findings:
        findings_by_page.setdefault(finding.page, []).append(finding)

    with fitz.open(stream=data, filetype="pdf") as source:
        if flatten_to_image:
            flattened = fitz.open()
            for page_index in range(source.page_count):
                source_page = source.load_page(page_index)
                pixmap = source_page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                draw = ImageDraw.Draw(image)
                scale_x = pixmap.width / float(source_page.rect.width or 1)
                scale_y = pixmap.height / float(source_page.rect.height or 1)
                for finding in findings_by_page.get(page_index + 1, []):
                    x0, y0, x1, y1 = finding.bbox
                    draw.rectangle(
                        (x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y),
                        fill=(0, 0, 0),
                    )
                image_bytes = io.BytesIO()
                image.save(image_bytes, format="PNG", optimize=True)
                new_page = flattened.new_page(width=source_page.rect.width, height=source_page.rect.height)
                new_page.insert_image(new_page.rect, stream=image_bytes.getvalue())
            _clean_document_metadata(flattened)
            output = _save_pdf(flattened)
            flattened.close()
            return output

        for page_index in range(source.page_count):
            page = source.load_page(page_index)
            _strip_page_features(page)
            _apply_page_redactions(page, findings_by_page.get(page_index + 1, []))
        _clean_document_metadata(source)
        return _save_pdf(source)


def redact_image(data: bytes, media_type: str, findings: Iterable[Detection]) -> bytes:
    with Image.open(io.BytesIO(data)) as original:
        image = original.convert("RGB")
    draw = ImageDraw.Draw(image)
    for finding in findings:
        x0, y0, x1, y1 = finding.bbox
        draw.rectangle((max(0, x0), max(0, y0), min(image.width, x1), min(image.height, y1)), fill=(0, 0, 0))
    output = io.BytesIO()
    if media_type == "image/png":
        image.save(output, format="PNG", optimize=True)
    else:
        image.save(output, format="JPEG", quality=95, optimize=True, exif=b"")
    return output.getvalue()


def _normalised(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _content_values(findings: Iterable[Detection]) -> list[str]:
    return [finding.value for finding in findings if finding.value.strip()]


def _values_absent(text: str, raw: bytes, values: list[str]) -> tuple[bool, bool]:
    text_normalized = _normalised(text)
    raw_lower = raw.lower()
    text_absent = all(_normalised(value) not in text_normalized for value in values)
    raw_absent = all(value.lower().encode("utf-8") not in raw_lower for value in values)
    return text_absent, raw_absent


def verify_export(data: bytes, document_type: str, findings: Iterable[Detection]) -> Verification:
    findings_list = list(findings)
    values = _content_values(findings_list)
    failures: list[str] = []
    ocr_status = "not-run"
    metadata_clean = True
    annotations_clean = True
    text = ""
    if document_type == "pdf":
        try:
            with fitz.open(stream=data, filetype="pdf") as document:
                text = "\n".join(page.get_text("text") for page in document)
                metadata = document.metadata or {}
                metadata_clean = not any(metadata.get(key) for key in ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate"))
                annotations_clean = all(
                    not list(page.annots() or []) and not list(page.widgets() or []) and not page.get_links()
                    for page in document
                )
                images = []
                for page in document:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                    images.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
        except Exception:
            text = ""
            images = []
            metadata_clean = False
            annotations_clean = False
    else:
        with Image.open(io.BytesIO(data)) as image:
            images = [image.convert("RGB")]
        metadata_clean = True
        annotations_clean = True

    text_absent, raw_absent = _values_absent(text, data, values)
    if not text_absent:
        failures.append("redacted content remained in extracted text")
    if not raw_absent:
        failures.append("redacted content remained in output bytes")
    if not metadata_clean:
        failures.append("document metadata was not fully stripped")
    if not annotations_clean:
        failures.append("annotations, links, or forms remained")

    ocr_text_parts: list[str] = []
    for image in images:
        result = run_ocr(image)
        if not result.available:
            ocr_status = "unavailable"
            break
        ocr_status = "passed"
        ocr_text_parts.extend(word.text for word in result.words)
    if ocr_text_parts and not all(_normalised(value) not in _normalised(" ".join(ocr_text_parts)) for value in values):
        failures.append("redacted content remained in OCR output")
        ocr_status = "failed"

    return Verification(
        passed=not failures,
        text_absent=text_absent,
        raw_bytes_absent=raw_absent,
        metadata_clean=metadata_clean,
        annotations_clean=annotations_clean,
        ocr=ocr_status,
        failures=tuple(failures),
    )
