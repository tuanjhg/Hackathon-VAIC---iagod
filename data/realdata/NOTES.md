# Ghi chú xử lý catalog BTC (Điện Máy Xanh)

> Nguồn: Google Sheet `Spec_cate_gia.xlsx` do user cung cấp 17/07. **Toàn bộ thư mục `data/btc/` bị gitignore — không lên repo public (NDA, brief E2).**

## Pipeline

1. `raw/full_workbook.xlsx` — tải nguyên workbook qua `export?format=xlsx` (KHÔNG dùng `gviz/tq?sheet=` — 4/14 sheet nhỏ bị lỗi header dính data khi query qua gviz, xem mục Sự cố bên dưới)
2. `raw/clean/*.csv` — xuất từng tab ra CSV UTF-8 sạch bằng `openpyxl`
3. `raw/profile_report.md` — profile toàn bộ 14 ngành: null-rate, distinct, mẫu giá trị mỗi cột (script: `scripts/profile_btc_catalog.py`)
4. `processed/*.json` — ETL sạch (script: `scripts/etl_btc_catalog.py`): universal clean mọi ngành + parser structured cho 2 ngành ưu tiên (máy lạnh, tủ lạnh)
5. `processed/_demo_ready_priority.json` — subset chỉ gồm SP CÓ GIÁ của máy lạnh/tủ lạnh, sẵn sàng seed demo

## Phát hiện quan trọng (ảnh hưởng thiết kế)

| # | Phát hiện | Hệ quả |
|---|---|---|
| 1 | **8.746 sản phẩm / 14 ngành hàng** — lớn hơn nhiều so với giả định mock ~100 SKU trong `dmx-data-eval-roi-plan.md` D1 | Không cần tự sinh mock catalog nữa cho 2 ngành ưu tiên; D1 "bản bẩn 20%" cũng dư thừa — data thật đã đủ bẩn (xem #4) |
| 2 | **Danh mục thực tế KHÔNG có điện thoại/laptop** — thay vào đó: tủ lạnh, máy lạnh, máy giặt, máy sấy, máy rửa chén, tủ mát/đông, máy nước nóng, micro karaoke, micro thu âm, đồng hồ thông minh, PC bàn, màn hình, máy in, máy tính bảng | Toàn bộ ví dụ trong workflow/guardrail/innovation docs dùng "điện thoại, laptop" (theo ví dụ brief C2, không phải cam kết) cần **đọc là ví dụ minh họa, không phải danh mục cứng**; slot schema H2 (máy lạnh/tủ lạnh/điện thoại/laptop) vẫn đúng cho 2 ngành có trong data, 2 ngành kia (điện thoại, laptop) không có data thật — nên **ưu tiên demo bằng máy lạnh + tủ lạnh**, nói rõ kiến trúc generalize được khi hỏi về điện thoại/laptop |
| 3 | **`sku` là khóa duy nhất thật, `model_code` KHÔNG duy nhất** (VD: model_code 181142 lặp 3 lần với 3 sku/giá khác nhau — biến thể cùng dòng máy) | Toàn bộ thiết kế dùng `sku` làm primary key sản phẩm, không dùng `model_code` |
| 4 | **Không có cột "tên sản phẩm"** ở bất kỳ ngành hàng nào — chỉ có `model_code` (mã nội bộ, không phải tên thương mại như "FTKB25") | `display_name` phải tự dựng từ brand + spec nổi bật (vd "Panasonic Inverter 24000 BTU") — ETL đã làm cho máy lạnh/tủ lạnh; các ngành khác tạm dùng "{brand} {ngành hàng} (mã {model_code})" chờ Category Profile Compiler |
| 5 | **Giá thiếu diện rộng**: máy lạnh chỉ 25.9% SP có giá, tủ lạnh 14.9%, các ngành khác 13–73% | Xác nhận đúng thiết kế: catalog tĩnh (spec) tách biệt Price/Promotion API (brief E1 liệt kê riêng) — SP không giá **không phải lỗi ETL**, là tín hiệu "giá sống ở hệ thống khác". Demo dùng subset có giá; **SP không giá là bộ test case thật cho guardrail honesty**, thay thế phần D5 red-team phải tự bịa trước đây |
| 6 | Nhiều field kết hợp nhiều số liệu trong 1 cell dạng text: `"Dàn lạnh: 45/34/29 dB - Dàn nóng: 51 dB"`, `"5 sao (Hiệu suất năng lượng 6.23)"`, `"Từ 30 - 40m² (từ 80 đến 120m³)"` | Đã viết parser regex cho máy lạnh/tủ lạnh (`scripts/etl_btc_catalog.py`); các ngành khác giữ nguyên trong `specs_raw` — đúng input shape mà Category Profile Compiler (ADR A7) được thiết kế để xử lý |
| 7 | Nhiều cột null gần 100% (`Khối lượng máy` ở máy lạnh, `Cao/Dài phụ kiện chính 2`...) | ETL tự động drop cột rỗng hoàn toàn theo từng ngành, không cần cấu hình tay |

## Sự cố kỹ thuật khi tải (để lần sau khỏi debug lại)

`gviz/tq?tqx=out:csv&sheet=<tên>` bị lỗi với 4 sheet nhỏ (Máy giặt, Máy sấy, Máy rửa chén, Micro karaoke): header row bị "dính" giá trị dòng đầu vào cùng 1 cell (`"model_code 180722"` thay vì tách riêng). Nguyên nhân nghi do query engine gviz tự suy luận kiểu dữ liệu sai với sheet nhỏ. **Fix**: dùng `export?format=xlsx` tải nguyên workbook rồi đọc bằng `openpyxl` — export "thô" theo grid gốc, không qua query engine, không bị lỗi này trên bất kỳ sheet nào.

## Việc còn mở (chưa làm trong lượt này)

- **Chưa parse structured cho 12/14 ngành còn lại** — chỉ máy lạnh + tủ lạnh có parser đầy đủ (đúng ưu tiên master plan). Category Profile Compiler (ADR A7) là hướng đúng để mở rộng, chưa build.
- **Chưa wire vào DB/API**: `apps/api/src/models/product.py` hiện có `ProductSpec` hardcode cho riêng máy lạnh (capacity_btu, horsepower...) — cần bảng tương tự cho tủ lạnh hoặc tổng quát hóa specs thành JSONB trước khi seed vào Postgres thật. Output ETL hiện là JSON độc lập, chưa chạm vào `scripts/seed_data.py`.
- **Chưa có Policy & FAQ, Customer Need Scenarios** — mới chỉ có Product Catalog trong 3 bộ data E1 liệt kê.
- **Chưa xin/kiểm tra Stock/Inventory data** — sheet này không có cột tồn kho; brief nói đây là API riêng, sẽ cần mock hoặc chờ BTC cấp thêm.
