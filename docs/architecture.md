# Kiến trúc NeedWise Copilot

## Mục tiêu phase skeleton

Hệ thống là monorepo gồm một Next.js storefront, một FastAPI service và PostgreSQL. Phase này ưu tiên luồng dữ liệu rõ ràng, khả năng test và các seam để thay mock advisor bằng pipeline AI ở phase sau.

```text
Browser
  └─ Next.js App Router
       ├─ TanStack Query ──────────────┐
       └─ Zustand (cart/compare/chat)  │
                                      ▼
                              FastAPI /api/v1
                               ├─ Routes
                               ├─ Services
                               │   ├─ Product/Comparison
                               │   └─ MockChat (rules)
                               └─ Repositories
                                      │
                                      ▼
                              SQLAlchemy 2 + PostgreSQL
```

## Ranh giới module

- `apps/web/app`: route và composition cấp trang.
- `apps/web/components`: UI tái sử dụng; không đọc mock JSON.
- `apps/web/lib/api.ts`: adapter HTTP duy nhất của storefront.
- `apps/web/stores`: client state có chủ đích; product catalog vẫn là server state.
- `apps/api/src/api`: HTTP validation và mapping endpoint, không query database.
- `apps/api/src/services`: use case và business rules.
- `apps/api/src/repositories`: SQL query, filter, sort và eager-loading.
- `apps/api/src/models`: persistence model đã chuẩn hóa.
- `data/demo/products.json`: nguồn dữ liệu demo dùng bởi seed, không dùng trực tiếp bởi UI.

## Mô hình dữ liệu

`categories 1—N products`; mỗi product có quan hệ 1—1 với `product_specs`, `prices`, `inventory` và promotion tùy chọn. Cách tách này cho phép phase sau lưu lịch sử giá, nhiều nguồn tồn kho hoặc nhiều promotion mà không làm thay đổi contract sản phẩm tổng hợp ở API.

## Hướng AI-native

`MockChatService` là strategy hiện tại. Có thể thay bằng orchestration gồm need extraction → catalog retrieval/RAG → deterministic filters → ranking engine → evidence/guardrail → response composer. `ProductRepository` và schema `Recommendation` là hai seam chính để thay đổi mà không buộc UI viết lại.

## Quyết định an toàn dữ liệu

- Recommendation chỉ dùng sản phẩm lấy từ repository.
- Trường không có dữ liệu giữ `null`; UI ghi “Chưa có dữ liệu”.
- Budget, diện tích và ưu tiên được trả lại trong context để flow HTTP stateless.
- Checkout, review và điểm phù hợp đang là demo, được ghi rõ trên UI/API.

