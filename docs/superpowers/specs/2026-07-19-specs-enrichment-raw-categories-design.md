# Thiết kế: Làm giàu `specs_json` cho 9 ngành `specs_raw` — mở khoá xương sống ranking

- **Ngày:** 2026-07-19
- **Nhánh:** `feat/business-response-contract`
- **Tiền đề:** [Preference-spine advisory](2026-07-19-preference-spine-advisory-design.md) đã xong — xương sống ranking chạy đủ cho 5 ngành có `specs` parse. Spec này mở khoá 9 ngành còn lại.

## Quyết định đã chốt

1. **Cách làm:** *tái dùng parser sẵn có*, làm giàu `Product.specs_json` — **không** viết parser mới, **không** đổi kiến trúc dữ liệu.
2. **Phạm vi:** cả 9 ngành `specs_raw` (`tu_mat_dong, man_hinh, may_in, may_nuoc_nong, may_say, may_tinh_bang, micro_karaoke, micro_thu_am, pc_de_ban`).
3. **Thành thật về độ thưa:** parser mở khoá ranking *ở nơi có dữ liệu*; nơi thiếu vẫn dùng hiển thị trung thực (đã có ở đợt trước).

## 1. Bối cảnh (đã khảo sát, xác nhận trên code + data)

Repo có **hai hệ catalog song song**:

- **Luồng chat đang chạy:** `catalog_search` + retriever đọc `Product.specs_json`
  (`src/tools/catalog_search.py`, `src/services/advisor_chat_service.py:194`). Cột này do
  `src/seed/seed_realdata.py` nạp từ `data/realdata/processed/*.json` (script
  `scripts/etl_btc_catalog.py`) — **chỉ parse máy lạnh + tủ lạnh**; 9 ngành kia `specs = {display_name}`.
  `sync_catalog_products` set `normalized_specs = {}`.
- **Hệ importer hybrid (đã có, KHÔNG trong luồng chat):** `src/importers/category_registry.py` +
  `src/importers/csv_importer.py` + `src/importers/normalizers/common.py` đã khai báo, cho **cả 14
  ngành**, ánh xạ cột thô → key kiểu số/bool + hàm parse (`SOURCE_COLUMNS`, `_parser_for`). Nhưng nó
  ghi vào bảng `ProductSpec.normalized_specs` (chat không đọc) và không nằm trong chuỗi seed live.

⇒ **9 ngành thật sự thiếu specs parse trong dữ liệu chat, nhưng *tri thức parse* đã có sẵn.** Việc cần
làm: chạy parse đó vào `Product.specs_json` + khai báo `ranking_criteria`.

## 2. Mục tiêu & phi mục tiêu

**Mục tiêu:** với mỗi ngành trong 9 (ở nơi dữ liệu cho phép), một phiên tư vấn đạt: sản phẩm hợp
nhu cầu nổi lên, mỗi card một lợi ích thật + một đánh đổi thật — như 5 ngành đã parse.

**Phi mục tiêu:**
- Không viết parser mới (tái dùng `normalize_product_row` + `category_registry` + `common.py`).
- Không chuyển chat sang đọc `normalized_specs`, không đưa `csv_importer` vào seed live, không migration.
- Không đụng 5 ngành đang chạy (chỉ enrich 9 ngành raw).
- Không thêm `target` (per-person) cho 9 ngành — chúng không có công thức nhu cầu đáng tin (khác tủ lạnh);
  chỉ dùng `higher_better`/`lower_better`/`boolean_pref`.

## 3. Thiết kế chi tiết

### 3.1. Bước làm giàu (`src/seed/enrich_specs.py`, mới)

- Hàm `enrich_specs(db, clean_csv_dir)`:
  - Với mỗi ngành trong 9 (map `category_key` chat → `CategoryConfig` của registry qua bảng ánh xạ
    khai báo trong module — vì tên khác nhau: `pc_de_ban`↔`desktop_computers`, `man_hinh`↔`computer_monitors`...),
    đọc CSV sạch (`read_csv` từ `data/realdata/raw/clean/<file>.csv`).
  - Mỗi hàng: `normalize_product_row(row, config)` → `typed_values: {key: (config, parsed, raw)}`.
    Lấy **các key kiểu số/bool** (bỏ text/array), **ép giá trị về int/float/bool qua `_json_value`**
    (bắt buộc: `parse_*` trả `Decimal`, mà S5 `_numeric` loại `Decimal`).
  - Khớp sản phẩm DB theo `sku`; **gộp `{key: value}` phẳng vào `product.specs_json`** (giữ nguyên
    `display_name` và các key cũ). Idempotent (chạy lại ghi đè các key parse).
  - Trả về report: số sản phẩm khớp/ngành, số trường parse được/ngành (để in coverage).
- `main()` chạy được độc lập; thêm vào chuỗi seed sau `seed_realdata` (Makefile + prod compose).

### 3.2. `ranking_criteria` cho 9 ngành (`slots/<category>.yaml`)

