from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    session_id: str
    document_type: str
    pages: int
    max_pages: int


class AnalyzeRequest(BaseModel):
    session_id: str = Field(min_length=16, max_length=64)
    use_ocr: bool = True


class FindingDecision(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    page: int = Field(ge=1, le=5)
    bbox: list[float] = Field(min_length=4, max_length=4)
    decision: Literal["keep", "redact"] = "redact"
    manual: bool = False
    keep_last_n: int | None = Field(default=None, ge=1, le=20)


class ExportRequest(BaseModel):
    session_id: str = Field(min_length=16, max_length=64)
    use_ocr: bool = True
    flatten_to_image: bool = False
    keep_last_n: int | None = Field(default=None, ge=1, le=20)
    retain_exports: int | None = Field(default=None, ge=1, le=20)
    findings: list[FindingDecision] = Field(default_factory=list, max_length=500)


class HealthResponse(BaseModel):
    status: str
    storage: str


class FindingResponse(BaseModel):
    id: str
    kind: str
    page: int
    bbox: list[float]
    confidence: float
    source: str
    decision: Literal["keep", "redact"] = "redact"
    manual: bool = False


class OcrResponse(BaseModel):
    requested: bool
    available: bool
    used: bool
    message: str | None = None


class VerificationResponse(BaseModel):
    passed: bool
    text_absent: bool
    raw_bytes_absent: bool
    metadata_clean: bool
    annotations_clean: bool
    ocr: str
    failures: list[str]
    fields: list[dict[str, Any]] = Field(default_factory=list)


class ReportResponse(BaseModel):
    report_id: str
    session_id: str
    document_type: str
    pages: int
    findings: list[FindingResponse]
    ocr: OcrResponse
    warnings: list[str]
    verification: VerificationResponse | None = None
    created_at: str
    detected_count: int = 0
    redacted_count: int = 0
    kept_count: int = 0
    redacted_categories: dict[str, int] = Field(default_factory=dict)
    kept_categories: dict[str, int] = Field(default_factory=dict)
    metadata_stripped: bool | None = None
    deletion_notes: str = ""


def safe_report_payload(
    *,
    report_id: str,
    session_id: str,
    document_type: str,
    pages: int,
    findings: list[Any],
    ocr: dict[str, Any],
    warnings: list[str],
    created_at: str,
    verification: dict[str, Any] | None = None,
    redacted_findings: list[Any] | None = None,
    kept_findings: list[Any] | None = None,
) -> dict[str, Any]:
    """Convert internal findings to a value-free public report."""
    all_findings = list(findings)
    redacted = list(all_findings if redacted_findings is None else redacted_findings)
    kept = list([] if kept_findings is None else kept_findings)
    kept_ids = {item.public_id for item in kept}

    def category_counts(items: list[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return dict(sorted(counts.items()))

    return {
        "report_id": report_id,
        "session_id": session_id,
        "document_type": document_type,
        "pages": pages,
        "findings": [
            {
                "id": item.public_id,
                "kind": item.kind,
                "page": item.page,
                "bbox": [round(float(value), 3) for value in item.bbox],
                "confidence": round(float(item.confidence), 3),
                "source": item.source,
                "decision": "keep" if item.public_id in kept_ids else "redact",
                "manual": item.source == "manual" or item.kind == "manual_redaction",
            }
            for item in all_findings
        ],
        "ocr": ocr,
        "warnings": list(warnings),
        "verification": verification,
        "created_at": created_at,
        "detected_count": len(all_findings),
        "redacted_count": len(redacted),
        "kept_count": len(kept),
        "redacted_categories": category_counts(redacted),
        "kept_categories": category_counts(kept),
        "metadata_stripped": verification.get("metadata_clean") if verification else None,
        "deletion_notes": "Source, report, and saved exports remain in the temporary session until explicit deletion or TTL cleanup.",
    }
