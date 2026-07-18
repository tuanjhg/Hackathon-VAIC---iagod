.PHONY: up down build migrate seed test lint typecheck bench-gate1 bench-gate3 bench-gate4 bench-gates vllm-up vllm-up-baseline vllm-down vllm-logs
.PHONY: up down build migrate seed vector-build vector-search vector-test-integration test lint typecheck
.PHONY: eval eval-judge eval-all

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python -m src.seed.seed_products
	docker compose run --rm api python -m src.seed.seed_realdata
	docker compose run --rm api python -m src.seed.sync_catalog_products

vector-build:
	python scripts/build_policy_vector_db.py

vector-search:
	python scripts/search_policy_vector_db.py "$(QUERY)"

vector-test-integration:
	cd apps/api && pytest tests/test_policy_pgvector_integration.py -q

# Golden-conversation eval (data/*.json -> replay through pipeline + LLM judge).
# Tier 1 (structural) is free; --judge adds LLM-as-judge (costs OpenRouter calls).
# Needs LLM_API_KEY in .env. Report lands in data/golden/eval_report.{md,json}.
eval:
	cd apps/api && python -m src.eval.run_eval --limit 5

eval-judge:
	cd apps/api && python -m src.eval.run_eval --limit 5 --judge

eval-all:
	cd apps/api && python -m src.eval.run_eval --all --judge

test:
	docker compose run --rm api pytest
	docker compose run --rm web npm test -- --run

lint:
	docker compose run --rm api ruff check src tests
	docker compose run --rm web npm run lint

typecheck:
	docker compose run --rm api mypy src
	docker compose run --rm web npm run type-check

# Benchmark gate Phase 0 (docs/research/dmx-tech-decisions.md, bảng cuối).
# Cần VLLM_BASE_URL trỏ vào vLLM thật đang chạy -- không chạy được offline.
# gate2 (flag pair) chạy tay 2 lần với --label khác nhau, xem scripts/bench/README.md.
bench-gate1:
	python3 scripts/bench/gate1_s2_latency.py

bench-gate3:
	python3 scripts/bench/gate3_embedding_latency.py

bench-gate4:
	python3 scripts/bench/gate4_qwen3_clean_run.py

bench-gates: bench-gate1 bench-gate3 bench-gate4
	@echo "Gate 2 (vLLM flag pair) is ARCHIVED -- không còn vLLM tự host để chỉnh flag, xem ADR A2'"

# ⚠️ ARCHIVED (18/07): self-host vLLM không còn trong kế hoạch -- team dùng
# API key FPT AI Factory cho Qwen3.6-27B (ADR A2'). Giữ target phòng khi
# roadmap pilot (ADR A8) cần self-host lại; KHÔNG chạy trong kế hoạch hiện tại.
vllm-up:
	docker compose -f docker-compose.vllm.yml up -d vllm
	@echo "Đang load model (~10 phút) -- theo dõi bằng: make vllm-logs"

vllm-up-baseline:
	docker compose -f docker-compose.vllm.yml up -d vllm-baseline
	@echo "Bản BASELINE (không prefix-caching/chunked-prefill) -- dùng cho Gate 2"

vllm-down:
	docker compose -f docker-compose.vllm.yml down
	@echo "Đã tắt vLLM -- kiểm tra dashboard FPT AI Factory để chắc chắn không còn tính phí"

vllm-logs:
	docker compose -f docker-compose.vllm.yml logs -f

