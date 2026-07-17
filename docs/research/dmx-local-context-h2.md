# Giải pháp cho yêu cầu Context địa phương (H2) — ngoài logic tư vấn

> v1 · 17/07/2026 · Dòng H2 "logic tư vấn theo ngành hàng" đã giải bằng Category Profile Compiler (ADR A7). Doc này giải 4 dòng còn lại: văn hóa giao tiếp · pháp lý · địa lý/khu vực · dữ liệu thị trường.

---

## H2.1 Văn hóa / phong tục giao tiếp (Bắt buộc: Có)

**Yêu cầu brief:** "giao tiếp lịch sự, tư vấn gần gũi trong tiếng Việt; tránh ép mua hoặc phóng đại."

**Vấn đề thật sự:** tiếng Việt không có "you/I" trung tính — hệ xưng hô theo quan hệ thân tộc (anh/chị/em/cô/chú/bác), chọn sai là mất thiện cảm ngay câu đầu. Kèm particle lễ phép ("dạ", "ạ") và văn hóa đồng thuận xã giao (khách nói "ừ để anh xem" ≠ chốt đơn).

**Giải pháp (3 lớp):**
1. **Style guide trong system prompt** (chuẩn retail VN): bot xưng **"em"**, gọi khách **"anh/chị"** mặc định; mở đầu "dạ", kết câu hỏi có "ạ"; không caps-lock, không chèn emoji quá 1/tin; cấm giọng phóng đại (đã có danh sách cấm ở guardrail tầng 4)
2. **Pronoun mirroring** (rule trong S2): phát hiện khách tự xưng gì — khách xưng "cô/chú" → bot giữ "em/con" + dạ thưa đậm hơn; khách xưng "mình/bạn" → bot thả lỏng theo; lưu vào Need Profile (`xưng_hô`) để nhất quán cả phiên
3. **Đồng thuận xã giao ≠ intent mua**: "ừ", "ok để xem" không kích hoạt bước chốt — S2 phân biệt `đồng_ý_xã_giao` vs `chọn_sản_phẩm`; bot không dồn ép tiếp mà mở lối ("anh cần em gửi lại so sánh để xem sau không ạ?")

**Đo:** rubric LLM-judge đã có câu #5 (giọng điệu); bổ sung câu #7: "xưng hô nhất quán và phù hợp với cách khách xưng?" — test bằng scenarios D3 có persona người lớn tuổi. Benchmark tham khảo: CSConDa (9k QA customer support tiếng Việt) nếu cần thêm mẫu văn phong.

## H2.2 Pháp lý — bảo vệ dữ liệu cá nhân (Bắt buộc: Có)

**Phát hiện quan trọng:** từ **1/1/2026, Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 đã có hiệu lực** (Quốc hội thông qua 26/6/2025) — NĐ 13/2023 vẫn là văn bản hướng dẫn chuyển tiếp. Tức là tại thời điểm thi (7/2026), **viện dẫn đúng phải là Luật 91/2025/QH15**, không chỉ NĐ 13 — chi tiết này thể hiện hiểu biết pháp lý cập nhật hơn phần lớn đội khác.

**Nghĩa vụ chạm đến chatbot:** quyền được biết / đồng ý / truy cập / sửa / **xóa** dữ liệu; consent phải chủ động (app được phép xin chấp thuận qua "thiết lập kỹ thuật"); default settings phải nghiêng về bảo vệ.

**Giải pháp — compliance-by-design (phần lớn đã có sẵn trong kiến trúc, giờ gọi đúng tên):**

| Nghĩa vụ | Cơ chế đã/cần có | Trạng thái |
|---|---|---|
| Consent trước khi xử lý | Banner đầu phiên chat: mục đích (tư vấn sản phẩm), phạm vi (nội dung hội thoại, không định danh), nút đồng ý | ➕ Thêm, ~0.5h |
| Tối thiểu hóa dữ liệu | Không hỏi/lưu tên, SĐT, địa chỉ chi tiết — tư vấn chỉ cần khu vực cấp tỉnh | ✅ thiết kế sẵn |
| Quyền xóa | Nút "Xóa hội thoại" + session TTL in-memory | ✅ tầng 5 guardrail |
| Mask log | Regex PII trước khi ghi audit log | ✅ tầng 5 guardrail |
| Chủ quyền dữ liệu | **On-prem/self-host toàn stack — dữ liệu không rời hạ tầng doanh nghiệp** | ✅ luận điểm bán hàng luôn |

**Pitch:** "Kiến trúc tuân thủ Luật BVDLCN 91/2025/QH15 từ thiết kế — không phải vá sau" + 1 slide bảng trên. Với pilot dùng data thật: thêm DPIA đơn giản vào roadmap (đúng điều kiện D3 brief).

