.PHONY: dev test lint migrate
dev:
	cd frontend && npm run dev
test:
	cd backend && poetry run pytest
	cd frontend && npm test
lint:
	cd backend && poetry run ruff check .
	cd frontend && npm run lint
migrate:
	cd backend && poetry run alembic upgrade head
