# Kiến trúc NeedWise Copilot

> **Trạng thái (18/07):** Tài liệu này mô tả kiến trúc đã **chốt** sau vòng research 17/07 (bản đồ tài liệu: `docs/research/dmx-phan-tich-ke-hoach-2026-07-17.md` §1) — cả phần đã build (skeleton) lẫn phần sắp build (pipeline AI-Native). Phần chưa build được đánh dấu rõ bên dưới. Chi tiết luồng 8 stage, ADR và guardrail nằm ở `docs/research/`; `docs/pipelines.md` §6 là bản tóm tắt để code theo hằng ngày.

## Mục tiêu

Hệ thống là monorepo gồm một Next.js storefront, một FastAPI service, PostgreSQL, và — khi lên AI-Native — một LLM qua API (Qwen3.6-27B, OpenRouter — ADR A2'', không tự host). Phase skeleton (đã xong) ưu tiên luồng dữ liệu rõ ràng, khả năng test và các seam để thay mock advisor bằng pipeline AI thật; pipeline đó nay đã có kiến trúc chốt.

```text
Browser
  └─ Next.js App Router
       ├─ TanStack Query ──────────────┐
       └─ Zustand (cart/compare/chat)  │
                                      ▼
                              FastAPI /api/v1  ◄──router OpenAI-compatible (ADR A6)──  OpenRouter API
                               ├─ Routes                                              (Qwen3.6-27B,
                               ├─ Services                                             ADR A2'', §6.9)
                               │   ├─ Product/Comparison
                               │   ├─ MockChat (rules — đang chạy)
                               │   └─ Pipeline S1–S8 (kế hoạch — xem pipelines.md §6)
                               ├─ Tools (5 MCP-compatible — ADR A5, kế hoạch)
                               ├─ Verifier (per-claim — ADR C6, kế hoạch)
                               └─ Repositories
                                      │
                                      ▼
                    SQLAlchemy 2 + PostgreSQL
                    (catalog + pgvector HNSW + BM25/FTS + pg_trgm — kế hoạch, ADR nhóm B)
```

## Frontend framework — quyết định giữ Next.js (18/07)

`docs/research/dmx-tech-decisions.md` ADR D2 (research 17/07) từng chốt Vite + React SPA để tránh SSR. Skeleton thực tế đã build bằng **Next.js 15 App Router** trước khi ADR đó được áp dụng (xem `git log`: commit data/research đi trước commit skeleton). Với ngân sách 48h còn lại, team quyết định **giữ Next.js** thay vì viết lại `apps/web` — xem ADR D2' (bản superseded) trong `dmx-tech-decisions.md`.

Hệ quả cho code: khu vực cần control UI thật và không được lẫn cache SSR (chat widget, slider re-rank, source panel) dùng Client Component (`"use client"`) + TanStack Query; SSE đọc trực tiếp bằng `fetch`/`ReadableStream` trong Client Component, không proxy qua Next.js Route Handler (thêm hop → chậm TTFT).

## Ranh giới module

**Đã có (skeleton):**

- `apps/web/app`: route và composition cấp trang.
- `apps/web/components`: UI tái sử dụng; không đọc mock JSON.
- `apps/web/lib/api.ts`: adapter HTTP duy nhất của storefront.
- `apps/web/stores`: client state có chủ đích; product catalog vẫn là server state.
- `apps/api/src/api`: HTTP validation và mapping endpoint, không query database.
- `apps/api/src/services`: use case và business rules (hiện có `MockChatService`).
- `apps/api/src/repositories`: SQL query, filter, sort và eager-loading.
- `apps/api/src/models`: persistence model đã chuẩn hóa.
- `data/demo/products.json`: nguồn dữ liệu demo dùng bởi seed, không dùng trực tiếp bởi UI.

**Kế hoạch (AI-Native, chưa build — đọc `docs/pipelines.md` §6 trước khi tạo các thư mục này):**

- `apps/api/src/pipeline/`: stage S1–S8, mỗi stage một module, theo `dmx-ai-workflow-v1.md` §3.
- `apps/api/src/tools/`: 5 tool MCP-compatible (`catalog_search`, `price_promo_stock`, `policy_faq`, `review_summary`, `need_profile`) — ADR A5.
- `apps/api/src/router/`: client OpenAI-compatible trỏ API OpenRouter (Qwen3.6-27B, ADR A2''), fallback chưa chọn provider thứ 2 — ADR A6. Đã build, xem `apps/api/src/router/client.py`.
- `apps/api/src/verifier/`: per-claim verification, numeric/enum matching — ADR C6.
- `apps/api/src/compiler/` (batch, ngoài request path): Category Profile Compiler — ADR A7.

