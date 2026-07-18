# Tham khảo kiến trúc: ProductAgent (arXiv 2407.00942)

> v1 · 18/07/2026 · Đọc trước khi viết orchestrator nhánh `tư_vấn` (S1→S8).
> Paper: **"ProductAgent: Benchmarking Conversational Product Search Agent with Asking Clarification Questions"** — Ye et al., Tsinghua + Alibaba DAMO Academy, 07/2024.
> Vì sao liên quan: cùng bài toán "product demand clarification" trên e-commerce (user vào với query mơ hồ → agent hỏi ngược → retrieval chính xác dần), có benchmark định lượng (ProClare, 1M sản phẩm AliMe KG, user simulator LLM) và ablation cho chính các quyết định ta đã chốt bằng lý luận.

---

## 1. Kiến trúc ProductAgent (tóm tắt)

3 module lõi + vòng lặp hội thoại 3 stage, **workflow cố định, không có tool router** ("the task... does not require a tool router" — trùng ADR A1 của ta):

```text
Mỗi turn:
  Stage 1  Category Analysis — demands → Text2SQL → SQL retrieval
           → tóm tắt candidates thành THỐNG KÊ (statistics per aspect)
  Stage 2  Item Search       — demands → NL query → dense retriever → items
  Stage 3  Question Gen      — demands + statistics → 3 câu hỏi trắc nghiệm
                               (mỗi câu kèm sẵn answer candidates)
  Trả về:  items ĐÃ retrieve + câu hỏi — cùng lúc, mỗi turn
```

- **Memory**: Q&A hỏi-đáp được chuyển thành **structured demand objects** (không giữ raw chat history); khi gọi tool chỉ inject phần cần thiết vào slot trong prompt. ≈ Need Profile của ta.
- **Database**: sản phẩm lưu song song SQL (exact match) + vector (relevance-ordered) — ≈ Postgres + pgvector của ta.
- 5 tool: Text2SQL, Category Analyze, Query Generation, Retriever, Question Generation.
- Eval: user simulator (GPT-3.5) chỉ được trả lời bằng candidates cho sẵn (tránh leak); đo MRR@10/HIT@10 theo từng turn; 5 turn agent/hội thoại.

## 2. Kết quả thực nghiệm đáng giá nhất

| # | Finding | Số liệu |
|---|---|---|
| F1 | Retrieval tăng đơn điệu theo số turn hỏi ngược | HIT@10 từ ~0 (turn 1) → 60–70 (turn 5) |
| F2 | **Statistics từ candidates là input quyết định** cho câu hỏi tốt: bỏ statistics hoặc lấy statistics ngẫu nhiên (bỏ qua demand hiện tại) đều sập | w/o stats HIT@10 = 15.6; random = 39.5; BM25-stats = **47.0** |
| F3 | Text2SQL là điểm gãy lớn nhất: SQL **trivial** (chạy được nhưng trả 0 dòng vì LLM gộp mọi demand thành query quá chặt) chiếm ~45–55% mọi LLM thử | GPT-4: 55.4% trivial, 3.5% invalid |
| F4 | Setting hội thoại: **BM25 thắng dense retriever** (câu trả lời của user chủ yếu là chính các option cho sẵn → exact-term match đủ); fusion naive không giúp | BM25 35.04 vs GTE 8.49 HIT@10 (GPT-3.5) |
| F5 | Câu hỏi trắc nghiệm kèm sẵn options → user simulator (và người thật) trả lời được ngay, không cần gõ tự do | — |

## 3. Đối chiếu với pipeline S1–S8 — cái gì được xác nhận

| Quyết định của ta | ProductAgent | Kết luận |
|---|---|---|
| ADR A1: workflow cố định, LLM chỉ quyết ở 2 nút | Cùng kết luận, bỏ hẳn tool router | ✅ giữ nguyên |
| S4 structured-first: SQL filter **map-driven từ slot** (không Text2SQL) | Text2SQL của họ fail ~50% dạng trivial (F3) | ✅ điểm gãy lớn nhất của họ **không tồn tại về mặt cấu trúc** trong thiết kế ta — giữ nguyên, không bao giờ đổi sang Text2SQL |
| S3b dynamic aspect discovery: chọn câu hỏi từ entropy trên **chính candidates hiện tại** | F2 chứng minh bằng ablation: câu hỏi phải ground vào thống kê candidates, không phải kiến thức nội tại LLM | ✅ đây là bằng chứng định lượng cho tính năng "hỏi ngược thông minh" (10% điểm) |
| Quick-replies đóng (canned options) thay vì bắt gõ tự do | F5 + chính format multi-choice của họ | ✅ đồng thời khớp bug-note hiện tại của FE (free text dead-loop) — hướng đúng là options-first |
| Adoption gate cho hybrid/dense (§6.4 điểm 5: chỉ bật nếu ablation thắng) | F4: dense **thua** BM25 trong hội thoại vì answer = option cho sẵn | ✅ gate là đúng; khả năng cao dense-rerank không cần cho nhánh tư_vấn (chỉ đáng cho sở thích mềm free-text) |
| Need Profile structured, không giữ raw history | Memory = structured demand objects | ✅ |
| Postgres + pgvector song song | SQL + vector DB song song | ✅ |

