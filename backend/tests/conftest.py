from __future__ import annotations

import io

import fitz
import pytest
from PIL import Image


def make_pdf(text: str, *, metadata: dict[str, str] | None = None) -> bytes:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), text, fontsize=12)
    if metadata:
        document.set_metadata(metadata)
    output = document.tobytes()
    document.close()
    return output


def make_png() -> bytes:
    image = Image.new("RGB", (240, 120), "white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def pdf_bytes() -> bytes:
    return make_pdf("PAN: ABCDE1234F\nEmail: alice@example.com")
