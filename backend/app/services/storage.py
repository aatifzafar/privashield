from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class SessionError(Exception):
    """Base class for safe session storage failures."""


class SessionNotFound(SessionError):
    pass


class SessionExpired(SessionError):
    pass


@dataclass(frozen=True)
class Session:
    session_id: str
    directory: Path
    source_path: Path
    document_type: str
    pages: int
    original_suffix: str


class SessionStore:
    def __init__(self, root: Path, ttl_seconds: int) -> None:
        self.root = root
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> int:
        now = time.time()
        removed = 0
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            try:
                if now - directory.stat().st_mtime > self.ttl_seconds:
                    shutil.rmtree(directory, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        return removed

    def create(
        self,
        source: bytes,
        *,
        document_type: str,
        pages: int,
        original_suffix: str,
    ) -> Session:
        for _ in range(5):
            session_id = secrets.token_urlsafe(18)
            directory = self.root / session_id
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError:
                continue
            source_path = directory / "source.bin"
            source_path.write_bytes(source)
            metadata = {
                "session_id": session_id,
                "document_type": document_type,
                "pages": pages,
                "original_suffix": original_suffix,
                "created_at": time.time(),
            }
            (directory / "session.json").write_text(json.dumps(metadata), encoding="utf-8")
            return Session(session_id, directory, source_path, document_type, pages, original_suffix)
        raise SessionError("Could not allocate a session identifier")

    def get(self, session_id: str) -> Session:
        if not SESSION_ID_RE.fullmatch(session_id):
            raise SessionNotFound("Session not found")
        directory = self.root / session_id
        try:
            metadata_path = directory / "session.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if time.time() - directory.stat().st_mtime > self.ttl_seconds:
                shutil.rmtree(directory, ignore_errors=True)
                raise SessionExpired("Session expired")
            source_path = directory / "source.bin"
            if not source_path.is_file():
                raise SessionNotFound("Session not found")
            return Session(
                session_id=session_id,
                directory=directory,
                source_path=source_path,
                document_type=str(metadata["document_type"]),
                pages=int(metadata["pages"]),
                original_suffix=str(metadata.get("original_suffix", "")),
            )
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError, OSError) as exc:
            raise SessionNotFound("Session not found") from exc

    def read_source(self, session: Session) -> bytes:
        return session.source_path.read_bytes()

    def save_report(self, session: Session, report: dict[str, Any]) -> None:
        (session.directory / "report.json").write_text(json.dumps(report), encoding="utf-8")

    def load_report(self, session: Session) -> dict[str, Any]:
        try:
            return json.loads((session.directory / "report.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise SessionNotFound("Analysis report not found") from exc

    def save_export(self, session: Session, content: bytes, suffix: str, keep_last_n: int) -> str:
        export_dir = session.directory / "exports"
        export_dir.mkdir(mode=0o700, exist_ok=True)
        export_id = secrets.token_urlsafe(12)
        path = export_dir / f"{export_id}{suffix}"
        path.write_bytes(content)
        exports = sorted(
            (candidate for candidate in export_dir.iterdir() if candidate.is_file()),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )
        for old_path in exports[keep_last_n:]:
            try:
                old_path.unlink()
            except OSError:
                pass
        return export_id

    def delete(self, session_id: str) -> None:
        if not SESSION_ID_RE.fullmatch(session_id):
            raise SessionNotFound("Session not found")
        directory = self.root / session_id
        if not directory.is_dir():
            raise SessionNotFound("Session not found")
        shutil.rmtree(directory)
