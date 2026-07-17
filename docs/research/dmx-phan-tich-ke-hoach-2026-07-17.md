# Điện Máy Xanh — MASTER PLAN (v2, tổng hợp)

> Track: **Năng Suất SME** · Đề: *Trợ lý AI so sánh và tư vấn sản phẩm theo nhu cầu thật của khách hàng*
> Nguồn đề: `VAIC/Điện Máy Xanh.docx.pdf` · Nộp bài: **10:00 ngày 19/07** · Demo: 16:00
> Hạ tầng chốt: **1× H100 80GB (VM thuê) · Qwen3-32B FP8 trên vLLM · Postgres duy nhất (catalog + pgvector + BM25)**
> 📌 v2 — 17/07: hợp nhất toàn bộ research + 5 tài liệu thiết kế thành kế hoạch thống nhất. Đây là tài liệu điều phối; chi tiết nằm ở các doc chuyên đề (§1).

---

## 0. TL;DR

Đề này là bài toán **khai thác nhu cầu (need elicitation) + đề xuất có căn cứ (grounded recommendation)** — không phải RAG chatbot thường. 30% điểm track = hỏi ngược thông minh (10%) + so sánh trade-off bình dân (10%) + chống hallucination (10%).

**Chiến lược thắng:** guardrail nhìn-thấy-được + đo-được (cards render thẳng từ data không qua LLM, verifier per-claim, source panel, eval report) · workflow cố định 8 stage với LLM ở nút quyết định (deterministic, đạt SLA <3s/<5s) · on-prem self-host (né anti-pattern "phụ thuộc API ngoại") · 4 tính năng sáng tạo xây trên nền kiến trúc đã trả trước chi phí (tiền điện TCO, slider re-rank realtime, suy luận nhu cầu ẩn, bảng nhu-cầu-làm-hàng).

## 1. Bản đồ tài liệu

| Tài liệu | Nội dung | Dùng khi |
|---|---|---|
| **File này** | Kế hoạch thống nhất, timeline 48h, rủi ro, demo script, checklist nộp | Điều phối hằng giờ |
| `dmx-ai-workflow-v1.md` | Luồng 8 stage S1–S8, state machine, slot schema + nguồn gốc slot, dialogue policy 3 mức, edge cases, latency budget | Code pipeline |
| `dmx-tech-decisions.md` | ADR: model/serving, pgvector hybrid (B2 v2), guided decoding, per-stage tech, 4 benchmark gate Phase 0 | Code + trả lời giám khảo kỹ thuật |
| `dmx-guardrail-design.md` | 6 tầng guardrail, traceability về brief, verifier spec, honesty/uncertainty, red-team, KPI | Code verifier + slide tin cậy |
| `dmx-data-eval-roi-plan.md` | 7 bộ data tự tạo (D1–D7), eval 3 lớp + ablation hybrid (B1b), mô hình ROI, thiết kế A/B pilot | Sinh data + `make eval` + pitch kinh tế |
| `dmx-innovation-features.md` | Tier 1/2/3 tính năng sáng tạo, mapping điểm, thứ tự làm | Phase 3–4 |
| `dmx-local-context-h2.md` | Giải pháp 4 dòng H2 còn lại: xưng hô/văn hóa, Luật BVDLCN 91/2025, bảng alias 34 tỉnh, thị trường VN (trả góp, khuyến mãi đa kiểu, mùa vụ) — ~3.5h rải vào các phase | Phase 1–4 + slide "Hiểu Việt Nam" |
| `dmx-comparables-landscape.md` | Bản đồ giải pháp tương đồng 4 nhóm (Rufus/Sparky/Klarna/Wenwen · bot VN · OSS repos · research) + ma trận khác biệt + 3 con số tham chiếu ROI (Sparky +35% AOV, Klarna $60M) | Slide so sánh + trả lời C2/I3 + tham khảo code Phase 1 |
| `data/btc/NOTES.md` | **Data catalog THẬT đã nhận (17/07)** — 8.746 SP/14 ngành hàng, đã ETL 2 ngành ưu tiên (máy lạnh, tủ lạnh); phát hiện quan trọng: không có điện thoại/laptop trong data thật (khác ví dụ brief C2), sku mới là khóa (không phải model_code), không có cột tên SP, giá chỉ phủ 15–26% (đúng thiết kế catalog/price API tách biệt) | Đọc TRƯỚC khi seed DB hoặc code ingestion — thay thế phần lớn kế hoạch mock D1 |

