.PHONY: up down build migrate seed vector-build vector-search vector-test-integration test lint typecheck

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python -m src.db.seed

import-catalog:
	docker compose run --rm api python -m src.importers.csv_importer --directory /app/data/realdata/raw/clean --update-existing

vector-build:
	python scripts/build_policy_vector_db.py

vector-search:
	python scripts/search_policy_vector_db.py "$(QUERY)"

vector-test-integration:
	cd apps/api && pytest tests/test_policy_pgvector_integration.py -q

test:
	docker compose run --rm api pytest
	docker compose run --rm web npm test -- --run

lint:
	docker compose run --rm api ruff check src tests
	docker compose run --rm web npm run lint

typecheck:
	docker compose run --rm api mypy src
	docker compose run --rm web npm run type-check

