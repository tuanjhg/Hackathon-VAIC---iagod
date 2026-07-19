# Thiết kế: "Xương sống ưu tiên" cho luồng tư vấn — để khách hiểu được trade-off & lợi ích

- **Ngày:** 2026-07-19
- **Nhánh:** `feat/business-response-contract`

## Quyết định đã chốt (ngã rẽ chính)

1. **Phạm vi:** tổng quát cho mọi ngành (cơ chế), sửa cả gốc (extraction/ranking) lẫn hiển thị.
2. **"Tiết kiệm điện" = ưu tiên mềm**, không lọc cứng — để trade-off inverter vẫn hiển thị được.
3. **Xử lý 9 ngành chỉ có `specs_raw`:** xương sống đầy đủ cho **5 ngành có specs đã parse**
   (tủ lạnh + 4 ngành `uu_tien`); **9 ngành raw** chỉ nhận **hiển thị trung thực**; **hoãn parser**
   (Category Profile Compiler ADR A7 tách thành dự án riêng).

## 1. Bối cảnh & vấn đề

Phiên tư vấn tủ lạnh thật (khách: nhà 3 người, ~15 triệu, ngăn đá dưới, **cần tiết kiệm điện**):
hệ thống gợi ý 2 máy LG **không inverter** ở nhãn "Phù hợp nhất", máy Hisense **inverter** (đúng thứ
khách cần) bị đẩy xuống #3. Cả 3 card "100% điểm tương đối", trade-off và lợi ích là **câu mẫu giống
hệt nhau**, và "không phải inverter" bị hiển thị như một **ưu điểm**. Khách không hiểu được đánh đổi
và lợi ích phù hợp.

Ưu tiên của khách **rơi rụng qua 3 tầng**:

1. **S2 (trích xuất) — không bắt được ưu tiên.** `catalog_search._direct_conditions`
   (`src/tools/catalog_search.py:230-248`) *có* lọc cứng slot boolean `inverter`. Máy không-inverter
   vẫn xuất hiện ⇒ `inverter=True` chưa từng được set. Overlay xác định của S2
   (`src/pipeline/s2_extract.py:564-568`) chỉ set `inverter` khi text chứa đúng chữ *"inverter"*;
   cụm *"tiết kiệm điện"* chỉ có đường dẫn tới enum value `tiet_kiem_dien` (`s2_extract.py:416`) —
   tủ lạnh không có slot enum nào nhận value đó. Nên "tiết kiệm điện" của tủ lạnh không rơi vào slot nào.
2. **S5 (chấm điểm) — không chấm ưu tiên.** `rank_candidates` (`src/pipeline/s5_ranking.py:443-485`)
   lấy `criterion_fields` **chỉ từ slot `uu_tien`** (`s5_ranking.py:456-457`), mà `uu_tien` chỉ có ở
   4/14 ngành. Tủ lạnh và 9 ngành khác không có ⇒ `criterion_fields` rỗng ⇒ không tiêu chí nào được chấm.
3. **Hiển thị — mất chỗ dựa nên bịa/nhiễu** (`src/services/advisor_chat_service.py`):
   - `_match_scores` (dòng 364-375) trả 100% cho tất cả.
   - `_trade_off_text` (dòng 378-404) rơi xuống nhánh cuối "Nên đối chiếu thêm bảo hành..." cho cả 3.
   - `reason` (dòng 425) rơi về mặc định "Phù hợp với nhu cầu đã nêu..." — do văn AI (S6) đã bị S7
     verifier loại và thay bằng bảng (`used_fallback_table`, guardrail `grounded_fallback`).
   - `_strengths` (dòng 407-413) render mọi spec kể cả điểm trừ ⇒ "không phải inverter..."
     (`src/pipeline/s6_generate.py:105-108`) nằm trong mục ưu điểm.

## 2. Thực tế dữ liệu (ràng buộc quyết định phạm vi)

