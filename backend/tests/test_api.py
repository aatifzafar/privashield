from __future__ import annotations

import fitz

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import make_pdf


def test_upload_analyze_report_export_and_delete(tmp_path) -> None:
    app = create_app(Settings(storage_dir=tmp_path, session_ttl_seconds=3600))
    source = make_pdf("PAN: ABCDE1234F\nName: Alice Example")
    with TestClient(app) as client:
        upload = client.post("/api/upload", files={"file": ("input.pdf", source, "application/octet-stream")})
        assert upload.status_code == 201
        session_id = upload.json()["session_id"]

        analyzed = client.post("/api/analyze", json={"session_id": session_id, "use_ocr": False})
        assert analyzed.status_code == 200
        report = analyzed.json()
        assert any(item["kind"] == "pan" for item in report["findings"])
        assert "ABCDE1234F" not in analyzed.text
        assert client.get(f"/api/report/{session_id}").status_code == 200

        exported = client.post("/api/export", json={"session_id": session_id, "use_ocr": False})
        assert exported.status_code == 200
        assert exported.headers["x-privashield-verification"] == "passed"
        assert b"ABCDE1234F" not in exported.content

        deleted = client.delete(f"/api/session/{session_id}")
        assert deleted.status_code == 200
        assert client.get(f"/api/report/{session_id}").status_code == 404


def test_upload_rejects_content_that_does_not_match_allowed_magic_bytes(tmp_path) -> None:
    app = create_app(Settings(storage_dir=tmp_path, session_ttl_seconds=3600))
    with TestClient(app) as client:
        response = client.post("/api/upload", files={"file": ("input.pdf", b"not a pdf", "application/pdf")})
    assert response.status_code == 415


def test_upload_rejects_more_than_five_pdf_pages(tmp_path) -> None:
    document = fitz.open()
    for _ in range(6):
        document.new_page()
    source = document.tobytes()
    document.close()
    app = create_app(Settings(storage_dir=tmp_path, session_ttl_seconds=3600))
    with TestClient(app) as client:
        response = client.post("/api/upload", files={"file": ("many.pdf", source, "application/pdf")})
    assert response.status_code == 415


def test_upload_rejects_more_than_ten_megabytes(tmp_path) -> None:
    source = b"%PDF-1.7\n" + b"x" * (10 * 1024 * 1024)
    app = create_app(Settings(storage_dir=tmp_path, session_ttl_seconds=3600))
    with TestClient(app) as client:
        response = client.post("/api/upload", files={"file": ("large.pdf", source, "application/pdf")})
    assert response.status_code == 413
