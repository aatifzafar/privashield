# PRIVASHIELD — Privacy-First Document Redaction

PRIVASHIELD is an OmniRush Frontier Buildathon 2026 prototype for the Systems, Infrastructure & Cybersecurity track. It helps a user minimize a document before sharing it: upload a PDF/JPG/PNG, review locally-run detections, choose what to keep or redact, export a sanitized copy, and inspect a value-free verification report.

This is a privacy-oriented tool, not a guarantee that every sensitive field was found and not a claim of legal or regulatory compliance. Review every page manually before sharing.

## Repository layout

```text
frontend/      React + Vite + TypeScript + Tailwind UI
backend/       Python 3.11 + FastAPI analysis/redaction API
samples/       Synthetic, obviously fake demo documents
scripts/       Sample generation helper
```

The frontend and backend are intentionally separate projects with separate dependencies and READMEs. The frontend calls the backend only through the documented REST API; there is no shared database or implicit code import between them.

## Quick start

### Backend

Requires Python 3.11. From `backend/`:

```bash
python3.11 -m venv .venv && . .venv/bin/activate && python -m pip install -r requirements.txt && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1; python -m pip install -r requirements.txt; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The API is at `http://127.0.0.1:8000`, with interactive docs at `/docs`.

### Frontend

Requires Node 20 (see `frontend/.nvmrc`). From `frontend/`:

```bash
npm ci && npm run dev
```

Open `http://127.0.0.1:5173`. Copy `frontend/.env.example` to `frontend/.env` only if the API is not at the default URL.

### Test and build

From the repository root:

```bash
make test
make frontend-build
```

The backend test suite is offline-friendly and generates its own PDFs. Frontend `npm test` runs the TypeScript check; `npm run build` performs the production Vite build.

### Tesseract (OCR)

Text PDFs work with the base backend dependencies. Scanned PDFs and images need the optional `pytesseract` Python package plus the Tesseract executable. Install the Python extra from `backend/`:

```bash
python -m pip install -e ".[ocr]"
```

Then install Tesseract using the platform package manager: Ubuntu/Debian `sudo apt-get install tesseract-ocr`; macOS `brew install tesseract`; Windows install the official Tesseract package and add its install directory to `PATH`. The app reports OCR-unavailable instead of silently claiming a scan was covered.

Optional QR/face heuristics use `python -m pip install -e ".[vision]"` and are always marked low confidence.

### Synthetic demo files

```bash
python scripts/generate_samples.py
```

This produces `samples/fake-pan-card.png`, `samples/fake-aadhaar-style-card.png`, and `samples/fake-bank-statement.pdf`. All values are fictional and intentionally labeled as demo-only.

## Architecture

```text
┌──────────────────────────────┐       REST / JSON + binary       ┌───────────────────────────────┐
│ frontend/                    │  ────────────────────────────▶  │ backend/                      │
│ React + Vite + TypeScript    │                                 │ FastAPI                      │
│ upload / review / preview    │  ◀────────────────────────────  │ validation + session TTL      │
│ decision state / report UI   │       value-free reports       │ PyMuPDF + Pillow + local OCR  │
└───────────────┬──────────────┘                                 └───────────────┬───────────────┘
                │ local browser preview                                         │
                ▼                                                               ▼
        User's selected file                                         per-session temp directory
        (object URL only)                                           source / report / bounded exports
```

Analysis runs locally in the backend process. There are no external AI calls, cloud OCR calls, analytics beacons, or third-party document APIs. The default session TTL is 15 minutes in the root example; configure it with `PRIVASHIELD_SESSION_TTL_SECONDS`.

## REST API contract

All routes are prefixed with `/api` and are CORS-enabled only for configured local development origins by default.

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness and storage readiness |
| POST | `/api/upload` | Multipart upload; validates magic bytes, size, and PDF page count |
| POST | `/api/analyze` | Runs text extraction/OCR and returns value-free detection boxes |
| POST | `/api/export` | Applies the reviewed redaction set and returns a verified binary |
| GET | `/api/report/{session_id}` | Reads the latest value-free report |
| DELETE | `/api/session/{session_id}` | Deletes source, report, and saved exports immediately |

