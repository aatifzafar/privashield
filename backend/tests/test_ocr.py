from __future__ import annotations

from types import SimpleNamespace

import pytesseract
from PIL import Image

from app.services.ocr import _configure_tesseract, run_ocr


def test_configure_tesseract_honors_explicit_command(monkeypatch) -> None:
    fake = SimpleNamespace(pytesseract=SimpleNamespace(tesseract_cmd="tesseract"))
    monkeypatch.setenv("PRIVASHIELD_TESSERACT_CMD", "C:/tools/tesseract.exe")

    _configure_tesseract(fake)

    assert fake.pytesseract.tesseract_cmd == "C:/tools/tesseract.exe"


def test_missing_tesseract_returns_actionable_warning(monkeypatch) -> None:
    def missing_binary() -> None:
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "get_tesseract_version", missing_binary)

    result = run_ocr(Image.new("RGB", (20, 20), "white"))

    assert result.available is False
    assert result.used is False
    assert result.message == "OCR unavailable: install Tesseract or set PRIVASHIELD_TESSERACT_CMD to tesseract.exe"
