from __future__ import annotations

import fitz

from app.services.analyzer import analyze_document
from app.services.detectors import Detection
from app.services.redaction import apply_keep_last_n, redact_pdf, verify_export
from tests.conftest import make_pdf


def test_pdf_redaction_removes_text_raw_bytes_metadata_and_annotations() -> None:
    secret = "ABCDE1234F"
    source = make_pdf(
        f"PAN: {secret}",
        metadata={"title": f"private {secret}", "author": "test"},
    )
    analysis = analyze_document(source, "pdf", "application/pdf", use_ocr=False)
    assert any(finding.kind == "pan" for finding in analysis.findings)

    output = redact_pdf(source, analysis.findings)
    with fitz.open(stream=output, filetype="pdf") as document:
        extracted = "\n".join(page.get_text() for page in document)
        assert secret not in extracted
        assert all(not document.metadata.get(key) for key in ("title", "author", "subject", "keywords", "creator", "producer"))
        assert all(not list(page.annots() or []) for page in document)
    assert secret.encode() not in output

    verification = verify_export(output, "pdf", analysis.findings)
    assert verification.passed
    assert verification.text_absent
    assert verification.raw_bytes_absent
    assert verification.metadata_clean
    assert verification.annotations_clean

    flattened = redact_pdf(source, analysis.findings, flatten_to_image=True)
    with fitz.open(stream=flattened, filetype="pdf") as document:
        assert secret not in "\n".join(page.get_text() for page in document)
    assert secret.encode() not in flattened


def test_keep_last_n_adjusts_only_the_leading_part_of_a_detection_box() -> None:
    finding = Detection("pan", 1, (10, 20, 110, 40), 0.9, "text", "ABCDE1234F", "finding-0001")
    partial = apply_keep_last_n(finding, 4)
    assert partial.bbox == (10, 20, 70.0, 40)
    assert apply_keep_last_n(finding, None).bbox == finding.bbox
