# Quyết định kỹ thuật cho AI Workflow — ADR rút gọn

> v1 · 17/07/2026 · Áp cho `dmx-ai-workflow-v1.md` (S1–S8) · Hạ tầng: 1× H100 80GB
> Format mỗi quyết định: **Chọn** → thay vì → vì → rủi ro & lối thoát. Những mục đánh dấu 🧪 phải benchmark xác nhận ở Phase 0.

---

## Nhóm A — Điều phối & Model

### A1. Kiến trúc điều phối: Workflow cố định + LLM ở các nút quyết định — KHÔNG phải free agent loop
- **Chọn**: pipeline S1→S8 cố định; LLM quyết định tại 2 nút: intent routing (S2) và nội dung câu hỏi/tư vấn (S6); nhánh rẽ S3 bằng rule tường minh
- **Thay vì**: agent loop tự do (LLM tự chọn tool, tự lặp đến khi xong)
- **Vì**: (1) SLA <3s/<5s — agent loop tự do có số vòng lặp không đoán được, mỗi vòng +1 lần LLM call; (2) demo trước giám khảo cần deterministic — cùng câu hỏi phải ra cùng hành vi; (3) đúng guidance ngành: workflow cho bài toán có cấu trúc rõ, agent cho bài toán mở
- **Trình bày với giám khảo**: đây vẫn là "agentic workflow" — LLM là bộ não định tuyến + diễn đạt, tools là MCP-compatible; điểm AI-Native nằm ở "LLM quyết định hỏi gì/khi nào đủ", không nằm ở vòng lặp tự do
- **Rủi ro**: câu hỏi ngoài luồng thiết kế → lối thoát: intent `hỏi_chi_tiết_SP` có nhánh function-calling tự do (hermes parser) trong phạm vi 4 tool read-only

### A2. Model chính: Qwen3-32B FP8, tắt thinking mode 🧪
- **Chọn**: `Qwen3-32B` FP8 trên vLLM, `enable_thinking=False` (chat template arg) — thinking mode đốt token + phá latency budget
- **Thay vì**: Qwen2.5-32B-Instruct (cũ hơn nhưng đã chứng minh; là fallback nếu Qwen3 gặp vấn đề template/tool parser) · 72B (đã loại — VRAM/latency, xem phân tích trước) · 14B (dự phòng nếu benchmark 32B không đạt p95)
- **Rủi ro**: chất lượng tiếng Việt 32B kém kỳ vọng → lối thoát đã cài sẵn: eval harness so 32B vs 14B vs cloud API trên D3/D6 ngay Phase 0, số quyết định chứ không phải cảm giác

### A3. Một model dùng chung cho S2 + S6 trước, chỉ tách khi benchmark bắt buộc 🧪
- **Chọn**: 32B làm cả extraction (S2) lẫn generation (S6); S2 dùng prompt ngắn + guided decoding + prefix caching → nhanh
- **Thay vì**: router 2 model ngay từ đầu (4-8B cho S2) — 2 vLLM instance chia VRAM (`--gpu-memory-utilization 0.55/0.25`) là làm được nhưng +1 điểm hỏng, +ops
- **Vì**: đơn giản vận hành trong 48h; prefix caching hiệu quả nhất khi mọi request cùng model; VRAM dư cho KV cache lớn
- **Ngưỡng chuyển**: nếu S2 p95 > 700ms trên benchmark Phase 0 → tách model nhỏ (kế hoạch B đã mô tả trong workflow doc)

### A4. Structured output: vLLM guided decoding (xgrammar) với Pydantic schema
- **Chọn**: `guided_json` cho S2 (slot extraction) và mọi output có cấu trúc — đảm bảo 100% JSON hợp lệ về mặt cú pháp, không bao giờ lỗi parse
- **Thay vì**: prompt "hãy trả JSON" + try/except reparse (mong manh, tốn retry = tốn latency) · function-calling cho extraction (vòng vo hơn guided_json)
- **Lưu ý**: guided decoding chặn cú pháp chứ không chặn ngữ nghĩa — slot sai giá trị vẫn phải nhờ eval D3/D6 bắt