Kiểm chứng trên `data/realdata/processed/*.json`: chỉ **5 ngành có dict `specs` đã parse** (số/boolean
thật, rank được) — 4 ngành `uu_tien` (may_lanh, may_giat, may_rua_chen, dong_ho_tm) + **tu_lanh**
(vd `capacity_total_l: 313.0`, `inverter: bool`). **9 ngành còn lại chỉ có `specs` = `{display_name}`**;
dữ liệu thật nằm trong `specs_raw` dạng chuỗi tiếng Việt thô (vd `"Điện năng tiêu thụ": "800W"`,
`"Độ phân giải": "Full HD (1920 x 1080)"`, nhiều `"Không có"`). Cả S4 lẫn S5 hiện bỏ qua `specs_raw`
(tiền tố `"specs."` không khớp `"specs_raw."`).

⇒ **Không thể chấm điểm/sinh trade-off spec-based cho 9 ngành raw** nếu chưa parse (đúng phần việc
ADR A7 chưa có). Do đó phạm vi thực tế chia 2 nhóm (mục Quyết định #3).

9 ngành raw: `tu_mat_dong, man_hinh, may_in, may_nuoc_nong, may_say, may_tinh_bang, micro_karaoke,
micro_thu_am, pc_de_ban`.

## 3. Mục tiêu & phi mục tiêu

**Mục tiêu** — với **5 ngành có specs parse**, một phiên tư vấn phải đạt cả 4:
1. Đúng nhóm sản phẩm khách cần **nổi lên top**.
2. Mỗi card nêu **một lợi ích thật, khác nhau**.
3. Mỗi card nêu **một đánh đổi thật, khác nhau**.
4. Không còn UI gây hiểu nhầm (không khoe điểm trừ; không "100%" giả).

Với **9 ngành raw** và **mọi ngành**: đạt (4) + trung thực khi thiếu dữ liệu ("chưa đủ dữ liệu cấu
trúc để so sánh chi tiết" thay vì câu-mẫu-giả-làm-phân-tích).

**Phi mục tiêu:**
- Không sửa verifier S7; thay vào đó làm **card không phụ thuộc văn AI** (mọi copy trên card xác định
  từ dữ liệu S5). Câu dẫn (message) vẫn có thể bị thay bằng bảng — chấp nhận.
- **Không** parse `specs_raw` / không xây Category Profile Compiler trong spec này.
- Không đụng luồng vector-rerank của S4.
- Không sửa chất lượng dữ liệu nguồn (bản ghi trùng, giá thưa).

## 4. Thiết kế chi tiết

### 4.1. S5 — chấm điểm theo tiêu chí, không khoá vào `uu_tien`

**Nguồn tiêu chí — cơ chế 2 lớp:**

- **Lớp khai báo:** khối tuỳ chọn `ranking_criteria` trong `slots/<category>.yaml`, mỗi mục có
  `field` + `direction` (+ tuỳ chọn `target`). **Chỉ tham chiếu field `specs.*` đã parse.** Trong spec
  này **chỉ tủ lạnh** được viết `ranking_criteria` (5 ngành parse còn lại giữ nguyên đường `uu_tien`):

  ```yaml
  # tu_lanh.yaml
  ranking_criteria:
    - field: inverter
      direction: boolean_pref          # True là pole tốt
    - field: capacity_total_l
      direction: target                # gần nhu cầu mới tốt; quá khổ bị trừ
      target: dung_tich_can            # lit_can = 45*so_nguoi + 100 (derivation_rules đã có)
  ```

- **Lớp suy luận (fallback):** ngành **không** có `ranking_criteria`:
  - có `uu_tien` ⇒ giữ **nguyên** logic hiện tại (4 ngành cũ không đổi hành vi).
  - không có `uu_tien` (9 ngành raw) ⇒ tự lấy các field `specs.*` **số/boolean có độ chênh**. Vì
    `specs` của 9 ngành này chỉ có `display_name` (không parse), fallback **ra tập tiêu chí rỗng một
    cách bình thường** (không lỗi) — đúng thực tế "chưa có dữ liệu để so sánh".

**Ngữ nghĩa hướng → `goodness` (0..1):**

| direction | goodness |
|---|---|
| `higher_better` | min-max chuẩn hoá, cao → 1 (như hiện tại) |
| `lower_better` | min-max chuẩn hoá, thấp → 1 (như `_lower_is_better` hiện có) |
| `boolean_pref` | True → 1.0, False → 0.0 |
| `target` | tính `need` từ derivation (`lit_can`); goodness = 1.0 khi dung tích trong `[need, need*OVERSIZE_TOLERANCE]`, giảm dần khi vượt. Dưới `need` đã bị S4 lọc cứng. |

`target` **thay** penalty oversize rời rạc (`s5_ranking.py`): vừa hạ điểm máy quá khổ, vừa tạo chất
liệu trade-off "kém hơn về dung tích phù hợp" (penalty rời không vào được `_trade_offs`). Tổng quát hoá
`_capacity_need` (`s5_ranking.py:250-263`) từ chỗ chỉ `may_lanh` sang bất kỳ ngành có `target` criterion
(tủ lạnh: `capacity_total_l` ↔ `so_nguoi_dung`).

**Trọng số:** giữ `STATED_PRIORITY_WEIGHT (3x)` / `UNSTATED_WEIGHT (1x)`. Mở rộng định nghĩa "đã nêu":
một tiêu chí ×3 nếu **slot tương ứng đã được khách set** (không chỉ qua `uu_tien`). Vd "tiết kiệm điện"
⇒ `inverter` đã nêu ⇒ ×3.

**Trade-offs:** giữ nguyên thuật toán `_trade_offs` (`s5_ranking.py:413-437`) — chỉ cần `pool` không rỗng.

### 4.2. S2 — cầu nối "tiết kiệm điện" → tín hiệu năng lượng của ngành

Trong `_overlay_text_slots` (`s2_extract.py:537-568`), thêm bắc cầu xác định: cụm ưu tiên năng lượng
(`tiet kiem dien`, `it ton dien`, `it hao dien`, `tiet kiem`) ⇒ nếu ngành hiện tại có slot boolean
`inverter` thì set `inverter=True`. Giữ đường enum cho ngành `uu_tien`. Chỉ nhận cụm tín hiệu cao,
deterministic. (Thực tế: chỉ tủ lạnh có slot boolean `inverter`.)

### 4.3. S4 — inverter chuyển từ lọc cứng sang mềm

Theo quyết định "ưu tiên mềm": trong `_direct_conditions` (`catalog_search.py:230-248`), **bỏ lọc cứng
theo boolean `inverter`**. Máy không-inverter vẫn trong tập ứng viên; S5 dùng `boolean_pref` (×3 khi đã
nêu) đẩy máy inverter lên top, nhưng máy không-inverter rẻ/đúng cỡ vẫn có thể vào top-3 **kèm đánh đổi
thật**.

**Bề mặt hồi quy (khu trú):** rà 14 profile — **chỉ `tu_lanh` có slot boolean map về specs** (`inverter`).
Máy lạnh xử lý inverter qua `uu_tien` (mềm sẵn). Nên thay đổi này chỉ tác động tủ lạnh. Cập nhật/kiểm lại
test đang assert lọc cứng inverter (`tests/test_catalog_search.py`).

> Ghi chú: inverter **luôn là ưu tiên mạnh, không bao giờ là cổng cứng** — nhất quán với triết lý "luôn
> cho thấy trade-off". Path "chỉ inverter" cứng (nếu cần) sẽ là tín hiệu ràng buộc riêng, ngoài phạm vi này.

### 4.4. Hiển thị — dùng dữ liệu thật, trung thực khi thiếu (áp cho **cả 14 ngành**)

Tất cả trong `src/services/advisor_chat_service.py`:

- **`_strengths` (dòng 407-413): lọc bỏ điểm trừ.** Không đưa spec pole xấu vào ưu điểm — bỏ render
  `boolean_pref` khi giá trị = pole xấu (vd `inverter=False`). "Ưu điểm" chỉ gồm spec pole tốt hoặc
  spec thông tin trung tính. Điểm trừ chỉ ở `trade_off`.
- **`reason` (lợi ích) → xác định (dòng 425-427).** Không còn phụ thuộc `result.advice.statements`
  (văn AI dễ bị verifier loại). Rút **tiêu chí khách-đã-nêu mà card này mạnh nhất** (goodness cao nhất),
  render qua GLOSSARY. Vd card inverter top: "Tiết kiệm điện nhờ inverter"; card mạnh về dung tích:
  "Dung tích ~235L vừa với nhà 3 người". Mỗi card một lợi ích khác nhau.
- **`_trade_off_text` (dòng 378-404): trung thực khi rỗng.** Khi không có tiêu chí nào (9 ngành raw),
  thay câu mẫu "Nên đối chiếu thêm bảo hành..." bằng câu **thành thật**: "Chưa đủ dữ liệu cấu trúc để
  nêu đánh đổi cụ thể; anh/chị nên xem chi tiết sản phẩm". Không giả vờ đã phân tích.
- **`_match_scores` trung thực (dòng 364-375).** Nếu `max-min` điểm top-3 dưới ngưỡng epsilon (tập gần
  tương đương / không tiêu chí), **không dựng thang %** — hiển thị "các lựa chọn khá tương đương".

## 5. Kiểm thử

- **S5 (`tests/test_s5_ranking.py`):**
  - Tủ lạnh với `ranking_criteria`: `inverter` ×3 khi đã nêu, máy inverter xếp trên máy không-inverter
    *ceteris paribus*; `target` dung tích: máy đúng cỡ xếp trên máy quá khổ; trade-off "dung tích" xuất hiện.
  - Fallback ngành không-`uu_tien` không có specs parse: ra tập tiêu chí rỗng, **không lỗi**.
  - **Hồi quy:** 4 ngành `uu_tien` kết quả **không đổi**.
- **S2 (`tests/test_s2_extract.py`):** "cần tiết kiệm điện" (không có chữ "inverter") ⇒ `inverter=True`
  cho tủ lạnh; cụm phủ định vẫn ra `False`.
- **S4 (`tests/test_catalog_search.py`):** inverter không còn lọc cứng; máy không-inverter vẫn trong tập;
  ngân sách + dung tích tối thiểu vẫn lọc như cũ.
- **Hiển thị (`tests/test_chat_advisor.py`):** `strengths` không chứa "không phải inverter"; `reason`
  khác nhau giữa các card, không phải câu mẫu; `_match_scores` trung thực khi tương đương; trade-off của
  ngành raw là câu thành thật, không phải boilerplate cũ.
- Chạy lại toàn bộ suite S5/S6/advisor để bắt hồi quy.

## 6. Rủi ro & giảm thiểu

- **Đổi hành vi lọc inverter (S4):** khu trú ở tủ lạnh; cập nhật test + thêm test hành vi mềm mới.
- **Nhân đôi hiệu ứng (penalty oversize cũ + target mới):** loại penalty oversize rời, chỉ dùng `target`;
  kiểm bằng test dung tích.
- **Kỳ vọng "10 ngành" vs thực tế:** spec này chỉ đưa xương sống đầy đủ tới 5 ngành parse; 9 ngành raw
  chờ parser (ADR A7). Ghi rõ để không hiểu nhầm độ phủ.

## 7. Việc nối tiếp (ngoài phạm vi, ghi để không quên)

- Category Profile Compiler / parser `specs_raw` → `specs` để mở khoá xương sống cho 9 ngành raw.
- Sau khi có parser, viết `ranking_criteria` cho 9 ngành đó (cùng cơ chế, không phải làm lại).
