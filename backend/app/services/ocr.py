from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Any


@dataclass(frozen=True)
class OcrWord:
    text: str
    left: float
    top: float
    right: float
    bottom: float
    confidence: float
    line_id: tuple[int, int]


@dataclass(frozen=True)
class OcrRun:
    words: tuple[OcrWord, ...]
    available: bool
    used: bool
    message: str | None


def _unavailable(message: str) -> OcrRun:
    return OcrRun((), False, False, message)


def _configure_tesseract(pytesseract: Any) -> None:
    configured = os.getenv("PRIVASHIELD_TESSERACT_CMD")
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured
        return
    if sys.platform != "win32":
        return
    # Common Windows install locations. This also works when the user has not
    # restarted their shell after installing Tesseract.
    candidates = (
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


def run_ocr(image: Any) -> OcrRun:
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError:
        return _unavailable("OCR unavailable: install the optional pytesseract package")

    try:
        _configure_tesseract(pytesseract)
        # This detects the common case where the Python wrapper exists but the binary does not.
        pytesseract.get_tesseract_version()
        data = pytesseract.image_to_data(image, output_type=Output.DICT)
    except Exception as exc:
        not_found = getattr(pytesseract, "TesseractNotFoundError", ())
        if not_found and isinstance(exc, not_found):
            return _unavailable("OCR unavailable: install Tesseract or set PRIVASHIELD_TESSERACT_CMD to tesseract.exe")
        return _unavailable("OCR unavailable: Tesseract could not process this page")

    words: list[OcrWord] = []
    for index, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text).strip()
        if not text:
            continue
        try:
            confidence = float(data.get("conf", ["-1"])[index])
            left = float(data["left"][index])
            top = float(data["top"][index])
            width = float(data["width"][index])
            height = float(data["height"][index])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if confidence < 0 or width <= 0 or height <= 0:
            continue
        try:
            block_number = int(data.get("block_num", [0])[index])
            line_number = int(data.get("line_num", [index])[index])
        except (IndexError, TypeError, ValueError):
            block_number, line_number = 0, index
        words.append(OcrWord(text, left, top, left + width, top + height, confidence / 100.0, (block_number, line_number)))
    return OcrRun(tuple(words), True, True, None)