## H2.3 Địa lý / hành chính — khu vực, tồn kho, giao lắp (Ưu tiên)

**Phát hiện quan trọng:** sáp nhập hành chính lớn nhất lịch sử — từ 12/6/2025 còn **34 đơn vị cấp tỉnh** (28 tỉnh + 6 TP), **bỏ cấp huyện**, 10.035 xã → 3.321; giấy tờ địa chỉ cũ vẫn hợp lệ đến 2027. Hệ quả cho chatbot: **khách sẽ còn nói địa chỉ CŨ trong nhiều năm** ("giao về Bình Dương", "ship ra Hà Tây") — bot không hiểu tên cũ là fail yêu cầu H2 ngay tình huống phổ biến nhất.

**Giải pháp:**
1. **Bảng alias 63→34** (public data, ~63 dòng + các TP/quận lớn hay được nhắc): chuẩn hóa `khu_vực` về mã mới ở S1, nhưng **echo lại theo tên khách dùng**: "Dạ khu vực Bình Dương (nay thuộc TP.HCM) bên em giao lắp trong 24h ạ" — vừa đúng dữ liệu vừa tôn trọng thói quen gọi tên
2. Slot `khu_vực` (cấp tỉnh là đủ cho demo) → tham số cho Stock API + luật phí giao/lắp trong D2 policy; mock D7 seed vài region có/không có hàng để demo honesty ("kho khu vực anh hiện hết mẫu này, còn ở kho X — giao chậm hơn 2 ngày")
3. Không cần geocoding API ngoài (né anti-pattern phụ thuộc API ngoại) — bảng tra cứu tĩnh đủ cho cấp tỉnh

**Effort:** ~1h (bảng alias + tích hợp S1 + seed mock). Demo detail nhỏ nhưng giám khảo địa phương *chắc chắn* nhận ra.

## H2.4 Dữ liệu thị trường VN (Bắt buộc: Có)

**Yêu cầu brief:** VND, giá khuyến mãi, trả góp, đơn vị đo, đặc thù điện máy/điện thoại VN. Phần lớn đã phủ trong thiết kế — bảng tổng hợp vị trí:

| Đặc thù | Giải pháp | Vị trí |
|---|---|---|
| VND văn nói ("20 củ", "2 chục tr") | Parser tiền S1 | ✅ workflow S1 |
| Đơn vị lẫn ("1 ngựa" = 1HP = 9000BTU) | Bảng quy đổi S1 + ingestion | ✅ S1 + D1b |
| Trả góp: 0% qua thẻ vs công ty tài chính (Home Credit/FE Credit/HD Saison), trả trước 30–50%, cần CCCD | Encode vào D2 policy docs; slot `trả_góp` có follow-up ("anh có thẻ tín dụng không ạ?" → rẽ nhánh điều kiện) | ➕ làm giàu D2, ~0.5h |
| Văn hóa khuyến mãi: giá niêm yết vs giá sốc, tặng kèm, thu cũ đổi mới | Field promotion đa kiểu trong D1 schema (giảm giá / quà tặng / thu cũ) — so sánh phải nói rõ loại ("giảm thẳng 2tr" ≠ "tặng nồi chiên 2tr") | ➕ schema D1, ~0.5h |
| Nhãn năng lượng (sao + kWh/năm) & điện bậc thang EVN / giá điện trọ | Field `energy_kwh_year` + TCO calculator (tính năng 1.1) | ✅ innovation 1.1 |
| Mùa vụ (tháng 7 = cao điểm nóng; Tết = tủ lạnh/TV) | 1 dòng context trong system prompt theo ngày hệ thống; luật "mùa cao điểm → cảnh báo lịch lắp đặt nếu stock API có data" | ➕ config, ~15' |

## Tổng hợp effort & vị trí trong kế hoạch

| Việc mới phát sinh từ doc này | Phase | Giờ |
|---|---|---|
| Consent banner + nút xóa hội thoại | 3 (cùng source panel) | 0.5h |
| Bảng alias 63→34 + echo tên cũ | 2 (cùng S1 dict) | 1h |
| Style guide + pronoun mirroring + rubric #7 | 2 (cùng dialogue) | 1h |
| Làm giàu D2 trả góp + schema promotion đa kiểu | 1–2 (cùng sinh data) | 1h |
| Context mùa vụ | 4 | 15' |

**Tổng ~3.5h** — rải vào các phase sẵn có, không tạo phase mới. Slide pitch thêm 1 trang "Hiểu Việt Nam": Luật 91/2025 ✓ · 34 tỉnh mới ✓ · xưng hô ✓ · trả góp ✓ · tiền điện ✓ — đây chính là hàng rào cạnh tranh với các đội dùng giải pháp chatbot ngoại nhập.
