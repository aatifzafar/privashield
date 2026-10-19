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
5. `POST /api/export` requests a verified redacted binary with flatten-to-image and keep-last-N options.
6. `DELETE /api/session/{session_id}` removes the temporary session.

The UI uses a local object URL for page previews so the uploaded file can be inspected immediately. Image pages receive positioned detection overlays; PDF pages use the browser PDF preview plus a coordinate-accurate overlay map. Values are never rendered in the report UI.

## Scope notes

- The current backend export contract accepts a session and export options, but does not accept review decisions or manual bounding boxes. Keep/manual decisions are therefore reflected in the interactive review preview; the server export continues to apply the backend's analyzed findings. The API would need an additional redaction-selection payload to make those decisions authoritative in the binary.
- The frontend surfaces low-confidence warnings and OCR availability warnings from the backend. It does not claim perfect detection, legal compliance, or coverage for every document type.
- No frontend test runner is added for this Phase 1 standalone shell; `npm test` provides the offline TypeScript check and `npm run build` is the production verification command.
