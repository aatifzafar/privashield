from __future__ import annotations

from app.services.detectors import detect_page, verhoeff_checksum
from app.services.extraction import PageContent, WordBox


def page_from_lines(*lines: str) -> PageContent:
    words: list[WordBox] = []
    y = 20.0
    for line_number, line in enumerate(lines):
        x = 20.0
        for value in line.split():
            width = max(12.0, len(value) * 7.0)
            words.append(WordBox(value, (x, y, x + width, y + 12), 1, (0, line_number), "text"))
            x += width + 5
        y += 18
    return PageContent(1, 500, 500, words)


def test_verhoeff_accepts_aadhaar_checksum_and_rejects_mutation() -> None:
    valid = next(f"12345678901{digit}" for digit in range(10) if verhoeff_checksum(f"12345678901{digit}"))
    assert verhoeff_checksum(valid)
    assert not verhoeff_checksum(valid[:-1] + str((int(valid[-1]) + 1) % 10))


def test_detector_finds_supported_sensitive_formats_without_exposing_values() -> None:
    page = page_from_lines(
        "PAN ABCDE1234F phone 9876543210 email alice@example.com",
        "DOB 01/02/1990 PIN 110011 passport A1234567 IFSC SBIN0001234",
        "Account Number 123456789012 Name Alice",
        "Address 42 Privacy Street",
    )
    findings = detect_page(page)
    kinds = {finding.kind for finding in findings}
    assert {"pan", "indian_phone", "email", "date_of_birth", "indian_pin", "passport", "ifsc", "bank_account"} <= kinds
    assert "name_label" in kinds
    assert "address_label" in kinds
    assert all(finding.value not in {""} for finding in findings if finding.kind not in {"qr_code", "face"})
