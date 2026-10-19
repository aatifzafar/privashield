from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

import fitz
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import Settings
from .models import (
    AnalyzeRequest,
    ExportRequest,
    FindingDecision,
    HealthResponse,
    ReportResponse,
    UploadResponse,
    safe_report_payload,
)
from .services.analyzer import AnalysisResult, analyze_document
from .services.detectors import Detection
from .services.redaction import apply_keep_last_n, redact_image, redact_pdf, verify_export
from .services.rate_limit import RateLimiter
from .services.storage import SessionExpired, SessionNotFound, SessionStore
from .services.validation import UploadTooLargeError, UploadValidationError, validate_upload


def _session_or_404(store: SessionStore, session_id: str):
    try:
        store.cleanup()
        return store.get(session_id)
    except SessionExpired as exc:
        raise HTTPException(status_code=404, detail="Session expired") from exc
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


def _analyze_session(store: SessionStore, session, use_ocr: bool) -> AnalysisResult:
    source = store.read_source(session)
    media_type = "application/pdf" if session.document_type == "pdf" else ("image/png" if session.original_suffix == ".png" else "image/jpeg")
    return analyze_document(source, session.document_type, media_type, use_ocr)


def _report_for(
    session,
    analysis: AnalysisResult,
    verification: dict[str, object] | None = None,
    *,
    report_findings: list[Detection] | None = None,
    redacted_findings: list[Detection] | None = None,
    kept_findings: list[Detection] | None = None,
) -> dict[str, object]:
    return safe_report_payload(
        report_id=session.session_id,
        session_id=session.session_id,
        document_type=session.document_type,
        pages=session.pages,
        findings=analysis.findings if report_findings is None else report_findings,
        ocr=getattr(analysis.content, "ocr_data"),
        warnings=analysis.warnings,
        created_at=analysis.created_at,
        verification=verification,
        redacted_findings=redacted_findings,
        kept_findings=kept_findings,
    )