## 4. Cái ta làm KHÁC (và nên giữ khác)

- **Giới hạn 2 lượt hỏi/hội thoại** (UX bán lẻ, SLA <3s) vs 5 turn của họ (benchmark không có ràng buộc UX). F1 cho thấy càng hỏi càng chính xác — nhưng ta bù bằng S3 information-gain (hỏi ít câu giá trị cao) thay vì hỏi nhiều. Giữ cap = 2.
- **Câu hỏi sinh bằng rule + information gain** (S3, giải thích được trước giám khảo) vs LLM sinh câu hỏi của họ. Limitations của paper tự thừa nhận "in-context learning... not always optimal" — giữ rule-based.
- **Guardrail/verifier**: paper không có tầng chống hallucination nào (không phải mục tiêu của họ) — S7 + facts provenance là lợi thế riêng, giữ nguyên.

## 5. Bài học ÁP DỤNG vào orchestrator nhánh `tư_vấn`

1. **Thứ tự trong turn: prefilter TRƯỚC khi quyết định hỏi.** Vòng lặp của họ (retrieve → statistics → question) khớp đúng contract sẵn có của ta: `decide_policy(profile, candidate_count)` đã nhận `candidate_count` từ catalog_search. Orchestrator do đó phải chạy:
   `S1 → S2 (merge slot) → S4-prefilter (COUNT + candidates) → S3 → [ask | S5 → S6 → S7 → S8]`
   — **không** phải S3 trước S4 như cách đọc tuyến tính sơ đồ §6.1. Prefilter chạy cả ở turn hỏi ngược, không chỉ turn trả kết quả.
2. **Trả items kèm câu hỏi trong cùng turn hỏi ngược** ("timely feedback", Figure 2): khi S3 quyết định hỏi mà prefilter đã có ≤N candidates khá tốt, response `follow_up` nên đính kèm luôn top candidates tạm thời. Paper cho thấy đây là pattern UI tự nhiên; với ta là thay đổi nhỏ ở `ChatResponse` (cho phép `recommendations` không rỗng khi `response_type="follow_up"`) + FE render. **Đề xuất: làm ở v2**, không nằm trong happy-path v1 của orchestrator — nhưng thiết kế schema ngay từ đầu để không phải breaking-change.
3. **Statistics-driven question là chỗ đáng đầu tư nhất** (F2): khi wire S3 mức "Vừa", truyền phân bố thuộc tính của candidates hiện tại (đã có `compute_information_gain` precompute + entropy runtime theo kế hoạch S3b) — ablation của paper là số liệu trích dẫn được cho pitch "hỏi ngược thông minh".
4. **Eval harness dùng user simulator LLM** (ProClare §5.4): mô phỏng khách bằng LLM *chỉ được trả lời bằng quick-replies cho sẵn* (tránh information leak — trick đáng học), đo Hit@3 theo turn trên Customer Need Scenarios. Rẻ, tự động, chạy được trong `make eval` — đúng Tầng 6 guardrail. Ghi vào backlog eval (`dmx-data-eval-roi-plan.md`).
5. **Không cần rerank/fusion cho v1** (F4): BM25/SQL-filter thuần đủ khi input là quick-replies. Để nguyên adoption gate, ưu tiên thời gian 48h cho orchestrator + S8.

## 6. Điều KHÔNG bê nguyên từ paper

- Text2SQL (F3 — chính họ fail).
- 3 câu hỏi trắc nghiệm/turn × 5 turn — quá nặng cho UX bán lẻ thật; ta gom ≤3 slot vào 1 tin nhắn, tối đa 2 lượt.
- Dense retrieval mặc định ở vòng item search (F4 — chính họ đo được là thua BM25 trong hội thoại).
- Category Analyze bằng LLM mỗi turn (thêm 1 LLM call/turn vào latency budget; entropy/statistics của ta tính bằng Python thuần, ~0ms).
