# Kế hoạch Dữ liệu tự tạo · Khung Evaluation · Giá trị kinh tế — ĐMX

> v1 · 17/07/2026 · Bổ trợ: `dmx-ai-workflow-v1.md` (luồng 8 stage) + `dmx-guardrail-design.md` (tầng 6 eval)
> Mục đích: **không ngồi chờ data BTC** — tự tạo đủ dữ liệu để tinh chỉnh luồng AI từ giờ 0, dựng khung eval chạy tự động, và chuẩn bị câu chuyện ROI cho pitch (Feasibility 15% + Startup 15%).

---

## A. Kế hoạch tạo lập dữ liệu (trước khi BTC phát data)

### A0. Nguyên tắc thiết kế
1. **Same-format-as-BTC**: brief E1 nói data phát dạng CSV/JSON (catalog), DOC/Markdown/JSON (policy), CSV/JSONL (scenarios) — mock data tự tạo theo đúng các format này, để khi nhận data thật chỉ **swap file, eval harness giữ nguyên**.
2. **Mọi bộ data đều có ground truth** — data không có nhãn đúng thì không tinh chỉnh được gì.
3. **Synthetic theo format thật, không scrape nguyên văn**: cấu trúc field + khoảng giá trị lấy theo dienmayxanh.com công khai, nội dung do LLM sinh + người duyệt — tránh rắc rối bản quyền khi repo public, và không đụng NDA.

### A1. Bảy bộ dữ liệu cần tạo