## 2. Tổng hợp research → quyết định đã chốt

| Mảng research | Phát hiện chính | Quyết định áp dụng |
|---|---|---|
| **Chiến lược recommendation** | CF/hybrid truyền thống vô dụng (cold-start, không có lịch sử hành vi); hướng đúng là conversational multi-agent (TTR/MACRS), Amazon Rufus (query planner + RAG + streaming); ProductAgent + ASK: hỏi làm rõ theo 3 mức ambiguity, dựa trên kết quả đã lọc | Pipeline intent→retrieval→rank tách bạch; dialogue policy 3 mức đo bằng pre-retrieval; suy luận nhu cầu ẩn kiểu TTR (tính năng 1.3) |
| **Explainable ranking** | LLM tự do viết giải thích = rủi ro bịa; statement-level ranking an toàn hơn | Fit-score tường minh + statement templates điền sẵn số; LLM chỉ diễn đạt; slider re-rank realtime (1.2) là quà tặng của kiến trúc này |
| **Tiếng Việt mua sắm** | ViSoLex/ViLexNorm (chuẩn hóa NSW, teencode); không cần model khôi phục dấu riêng — LLM 32B đọc tốt không dấu | S1 = regex + dict ngành hàng + lexicon ViSoLex; đưa cả text gốc + chuẩn hóa vào LLM; D6 làm test set |
| **Anti-hallucination** | Claim decomposition + đối chiếu per-claim là chuẩn tin cậy nhất; báo cáo per-claim rate chứ không phải answer-level; citation-shaped hallucination (nguồn thật nhưng cũ) | Guardrail 6 tầng; verifier numeric-only (fact đề yêu cầu đều là số/enum, bỏ NLI trong 48h); cards không qua LLM; freshness check `fetched_at` |
| **Hybrid retrieval** | Hybrid lexical+dense là mặc định production 2026 (WANDS +7.4% NDCG); bẫy: blend điểm BM25+cosine hỏng — bắt buộc RRF trên rank; pgvector khi đã có Postgres + data nhỏ, Qdrant khi cần sparse server-side | **Postgres duy nhất**: pgvector (dense) + BM25 (pg_textsearch/FTS) + RRF SQL, filter+hybrid+join trong 1 query; adoption gate = ablation B1b; tên SP vẫn fuzzy/trigram |
| **Serving/latency** | 72B không khả thi trên 1×80GB (FP8 ~72GB weights, AWQ chậm decode TP=1); 32B FP8 để ~45GB cho KV cache; prefix caching + chunked prefill giảm TTFT p95 tới 68%; cặp flag này từng có bug — phải test | Qwen3-32B FP8 (gate lùi Qwen2.5); 1 model chung S2+S6 (gate tách model nhỏ nếu S2 >700ms); guided decoding xgrammar; 4 benchmark gate Phase 0 |

## 3. Giải mã đề — điểm nằm ở đâu

### 3.1 Cơ cấu điểm & cách ăn

