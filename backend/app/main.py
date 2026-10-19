from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import Settings
from .models import (
    AnalyzeRequest,
    ExportRequest,
    HealthResponse,
    ReportResponse,
    UploadResponse,
    safe_report_payload,
)
from .services.analyzer import AnalysisResult, analyze_document
from .services.redaction import redact_image, redact_pdf, verify_export
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


def _report_for(session, analysis: AnalysisResult, verification: dict[str, object] | None = None) -> dict[str, object]:
    return safe_report_payload(
        report_id=session.session_id,
        session_id=session.session_id,
        document_type=session.document_type,
        pages=session.pages,
        findings=analysis.findings,
        ocr=getattr(analysis.content, "ocr_data"),
        warnings=analysis.warnings,
        created_at=analysis.created_at,
        verification=verification,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    store = SessionStore(active_settings.storage_dir, active_settings.session_ttl_seconds)

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
    )

    @application.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        store.cleanup()
        return HealthResponse(status="ok", storage="ready")

    @application.post("/api/upload", response_model=UploadResponse, status_code=201)
    async def upload(file: Annotated[UploadFile, File(...)]) -> UploadResponse:
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
    async def analyze(request: AnalyzeRequest) -> ReportResponse:
        session = _session_or_404(store, request.session_id)
        analysis = _analyze_session(store, session, request.use_ocr)
        report = _report_for(session, analysis)
        store.save_report(session, report)
        return ReportResponse(**report)

    @application.get("/api/report/{report_id}", response_model=ReportResponse)
    async def report(report_id: str) -> ReportResponse:
        session = _session_or_404(store, report_id)
        try:
            saved = store.load_report(session)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Analysis report not found") from exc
        return ReportResponse(**saved)

    @application.post("/api/export")
    async def export(request: ExportRequest) -> Response:
        session = _session_or_404(store, request.session_id)
        analysis = _analyze_session(store, session, request.use_ocr)
        source = store.read_source(session)
        media_type = "application/pdf" if session.document_type == "pdf" else ("image/png" if session.original_suffix == ".png" else "image/jpeg")
        if request.use_ocr and not analysis.content.ocr_available and any(not page.words for page in analysis.content.pages):
            raise HTTPException(
                status_code=503,
                detail=analysis.content.ocr_message or "OCR is required for this image-only page but is unavailable",
            )
        if session.document_type == "pdf":
            output = redact_pdf(source, analysis.findings, request.flatten_to_image)
            suffix = ".pdf"
        else:
            output = redact_image(source, media_type, analysis.findings)
            suffix = ".png" if media_type == "image/png" else ".jpg"
        verification = verify_export(output, session.document_type, analysis.findings)
        if not verification.passed:
            raise HTTPException(status_code=500, detail="Post-export verification failed; the export was not returned")
        export_id = store.save_export(
            session,
            output,
            suffix,
            request.keep_last_n or active_settings.keep_last_n,
        )
        report = _report_for(session, analysis, verification.as_dict())
        store.save_report(session, report)
        headers = {
            "Content-Disposition": f'attachment; filename="privashield-redacted{suffix}"',
            "X-Privashield-Session-ID": session.session_id,
            "X-Privashield-Export-ID": export_id,
            "X-Privashield-Verification": "passed",
        }
        return Response(content=output, media_type=media_type, headers=headers)

    @application.delete("/api/session/{session_id}")
    async def delete_session(session_id: str) -> dict[str, bool]:
        try:
            store.delete(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        return {"deleted": True}

    return application


app = create_app()