## Mô hình dữ liệu

**Đã có:** `categories 1—N products`; mỗi product có quan hệ 1—1 với `product_specs`, `prices`, `inventory` và promotion tùy chọn.

**Kế hoạch mở rộng (ADR nhóm B, D4):**

- `products`: thêm cột embedding mô tả (pgvector HNSW) cho hybrid rerank, và index `pg_trgm` cho fuzzy match tên/mã model.
- Full-text index (`tsvector`/`pg_textsearch`) trên mô tả sản phẩm cho nhánh lexical của hybrid search.
- `category_profile`: output JSON của Category Profile Compiler (slot schema, luật quy đổi, information gain) — AI sinh, chuyên gia duyệt.
- `policy_chunk`: chunk tài liệu chính sách (bảo hành, trả góp, giao lắp), theo heading 300–500 token, giữ `(tài_liệu, mục, hiệu_lực_từ)` cho citation.
- `need_profile_log`: snapshot Need Profile mỗi turn — **chỉ để audit/eval**; session state runtime là in-memory dict + TTL (ADR C7), không phải bảng này.
- `audit_log`: timing từng stage S1–S8, tokens, tool calls, verifier verdict, claims (mask PII, không log giá vốn).

Cách tách này vẫn cho phép lưu lịch sử giá, nhiều nguồn tồn kho hoặc nhiều promotion mà không làm thay đổi contract sản phẩm tổng hợp ở API — nguyên tắc gốc giữ nguyên khi mở rộng cho AI-Native.

## Kiến trúc AI-Native — tóm tắt

`MockChatService` là strategy hiện tại (rule-based, 3 bước hỏi cố định). Kiến trúc thay thế **đã chốt**: workflow **cố định** 8 stage S1→S8 — **không phải agent loop tự do** (ADR A1) — trong đó LLM chỉ quyết định tại 2 nút: intent routing (S2) và nội dung câu hỏi/tư vấn (S6). `ProductRepository` và schema `Recommendation` vẫn là hai seam chính để thay pipeline mà không buộc UI viết lại — đúng như thiết kế skeleton ban đầu. Chi tiết đầy đủ 8 stage, Need Profile, hybrid retrieval, tools/router, Category Profile Compiler và interface mới: xem `docs/pipelines.md` §6.

## Guardrail — chống hallucination (7 tầng, `dmx-guardrail-design.md`)

| Tầng | Cơ chế |
|---|---|
| 0. Data | Giá vốn không vào DB; fact nào cũng mang provenance; null là null |
| 1. Generation | LLM chỉ thấy `<facts>`; số liệu đến từ template điền sẵn, LLM diễn đạt không sáng tác |
| 2. Verifier | Tách atomic claims sau sinh, đối chiếu ngược facts JSON; lệch → sửa/cắt + log |
| 3. Honesty | Thiếu data nói thiếu; data cũ ghi thời điểm; nguồn mâu thuẫn có luật ưu tiên |
| 4. Tone | Không ép mua, không tuyệt đối hóa; mọi card bắt buộc có trade-off (ép bằng schema) |
| 5. Audit | Source panel mỗi câu trả lời hiện trên UI; mask PII; không lưu hội thoại thật |
| 6. Eval | Metric per-claim rate + red-team set — chứng minh bằng số |

## Quyết định an toàn dữ liệu

- Recommendation chỉ dùng sản phẩm lấy từ repository.
- Trường không có dữ liệu giữ `null`; UI ghi "Chưa có dữ liệu".
- Budget, diện tích và ưu tiên được trả lại trong context để flow HTTP stateless (kế hoạch: mở rộng thành toàn bộ Need Profile thay vì 3 field rời — xem `docs/pipelines.md` §6.10).
- Checkout, review và điểm phù hợp đang là demo, được ghi rõ trên UI/API.
- (Kế hoạch) Product card render thẳng từ facts JSON của S5, không qua LLM — xác suất hallucination = 0 tuyệt đối về mặt cấu trúc cho phần chứa nhiều fact nhất (ADR C5).