| Tiêu chí | % | Ta trả lời bằng |
|---|---|---|
| Problem Relevance | 20 | Bám kịch bản I1; pilot roadmap khớp từng dòng D3 |
| AI-Native Architecture | 20 | LLM định tuyến intent + quyết nội dung hỏi/tư vấn; tools MCP-compatible; fact chỉ từ tool result |
| Technical Execution | 15 | Pipeline E2E thật, ingestion chịu data bẩn, eval harness + ablation |
| Deployment | 15 | docker-compose 4 service 1 lệnh; self-host toàn bộ |
| Feasibility | 15 | Latency đo thật đạt SLA; chi phí/hội thoại đo thật; tích hợp API mock chuẩn |
| Startup Potential | 15 | Config-driven đa ngành hàng; dashboard nhu cầu (2.1); mô hình ROI tham số |
| **Hỏi ngược thông minh** | **10** | Policy 3 mức ambiguity + information gain + quota 2 lượt + suy luận nhu cầu ẩn |
| **Trade-off bình dân** | **10** | Statement templates + tiền điện TCO + bảng nhu-cầu-làm-hàng + anti-pick |
| **Đúng dữ liệu & chống bịa** | **10** | 6 tầng guardrail + source panel + eval report per-claim |

### 3.2 Yêu cầu cứng (fail = mất điểm lớn)
Tiếng Việt bẩn + code-switching (H1) · <3s hỏi ngược, <5s top-3 (H3) · on-premise, web browser · luật tư vấn ngành hàng (H2: máy lạnh diện tích/nắng/ồn, tủ lạnh số người, ĐT camera/pin/game, laptop công việc) · không giá vốn, mask log, không lưu data khách thật · Deliverables D2: web demo + GitHub public + kiến trúc giải thích được + pilot roadmap 1–2 trang + flow hỏi ngược + so sánh ≥3 SP + top-3 trade-off.

### 3.3 Anti-patterns (I2) → nghĩa vụ demo ngược

| BTC sợ | Ta demo |
|---|---|
| Chỉ chạy data sạch | Nạp CSV bẩn 20% live (D1b) |
| Bắt khách đọc bảng spec | Bảng nhu-cầu-làm-hàng, spec gập phụ lục |
| Phụ thuộc API ngoại | Self-host vLLM; cờ fallback cloud TẮT khi demo |
| Demo mockup | Giám khảo gõ tự do; live query catalog |
| Không kế hoạch triển khai | Pilot roadmap + A/B design + ROI tham số |
| Khen mọi SP, bịa giá, không hỏi lại | trade_off bắt buộc theo schema; verifier; quota hỏi thông minh |

## 4. Kiến trúc chốt (tóm tắt — chi tiết ở workflow + tech-decisions doc)

**Luồng 8 stage:** S1 chuẩn hóa deterministic (~50ms) → S2 intent+slot (guided_json, ~400ms) → S3 dialogue policy 3 mức ambiguity (rule + pre-retrieval count, ~110ms) → S4 retrieval structured-first (SQL filter → hybrid rerank pgvector+BM25/RRF → gọi song song price/promo/stock, ~250ms) → S5 fit-score tường minh + top-3 + anti-pick (~50ms) → S6 sinh lời tư vấn từ statement templates (streaming TTFT <1s; **cards render thẳng từ S5, không qua LLM**) → S7 verifier per-claim song song stream → S8 respond + source panel + audit log.

**Stack:**

| Lớp | Chọn |
|---|---|
| LLM | Qwen3-32B FP8, vLLM (prefix-caching, chunked-prefill 🧪, guided decoding xgrammar, hermes tools), 1 model chung S2+S6 🧪 |
| Embedding | `AITeamVN/Vietnamese_Embedding` in-process 🧪 |
| Store | **Postgres 16 duy nhất**: catalog + audit + pgvector HNSW + BM25 + pg_trgm; RRF trong SQL |
| Backend | FastAPI + SSE; router fallback tự viết (tắt cloud khi demo); session in-memory TTL |
| Frontend | Vite + React + Tailwind (cards, slider, source panel) |
| Đóng gói | docker-compose 4 service (vllm/api/web/postgres), `make up/eval/demo-reset` |

**Latency budget:** hỏi ngược ~1.2s tới token đầu (<3s ✓) · top-3 ~1.7s tới token đầu, ~4s trọn (<5s ✓).

## 5. KẾ HOẠCH 48H THỐNG NHẤT