| # | Bộ dữ liệu | Kích thước | Mục đích (stage nào dùng) | Cách tạo | Ước giờ |
|---|---|---|---|---|---|
| D1 | **Mock Product Catalog** | 80–120 SKU, 4 ngành chính (máy lạnh, tủ lạnh, điện thoại, laptop) + ít tai nghe/robot | S4 retrieval, S5 ranking, ingestion | LLM sinh theo schema + field thật của web DMX (BTU, inverter, dB, lít, chip, RAM, pin, giá VND); người duyệt chéo 30' | 2h |
| D1b | **Bản "bẩn" của D1** (~20% record) | 20–25 SKU lỗi | Test ingestion (anti-pattern #1) | Script làm bẩn có chủ đích: thiếu field, "1HP" vs "9000BTU" lẫn lộn, giá dạng text "11.490.000₫", mô tả lệch spec, SKU trùng | 0.5h |
| D2 | **Policy & FAQ docs** | 6–8 tài liệu (bảo hành, trả góp 0%, giao lắp, đổi trả, thanh toán, khu vực phục vụ) | Nhánh PF (policy RAG) | Viết lại tóm tắt từ chính sách công khai DMX, thêm bảng điều kiện cụ thể | 1h |
| D3 | **Customer Need Scenarios** | 60–100 tình huống, JSONL | Eval E2E + tinh chỉnh S2/S3 | Ma trận persona × ngành × độ mơ hồ (xem A2); mỗi scenario kèm **ground truth**: category, slots đúng, expected clarify slots, gold top-3 | 2h |
| D4 | **Golden conversations** | 10–15 hội thoại đa lượt | Regression test toàn luồng | Viết tay từ D3 (các ca quan trọng: I1 nguyên văn, đổi ý giữa chừng, hỏi policy xen kẽ) — expected behavior từng lượt | 1.5h |
| D5 | **Red-team set** | ~30 câu | Guardrail eval (tầng 6) | Theo danh mục trong `dmx-guardrail-design.md` §8: SP không tồn tại, promo null, gán fact sai, injection, hỏi giá vốn | 1h |
| D6 | **Bộ tiếng Việt bẩn** | 80–100 cặp (bẩn → chuẩn + slots đúng) | Unit test S1 + S2 | Biến thể hóa từ D3: bỏ dấu, teencode ("mik mún mua"), viết tắt ("ml 1 ngựa rưỡi"), tiền ("20 củ", "2 chục tr"), code-switching ("laptop core i7 ram 16 gb chạy autocad") | 1h |
| D7 | **Mock APIs** (price/promotion/stock/review) | FastAPI server, seed từ D1 | S4 tool calls, test guardrail | Endpoint có tham số giả lập: latency 50–300ms, tỷ lệ field null cấu hình được, chế độ "mâu thuẫn nguồn" (API ≠ catalog) để test tầng 3 guardrail | 1.5h |

**Tổng ~10.5h** — khớp Phase 0–2 trong kế hoạch 48h; D1/D3/D7 là đường găng (làm trước), D4/D5 làm ở Phase 3.

### A2. Ma trận sinh Scenarios (D3) — đảm bảo phủ đủ phổ

```
Persona (5):  sinh viên tiết kiệm · gia đình 4 người · dân văn phòng · game thủ · người lớn tuổi (con mua hộ)
Ngành (4):    máy lạnh · tủ lạnh · điện thoại · laptop
Độ mơ hồ (3): đủ slot (kiểu I1) · thiếu một nửa ("mua máy lạnh tầm 15tr") · rất mơ hồ ("tư vấn em cái điều hòa")
Nhiễu (4):    chuẩn · không dấu · teencode/viết tắt · code-switching
```
→ 5×4×3 = 60 lõi, mỗi cái random 1 kiểu nhiễu; thêm ~20 ca đặc biệt: so sánh trực tiếp 2 SP, hỏi policy thuần, đổi ngành giữa chừng, đổi ngân sách, hỏi tồn kho theo khu vực.

**Format JSONL** (ăn khớp field brief D1.1 "phân loại đúng nhu cầu, ngân sách, ưu tiên và ràng buộc"):
```json
{"id": "SC-041", "persona": "gia_đình_4_người", "text": "nha minh 4 nguoi can tu lanh tam 12 cu, bep hoi chat",
 "gold": {"category": "tủ_lạnh", "slots": {"ngân_sách_max": 12000000, "số_người": 4, "ràng_buộc_kích_thước": true},
          "expected_clarify": ["kiểu_ngăn_đá", "kích_thước_chỗ_đặt_cm"], "gold_top3": ["SKU..", "SKU..", "SKU.."],
          "ambiguity": "vừa"}}
```

### A3. Quy trình sinh + kiểm soát chất lượng
1. LLM sinh theo template + few-shot → 2. script validate schema (đơn vị, khoảng giá hợp lý — máy lạnh 5–50tr, không có tủ lạnh 2 lít) → 3. người duyệt nhanh 15–20% mẫu → 4. commit vào `data/mock/` (**`data/btc/` trong .gitignore** dành cho data NDA sau này).
- **User simulator** (kiểu PROCLARE): LLM đóng vai khách theo persona + scenario, chat với hệ thống để sinh hội thoại đa lượt tự động — dùng cho eval E2E lớp 2, viết 1 lần dùng cả hackathon.

---

## B. Khung Evaluation — 3 lớp, chạy được bằng một lệnh

> Mục tiêu: `make eval` → 1 báo cáo markdown/HTML gồm mọi bảng dưới đây. Mỗi lần đổi prompt/policy/model → chạy lại → so trước/sau. Đây vừa là công cụ dev vừa là **bằng chứng kỹ thuật trong pitch**.

### B1. Lớp 1 — Component metrics (đo từng stage riêng)

| Stage | Metric | Cách đo | Ngưỡng chấp nhận |
|---|---|---|---|
| S1 Normalizer | Exact-match accuracy (tiền, đơn vị, từ ngành hàng) | Bộ D6, so output vs chuẩn | ≥95% cho tiền/đơn vị |
| S2 Intent | Intent accuracy | D3 + D6, so gold | ≥95% |
| S2 Slots | **Per-slot Precision/Recall/F1** (khớp D1.1 brief: "tỉ lệ phân loại đúng nhu cầu, ngân sách, ưu tiên, ràng buộc") | D3, so slots gold | F1 ≥0.9 slot bắt buộc; ≥0.8 slot phụ |
| S3 Policy | Đúng nhánh ambiguity (cao/vừa/thấp); câu hỏi chọn ⊆ expected_clarify; **% hỏi lại slot đã có = 0**; số câu hỏi TB/hội thoại | D3 + golden conversations | nhánh đúng ≥90%; hỏi lại = 0% |
| S4 Retrieval | Recall@10 vs gold_top3; **Constraint-violation rate** (SP vượt ngân sách/sai công suất lọt vào) | D3 | Recall ≥0.9; violation = **0** (đây là lời hứa của structured-first) |
| S5 Ranking | Hit@3 / NDCG@3 vs gold_top3; breakdown đầy đủ 100% | D3 | Hit@3 ≥0.8 |
| S6 Generation | LLM-judge rubric (B3) + schema compliance (100% card có trade_off) | 30 mẫu/lần chạy | rubric TB ≥4/5 |
| S7 Guardrail | Per-claim hallucination rate · honesty recall · refusal correctness (định nghĩa tại `dmx-guardrail-design.md` §8) | Toàn bộ output eval + D5 | 0 MISMATCH lọt · honesty ≥95% · refusal 100% |
| Hạ tầng | Latency p50/p95 theo loại turn; token/turn; cost/turn | Log tự động mọi lần chạy eval | p95 <3s (hỏi ngược), <5s (top-3) |

### B1b. Ablation retrieval — quyết định hybrid search bằng số (bổ sung 17/07)

So 3 cấu hình **dense-only · lexical-only (BM25) · hybrid-RRF** tại 2 điểm chèn:

| Điểm chèn | Bộ test | Metric | Slice bắt buộc |
|---|---|---|---|
| Catalog rerank (sau SQL filter) | D3 gold_top3 | Hit@3, NDCG@3, Recall@10 | chuẩn · không dấu · code-switching (từ D6) |
| Policy/FAQ RAG | **D2q mới**: ~20 câu hỏi policy có gold chunk (thêm vào D2, +0.5h) | Recall@3, MRR | chuẩn · văn nói |

- **Adoption rule**: bật hybrid nếu ≥ dense-only trên mọi slice và thắng rõ ở ≥1 slice (kỳ vọng: code-switching + policy); thua ở bất kỳ slice nào → giữ dense-only, ghi lý do vào ADR
- Latency không phải tiêu chí ở scale này (<10ms mọi cấu hình) nhưng vẫn log
- Kết quả ablation đưa vào eval report — giám khảo kỹ thuật hỏi "sao chọn hybrid?" → chỉ vào bảng

### B2. Lớp 2 — End-to-end (user simulator chạy trên D3)

| Metric | Định nghĩa | Vì sao quan trọng |
|---|---|---|
| **Task success rate** | % hội thoại kết thúc với top-3 thỏa mọi ràng buộc gold + LLM-judge xác nhận hợp nhu cầu | Con số tổng hợp duy nhất nếu chỉ được nói 1 số |
| Turns-to-recommendation | Số lượt từ câu đầu → top-3 (TB & p90) | Đo "hỏi vừa đủ" — quá ít = ẩu, quá nhiều = thẩm vấn; mục tiêu TB ≤3 |
| Slot coverage cuối phiên | % slot bắt buộc được điền khi ra đề xuất | Đo chất lượng hỏi ngược về mặt *kết quả* |
| Clarify efficiency | Information gain thực tế: mức giảm số candidates sau mỗi câu hỏi | Chứng minh câu hỏi "thông minh" bằng số, không bằng cảm giác |
| Guardrail E2E | Chạy D5 xuyên pipeline thật (không mock từng tầng) | Tầng nào thủng lộ ra ở đây |

### B3. LLM-as-judge — rubric nhị phân, không chấm điểm mù
Model judge (32B, prompt riêng, temperature 0) chấm từng câu trả lời bằng **câu hỏi có/không** (tránh bias điểm tổng):
1. Có tóm tắt lại nhu cầu khách trước khi đề xuất?
2. Ngôn ngữ có bình dân không (không thuật ngữ chưa giải thích)? — khớp tiêu chí "điểm dễ hiểu" D1.3
3. Mỗi SP đề xuất có ≥1 ưu VÀ ≥1 nhược/trade-off?
4. Có nêu SP không nên chọn + lý do?
5. Giọng có gần gũi, không ép mua, không phóng đại? (H2)
6. Câu hỏi ngược (nếu có) có kèm lý do vì sao hỏi?
→ điểm = số tiêu chí đạt/6; **human spot-check 10 mẫu/ngày** để hiệu chỉnh judge (judge lệch người → sửa prompt judge, không sửa số).

### B4. Nhịp chạy trong 48h
- **Phase 0**: dựng khung `eval/` + D1/D3/D6 tối thiểu → có baseline ngay khi pipeline chạy được
- **Phase 2–3**: mỗi thay đổi prompt/policy → `make eval` (~5–10 phút trên H100) → so bảng
- **Phase 4**: nhận data BTC → swap vào `data/btc/` → chạy lại toàn bộ → **báo cáo cuối cùng in vào slide** (bảng số + biểu đồ trước/sau)
- Xuất `eval_report.md` có timestamp — giám khảo hỏi "làm sao biết không bịa?" → mở report, không nói suông

---

## C. Đánh giá lợi ích kinh tế — so với giải pháp chưa tích hợp AI

### C0. Baseline so sánh (định nghĩa rõ để không so mơ hồ)
**Hiện trạng (theo chính brief C2)**: bộ lọc + bảng spec + review + nhân viên tư vấn + chatbot kịch bản. Hệ quả brief nêu: khách chậm ra quyết định, nhân viên trả lời lặp lại, traffic không chuyển thành đơn.

### C1. Cây giá trị (value tree) — 3 dòng lợi ích

```
GIÁ TRỊ = ① Doanh thu tăng (CR ↑, bỏ giỏ ↓, time-to-decision ↓)
        + ② Chi phí giảm (deflection tư vấn viên, scale giờ cao điểm không tăng biên chế)
        + ③ Giá trị dài hạn (log nhu cầu thật → insight ngành hàng, giảm hàng tồn sai nhu cầu)
        − ④ Chi phí AI (GPU + vận hành + tích hợp)
```
③ nói ngắn trong pitch (chưa demo được), tập trung ①②④.

### C2. Proxy metrics đo được NGAY trong hackathon (không cần traffic thật)
Không có user thật trong 48h — nhưng có thể đo **hành vi thay thế** trên user simulator + demo tại gian hàng:

| Proxy | Cách đo | Thay thế cho |
|---|---|---|
| Time-to-decision | Số lượt + phút từ câu đầu → chốt top-3 (bot) **vs** số thao tác lọc/so sánh thủ công để tới cùng kết quả trên flow web mô phỏng | Tốc độ ra quyết định của khách |
| Decision confidence | % hội thoại simulator kết thúc bằng chọn 1 SP (không bỏ dở) | CR |
| Deflection tiềm năng | % câu trong D3+D2 bot trả lời đạt (judge + guardrail pass) không cần người | Tải nhân viên |
| Cost per conversation | Token × giá GPU/giờ thực đo trên H100 | Chi phí vận hành |

### C3. Mô hình ROI tham số (đưa vào pilot roadmap + slide)

**Công thức** (tháng, cho 1 site/ngành hàng pilot — khớp quy mô D3):
```
Doanh thu thêm  = Sessions × (CR_new − CR_base) × AOV
Chi phí tiết kiệm = Chats/tháng × Deflection% × Cost_per_human_chat
Chi phí AI      = GPU_giờ × đơn_giá + vận_hành
ROI             = (Doanh thu thêm × Biên_LN_gộp + Tiết kiệm − Chi phí AI) / Chi phí AI
```

**Bảng tham số minh họa** (⚠️ số VÍ DỤ để demo mô hình — pilot sẽ điền số thật của ĐMX; ghi rõ điều này trên slide, trung thực số liệu chính là brand của giải pháp):

| Tham số | Giá trị minh họa | Nguồn khi làm thật |
|---|---|---|
| Sessions/tháng (1 ngành hàng) | 300.000 | Analytics ĐMX |
| CR baseline | 1,5% | Analytics ĐMX (ngành điện máy VN thường 1–2%) |
| Uplift CR giả định thận trọng | +10% tương đối (1,5% → 1,65%) | Đo bằng A/B trong pilot — KHÔNG cam kết trước |
| AOV điện máy | 8.000.000₫ | Số liệu ĐMX |
| Biên LN gộp | 12% | Số liệu ĐMX |
| Chats tư vấn/tháng | 20.000 | CS logs |
| Deflection | 40% | Đo từ pilot (proxy hackathon: C2) |
| Chi phí/chat người | 15.000₫ | Lương CS ÷ số chat xử lý |
| GPU 1× H100 | ~45tr₫/tháng (~$2,5/h) | Hóa đơn thuê thực tế |

→ Minh họa: doanh thu thêm = 300k × 0,15% × 8tr = **3,6 tỷ₫/tháng** → LN gộp thêm ~430tr; tiết kiệm CS = 20k × 40% × 15k = **120tr/tháng**; chi phí AI ~50tr → **ROI ≈ 10:1**. Điểm mạnh của cách trình bày: mô hình là spreadsheet tham số — giám khảo/DN tự kéo số của họ vào, không phải tin lời mình.

### C4. Thiết kế thí nghiệm cho pilot 3 tháng (điền thẳng vào Pilot Roadmap — khớp D3 brief)
- **A/B split**: 50% traffic thấy nút "Tư vấn cùng AI", 50% flow cũ; cùng ngành hàng pilot (máy lạnh — mùa nóng, volume cao)
- **Primary**: CR & time-to-decision (A vs B) · **Secondary**: deflection, CSAT sau chat, AOV
- **Guardrail KPI = điều kiện dừng** (đúng điều kiện ký hợp đồng D3): per-claim hallucination nghiêm trọng = 0, nếu phát sinh sự cố nghiêm trọng → tắt, sửa, chạy lại — cam kết này *là* selling point
- Tháng 1: shadow mode (bot chạy song song, người duyệt) → Tháng 2–3: A/B thật 1.000–10.000 hội thoại (khớp quy mô brief)
- Mọi số trong mô hình C3 được đo thật ở đây → sau pilot có business case bằng số của chính ĐMX

### C5. Nguyên tắc trung thực khi pitch phần kinh tế
1. Không nói "tăng X% conversion" như sự thật — nói "mô hình với giả định thận trọng cho thấy ROI dương từ uplift +10%; pilot đo số thật"
2. Mọi số minh họa gắn nhãn "ví dụ" trên slide; 3. Guardrail KPI đưa vào như *điều kiện* của business case — nhất quán với triết lý anti-hallucination của chính sản phẩm: **bot không bịa giá, đội không bịa ROI**.

---

## D. Gắn vào kế hoạch 48h (cập nhật phân công)

| Phase | Bổ sung từ kế hoạch này |
|---|---|
| 0 (0–2h) | Khung `eval/` + schema D1/D3; sinh D1 catalog + 20 scenarios đầu |
| 1 (2–10h) | D7 mock APIs (cần cho S4); D6 bộ tiếng Việt bẩn; baseline eval chạy lần đầu |
| 2 (10–20h) | Đủ 60 scenarios D3 + user simulator; `make eval` sau mỗi thay đổi prompt |
| 3 (20–30h) | D4 golden conversations + D5 red-team; eval report v1; bảng proxy C2 |
| 4 (30–38h) | Swap data BTC, chạy lại toàn bộ; chốt số cho slide |
| 5 (38–44h) | Mô hình ROI C3 vào pilot roadmap; eval report cuối vào phụ lục pitch |