### A5. Tool layer: hàm Python + schema MCP-compatible; thực thi deterministic theo stage
- **Chọn**: 5 tool (`catalog_search`, `price_promo_stock`, `policy_faq`, `review_summary`, `need_profile`) là hàm Python có JSON schema chuẩn MCP; pipeline gọi trực tiếp ở S4; chỉ nhánh `hỏi_chi_tiết_SP` cho LLM tự chọn tool (hermes tool parser)
- **Vì**: giữ câu chuyện MCP (thế mạnh đội + rubric AI-Native) mà không trả giá latency của LLM-driven tool selection ở luồng chính
- **Thay vì**: dựng MCP server riêng qua stdio/SSE — wrapper trình diễn được thêm sau nếu dư giờ, không nằm trên đường găng

### A6. Router & fallback: client OpenAI-compatible + router tự viết ~50 dòng
- **Chọn**: mọi LLM call qua interface chung trỏ local vLLM; timeout/5xx → retry 1 lần → fallback cloud API (config bật/tắt — **tắt khi demo** để thuần on-prem, bật khi dev)
- **Thay vì**: LiteLLM proxy (thêm 1 service + config surface; tính năng dùng thật chỉ là fallback — 50 dòng tự viết rẻ hơn nợ vận hành)

### A7. Logic tư vấn ngành hàng: AI-sinh + người duyệt + runtime compiled — KHÔNG phải dev viết config (bổ sung 17/07)
- **Chọn**: Category Profile Compiler — pipeline LLM offline chạy lúc ingest: đọc catalog fields/phân bố + guide corpus → sinh slot schema + luật quy đổi (có citation) + câu hỏi mẫu + information gain → auto-check actionable → chuyên gia duyệt → xuất profile JSON cho runtime; kèm dynamic aspect discovery ở runtime (S3b) làm lưới an toàn; luật tư vấn đi qua RAG guide corpus có citation thay vì hardcode
- **Thay vì**: (a) YAML dev viết tay thuần (vi phạm tinh thần H2 "AI cần hiểu", chết khi thêm ngành mới, yếu Startup Potential) · (b) LLM tự do suy luận runtime không schema (không kiểm soát được quota hỏi, latency, không eval được, rủi ro bịa luật)
- **Vì**: đây là điểm giao đúng của 2 yêu cầu mâu thuẫn — "AI hiểu" (H2 + AI-Native 20%) và "deterministic + <3s" (H3); nghiên cứu nền: Slot Schema Induction (LLM tự dựng schema từ dữ liệu — TACL 2026), BEATS/AutoPKG (bootstrap attribute taxonomy từ catalog e-commerce)
- **Scoping 48h**: YAML v0 tay ở Phase 0 (bootstrap + fallback) → compiler v0 Phase 3 (so output với bản tay trên 4 ngành = validation) → demo "thêm ngành robot live" Phase 4 nếu xanh
- **Rủi ro**: compiler sinh slot rác → auto-check actionable + expert gate chặn; sinh luật sai → luật phải có citation từ guide corpus, không có nguồn thì không vào profile

### A8. KHÔNG fine-tune model trong hackathon — style bình dân giải bằng prompt + template + glossary (bổ sung 17/07, ràng buộc 10h GPU credit)
- **Chọn**: đạt "ngôn ngữ bình dị, ít thông số" bằng 4 đòn bẩy không-training: (1) system prompt style guide + 2–3 few-shot mẫu giọng chuẩn; (2) statement templates + cards đã tách thông số ra khỏi lời văn về mặt cấu trúc; (3) **bảng quy đổi cảm nhận** (glossary tool: inverter → "tự điều chỉnh công suất, đỡ tốn điện"; 24dB → "êm hơn tiếng thì thầm"; BTU → "sức làm lạnh") — deterministic, nhét vào template; (4) vòng lặp prompt-eval: LLM-judge câu #2 "bình dân" chấm → sửa prompt → chạy lại, đạt hiệu quả của fine-tune với chi phí ≈0 GPU
- **Thay vì**: LoRA/QLoRA SFT trên 32B — bị loại vì: (a) style là bài prompt giải tốt với instruct model 32B, fine-tune là dùng búa tạ đóng đinh mũ; (b) không có dataset (cần hàng nghìn cặp hội thoại tư vấn giọng chuẩn — tự sinh + QA tốn hơn 10h credit hiện có); (c) rủi ro thật: SFT lệch làm **thoái hóa tool-calling/guided-JSON** — vỡ S2 là vỡ cả pipeline; (d) mỗi giờ training = một giờ mất khỏi serving/demo trong quỹ 10h
- **Roadmap pilot** (nói trong pitch nếu bị hỏi): sau 3 tháng pilot có corpus hội thoại thật → LoRA style + DPO từ feedback nhân viên duyệt — lúc đó mới có data và có lý
- **Hệ quả ràng buộc 10h credit**: mọi dev logic chạy qua router (A6) trỏ **API cloud/model nhỏ local**; H100 chỉ bật theo **cửa sổ tập trung** (xem ngân sách GPU trong master plan §5b); style iteration bắt buộc làm trong cửa sổ H100 vì giọng văn là thứ model-specific

