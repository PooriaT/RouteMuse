.PHONY: dev test lint migrate
dev:
	cd frontend && npm run dev
test:
	cd backend && python -m pytest
	cd frontend && npm test
lint:
	cd backend && ruff check .
	cd frontend && npm run lint
migrate:
	cd backend && alembic upgrade head
