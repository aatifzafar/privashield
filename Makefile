.PHONY: test frontend-build

test:
	cd backend && python -m pytest

frontend-build:
	cd frontend && npm run typecheck && npm run build