## Nhóm B — Data & Retrieval

### B1. Store chính: PostgreSQL (catalog + Need Profile log + audit log)
- **Chọn**: Postgres 16 trong docker-compose, SQLAlchemy 2.0
- **Thay vì**: SQLite (đủ cho demo nhưng câu chuyện Deployment 15% + đường pgvector yếu hơn) · MongoDB (catalog là dữ liệu quan hệ có schema — không có lý do)

### B2. Vector + hybrid search: pgvector + BM25/FTS ngay trong Postgres (REVISED v2 — 17/07, sau đánh giá hybrid)
- **Chọn**: dense = pgvector (HNSW); lexical = BM25 trong Postgres (pg_textsearch — production-ready 2026; fallback: tsvector FTS config `simple` + unaccent); fusion = **RRF trong SQL** (~30 dòng, rank-based)
- **Vì**: (1) hybrid lexical+dense là mặc định production 2026 — dense-only trượt exact token ("inverter", mã SP trong mô tả), lexical-only trượt paraphrase ("êm" ↔ "độ ồn thấp"); (2) **filter cứng + hybrid + join nằm trong MỘT query Postgres** — structured-first thành 1 câu SQL, không dual-write; (3) stock/price update từ API → search phản ánh cùng transaction (hợp câu chuyện freshness của guardrail); (4) compose giữ nguyên 4 service; (5) trần ~10M vector của pgvector thừa xa cho catalog điện máy
- **Điểm chèn hybrid**: chỉ 2 chỗ — (a) rerank mô tả/review sau SQL filter, (b) policy/FAQ RAG. Hard constraints vẫn SQL thuần; tên SP vẫn trigram/fuzzy (B4) — BM25 không thay được vì fail với typo
- **Bẫy phải né**: KHÔNG blend điểm BM25 + cosine theo trọng số (thang điểm không tương thích — BM25 unbounded, cosine [-1,1]) → bắt buộc RRF trên rank
- **Thay vì**: FAISS in-memory (quyết định v1 — bị thay vì không có chân lexical, index rời data phải rebuild khi swap data BTC) · Qdrant (runner-up tốt: hybrid dense+sparse server-side có sẵn, container nhẹ — nhưng dual-write Postgres↔Qdrant phải sync stock/price, thêm điểm hỏng) · Milvus (etcd+minio, quá nặng) · Weaviate/Elasticsearch (nặng hơn không thêm giá trị ở scale này)
- **Adoption gate 🧪**: hybrid chỉ được bật nếu ablation trên eval (dense vs lexical vs hybrid-RRF, xem `dmx-data-eval-roi-plan.md` §B1b) cho Hit@3/Recall@3 tốt hơn hoặc bằng ở mọi slice — quyết định bằng số, không bằng niềm tin
- **Nâng cấp nếu chân lexical yếu trên eval**: bge-m3 xuất được cả sparse (learned lexical, mạnh cho code-switching) — pgvector 0.7+ có `sparsevec`, giữ nguyên kiến trúc

### B3. Embedding: `AITeamVN/Vietnamese_Embedding` chạy in-process 🧪
- **Chọn**: sentence-transformers trong process FastAPI; benchmark CPU vs GPU-share ở Phase 0 (query 1 câu/lượt — CPU có thể đủ, khỏi tranh VRAM)
- **Thay vì**: bge-m3 gốc (fallback nếu bản finetune kém trên code-switching — eval quyết định) · dựng TEI server riêng (thêm service không cần thiết ở quy mô này)

### B4. Tìm theo tên sản phẩm: fuzzy string match, KHÔNG embedding
- **Chọn**: rapidfuzz + Postgres `pg_trgm` cho câu kiểu "con FTKY35 với XU12 con nào hơn" — mã model là chuỗi ký hiệu, embedding biểu diễn kém trong khi trigram/fuzzy bắt chính xác kể cả gõ thiếu
- **Nguyên tắc chung rút ra**: semantic search chỉ dành cho *sở thích mềm diễn đạt bằng lời* ("chạy êm", "sang trọng"); mọi thứ có cấu trúc (tên, mã, giá, công suất) đi đường exact/fuzzy/SQL

