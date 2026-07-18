# Policy Vector Database với PostgreSQL/pgvector

Module `apps/api/src/rag` tạo chỉ mục truy hồi từ các file Markdown trong `data/policy`.
Vector được lưu trong PostgreSQL bằng extension `pgvector`; cosine search và HNSW index đều chạy
ở database server.

## Thành phần

- `markdown.py`: đọc UTF-8, lấy cây heading và chia chunk có overlap.
- `embeddings.py`: hashing embedding offline 384 chiều, không cần API key/GPU.
- `pgvector_store.py`: transaction ingest, cột `vector(384)`, cosine `<=>` và HNSW index.
- `pipeline.py`: ingest tăng dần theo SHA-256 và xóa tài liệu nguồn không còn tồn tại.
- `memory_store.py`: test double cho unit test, không được dùng làm production storage.
- Alembic revision `20260718_0003`: cài extension và tạo schema `policy_rag`.

## Khởi động PostgreSQL pgvector

Khi cần PostgreSQL local, Docker Compose dùng image `pgvector/pgvector:pg16` qua profile
`local-db`:

```powershell
docker compose --profile local-db up -d postgres
docker compose run --rm api alembic upgrade head
```

Database mặc định khi chạy script từ máy host:

```text
postgresql://needwise:needwise@localhost:5432/needwise
```

Có thể cấu hình bằng biến môi trường:

```powershell
$env:POLICY_DATABASE_URL = "postgresql://needwise:needwise@localhost:5432/needwise"
$env:POLICY_VECTOR_SCHEMA = "policy_rag"
```

`DATABASE_URL` được dùng làm fallback nếu `POLICY_DATABASE_URL` không được khai báo. URL dạng
SQLAlchemy `postgresql+psycopg://...` cũng được hỗ trợ. Hai script ở repository root tự động đọc
file `.env`; không cần export URL thủ công.

Với Neon, chỉ cần đặt URL có `sslmode=require` trong `.env` rồi chạy `docker compose up -d api`.
API không phụ thuộc hoặc tự khởi động service PostgreSQL local.

## Build và search thủ công

Từ repository root:

```powershell
python scripts/build_policy_vector_db.py --force
python scripts/search_policy_vector_db.py "đổi trả sản phẩm lỗi trong bao lâu" --limit 3
```

`--force` xóa và tạo lại đúng schema đã chọn. Những lần ingest tiếp theo không cần `--force`:

```powershell
python scripts/build_policy_vector_db.py
```

CLI module tương đương:

```powershell
cd apps/api
python -m src.rag.cli build --source ../../data/policy
python -m src.rag.cli search "chính sách bảo hành"
python -m src.rag.cli stats
```

## Test tự động

Unit test không yêu cầu PostgreSQL:

```powershell
cd apps/api
pytest tests/test_policy_vector.py -q
ruff check src/rag tests/test_policy_vector.py tests/test_policy_pgvector_integration.py
mypy src/rag
```

Integration test thật với pgvector:

```powershell
$env:POLICY_TEST_DATABASE_URL = "postgresql://needwise:needwise@localhost:5432/needwise"
pytest tests/test_policy_pgvector_integration.py -q
```

Integration test chỉ thao tác schema `policy_rag_test` và rebuild schema này trước khi chạy.

## Kiểm tra trực tiếp bằng SQL

```powershell
docker compose exec postgres psql -U needwise -d needwise -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
docker compose exec postgres psql -U needwise -d needwise -c "SELECT COUNT(*) AS documents FROM policy_rag.documents;"
docker compose exec postgres psql -U needwise -d needwise -c "SELECT COUNT(*) AS chunks FROM policy_rag.chunks;"
docker compose exec postgres psql -U needwise -d needwise -c "SELECT indexname FROM pg_indexes WHERE schemaname = 'policy_rag';"
```

## Ghi chú migration từ SQLite

File `data/vector/policies.sqlite3` cũ không còn được đọc. Không cần chuyển đổi binary vector cũ;
hãy chạy build với `--force` để tạo lại embedding trực tiếp từ nguồn Markdown. PostgreSQL là nguồn
lưu trữ duy nhất của pipeline production sau thay đổi này.
