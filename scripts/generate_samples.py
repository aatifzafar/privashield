"""Create synthetic PRIVASHIELD demo documents with obviously fake data."""

from __future__ import annotations

import io
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples"


def font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def card(title: str, subtitle: str, lines: list[tuple[str, str]], filename: str, accent: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (1400, 880), "#f4f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 70, 1330, 810), radius=32, fill="#ffffff", outline=accent, width=5)
    draw.rectangle((70, 70, 1330, 220), fill=accent)
    draw.text((115, 105), title, fill="#ffffff", font=font(44, True))
    draw.text((118, 166), subtitle, fill="#d7ffff", font=font(22))
    y = 280
    for label, value in lines:
        draw.text((125, y), label, fill="#64748b", font=font(24, True))
        draw.text((390, y), value, fill="#102038", font=font(31))
        y += 78
    draw.rounded_rectangle((1020, 590, 1245, 760), radius=12, fill="#e6edf3")
    draw.text((1052, 650), "SYNTHETIC", fill="#64748b", font=font(23, True))
    draw.text((1075, 690), "DEMO ONLY", fill="#64748b", font=font(18))
    draw.text((118, 770), "Not a government document · fictional data · do not use for identity verification", fill="#be123c", font=font(18, True))
    image.save(OUT / filename, format="PNG", optimize=True)


def bank_statement(filename: str) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((48, 62), "NORTHSTAR DEMO BANK", fontsize=22, fontname="helv", color=(0.06, 0.13, 0.22))
    page.insert_text((48, 88), "SYNTHETIC STATEMENT — NOT A REAL BANK RECORD", fontsize=10, fontname="helv", color=(0.75, 0.07, 0.22))
    rows = [
        "Statement period: 01/01/2026 - 31/01/2026",
        "Name: Avery Example",
        "Account Number: 987654321012",
        "IFSC: DEMO0001234",
        "Address: 42 Privacy Street, Fiction City, 110011",
        "Phone: +91 9876543210   Email: demo@example.test",
        "",
        "DATE          DESCRIPTION                         AMOUNT",
        "05/01/2026    DEMO COFFEE SHOP                    450.00",
        "12/01/2026    SAMPLE PAYROLL                    85000.00",
        "21/01/2026    FICTIONAL UTILITY BILL              1200.00",
        "31/01/2026    Closing balance                    83350.00",
    ]
    y = 140
    for row in rows:
        page.insert_text((48, y), row, fontsize=11, fontname="cour", color=(0.10, 0.16, 0.24))
        y += 31
    page.insert_text((48, 755), "Synthetic data for PRIVASHIELD testing only.", fontsize=9, fontname="helv", color=(0.39, 0.45, 0.55))
    document.set_metadata({"title": "Synthetic demo statement", "author": "PRIVASHIELD sample generator"})
    document.save(OUT / filename)
    document.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    card(
        "INCOME TAX DEPARTMENT — DEMO",
        "PERMANENT ACCOUNT NUMBER · FICTIONAL SAMPLE",
        [("Name", "Avery Example"), ("PAN", "ABCDE1234F"), ("Date of birth", "02/01/1990"), ("Phone", "+91 9876543210"), ("Email", "demo@example.test")],
        "fake-pan-card.png",
        (13, 110, 145),
    )
    card(
        "UNIQUE IDENTITY DEMO CARD",
        "AADHAAR-STYLE LAYOUT · NOT AN OFFICIAL DOCUMENT",
        [("Name", "Avery Example"), ("ID", "1111 2222 3330"), ("DOB", "02/01/1990"), ("Address", "42 Privacy Street, Fiction City"), ("PIN", "110011")],
        "fake-aadhaar-style-card.png",
        (7, 122, 91),
    )
    bank_statement("fake-bank-statement.pdf")
    print(f"Generated synthetic samples in {OUT}")


if __name__ == "__main__":
    main()
