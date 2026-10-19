# PRIVASHIELD Phase 1 backend

Self-contained Python 3.11 FastAPI service for temporary document analysis and redaction. It accepts PDF, JPG, and PNG uploads, limits uploads to 10 MB and five PDF pages, and keeps session data in a local TTL-managed directory.

## Setup

From this `backend/` directory:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate with `.\.venv\Scripts\Activate.ps1`. The application reads the environment variables shown in `.env.example`; it does not require a secret for local operation.

Optional capabilities are deliberately separate from the basic text-PDF path:

```bash
python -m pip install -e ".[ocr,vision]"
```

The `ocr` extra installs the Python wrapper, but the Tesseract executable must also be installed and available on `PATH`. If either part is missing, analysis continues with text-layer detections and reports a clear OCR-unavailable warning. The `vision` extra enables best-effort QR and face boxes at low confidence; it is not required for text redaction.

When OCR is requested for an image-only page and is unavailable, analysis returns the warning but export returns a clear `503` instead of presenting an unchanged image as safely redacted. Text PDFs with a usable text layer remain usable without OCR.

## Run

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Test

```bash
python -m pytest
```

The suite uses generated in-memory PDFs and does not require Tesseract, OpenCV, a frontend, or network access.

## API flow

1. `POST /api/upload` with multipart field `file`. File type is determined from magic bytes, not the client MIME type. The response contains a random `session_id`.
2. `POST /api/analyze` with `{"session_id":"...", "use_ocr":true}`. The response is a value-free report containing finding type, page, bounding box, confidence, and source. It never returns matched PII values or extracted document text.
3. `GET /api/report/{session_id}` reads the latest safe report.
4. `GET /api/session/{session_id}/preview/{page}` renders a temporary unredacted page preview for the local review UI.
5. `POST /api/export` with `{"session_id":"...", "findings":[{"id":"finding-0001", "page":1, "bbox":[...], "decision":"redact"}], "flatten_to_image":false, "keep_last_n":4}`. The server re-analyzes the source, resolves known IDs against its own boxes, accepts only explicit manual rectangles from the client, and applies the reviewed redaction set. `keep_last_n` is optional leading-mask behavior; `retain_exports` separately bounds saved server-side copies. The response body is the redacted PDF/JPG/PNG binary. Verification status and the random export ID are returned as `X-Privashield-*` headers. A failed post-export verification prevents the binary from being returned.
6. `DELETE /api/session/{session_id}` explicitly removes source, report, and saved export files.

`GET /api/health` returns the service/storage status. CORS is restricted by default to common local frontend origins and can be changed with `PRIVASHIELD_CORS_ORIGINS`.

## Implementation notes

- PyMuPDF extracts PDF words and coordinates. Optional pytesseract OCR supplies words and boxes for image-only pages and image uploads.
- PAN, Verhoeff-checked Aadhaar, Indian phone, email, date-of-birth-like dates, Indian PIN, passport, IFSC, label-based names/addresses, and bank accounts near account labels are detected using validators and bounded regexes.
- QR and face detection is best-effort and low-confidence when OpenCV is installed.
- PDF redaction uses `add_redact_annot` and `apply_redactions`, then strips metadata, embedded files, links, annotations, and form widgets before a garbage/clean/deflate save. `flatten_to_image` creates a raster-only PDF.
- Image redaction draws opaque boxes with Pillow and writes fresh image bytes without source EXIF.
- Export verification checks extracted text, direct raw-byte remnants, metadata, annotations/links/forms, and OCR when available. It also stores per-redacted-field pass/fail statuses without values. Verification reports contain only boolean/status information and generic failure categories.
- Session content is never written to application logs. This service is a Phase 1 implementation; its detection coverage and document-format behavior should be evaluated against the documents and operational threat model used for deployment.

## Docker

The included image supports the base text-PDF and Pillow flows. OCR remains optional and reports its unavailable status unless a Tesseract runtime is added to the image.

```bash
docker build -t privashield-backend .
docker run --rm -p 8000:8000 -e PRIVASHIELD_STORAGE_DIR=/tmp/privashield-sessions privashield-backend
```
