# NeedWise Copilot

Skeleton chạy được cho ứng dụng **AI Product Comparison Advisor Based on Real Customer Needs**, tập trung ngành hàng máy lạnh. Người dùng có thể duyệt/filter catalog, xem chi tiết, thêm giỏ, so sánh tối đa ba sản phẩm và đi qua flow tư vấn rule-based hai bước để nhận ba đề xuất từ API.

## Tech stack

- Web: Next.js 15, TypeScript, Tailwind CSS, shadcn/ui conventions, TanStack Query, Zustand, Vitest.
- API: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, Pytest.
- Data/deploy: PostgreSQL 16, Docker, Docker Compose.

## Kiến trúc

Frontend chỉ giao tiếp qua REST API. FastAPI route gọi service, service gọi repository; route không query database. Dữ liệu PostgreSQL được chuẩn hóa thành category, product, specs, price, inventory và promotion. Xem [tài liệu kiến trúc](docs/architecture.md) và [pipeline backend/frontend](docs/pipelines.md).

## Cấu trúc thư mục

```text
.
├── apps/
│   ├── web/                  # Next.js storefront + component/store tests
│   └── api/                  # FastAPI, Alembic, models, services, tests
├── data/demo/products.json   # 20 máy lạnh demo
├── docs/architecture.md
├── scripts/seed_data.py
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Chạy nhanh bằng Docker Compose

Yêu cầu Docker Desktop/Engine có Compose v2.

```bash
cp .env.example .env
docker compose up --build
```

Compose đợi PostgreSQL healthy, chạy migration, seed idempotent rồi khởi động API. Truy cập:

- Frontend: http://localhost:3000
- Backend OpenAPI: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

Dừng hệ thống bằng `docker compose down`. Thêm `-v` nếu chủ động muốn xóa volume dữ liệu.

## Biến môi trường

Sao chép `.env.example` thành `.env`. Các biến chính:

| Biến | Ý nghĩa |
|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL DSN của API |
| `POSTGRES_DB/USER/PASSWORD` | Khởi tạo PostgreSQL container |
| `NEXT_PUBLIC_API_URL` | Base URL mà browser gọi |
| `CORS_ORIGINS` | Origin frontend được API cho phép |

Không commit `.env` hoặc credential thật.

## Migration và seed

Khi stack đang chạy:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m src.seed.seed_products
```

Hoặc dùng container one-off: `make migrate` và `make seed`. Seed đọc `data/demo/products.json`, bỏ qua SKU đã tồn tại nên có thể chạy lặp lại.

Tạo migration mới sau khi đổi model:

```bash
docker compose run --rm api alembic revision --autogenerate -m "describe change"
```

## Chạy local không Docker

API (mặc định dùng SQLite để phát triển nhanh nếu chưa đặt `DATABASE_URL`):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e "./apps/api[dev]"
cd apps/api
alembic upgrade head
python -m src.seed.seed_products
uvicorn src.main:app --reload --port 8000
```

Web ở terminal khác:

```bash
cd apps/web
npm install
npm run dev
```

## Kiểm tra chất lượng

```bash
# Backend
cd apps/api
pytest
ruff check src tests
mypy src

# Frontend
cd apps/web
npm test -- --run
npm run lint
npm run type-check
npm run build
```

Hoặc dùng `make test`, `make lint`, `make typecheck` với Docker.

## API

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/api/v1/health` | Trạng thái service |
| GET | `/api/v1/categories` | Danh mục |
| GET | `/api/v1/products` | Catalog có filter/sort/pagination |
| GET | `/api/v1/products/{slug}` | Chi tiết sản phẩm |
| POST | `/api/v1/compare` | So sánh 2–3 product ID |
| POST | `/api/v1/chat/messages` | Tin nhắn advisor rule-based |
| GET | `/api/v1/chat/demo-scenarios` | Kịch bản gợi ý |

`GET /products` hỗ trợ `search`, `brand`, `min_price`, `max_price`, `room_area`, `inverter`, `in_stock`, `sort`, `page`, `page_size`.

## Demo chatbot

1. Mở nút chat nổi và gửi: `Tư vấn máy lạnh cho phòng 18m2`.
2. Chọn một mức ngân sách, ví dụ `10–15 triệu`.
3. Chọn ưu tiên, ví dụ `Tiết kiệm điện`.
4. Bot gọi API và hiển thị ba card gồm nhãn lựa chọn, giá, điểm mock, lý do, điểm mạnh và trade-off.

Client gửi lại `context` nhận từ response trước. Với “Không giới hạn”, backend dùng `budget_max=0` làm sentinel nội bộ cho flow stateless.

## Phần đang mock

- Chat advisor dùng rule và regex đơn giản, chưa gọi LLM.
- Match score, label và diễn giải recommendation là deterministic mock.
- Review và checkout không có persistence/giao dịch thật.
- Ảnh dùng placeholder; tồn kho, giá và promotion là dữ liệu demo.
- Chưa có authentication, order/payment, admin hoặc telemetry production.

## Lộ trình AI thật

- **Need extraction:** schema hóa nhu cầu từ hội thoại, xác nhận ambiguity và lưu session.
- **RAG:** truy xuất catalog, tài liệu hãng, chính sách và review có provenance.
- **Ranking engine:** hard filters + weighted scoring/learning-to-rank, giải thích được và test offline.
- **Guardrail:** chỉ khẳng định theo evidence, citation, kiểm tra giá/tồn kho theo thời điểm và fallback khi thiếu dữ liệu.
- **LLM provider:** adapter đa nhà cung cấp, structured output, timeout/retry/cost controls và evaluation.
