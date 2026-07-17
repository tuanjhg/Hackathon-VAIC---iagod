# Điểm sáng tạo giải pháp — xây trên nền plan hiện tại

> v1 · 17/07/2026 · Bổ trợ: `dmx-ai-workflow-v1.md`, `dmx-guardrail-design.md`, `dmx-data-eval-roi-plan.md`
> Triết lý chọn: sáng tạo KHÔNG phải thêm tính năng lạ — mà là làm 3 thứ được chấm điểm (hiểu nhu cầu · trade-off · tin cậy) **sâu hơn hẳn mặt bằng chung**, tận dụng hạ tầng đã thiết kế sẵn (fit-score tường minh, provenance, audit log, Need Profile). Mỗi tính năng phải trả lời được: "cái này ăn điểm tiêu chí nào, demo trong bao nhiêu giây?"

---

## TIER 1 — Làm chắc (impact cao / effort thấp-vừa, nằm trong Phase 2–4)

### 1.1 ⚡ Máy tính tiền điện — trade-off bằng TIỀN, không bằng thông số (~2–3h)
**Ý tưởng:** thay vì "máy A 850W, máy B inverter 720W", bot nói: *"Máy A tốn ~320.000đ tiền điện/tháng nếu chạy 8 tiếng/ngày, máy B ~230.000đ — chênh 90.000đ/tháng, sau ~20 tháng bù được phần chênh giá mua."*
- **Grounded 100%:** công suất/điện năng tiêu thụ kWh/năm lấy từ **nhãn năng lượng trong catalog** (thêm field này vào mock D1); giờ dùng/ngày = khách nói (slot mới, hỏi được tự nhiên); đơn giá điện = bậc thang EVN (public) **hoặc giá chủ trọ khách khai** ("điện trọ 4k/số" — chi tiết cực Việt Nam)
- Gắn nhãn "ước tính" + nguồn loại "quy tắc tư vấn" trong source log — khớp guardrail tầng 3
- **Ăn điểm:** So sánh trade-off 10% (ngôn ngữ tiền ai cũng hiểu — đúng nghĩa "bình dân" mà brief I1 đòi) · Context VN (H2) · khác biệt cao vì cần cả field nhãn năng lượng + luật bậc thang
- **Demo 20 giây:** kịch bản I1 "tiết kiệm điện" → bot quy hẳn ra đồng/tháng + thời gian hoàn vốn inverter

### 1.2 🎚️ Thanh trượt ưu tiên — re-rank realtime không cần gọi LLM (~2–4h frontend)
**Ý tưởng:** dưới top-3 có 3 slider: Êm ↔ Giá ↔ Tiết kiệm điện. Khách kéo → **top-3 xáo lại ngay lập tức** vì fit-score là hàm tường minh (S5) — chỉ tính lại `Σ wᵢ·match`, zero LLM call, <50ms.
- Lời giải thích ngắn cập nhật bằng template điền sẵn (không chờ LLM); giải thích đầy đủ sinh lại async nếu khách dừng kéo >2s
- **Ăn điểm:** đây là bằng chứng *nhìn thấy được* của "explainable ranking" (AI-Native 20% + Technical 15%) — giám khảo kéo slider và thấy vì sao thứ hạng đổi; đội dùng LLM-rerank đen hộp không thể làm realtime như vậy
- **Demo 15 giây:** "anh chê ồn?" → kéo slider Êm lên → máy khác nhảy lên #1 kèm lý do đổi