Chỉ tiêu chí số/bool có ý nghĩa phân biệt (bảng đề xuất; tinh chỉnh theo coverage khi implement):

Bảng dưới đã đối chiếu **coverage thật** (dry-run `normalize_product_row` trên CSV) — chỉ chọn
trường phổ biến, bỏ trường thưa (vd pc_de_ban `cpu_core_count` chỉ 22/405 → bỏ). Bước implement
xác nhận lại coverage từng ngành trước khi chốt.

| Ngành | ranking_criteria (field → direction) |
|---|---|
| pc_de_ban | `ram_gb` higher, `storage_gb` higher, `cpu_base_clock_ghz` higher |
| may_tinh_bang | `ram_gb` higher, `storage_gb` higher, `battery_capacity_mah` higher, `cpu_speed_ghz` higher |
| man_hinh | `resolution_width` higher, `response_time_ms` lower, `brightness_nit` higher |
| may_in | `print_resolution_dpi` higher, `monthly_duty_cycle` higher, `print_speed_ppm` higher |
| may_say | `energy_consumption_kwh` lower, `drying_capacity_kg` higher |
| may_nuoc_nong | `has_booster_pump` boolean_pref, `power_watt` higher |
| tu_mat_dong | `inverter` boolean_pref, `energy_consumption_kwh` lower |
| micro_thu_am | `transmission_distance_meter` higher |
| micro_karaoke | `distortion_percent` lower |

Key trỏ vào `specs.<key>` phẳng khớp `attribute.key` của registry. Không đụng `catalog_field_map`
hiện có (vẫn trỏ `specs_raw.*` để hiển thị/hỏi); `ranking_criteria` là kênh riêng cho ranking.

### 3.3. GLOSSARY + field_label cho key mới

- `s6_generate.GLOSSARY`: thêm renderer tiếng Việt cho mỗi field dùng trong `ranking_criteria`
  (vd `ram_gb` → `f"RAM {v}GB"`, `resolution_width` → `f"độ phân giải ngang {v}px"`,
  `response_time_ms` → `f"thời gian đáp ứng {v}ms"`, `print_speed_ppm` → `f"in {v} trang/phút"`...).
  Không có renderer ⇒ strengths/reason bỏ qua field đó (an toàn), nên đây là điều kiện để card nói
  được lợi ích/đánh đổi.
- `s8_respond._FIELD_LABELS`: thêm nhãn ngắn cho mỗi field (dùng trong câu trade-off "kém hơn về …").

### 3.4. Không đổi S5/S2/S4

S5 đã tổng quát (đợt trước). 9 ngành có `ranking_criteria` ⇒ tự chạy. Không `target` ⇒ không cần
`_need_for_target` mới. S2/S4 không liên quan.

## 4. Kiểm thử & xác minh

- **Enrich (`tests/test_enrich_specs.py`):** với hàng CSV mẫu/ngành, `enrich_specs` ghi đúng key số/bool
  (vd pc_de_ban `ram_gb: 16` là `int`, không `Decimal`); "Không có"/parse lỗi → không ghi key.
- **S5 (`tests/test_s5_ranking.py`):** ngành mẫu (pc_de_ban) với `ranking_criteria`: RAM cao xếp trên
  RAM thấp *ceteris paribus*; sinh trade-off khi có đảo chiều.
- **Slots (`tests/test_slots.py`):** 9 ngành load được `ranking_criteria`; trường trỏ `specs.*` (không `specs_raw.*`).
- **Render (`tests/test_s6_generate.py`):** GLOSSARY render đúng các field mới.
- **End-to-end (`tests/test_chat_advisor.py`):** 1 ngành raw (pc_de_ban) — sau enrich, card có lợi ích/đánh
  đổi khác nhau, không còn câu "chưa đủ dữ liệu".
- **Coverage:** in % sản phẩm/ngành có ≥1 trường parse được; ghi lại (thành thật về ngành vẫn thưa).
- Chạy full suite + ruff + mypy; không hồi quy 5 ngành cũ.

## 5. Rủi ro & giảm thiểu

- **`Decimal` lọt vào specs_json** → ép `_json_value` + test khẳng định kiểu int/float.
- **Sku CSV không khớp DB** → report số khớp; nếu lệch nhiều, kiểm cột sku/nguồn trước khi mở rộng.
- **Ngành dữ liệu quá thưa** (micro, pc field màn hình) → chấp nhận; hiển thị trung thực lo phần thiếu.
- **Hướng tiêu chí sai** (vd "càng lớn càng tốt" không đúng ngữ cảnh) → bảng §3.2 review tay theo coverage;
  chỉ khai báo field có hướng rõ ràng, bỏ field mơ hồ.

## 6. Việc nối tiếp (ngoài phạm vi)

- Hợp nhất hai hệ catalog (ETL processed vs hybrid `normalized_specs`) về một nguồn — nợ kiến trúc, tách riêng.
- `target` right-sizing cho ngành có công thức nhu cầu thật (nếu chuyên gia cấp công thức cho tủ mát/máy nước nóng).