def _reviewed_findings(
    analysis: AnalysisResult,
    decisions: list[FindingDecision],
    pages: int,
) -> tuple[list[Detection], list[Detection], list[Detection]]:
    """Resolve value-free client decisions against fresh server detections.

    Existing detections always use the server's coordinates and value. Client
    coordinates are accepted only for explicitly manual rectangles.
    """
    by_id = {finding.public_id: finding for finding in analysis.findings}
    requested = {item.id: item for item in decisions}
    redacted: list[Detection] = []
    kept: list[Detection] = []
    review_findings = list(analysis.findings)

    for finding in analysis.findings:
        choice = requested.get(finding.public_id)
        if choice is not None and choice.decision == "keep":
            kept.append(finding)
        else:
            redacted.append(finding)

    for choice in decisions:
        if not choice.manual:
            if choice.id not in by_id:
                raise HTTPException(status_code=400, detail="Export contains an unknown detection id")
            continue
        if choice.page > pages:
            raise HTTPException(status_code=400, detail="Manual redaction page is outside the uploaded document")
        x0, y0, x1, y1 = choice.bbox
        if not (x1 > x0 and y1 > y0 and x0 >= 0 and y0 >= 0):
            raise HTTPException(status_code=400, detail="Manual redaction rectangle is invalid")
        manual = Detection(
            kind="manual_redaction",
            page=choice.page,
            bbox=(float(x0), float(y0), float(x1), float(y1)),
            confidence=1.0,
            source="manual",
            public_id=choice.id,
        )
        redacted.append(manual)
        review_findings.append(manual)

    return review_findings, redacted, kept


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    store = SessionStore(active_settings.storage_dir, active_settings.session_ttl_seconds)
    rate_limiter = RateLimiter(active_settings.rate_limit_per_minute)

    def enforce_rate_limit(http_request: Request) -> None:
        client_key = http_request.client.host if http_request.client else "unknown"
        if not rate_limiter.allow(client_key):
            raise HTTPException(status_code=429, detail="Too many requests; retry after one minute", headers={"Retry-After": "60"})

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.cleanup()
        yield

    application = FastAPI(title="PRIVASHIELD Phase 1 API", version="0.1.0", lifespan=lifespan)
    application.state.settings = active_settings
    application.state.store = store
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            "Content-Disposition",
            "X-Privashield-Session-ID",
            "X-Privashield-Export-ID",
            "X-Privashield-Verification",
        ],
    )

    @application.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        store.cleanup()
        return HealthResponse(status="ok", storage="ready")

    @application.post("/api/upload", response_model=UploadResponse, status_code=201)
    async def upload(file: Annotated[UploadFile, File(...)], http_request: Request) -> UploadResponse:
        enforce_rate_limit(http_request)
        store.cleanup()
        data = await file.read(active_settings.max_upload_bytes + 1)
        try:
            validated = validate_upload(data, active_settings.max_upload_bytes, active_settings.max_pages)
        except UploadTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except UploadValidationError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        session = store.create(
            data,
            document_type=validated.document_type,
            pages=validated.pages,
            original_suffix=validated.suffix,
        )
        return UploadResponse(
            session_id=session.session_id,
            document_type=validated.document_type,
            pages=validated.pages,
            max_pages=active_settings.max_pages,
        )

    @application.post("/api/analyze", response_model=ReportResponse)
    async def analyze(payload: AnalyzeRequest, http_request: Request) -> ReportResponse:
        enforce_rate_limit(http_request)
        session = _session_or_404(store, payload.session_id)
        analysis = _analyze_session(store, session, payload.use_ocr)
        report = _report_for(session, analysis)
        store.save_report(session, report)
        return ReportResponse(**report)

    @application.get("/api/report/{report_id}", response_model=ReportResponse)
    async def report(report_id: str, http_request: Request) -> ReportResponse:
        enforce_rate_limit(http_request)
        session = _session_or_404(store, report_id)
        try:
            saved = store.load_report(session)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Analysis report not found") from exc
        return ReportResponse(**saved)

    @application.get("/api/session/{session_id}/preview/{page_number}")
    async def preview(session_id: str, page_number: int, http_request: Request) -> Response:
        """Render an unredacted session page for the authenticated local UI preview."""
        enforce_rate_limit(http_request)
        session = _session_or_404(store, session_id)
        if page_number < 1 or page_number > session.pages:
            raise HTTPException(status_code=404, detail="Preview page not found")
        source = store.read_source(session)
        media_type = "application/pdf" if session.document_type == "pdf" else ("image/png" if session.original_suffix == ".png" else "image/jpeg")
        if session.document_type == "image":
            return Response(content=source, media_type=media_type, headers={"Cache-Control": "no-store"})
        try:
            with fitz.open(stream=source, filetype="pdf") as document:
                page = document.load_page(page_number - 1)
                # 1 point/pixel keeps PDF point coordinates aligned with the overlay map.
                rendered = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes("png")
        except Exception as exc:
            raise HTTPException(status_code=422, detail="The document preview could not be rendered") from exc
        return Response(content=rendered, media_type="image/png", headers={"Cache-Control": "no-store"})

    @application.post("/api/export")
    async def export(payload: ExportRequest, http_request: Request) -> Response:
        enforce_rate_limit(http_request)
        session = _session_or_404(store, payload.session_id)
        analysis = _analyze_session(store, session, payload.use_ocr)
        source = store.read_source(session)
        media_type = "application/pdf" if session.document_type == "pdf" else ("image/png" if session.original_suffix == ".png" else "image/jpeg")
        if payload.use_ocr and not analysis.content.ocr_available and any(not page.words for page in analysis.content.pages):
            raise HTTPException(
                status_code=503,
                detail=analysis.content.ocr_message or "OCR is required for this image-only page but is unavailable",
            )
        review_findings, redacted_findings, kept_findings = _reviewed_findings(analysis, payload.findings, session.pages)
        requested_by_id = {item.id: item for item in payload.findings}
        effective_redactions = [
            apply_keep_last_n(finding, requested_by_id.get(finding.public_id).keep_last_n if requested_by_id.get(finding.public_id) else payload.keep_last_n)
            for finding in redacted_findings
        ]
        if session.document_type == "pdf":
            output = redact_pdf(source, effective_redactions, payload.flatten_to_image)
            suffix = ".pdf"
        else:
            output = redact_image(source, media_type, effective_redactions)
            suffix = ".png" if media_type == "image/png" else ".jpg"
        verification = verify_export(output, session.document_type, effective_redactions)
        if not verification.passed:
            raise HTTPException(status_code=500, detail="Post-export verification failed; the export was not returned")
        export_id = store.save_export(
            session,
            output,
            suffix,
            payload.retain_exports or active_settings.keep_last_n,
        )
        report = _report_for(
            session,
            analysis,
            verification.as_dict(),
            report_findings=review_findings,
            redacted_findings=redacted_findings,
            kept_findings=kept_findings,
        )
        store.save_report(session, report)
        headers = {
            "Content-Disposition": f'attachment; filename="privashield-redacted{suffix}"',
            "X-Privashield-Session-ID": session.session_id,
            "X-Privashield-Export-ID": export_id,
            "X-Privashield-Verification": "passed",
        }
        return Response(content=output, media_type=media_type, headers=headers)

    @application.delete("/api/session/{session_id}")
    async def delete_session(session_id: str, http_request: Request) -> dict[str, bool]:
        enforce_rate_limit(http_request)
        try:
            store.delete(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        return {"deleted": True}

    return application


app = create_app()
