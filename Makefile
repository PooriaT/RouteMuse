.PHONY: dev test lint migrate down
dev:
	docker compose up --build
down:
	docker compose down
test:
	cd backend && python -m pytest
	cd frontend && npm test
lint:
	cd backend && ruff check .
	cd frontend && npm run lint
migrate:
	docker compose run --rm backend alembic upgrade head
