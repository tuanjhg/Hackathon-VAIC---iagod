# Báo cáo migration Hybrid Relational + JSONB + Typed Facet Index

> Snapshot production/Neon ngày 18/07/2026. Migration head: `20260718_0005`.

## 1. Kết quả

Database catalog đã chuyển sang kiến trúc hybrid mà không xóa dữ liệu cũ:

```text
14 CSV
  → import_batches
  → raw_product_rows (JSONB nguyên bản)
  → categories / brands / products
  → product_specs (raw_specs + normalized_specs)
  → product_offers (lịch sử giá/quà)
  → attribute_definitions
  → product_attribute_values (typed facet index)
```

Policy RAG được migrate song song:

```text
policy_rag.policy_documents (UUID)
  → policy_rag.policy_chunks (UUID + vector(384))
```

Các bảng legacy `prices`, `promotions`, `inventory`, `catalog_products`, 14 bảng raw và các bảng RAG cũ vẫn được giữ để đối chiếu/rollback. Không có bảng dữ liệu cũ nào bị drop.

## 2. Schema trước và sau

### Trước migration

- `categories`: chỉ có `id`, `name`, `slug`.
- `products`: brand dạng chuỗi; dữ liệu hiển thị và `specifications` JSONB cùng nằm trên read model.
- `product_specs`: cột cố định dành cho máy lạnh.
- `prices`: một giá hiện tại trên mỗi product.
- `promotions`: một chuỗi khuyến mãi trên mỗi product.
- Không có batch lineage, brand dimension, offer history hoặc typed facet index.
- RAG dùng `source_path` và chunk ID dạng text làm primary key.

### Sau migration

| Lớp | Bảng | Vai trò |
|---|---|---|
| Lineage | `import_batches` | Theo dõi file, checksum, trạng thái và số dòng |
| Lineage | `raw_product_rows` | Giữ JSONB nguyên bản và lỗi theo dòng |
| Master | `categories` | 14 ngành hàng với code ổn định |
| Master | `brands` | Brand nội bộ và `normalized_name` duy nhất |
| Core | `products` | SKU, web ID, model, category, brand, trạng thái |
| Specs | `product_specs` | Raw JSONB, normalized JSONB và search text |
| Commerce | `product_offers` | Lịch sử giá/quà, tối đa một current offer |
| Facet metadata | `attribute_definitions` | Kiểu, đơn vị, group, filterable/comparable |
| Facet data | `product_attribute_values` | Giá trị text/number/boolean/JSON đã typed |
| RAG | `policy_rag.policy_documents` | UUID document và metadata JSONB |
| RAG | `policy_rag.policy_chunks` | UUID chunk, metadata, embedding và model |

## 3. Migration đã chạy

| Revision | Nội dung |
|---|---|
| `20260718_0004` | Thêm JSONB tương thích cho catalog đa ngành |
| `20260718_0005` | Hybrid catalog, typed facets, import lineage, offer history, UUID policy RAG, `pgcrypto` |

`20260718_0005` thực hiện theo thứ tự:

1. Bật `vector` và `pgcrypto`.
2. Widen ID/FK hiện hữu sang `BIGINT`.
3. Alter `categories` và seed code ổn định.
4. Tạo/backfill `brands`.
5. Bổ sung trường relational cho `products`.
6. Chuyển `product_specs.product_id` thành primary key và backfill raw specs.
7. Tạo `product_offers`, migrate giá/quà từ `prices`/`promotions`.
8. Tạo import lineage và typed facet tables.
9. Tạo policy tables UUID và copy đủ document/chunk/vector cũ.
10. Tạo B-tree, partial unique, GIN, full-text và HNSW indexes.

Downgrade có thể làm mất dữ liệu chỉ tồn tại trong các bảng mới. Migration không tự thu hẹp BIGINT về INTEGER vì ID tương lai có thể overflow; phải backup trước khi downgrade.

## 4. Mapping dữ liệu

| CSV | Đích |
|---|---|
| `sku` | `products.sku` |
| `productidweb` | `products.product_web_id`; bản gốc luôn có trong `source_data` |
| `model_code` | `products.model_code` |
| `category_code` | `categories.code` theo registry chuẩn |
| `brand` | `brands` + `products.brand_id` |
| `brand_id` nguồn | `brands.source_brand_id`, không dùng làm PK |
| `gia_goc` | `product_offers.original_price` |
| `gia_khuyen_mai` | `product_offers.sale_price` |
| `khuyen_mai_qua` | `product_offers.gifts[]` |
| Các cột còn lại | `product_specs.raw_specs` |
| Giá trị parse thành công | `product_specs.normalized_specs` |
| Thuộc tính filter/compare | `product_attribute_values` |

Có 1.448 nhóm `productidweb` bị trùng giữa các SKU trong nguồn. Chỉ web ID duy nhất toàn catalog được đưa vào cột UNIQUE; web ID trùng vẫn được bảo toàn ở `products.source_data.raw_product_web_id`.