> Vai: **A** = pipeline/backend · **B** = data/eval · **C** = UI/demo (kiêm docs/pitch từ Phase 4). Mốc: nộp 10:00 ngày 19/07 — **freeze trước 1h**.

| Phase | Giờ | Core build (A) | Data & Eval (B) | UI/Sáng tạo (C) | Gate/Output kiểm chứng |
|---|---|---|---|---|---|
| **0. Setup + Gates** | 0–2 | Repo public mới + compose 4 service; **chạy 4 benchmark gate** (32B đạt S2<700ms? cặp flag vLLM ổn? embedding CPU đủ? Qwen3+guided_json sạch?) | Schema catalog + slot YAML v0 (từ brief H2 + facets web DMX); sinh D1 catalog + 20 scenarios đầu | Khung chat UI trống | `docker compose up` ra UI; 4 gate có kết quả → chốt model/flags |
| **1. Xương sống** | 2–10 | S1→S8 happy path **1 ngành (máy lạnh)**: parse→filter→rank→top-3+anti-pick; tools nội bộ + facts JSON provenance | D7 mock APIs (null/mâu thuẫn config được); D6 bộ tiếng Việt bẩn; baseline eval chạy lần 1 | Cards render từ S5 (không LLM) + streaming | Kịch bản I1 chạy E2E; baseline metrics có số |
| **2. Hỏi ngược + tiếng Việt** | 10–20 | Dialogue policy 3 mức + information gain precompute + quota 2 lượt; S1 dict đầy đủ; **ablation hybrid B1b** → bật/tắt hybrid | D3 đủ 60 scenarios + user simulator; D2q 20 câu policy gold | Chips giả định (1.3 suy luận nhu cầu ẩn) | 10 câu bẩn hiểu đúng; ablation có bảng → quyết hybrid; % hỏi lại slot = 0 |
| **3. Guardrail + eval** | 20–30 | Verifier per-claim + honesty path + escalation; policy/FAQ RAG; **Category Profile Compiler v0** (AI sinh schema, so với YAML tay — ADR A7) | D4 golden conversations + D5 red-team 30 câu; eval report v1 | Source panel + badge "chưa có dữ liệu"; **1.1 tiền điện TCO** (cần field kWh/năm trong D1) | Xóa giá 1 SP → bot nói "chưa có dữ liệu"; red-team 100% pass; report v1; compiler output ≈ bản tay trên 4 ngành |
| **4. Mở rộng + tốc độ** | 30–38 | **[SỬA 17/07 — data thật không có điện thoại/laptop, xem `data/btc/NOTES.md`]** Thêm 1–2 ngành từ 12 ngành còn lại của data thật (ưu tiên máy giặt hoặc tủ mát/đông — null-rate thấp, parser đơn giản); ETL structured cho ngành mới; latency tune theo gate; chuẩn bị demo "thêm ngành robot/PC live" bằng compiler (1.5) nếu xanh | Chạy lại toàn bộ eval trên data thật | **1.4 bảng nhu-cầu-làm-hàng + 1.2 slider re-rank**; Tier 2 nếu xanh (2.3 badge đếm → 2.1 dashboard → 2.2 QR) | p95 đo thật <3s/<5s; 3–4 ngành chạy; eval trên data thật |
| **5. Đóng gói** | 38–44 | README + sơ đồ kiến trúc; dọn repo (check NDA: `data/btc/` không lên git) | Eval report cuối + bảng proxy ROI vào phụ lục | Pilot roadmap 1–2 trang (A/B design + ROI tham số + guardrail KPI làm điều kiện); quay video backup; slide + tổng duyệt demo | Video xong; pitch 5' trơn; repo sạch |
| **6. Freeze** | 44–48 | Chỉ fix bug chặn demo | — | Nộp trước 09:00 | ✅ 10:00 |

