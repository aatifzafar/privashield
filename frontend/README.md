# PRIVASHIELD Phase 1 frontend

Standalone React + Vite + TypeScript + Tailwind UI for the PRIVASHIELD Phase 1 document analysis and redaction service.

## Setup

Requirements:

- Node.js 22 (the version is pinned in `.nvmrc`)
- The PRIVASHIELD backend running locally or at a reachable URL

From this directory:

```bash
npm install
copy .env.example .env
npm run dev
```

On macOS/Linux, use `cp .env.example .env` instead of `copy`.

Set `VITE_API_URL` to the backend origin. The frontend adds `/api` automatically, so the default is:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

Open `http://localhost:5173`.

## Run, check, and build

```bash
npm run dev        # local development server
npm run typecheck  # TypeScript project check
npm run build      # typecheck + production Vite build
npm run preview    # serve the production build locally
```

`npm test` is an offline alias for `npm run typecheck`.

## Docker

Build and serve the production bundle with nginx:

```bash
docker build -t privashield-frontend .
docker run --rm -p 5173:80 privashield-frontend
```

For a non-default API origin, pass it at build time because Vite embeds `VITE_API_URL` in the bundle:

```bash
docker build --build-arg VITE_API_URL=http://127.0.0.1:8000 -t privashield-frontend .
```

## Implemented API flow

The typed client in `src/lib/api.ts` matches the current backend contract:

1. `GET /api/health` checks service/storage readiness.
2. `POST /api/upload` sends the selected PDF/JPG/PNG as multipart form data.
3. `POST /api/analyze` requests a value-free detection report, with optional OCR.
4. `GET /api/report/{session_id}` refreshes the report after export.
5. `GET /api/session/{session_id}/preview/{page}` renders the temporary page preview used by the overlay canvas.
6. `POST /api/export` sends the reviewed Keep/Redact decisions and manual rectangles, with flatten-to-image and optional partial masking.
7. `DELETE /api/session/{session_id}` removes the temporary session.

The UI uses a local object URL for image previews and a temporary backend-rendered PNG for each PDF page, so both formats receive positioned detection overlays. Values are never rendered in the report UI.

## Scope notes

- The backend re-analyzes on export and treats omitted known findings as redact-by-default. Manual rectangles are accepted as explicit client geometry and are still subject to output verification; they cannot be verified against a known value.
- The frontend surfaces low-confidence warnings and OCR availability warnings from the backend. It does not claim perfect detection, legal compliance, or coverage for every document type.
- No frontend test runner is added for this Phase 1 standalone shell; `npm test` provides the offline TypeScript check and `npm run build` is the production verification command.