Kiểm tra dữ liệu cho thấy 1.199 nhóm trùng hợp lệ theo `(category_id, brand_id, model_code)`, vì vậy **không tạo** unique constraint ba cột này.

## 5. Row count sau migration

| Bảng/lớp | Số dòng |
|---|---:|
| `categories` | 14 |
| `brands` | 143 |
| `products` | 8.746 |
| `product_specs` | 8.746 |
| `product_offers` (toàn bộ lịch sử) | 17.462 |
| Current `product_offers` | 8.746 |
| `attribute_definitions` | 152 |
| `product_attribute_values` | 69.496 |
| `product_specs` có normalized data | 7.698 |
| `import_batches` | 46 |
| `raw_product_rows` | 26.386 |
| `policy_rag.policy_documents` | 6 |
| `policy_rag.policy_chunks` | 66 |

`product_offers` giữ lịch sử. Tổng offer có thể lớn hơn 8.746; partial unique index chỉ cho phép tối đa một dòng `is_current = TRUE` trên mỗi product.

### Batch production gần nhất

| Category | Total | Success | Failed |
|---|---:|---:|---:|
| `refrigerators` | 1.692 | 1.692 | 0 |
| `air_conditioners` | 1.039 | 1.039 | 0 |
| `washing_machines` | 1.337 | 1.337 | 0 |
| `clothes_dryers` | 107 | 107 | 0 |
| `dishwashers` | 134 | 134 | 0 |
| `coolers_freezers` | 222 | 222 | 0 |
| `water_heaters` | 319 | 319 | 0 |
| `karaoke_microphones` | 37 | 37 | 0 |
| `phone_recording_microphones` | 33 | 33 | 0 |
| `smartwatches` | 1.336 | 1.336 | 0 |
| `desktop_computers` | 405 | 405 | 0 |
| `computer_monitors` | 469 | 469 | 0 |
| `printers` | 147 | 147 | 0 |
| `tablets` | 1.469 | 1.469 | 0 |
| **TOTAL** | **8.746** | **8.746** | **0** |

## 6. Thuộc tính chưa normalize hoàn toàn

Pipeline không ghi typed value nếu không chắc chắn. Giá trị gốc vẫn có trong `raw_specs` và warning theo file/dòng nằm ở `logs/hybrid_import_final2.log`.

Các nhóm còn cần override tốt hơn gồm:

- Dung tích/điện năng có chuỗi “Hãng không công bố”.
- Tốc độ CPU gồm nhiều clock hoặc turbo profile trong một chuỗi.
- Thời gian pin có điều kiện sử dụng thay vì một số tuyệt đối.
- Dung lượng GPU dùng chung RAM, không có số GB độc lập.
- Nhiệt độ/áp suất dạng nhiều mức hoặc khoảng phức tạp.
- Một số kích thước gộp `dài × rộng × cao` trong một cột.

Parser refinement đã giảm warning từ 8.270 xuống 3.553 bằng cách xử lý đúng eSIM/GPS/Wi-Fi, boolean mô tả, BTU có dấu phân cách, kích thước/độ phân giải và thời lượng năm/giờ/phút.

| Category | Sản phẩm có normalized data | Attribute warning cuối |
|---|---:|---:|
| `refrigerators` | 1.554/1.692 | 953 |
| `air_conditioners` | 1.031/1.039 | 198 |
| `washing_machines` | 1.036/1.337 | 56 |
| `clothes_dryers` | 107/107 | 10 |
| `dishwashers` | 133/134 | 3 |
| `coolers_freezers` | 221/222 | 292 |
| `water_heaters` | 313/319 | 389 |
| `karaoke_microphones` | 31/37 | 5 |
| `phone_recording_microphones` | 28/33 | 21 |
| `smartwatches` | 842/1.336 | 634 |
| `desktop_computers` | 401/405 | 460 |
| `computer_monitors` | 428/469 | 21 |
| `printers` | 137/147 | 20 |
| `tablets` | 1.436/1.469 | 491 |

Warning là số thuộc tính không parse được, không phải số dòng import lỗi. Kiểm tra integrity sau import: 0 SKU trùng, 0 product inactive, 0 product có nhiều current offer; 18 product không có brand vì nguồn để trống và `brand_id` được phép NULL.

## 7. Index và constraint quan trọng

- UNIQUE `products.sku`.
- Partial UNIQUE `products.product_web_id IS NOT NULL`.
- Index `products(category_id)`, `brand_id`, `model_code`, `status`, `(category_id, brand_id)`.
- GIN `product_specs.raw_specs`.
- GIN `product_specs.normalized_specs jsonb_path_ops`.
- Full-text GIN trên `product_specs.search_text`.
- Partial UNIQUE current offer trên `product_offers(product_id)`.
- Typed partial indexes `(attribute_id, value_number/text/boolean)`.
- GIN `product_attribute_values.value_json`.
- HNSW cosine trên `policy_rag.policy_chunks.embedding`.
- Cascade batch → raw rows, product → specs/offers/facets, policy document → chunks.