**Nguyên tắc cắt khi cháy giờ** (hy sinh theo thứ tự): Tier 2 (trừ 2.2 handoff — đã nâng Tier 1) → tủ lạnh/tai nghe → compiler 1.5 (lùi về pitch-only) → 1.2 slider → 1.4 bảng → review_summary tool → policy RAG → 1.1 TCO → 1.3 chips. **Không bao giờ cắt**: hỏi ngược, top-3 + trade-off, guardrail + source panel, latency — đó là 30% điểm track + điều kiện pilot.

**🚦 Checkpoint MVP giờ-20 (chốt chặn cứng):** 1 ngành hàng chạy E2E + hỏi ngược đúng quota + top-3 có trade-off + verifier v1 + source panel + kịch bản I1 pass + p95 xanh (1 user). **Không đạt → kích hoạt danh sách cắt ngay, không thương lượng.** Mọi thứ chưa build được đến giờ 38 chuyển sang "pitch-only" (nói trong slide dưới dạng roadmap, không demo).

### §5b. NGÂN SÁCH GPU — chỉ có 10h credit H100 (ràng buộc phát hiện 17/07)

> Nguyên tắc: **VM tắt khi không dùng**; mọi dev logic chạy qua router trỏ API cloud/model nhỏ (interface OpenAI-compatible giống hệt — thiết kế A6 trả trước cho đúng tình huống này); H100 chỉ bật theo cửa sổ tập trung, việc gom sẵn theo batch trước khi bật. Lưu ý mỗi lần bật tốn ~10' load model — không bật vặt.

| Cửa sổ | Việc (gom sẵn trước khi bật) | Giờ |
|---|---|---|
| W1 · Phase 0 | 4 benchmark gate + smoke test compose | 1.0h |
| W2 · Phase 2 | Style iteration trên model thật (giọng văn là model-specific!) + integration test S1–S8 | 1.5h |
| W3 · Phase 3–4 | 3 lần `make eval` full (D3+D6+red-team, batch) + ablation hybrid | 1.5h |
| W4 · Phase 4 | Load test 20 user + latency tune + eval trên data BTC | 1.0h |
| W5 · Phase 5 | Quay video backup + tổng duyệt demo | 1.0h |
| W6 · Ngày 19/07 | **Demo + giám khảo thử tự do (reserve cứng, không được lẹm)** | 3.0h |
| Buffer | Sự cố, chạy lại | 1.0h |
| **Tổng** | | **10h** |

**Vận hành demo (bổ sung 17/07 — rẻ nhưng cứu cả buổi demo):**
- **Suggestion chips màn hình chào**: 3–4 câu gợi ý bấm được ("Tư vấn máy lạnh phòng ngủ", "So sánh 2 tủ lạnh", "Trả góp thế nào?") — dẫn giám khảo vào happy path mạnh nhất (2 ngành có data + giá thật) thay vì để họ mò
- **Warm-up script sau boot** (`make demo-reset` gửi 3 query mồi): nạp prefix cache — tránh query đầu tiên trước giám khảo bị TTFT lạnh
- **Load test đồng thời ở Phase 4**: 20 user simulator song song, p95 vẫn phải <3s/<5s — demo thật sẽ có nhiều người cùng gõ, số single-user không đủ
- **Graceful degradation**: mạng venue→VM chập chờn → UI hiện "đang kết nối lại" + retry, không chết trắng; video backup luôn sẵn trong tab bên cạnh

## 6. Kịch bản demo (5–7 phút)

