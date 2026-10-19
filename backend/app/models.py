from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    session_id: str
    document_type: str
    pages: int
    max_pages: int


class AnalyzeRequest(BaseModel):
    session_id: str = Field(min_length=16, max_length=64)
    use_ocr: bool = True


class ExportRequest(BaseModel):
    session_id: str = Field(min_length=16, max_length=64)
    use_ocr: bool = True
    flatten_to_image: bool = False
    keep_last_n: int | None = Field(default=None, ge=1, le=20)


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
) -> dict[str, Any]:
    """Convert internal findings to a value-free public report."""
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
            }
            for item in findings
        ],
        "ocr": ocr,
        "warnings": list(warnings),
        "verification": verification,
        "created_at": created_at,
    }