Detection reports contain category, page, bounding box, confidence, and source. They never contain the matched sensitive value or extracted document text. Export requests carry the user-reviewed finding IDs/bounding boxes plus optional manual rectangles; the server re-analyzes and validates them before redaction.

## Security and threat model

### What it is designed to protect against

- Recoverable PDF redactions caused by drawing a black rectangle over an intact text/image layer.
- Common metadata leaks in PDF properties, XMP, links, annotations, form widgets, and embedded files.
- Leaving the original source and exported copies indefinitely in the session store; TTL cleanup and an explicit delete endpoint are provided.
- Accidental sharing of values through the analysis report; reports are intentionally value-free.
- Obvious upload abuse: random session identifiers, magic-byte checks, a 10 MB limit, a five-page limit, bounded saved exports, safe internal filenames, and local CORS defaults.

### What it does not protect against

- A sensitive field that the detector did not find, including unusual layouts, handwriting, adversarial documents, or context that visually identifies someone.
- A malicious or compromised server process, host, browser extension, or operator.
- Correctness of OCR on poor scans, glare, low contrast, or unusual scripts.
- A recipient's policy or an official verification workflow; a redacted copy may be rejected where the original is required.
- Data inferred from fields the user intentionally keeps, including combinations of name, address, dates, and transactions.
- All steganography, unusual embedded content, or every possible PDF object without a deployment-specific security review.

Never use this prototype as the sole control for high-impact identity decisions. The UI repeats the manual-review warning and does not claim “100% secure.”

## Phase status

| Area | Implemented now | Future work / limitation |
|---|---|---|
| Upload | PDF/JPG/PNG magic-byte validation, 10 MB, max 5 PDF pages | More formats and organization-specific policy limits |
| Detection | PyMuPDF word boxes, local Tesseract OCR when installed, regex/Verhoeff/label heuristics, optional low-confidence QR/face | More document-specific models, handwriting, adversarial-layout evaluation |
| Review | Keep/redact controls, page overlays, manual rectangles, low-confidence warnings | Stronger native PDF rendering and synchronized before/after pane |
| Export | PyMuPDF true redactions, image pixel burns, metadata/object cleanup, flatten-to-image PDF, keep-last-N partial masking | Independent sandboxing and formal external security review |
| Verification | Extracted text/raw bytes/metadata/annotations and optional OCR checks, per-field statuses | Better OCR evidence for every scan and corpus-based regression suite |
| Privacy | Per-session temp storage, TTL cleanup, explicit delete, no content logging, value-free reports | Memory-only deployment option and hardened multi-tenant isolation |
| Product | Purpose presets and printable/JSON report | Bank-statement narration preset, batch review, client-only image mode |

## Two-minute demo script

1. Start the backend and frontend using the commands above.
2. Open `samples/fake-bank-statement.pdf` in PRIVASHIELD, then click **Upload securely**.
3. Choose **Analyze document**. Point out that the API is local, reports show categories/boxes but never values, and the low-confidence/manual-review warning is visible.
4. In the review panel, keep the synthetic name, redact the account number, IFSC, phone, email, address, dates, and PIN. Add a manual rectangle over any remaining statement area.
5. Open the preview overlay and show that each decision is explicit. Enable **Flatten PDF to image** for maximum-safety mode; optionally use the keep-last-N control for an identifier.
6. Click **Export redacted file**. Explain that the backend applies PyMuPDF redactions or burns image pixels, strips metadata/links/forms/attachments, re-extracts text, scans raw bytes, and optionally OCR-checks the result before returning it.
7. Show the value-free privacy report, its verification badges, JSON download/print view, then click **Delete session**.
8. Repeat with `fake-pan-card.png` if time remains; if Tesseract is not installed, use the warning to explain why a scan is not silently treated as safe.

## Docker

The two folders are independently containerizable. Use `backend/Dockerfile` for the API and `frontend/Dockerfile` for the static UI. The backend image intentionally does not bundle Tesseract by default; add it in a deployment-specific image if OCR is required.

```bash
docker build -t privashield-backend ./backend
docker run --rm -p 8000:8000 -e PRIVASHIELD_STORAGE_DIR=/tmp/privashield-sessions privashield-backend
docker build -t privashield-frontend ./frontend
docker run --rm -p 8080:80 privashield-frontend
```

Review `frontend/.env.example` and configure the API URL for a containerized deployment. Do not put secrets in these files.