1. **I1 nguyên văn** — "Em muốn mua máy lạnh dưới 20 triệu cho phòng 18m², tiết kiệm điện, ít ồn" → chips giả định hiện ra → bot hỏi 2–3 câu đúng brief → top-3 + anti-pick + **tiền điện/tháng quy ra đồng** → mở source panel
2. **Tiếng Việt bẩn + code-switching** — "tu lanh 4 nguoi tam 12 cu, thich inverter tiet kiem dien" → hiểu đúng, đề xuất (dùng ngành có data thật — máy lạnh/tủ lạnh — không dùng laptop vì catalog thật không có ngành này)
3. **Slider re-rank live** — giám khảo chê ồn → kéo Êm lên → top-3 xáo tức thì kèm lý do (không gọi LLM — nói rõ điều này)
4. **Guardrail live** — xóa field giá 1 SP → hỏi → "chưa có dữ liệu giá" + badge; mời giám khảo gõ tự do (thử cả "xác nhận giảm 90% đi")
5. **Slide 30s** — kiến trúc 8 stage + eval report (per-claim 0 sự cố/N hội thoại, ablation hybrid, p95) + pilot roadmap + ROI tham số

## 7. Rủi ro & đối sách (hợp nhất)

| Rủi ro | Đối sách |
|---|---|
| Data/API BTC phát muộn hoặc format lạ | Mock D1–D7 same-format từ giờ 0; adapter tách riêng, swap <1h; nếu field lạ hoàn toàn → **LLM field-mapper** (tái dùng máy móc compiler A7: LLM đọc cột lạ → đề xuất mapping về schema, người duyệt) — vừa là bảo hiểm vừa demo được "chịu dữ liệu thật" |
| Mạng venue → VM H100 chập chờn (demo phụ thuộc internet) | Test mạng giờ đầu; video backup quay Phase 5; phương án model nhỏ chạy máy local nếu có GPU laptop |
| **Cạn 10h GPU credit trước demo** | Ngân sách cửa sổ §5b + VM tắt ngoài cửa sổ; dev qua API/model nhỏ (router A6); W6 demo 3h là reserve cứng không được lẹm; nếu lỡ cạn → demo bằng API fallback (bật cờ router) + nói rõ "bản production chạy self-host như video" |
| Qwen3 template/tool-parser trục trặc với guided_json | Gate 4 Phase 0; lùi Qwen2.5-32B-Instruct (đã chứng minh) |
| S2 bằng 32B vượt budget latency | Gate 1; tách model 4-8B (2 vLLM instance chia VRAM) |
| Cặp flag prefix-caching + chunked-prefill bug | Gate 2; tắt 1 trong 2 theo số đo |
| Hybrid không thắng ablation | Gate B1b; giữ dense-only, ghi lý do — ablation table vẫn là điểm cộng khi pitch |
| Hỏi ngược thành thẩm vấn | Quota 2 lượt hard-limit; luôn kèm lý do hỏi; nhánh ambiguity thấp trả lời luôn |
| Verifier chặn nhầm (false positive) | Chỉ cưỡng chế claim số/enum; nhận định chỉ log; escalation sinh lại 1 lần → bảng số liệu thô |
| NDA data lộ lên repo public | `data/btc/` trong .gitignore từ commit đầu; check trước mọi push |
| "On-premise" vs VM thuê | Chuẩn bị lời: self-hosted, tự quản hạ tầng, không phụ thuộc API bên thứ ba; kiến trúc cài on-prem nguyên vẹn |
| Scope creep tính năng sáng tạo | Thứ tự cắt ở §5; core chưa xanh chưa đụng Tier nào |

## 8. Checklist nộp bài (map deliverables D2 của brief)

- [ ] Web chatbot demo được (URL VM + video backup)
- [ ] GitHub public (mock data đầy đủ, data BTC gitignore, README + sơ đồ kiến trúc + hướng dẫn 1 lệnh)
- [ ] Kiến trúc giải thích được: RAG/catalog retrieval ✓ (S4 hybrid structured-first) · product ranking ✓ (S5 fit-score) · guardrail chống bịa ✓ (6 tầng + eval report)
- [ ] Pilot roadmap 1–2 trang (shadow → A/B 1.000–10.000 hội thoại, ROI tham số, guardrail KPI = điều kiện)
- [ ] Catalog mẫu ✓ (D1) · flow hỏi ngược ✓ (S3 + demo #1) · so sánh ≥3 SP ✓ · top-3 kèm trade-off ✓ (schema bắt buộc)