### B5. Policy chunking: theo heading, 300–500 token, giữ metadata mục
- Chunk mang `(tài_liệu, mục, hiệu_lực_từ)` → citation trong câu trả lời trỏ được về đúng mục chính sách — cùng cơ chế provenance với catalog

## Nhóm C — Quyết định theo stage

### C1 (S1). Chuẩn hóa: regex + từ điển thuần Python, không thư viện NLP tiếng Việt
- **Chọn**: bảng dict ngành hàng tự xây (~100 entry) + regex tiền/đơn vị; lấy **lexicon NSW** của ViSoLex làm dữ liệu tra cứu nếu tích hợp nhanh
- **Thay vì**: underthesea/pyvi (không cần word segmentation — LLM đọc thẳng), full pipeline model ViSoLex (nặng, thêm model phải load; 48h không đáng), model khôi phục dấu riêng (Qwen 32B đọc tốt không dấu — đã quyết định trong workflow doc)
- **Nguyên tắc**: S1 chỉ làm việc *chắc chắn đúng* (đơn vị, tiền, viết tắt trong dict); mọi thứ mơ hồ để LLM xử lý với cả text gốc lẫn text chuẩn hóa

### C2 (S2). Extraction: guided_json + few-shot từ chính D3, context cắt gọn
- Context = Need Profile hiện tại + **4 lượt gần nhất** (không full history — latency + không cần); temperature 0; few-shot 3–4 ví dụ phủ: không dấu, code-switching, đổi ý
- Schema Pydantic sinh từ **YAML slot config per category** (single source of truth — thêm ngành hàng không sửa code)

### C3 (S3). Dialogue policy: rule thuần + LLM chỉ viết lời
- Đếm candidates = 1 câu SQL COUNT trên filter hiện có (~5ms); ngưỡng ambiguity (5/20) là config; information gain per slot **precompute** từ phân bố catalog lúc ingest (entropy — script offline, không tính runtime)
- Văn bản câu hỏi: LLM sinh (ngắn, ~50 token, stream) từ guide "hỏi slot X, Y vì lý do Z, kèm thống kê candidates" — tự nhiên hơn template khô; template bank là fallback khi LLM lỗi
- **Vì sao không để LLM tự quyết hỏi-hay-không**: quyết định này phải nhất quán và giải thích được trước giám khảo ("vì sao bot hỏi câu này?" → chỉ vào rule + số), LLM tự quyết là hộp đen + không kiểm soát được quota 2 lượt

### C4 (S5). Scoring: trọng số YAML per category; field thiếu = trung tính + cờ honesty
- Field thiếu **không phạt về 0** — data bẩn không được giết sản phẩm tốt; SP thiếu field quan trọng bị gắn cờ → câu tư vấn nêu "chưa có dữ liệu độ ồn của mẫu này"
- Trọng số khởi tạo từ ưu tiên khách nói (slot `ưu_tiên`), user chỉnh qua slider (tính năng 1.2) — cùng một hàm score phục vụ cả hai

### C5 (S6). Product cards render THẲNG từ dữ liệu S5 — LLM không đụng vào card
- **Chọn**: UI card (tên, giá, khuyến mãi, tồn kho, badge, bảng nhu-cầu-làm-hàng) render từ JSON của S5/facts — **không đi qua LLM**; LLM chỉ viết phần lời dẫn tư vấn + trade-off narrative
- **Vì**: phần chứa nhiều fact nhất (giá, %, thông số) có **xác suất hallucination = 0 tuyệt đối** về mặt cấu trúc; verifier S7 chỉ còn phải soi phần prose → nhẹ và nhanh hơn
- Đây là quyết định chống bịa mạnh nhất toàn hệ thống — nói rõ trong slide kiến trúc

### C6 (S7). Verifier: numeric/enum matching thuần, KHÔNG NLI model trong 48h
- **Chọn**: regex claim extraction + bảng chuẩn hóa đơn vị + so khớp về facts JSON (~200 dòng Python, <50ms)
- **Vì**: 4 loại fact bắt buộc theo đề (thông số, giá, tồn kho, khuyến mãi) đều là số/enum — numeric matching phủ đủ yêu cầu chấm điểm; NLI model = +1 model load + latency + rủi ro false positive, giá trị biên thấp
- Text claim (nhận định) → log-only như đã chốt trong guardrail doc; NLI ghi vào roadmap pilot

