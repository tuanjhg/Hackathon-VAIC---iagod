# NeedWise Copilot

## Import catalog CSV vào PostgreSQL

Script [`scripts/import_catalog.py`](scripts/import_catalog.py) đọc 14 file CSV, tự nhận diện
encoding/delimiter/header, chuẩn hóa cột, suy luận schema và import mỗi ngành hàng vào một
table riêng. Chế độ mặc định là `append`, vì vậy không xóa dữ liệu cũ và tự bỏ qua bản ghi
đã có cùng SHA-256 hash. Python yêu cầu phiên bản 3.11 trở lên.

### 1. Tạo virtual environment và cài dependency

PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows CMD:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Cấu hình `.env`

Sao chép `.env.example` thành `.env`, rồi thay credential mẫu. Script ưu tiên
`DATABASE_URL`:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/product_catalog
CSV_DATA_DIR=./data
IMPORT_BATCH_SIZE=500
```

Nếu không khai báo `DATABASE_URL`, phải khai báo đủ `POSTGRES_HOST`, `POSTGRES_PORT`,
`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`. Không commit `.env`. Script không
ghi password hoặc connection string đầy đủ vào log.

Khi chạy importer từ máy host với PostgreSQL trong Docker Compose, dùng host `localhost`.
Container API hiện tại có thể tiếp tục dùng URL `postgresql+psycopg://...@postgres:5432/...`;
importer chấp nhận URL đó và dùng driver `psycopg2` cho riêng tiến trình import.

### 3. Đặt file và sửa mapping

Có thể đặt 14 file trực tiếp trong thư mục được cấu hình bởi `CSV_DATA_DIR`, hoặc giữ cấu
trúc repo hiện tại:

```text
data/realdata/raw/clean/
├── tu_lanh.csv
├── may_lanh.csv
├── may_giat.csv
├── may_say.csv
├── may_rua_chen.csv
├── tu_mat_dong.csv
├── may_nuoc_nong.csv
├── micro_karaoke.csv
├── micro_thu_am.csv
├── dong_ho_tm.csv
├── pc_de_ban.csv
├── man_hinh.csv
├── may_in.csv
└── may_tinh_bang.csv
```

Nếu tên file thực tế khác, sửa hằng `CATEGORIES` ở đầu
`scripts/import_catalog.py`; mỗi phần tử chứa tên ngành hàng, tên table, tên file và số dòng
kỳ vọng. Đường dẫn Unicode/tiếng Việt được hỗ trợ qua `pathlib` và file được giữ ở Unicode.

### 4. Chạy import

Import toàn bộ ở chế độ an toàn mặc định:

```powershell
python scripts/import_catalog.py --all --mode append
```

Import riêng một ngành hàng:

```powershell
python scripts/import_catalog.py --category refrigerators --mode append
```

Các mode:

- `append`: giữ dữ liệu cũ, tự thêm cột CSV mới và chỉ insert hash chưa tồn tại.
- `replace`: `DROP TABLE`, tạo lại schema và import lại; chỉ dùng khi chủ động muốn xóa table.
- `truncate`: giữ schema, `TRUNCATE ... RESTART IDENTITY`, rồi import lại.

Ví dụ import lại có chủ đích:

```powershell
python scripts/import_catalog.py --category refrigerators --mode truncate
python scripts/import_catalog.py --all --mode replace
```

Mỗi table chạy trong transaction độc lập. Nếu một file lỗi thì transaction đó rollback,
lỗi được ghi lại và các ngành hàng còn lại vẫn tiếp tục. Log UTF-8 nằm tại
`logs/import_catalog.log`.

### 5. Kiểm tra PostgreSQL

Chạy file kiểm tra đầy đủ bằng `psql`:

```powershell
psql -h localhost -U postgres -d product_catalog -f sql/verify_import.sql
```

Một số câu lệnh kiểm tra nhanh:

```sql
SELECT COUNT(*) FROM refrigerators;
SELECT COUNT(*) FROM tablets;
SELECT data_hash, COUNT(*)
FROM refrigerators
GROUP BY data_hash
HAVING COUNT(*) > 1;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'refrigerators'
ORDER BY ordinal_position;
```

Để rollback một lần import đang chạy, PostgreSQL tự rollback table bị lỗi. Với lần import đã
commit, chạy lại bằng `--mode truncate` hoặc `--mode replace` chỉ sau khi đã sao lưu và xác
nhận muốn xóa dữ liệu. Chế độ `append` luôn là lựa chọn an toàn để chạy lại.

### 6. Luồng xử lý và chẩn đoán

Với từng file, script thử lần lượt `utf-8-sig`, `utf-8`, `cp1258`, `windows-1252`; nhận diện
`,`, `;` hoặc tab; chuẩn hóa header thành `snake_case`; đổi các biểu diễn rỗng thành SQL
`NULL`; bỏ cột/dòng hoàn toàn rỗng; suy luận kiểu bảo thủ; tạo hash từ record đã chuẩn hóa;
tạo/evolve table; bulk insert theo batch; cuối cùng đối chiếu số dòng trong DB. Log ghi tỷ lệ
dòng rỗng, tỷ lệ NULL theo cột, header đổi tên, cột `TEXT`, hash trùng và lỗi chi tiết.

Các lỗi thường gặp:

- `Thiếu cấu hình PostgreSQL`: điền `DATABASE_URL` hoặc đủ năm biến `POSTGRES_*`.
- `Không thể kết nối PostgreSQL`: kiểm tra service, host/port, firewall, database và quyền user.
- `FILE MISSING`: kiểm tra `CSV_DATA_DIR` và tên file trong `CATEGORIES`.
- Lỗi encoding/delimiter: lưu lại CSV bằng UTF-8 có BOM hoặc một trong ba delimiter hỗ trợ;
  kiểm tra dấu nháy kép chưa đóng và số field không đồng nhất.
- `permission denied`: cấp quyền `CREATE`, `ALTER`, `INSERT`, `SELECT`; mode destructive cần
  thêm quyền `DROP` hoặc `TRUNCATE`.
- `duplicate key` khi tạo unique index: table cũ đã có hash trùng; sao lưu và dọn duplicate
  trước khi chạy lại. Script không tự xóa dữ liệu cũ.
- Sai số lượng: xem cột `Status`, cảnh báo console và `logs/import_catalog.log`; kiểm tra dòng
  rỗng, hash trùng, file bị thiếu hoặc dữ liệu cũ khác hash trong mode `append`.
- Dữ liệu mới dài hơn schema `VARCHAR` cũ hoặc không phù hợp kiểu cũ: dùng `ALTER TABLE`
  có kiểm soát, hoặc sau khi sao lưu dùng `--mode replace` để suy luận lại schema.

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
├── data/realdata/raw/clean/  # 14 catalog CSV thực tế
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

Compose đợi PostgreSQL healthy, chạy migration, đồng bộ catalog thực tế idempotent rồi khởi động API. Truy cập:

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

## Migration và đồng bộ catalog

Khi stack đang chạy:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m src.seed.sync_catalog_products
```

Hoặc dùng container one-off: `make migrate` và `make seed`. Lệnh đồng bộ đọc bảng
`air_conditioners` đã import, upsert 1.039 SKU thực tế và loại các SKU demo cũ trong ngành
hàng máy lạnh. Lệnh có thể chạy lặp lại mà không nhân bản dữ liệu.

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
python -m src.seed.sync_catalog_products
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