### 1.3 🧠 Suy luận nhu cầu ẩn — inference, không chỉ extraction (~1–2h, prompt-level)
**Ý tưởng:** khách nói "*máy lạnh cho phòng bé ngủ*" → hệ thống điền ngầm: ưu tiên êm (<25dB), chế độ không thổi thẳng, lọc khí — hiển thị thành **chips giả định khách click để sửa/bỏ**: `[phòng ngủ trẻ em ✓] [cần chạy êm ✓] [lọc không khí ?]`. "Sinh viên ở trọ" → suy: nhạy giá, điện tính theo giá trọ, không khoan tường được (→ máy lắp đơn giản).
- Là "Detailed Intent Generation" của nghiên cứu TTR áp vào bối cảnh VN — slot điền ngầm giúp **giảm số câu hỏi** (turns-to-rec ↓, clarify efficiency ↑ trong eval)
- An toàn: giả định luôn *hiển thị* và sửa được — thông minh nhưng minh bạch, không đoán mò trong im lặng
- **Ăn điểm:** Hiểu nhu cầu & hỏi ngược 10% (nâng từ "hỏi đúng" lên "hiểu điều chưa nói") — đây là điểm khác biệt AI thật sự so với form hỏi đáp
- **Demo 15 giây:** gõ "phòng trọ 15m2 chủ tính điện 4k/số" → chips giả định hiện ra + tiền điện tính theo 4.000đ/kWh

### 1.4 🃏 Bảng so sánh "nhu-cầu-làm-hàng" (~2h frontend)
**Ý tưởng:** bảng so sánh có **hàng là nhu cầu của khách**, không phải spec: "Êm cho phòng ngủ ✓/～/✗", "Tiền điện/tháng ~230k/~320k", "Vừa ngân sách ✓/✓/vượt 500k" — mỗi ô là verdict kèm con số làm bằng chứng (bấm vào xem spec gốc + nguồn). Bảng spec truyền thống vẫn còn, nhưng gập lại làm phụ lục.
- **Ăn điểm:** đánh thẳng anti-pattern I2 "bắt khách tự hiểu bảng thông số phức tạp"; trade-off 10%; UI kể chuyện đúng triết lý đề
- Cột thứ 4 mờ: **anti-pick** với dấu ✗ đỏ ở đúng nhu cầu nó fail — "vì sao không chọn" trực quan hóa

### 1.5 🏗️ Category Profile Compiler — AI tự học logic tư vấn ngành hàng (~3–4h, bổ sung 17/07)
**Ý tưởng:** không phải dev viết config tư vấn — pipeline LLM offline đọc catalog + bài hướng dẫn chọn mua → tự sinh slot schema, luật quy đổi (có citation), câu hỏi mẫu; chuyên gia duyệt; runtime đọc profile compiled (chi tiết: `dmx-ai-workflow-v1.md` §2 + ADR A7).
- **Demo kill-shot:** thêm ngành hàng **robot hút bụi** live trước giám khảo → compiler chạy ~1 phút → bot lập tức biết hỏi "nhà sàn gỗ hay gạch, có thú cưng không, cần lau hay chỉ hút" — chứng minh "AI hiểu logic tư vấn" đúng nghĩa H2, không phải form đóng cứng
- **Ăn điểm:** AI-Native 20% (AI sinh cấu hình cho chính nó) · Hiểu nhu cầu 10% · Startup Potential 15% (onboard ngành hàng mới tính bằng phút — luận điểm scale mạnh nhất toàn hệ thống)
- **Điều kiện:** core xanh + YAML v0 tay vẫn là fallback; build Phase 3, demo Phase 4

## TIER 2 — Làm nếu đúng tiến độ (Phase 4, sau khi core xong)

### 2.1 📊 Dashboard "Nhu cầu thị trường" cho doanh nghiệp (~2–4h)
View trên audit log **đã có sẵn**: phân bố ngân sách khách hỏi theo ngành hàng · slot thiếu nhiều nhất (khách không biết mình cần gì) · **SP được recommend nhiều nhưng hết hàng** (mismatch cung–cầu = tiền rơi) · câu hỏi bot chịu thua (data gap để ĐMX bổ sung catalog).
- **Ăn điểm:** Startup Potential 15% — biến chatbot từ cost-center thành **nguồn insight nhu cầu thật**, dòng giá trị ③ trong value tree ROI; giám khảo doanh nghiệp sẽ nhớ slide này
- Câu pitch: "Mỗi hội thoại là một khảo sát thị trường miễn phí mà khách tự nguyện làm."

