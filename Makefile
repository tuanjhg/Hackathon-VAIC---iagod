.PHONY: up down build migrate seed test lint typecheck

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python -m src.seed.sync_catalog_products

test:
	docker compose run --rm api pytest
	docker compose run --rm web npm test -- --run

lint:
	docker compose run --rm api ruff check src tests
	docker compose run --rm web npm run lint

typecheck:
	docker compose run --rm api mypy src
	docker compose run --rm web npm run type-check

