.PHONY: up down build migrate seed test lint typecheck bench-gate1 bench-gate3 bench-gate4 bench-gates vllm-up vllm-up-baseline vllm-down vllm-logs

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
	@echo "Gate 2 (vLLM flag pair) can be run manually with 2 different --label values, see scripts/bench/README.md"

# vLLM trên VM GPU thuê (FPT AI Factory H100 80GB) -- chạy lệnh này TRÊN VM
# qua SSH, không phải máy dev local. Chỉ 10h credit tổng -- LUÔN vllm-down
# ngay khi xong cửa sổ, xem docs/pipelines.md §6.9.
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