### C7. Session state: in-memory dict + TTL, interface tách riêng
- Demo 1 server → in-memory đủ; `SessionStore` là interface → Redis là 1 class thay thế khi pilot (đã có sẵn trong compose comment-out)

## Nhóm D — Giao vận & Observability

### D1. API: FastAPI + SSE (POST → text/event-stream)
- **Thay vì** WebSocket: chat là streaming một chiều, SSE đơn giản hơn (không quản lý connection state), proxy/firewall thân thiện hơn cho demo venue

### D2. Frontend: Vite + React + Tailwind (SPA, không SSR) — ⚠️ SUPERSEDED (18/07, xem D2')
- **Chọn (gốc)**: SPA Vite + React + Tailwind
- **Vì**: slider re-rank (1.2) + card nhu-cầu-làm-hàng (1.4) + panel nguồn dữ liệu cần control UI thật
- **Thay vì**: Streamlit/Gradio — không đủ control cho các tính năng Tier 1, và nhìn "notebook demo" thay vì "sản phẩm" (ảnh hưởng Startup Potential); Next.js — SSR không cần cho demo local, thêm phức tạp
- **Ghi chú superseded**: skeleton thực tế đã build bằng Next.js 15 App Router trước khi ADR này được đọc/áp dụng (xem `git log`: commit data/research đi trước commit skeleton). Giữ nguyên lý luận gốc để tham khảo khi pilot có thời gian đánh giá lại framework.

### D2'. Frontend (revised 18/07): giữ Next.js 15 App Router, dùng như SPA-nặng cho phần cần control UI thật
- **Chọn**: giữ nguyên `apps/web` (Next.js 15 + React 19) đã build; các khu vực cần control tương tác cao và không được lẫn cache SSR (chat widget, slider re-rank 1.2, bảng nhu-cầu-làm-hàng 1.4, source panel) dùng Client Component (`"use client"`) + TanStack Query, không dùng Server Component data-fetching cho các phần này
- **Vì**: skeleton đã chạy, có test, có Docker build; viết lại sang Vite tốn thời gian không có trong ngân sách 48h (xem `dmx-phan-tich-ke-hoach-2026-07-17.md` §5) và không đổi điểm rubric (Deployment/Feasibility không chấm framework cụ thể)
- **Điểm cần cẩn thận**: SSE streaming (D1) từ FastAPI phải được đọc bằng `fetch` + `ReadableStream` ngay trong Client Component, KHÔNG proxy qua Next.js Route Handler — proxy thêm 1 hop làm chậm TTFT, đúng rủi ro mà ADR D2 gốc từng lo ngại về SSR/streaming. Chi tiết implementation xem `docs/pipelines.md` §3.10 và §6.10

### D3. Đóng gói: docker-compose 4 service, 1 lệnh
```
vllm (image chính thức, --model Qwen3-32B FP8, prefix-caching + chunked-prefill 🧪 test cặp flag này)
api  (FastAPI: pipeline S1–S8, tools, verifier, eval endpoints)
web  (Vite build tĩnh, nginx)
postgres (catalog + audit; pgvector extension sẵn nhưng chưa dùng)
```
- Healthcheck từng service; `make up / make eval / make demo-reset`; `.env` chọn model → đổi 14B/32B không sửa code

### D4. Observability: middleware timer per stage → audit log Postgres, loguru JSON
- Mỗi turn ghi: timing từng stage S1–S8, tokens, verifier verdicts, tool calls — **eval harness và dashboard 2.1 đọc cùng bảng này** (một nguồn số liệu, ba người dùng: dev, eval, pitch)

---

## Tổng hợp: 4 việc PHẢI benchmark ở Phase 0 (quyết định treo)

| # | Câu hỏi | Cách đo | Quyết định treo |
|---|---|---|---|
| 1 | 32B FP8 đạt p95 S2 <700ms, S6 TTFT <1s? | `vllm bench serve` + 20 request mẫu | A3 tách model nhỏ hay không |
| 2 | Cặp flag prefix-caching + chunked-prefill ổn trên version vLLM đang dùng? | benchmark có/không từng flag | D3 flag cuối cùng |
| 3 | Embedding CPU đủ nhanh (<30ms/query)? | timeit 100 query | B3 CPU hay GPU-share |
| 4 | Qwen3-32B tắt thinking hoạt động sạch với guided_json + hermes tools? | 10 call thử | A2 giữ Qwen3 hay lùi Qwen2.5 |