### 2.2 📱 Thẻ bàn giao nhân viên / QR O2O — **NÂNG HẠNG lên Tier 1 (17/07, sau bài học Klarna)**
Nút "Gặp tư vấn viên" → xuất thẻ tóm tắt Need Profile + top-3 + điểm còn phân vân (QR/mã ngắn) → nhân viên tại cửa hàng/chat người tiếp nhận **không hỏi lại từ đầu**.
- **Vì sao nâng hạng:** vụ Klarna quay xe 2025 (phải tuyển lại người vì AI trả lời chung chung ở ca khó) biến human-handoff từ "nice-to-have" thành **luận điểm chiến lược**: "chúng tôi không thay người — chúng tôi đưa nhân viên một khách hàng đã được hiểu sẵn". Effort thấp (render thẻ từ Need Profile có sẵn ~1–2h) mà chặn được câu hỏi phản biện chắc chắn sẽ có: "AI sai ở ca khó thì sao?"
- **Ăn điểm:** giải đúng pain "nhân viên trả lời lặp lại" (brief C2); O2O hợp thế mạnh chuỗi cửa hàng ĐMX; human-in-the-loop mà brief mục F gợi ý

### 2.3 🛡️ Bộ đếm tin cậy công khai (~0.5h)
Badge góc UI: "**100% câu trả lời có nguồn · 0 sự cố dữ liệu / 1.284 hội thoại test**" — đếm live từ verifier log. Guardrail thành marketing; con số lấy từ eval report nên không bịa.

### 2.4 🏠 Gói luật ngữ cảnh VN sâu (~1–2h, chỉ là YAML)
Mở rộng luật tư vấn: **phòng trọ** (điện giá chủ trọ, không khoan tường, dễ tháo mang đi) · **nhà có trẻ nhỏ** (êm, ion, khóa trẻ em) · **mùa** (tháng 7 cao điểm nóng → cảnh báo lắp đặt chờ 2–3 ngày nếu stock API có data) · **chung cư** (giới hạn cục nóng ban công). Mỗi luật = vài dòng config, nhưng demo trúng là giám khảo nhớ — "hiểu địa phương" H2 ăn ở đây.

## TIER 3 — Chỉ đưa vào roadmap pilot, KHÔNG build trong 48h

| Ý tưởng | Vì sao để dành |
|---|---|
| 🎤 Voice input tiếng Việt (PhoWhisper) | Wow cao nhưng STT sai làm hỏng demo live; chỉ thử nếu Phase 4 xong sớm, có toggle tắt |
| 📷 Gửi ảnh máy cũ/nhãn năng lượng để tư vấn nâng cấp (Qwen-VL) | Thêm model + VRAM + rủi ro; slide roadmap "quý 2 pilot" |
| 👔 Staff copilot (UI thứ 2 cho nhân viên) | Nhân đôi surface UI trong 48h là tự sát tiến độ; nói miệng trong pitch — backend dùng chung |

---

## Mapping tổng: sáng tạo → điểm

| Tính năng | Hiểu nhu cầu 10% | Trade-off 10% | Anti-hallu 10% | AI-Native 20% | Startup 15% |
|---|---|---|---|---|---|
| 1.1 Tiền điện TCO | | ●● | ● (grounded) | | ● |
| 1.2 Slider re-rank | | ●● | | ●● | |
| 1.3 Nhu cầu ẩn + chips | ●● | | ● (minh bạch) | ●● | |
| 1.4 Bảng nhu-cầu-làm-hàng | ● | ●● | ● (ô bấm ra nguồn) | | |
| 2.1 Dashboard nhu cầu | | | | | ●● |
| 2.2 QR bàn giao O2O | ● | | | | ●● |
| 2.3 Bộ đếm tin cậy | | | ●● | | ● |
| 2.4 Luật ngữ cảnh VN | ●● | ● | | | |

**Thứ tự triển khai đề xuất:** 1.3 (rẻ nhất, prompt) → 1.1 (cần thêm field data D1) → 1.4 → 1.2 → Tier 2 theo giờ còn lại. Nguyên tắc cắt giữ nguyên như plan chính: core (hỏi ngược, top-3, guardrail, latency) chưa xanh thì chưa đụng Tier nào.
