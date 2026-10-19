from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .detectors import Detection, detect_page
from .extraction import DocumentContent, extract_document
from .vision import detect_vision


@dataclass
class AnalysisResult:
    content: DocumentContent
    findings: list[Detection]
    warnings: list[str]
    created_at: str


def analyze_document(data: bytes, document_type: str, media_type: str, use_ocr: bool) -> AnalysisResult:
    content = extract_document(data, document_type, media_type, use_ocr)
    findings: list[Detection] = []
    warnings = list(content.warnings)
    for page in content.pages:
        vision_findings = []
        if page.rendered is not None:
            vision_findings, vision_warnings = detect_vision(page.rendered)
            warnings.extend(vision_warnings)
        findings.extend(detect_page(page, vision_findings))
    for index, finding in enumerate(findings, start=1):
        finding.public_id = f"finding-{index:04d}"
    ocr_message = content.ocr_message
    ocr_data: dict[str, Any] = {
        "requested": content.ocr_requested,
        "available": content.ocr_available,
        "used": content.ocr_used,
        "message": ocr_message,
    }
    # Store this as an attribute so callers do not have to expose the DocumentContent object.
    setattr(content, "ocr_data", ocr_data)
    return AnalysisResult(content, findings, list(dict.fromkeys(warnings)), datetime.now(timezone.utc).isoformat())