## 8. API

Endpoints:

```text
GET  /api/v1/health/db
GET  /api/v1/categories
GET  /api/v1/products
GET  /api/v1/products/{id-or-slug}
GET  /api/v1/products/compare?ids=1&ids=2
POST /api/v1/products/search
```

Ví dụ typed search:

```http
POST /api/v1/products/search
Content-Type: application/json

{
  "category_code": "refrigerators",
  "price_max": 15000000,
  "filters": {
    "total_capacity_liter": {"gte": 300, "lte": 500},
    "inverter": {"eq": true}
  },
  "sort": [{"field": "sale_price", "direction": "asc"}],
  "limit": 20
}
```

Kết quả kiểm tra thật trên Neon:

```json
{
  "total": 56,
  "limit": 20,
  "offset": 0,
  "items": ["... product objects ..."]
}
```

Attribute key được đối chiếu với `attribute_definitions`. Key không tồn tại hoặc không filterable trả HTTP 422; client không thể truyền table name hay SQL fragment.

## 9. Lệnh chạy

Từ repository root:

```bash
pip install -r requirements.txt
cd apps/api
alembic upgrade head
python -m app.db.seed
python -m app.importers.csv_importer --directory ../../data/realdata/raw/clean --update-existing
pytest
uvicorn app.main:app --reload
```

Nếu CSV được mount/copy vào `data/products` của working directory:

```bash
python -m app.importers.csv_importer --directory data/products
```

Dry-run và import một file:

```bash
python -m app.importers.csv_importer --directory ../../data/realdata/raw/clean --dry-run
python -m app.importers.csv_importer --category refrigerators --file ../../data/realdata/raw/clean/tu_lanh.csv --batch-size 300 --update-existing
```

## 10. Test đã chạy

- Parser: giá Việt Nam, lít, cm→mm, kg, m², range, boolean, list, null.
- Import: CSV mẫu, lỗi theo dòng, idempotency, Numeric price, gifts JSONB, raw specs, typed facets.
- Query: tủ lạnh theo dung tích/inverter, máy lạnh theo diện tích, máy giặt theo kg, tablet theo RAM/giá, reject facet lạ.
- API: health DB, list/detail, detail theo ID, compare và dynamic search.
- RAG: idempotency, chunk metadata, search; PostgreSQL integration test chạy khi có `POLICY_TEST_DATABASE_URL`.
- Kết quả local + Neon schema integration: **33 passed, 1 skipped**; Web: **4 passed**, production build thành công.

## 11. Rủi ro và công việc còn lại

- Các bảng legacy chưa drop có chủ ý. Chỉ tạo cleanup migration sau một chu kỳ production verification và backup.
- 1.048 sản phẩm hiện chưa có normalized field vì nguồn chỉ có trường chung hoặc giá trị không đủ chắc chắn để tạo typed value; toàn bộ thông số gốc vẫn nằm trong `raw_specs`.
- `inventory` vẫn là compatibility data, chưa thuộc MVP import mới.
- Full-text `search_text` đã có index; endpoint search text nâng cao chưa được tách riêng.
- Cần theo dõi kích thước offer history và có retention policy nếu giá cập nhật thường xuyên.
- Integration test pgvector cần database test riêng qua `POLICY_TEST_DATABASE_URL`.

## 12. File triển khai chính

- Migration: `apps/api/alembic/versions/20260718_0004_multicategory_catalog.py`, `apps/api/alembic/versions/20260718_0005_hybrid_catalog.py`.
- Models: `apps/api/src/models/hybrid_catalog.py`, `category.py`, `product.py`, `price.py`, `promotion.py`, `inventory.py`, `__init__.py`.
- Import/normalize: `apps/api/src/importers/csv_importer.py`, `category_registry.py`, `normalizers/common.py`.
- Seed và entrypoint tương thích câu lệnh yêu cầu: `apps/api/src/db/seed.py`, `apps/api/app/db/seed.py`, `apps/api/app/importers/csv_importer.py`, `apps/api/app/main.py`.
- API: `apps/api/src/api/v1/health.py`, `products.py`, `repositories/product_repository.py`, `services/product_service.py`, `schemas/product.py`.
- RAG: `apps/api/src/rag/pgvector_store.py`, `apps/api/src/rag/cli.py`.
- Tests: `test_normalizers.py`, `test_hybrid_import.py`, `test_hybrid_schema.py`, `test_hybrid_postgres_integration.py`, `test_typed_facet_search.py` và các test API/catalog hiện hữu được cập nhật.
- Runtime/docs: `.env.example`, `requirements.txt`, `apps/api/pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `README.md`, `docs/database.md`.
- Web catalog: `apps/web/app/products/page.tsx`, `ProductCard.tsx`, `ProductDetail.tsx`, `ProductFilter.tsx`, `lib/api.ts`, type và fixture liên quan.
