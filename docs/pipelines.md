# Pipeline Backend và Frontend — NeedWise Copilot

Tài liệu này mô tả cách dữ liệu và request đi xuyên suốt hệ thống, cách build/test/deploy từng phần, và những điểm mở rộng dự kiến cho các phase AI-Native tiếp theo.

## 1. Tổng quan hệ thống

> **Trạng thái (18/07):** Sơ đồ dưới mô tả hệ thống skeleton hiện tại (đang chạy). Pipeline AI-Native đã **chốt kiến trúc** ở §6 — khi build xong sẽ thêm service `vllm` và chuyển `/chat/messages` sang SSE, không đổi `/products`/`/compare`.

```text
Browser
  │
  │ HTTP/JSON
  ▼
Next.js Web :3000
  │
  │ REST /api/v1
  ▼
FastAPI :8000
  │
  │ SQLAlchemy 2
  ▼
PostgreSQL :5432
```

Các nguyên tắc chính:

- Frontend không đọc trực tiếp `data/demo/products.json`.
- Product catalog là server state, được quản lý bằng TanStack Query.
- Cart, comparison và trạng thái giao diện chat là client state, được quản lý bằng Zustand.
- FastAPI route chỉ xử lý HTTP, validation và dependency injection; không query database trực tiếp.
- Business rule nằm trong service; SQL query nằm trong repository.
- Recommendation chỉ sử dụng product tồn tại trong database.
- Trường dữ liệu không có giá trị được giữ là `null`; frontend hiển thị “Chưa có dữ liệu”.
- **(Kế hoạch, §6)** Chat endpoint chuyển sang SSE streaming; mọi LLM call đi qua router nội bộ trỏ vLLM tự host, không gọi thẳng API ngoài (ADR A6).

---

# 2. Backend pipeline

## 2.1. Cấu trúc các tầng

```text
Request
  ▼
FastAPI Router
  ▼
Pydantic Schema
  ▼
Service / Use Case
  ▼
Repository
  ▼
SQLAlchemy Session
  ▼
PostgreSQL
```

| Tầng | Thư mục | Trách nhiệm |
|---|---|---|
| Application bootstrap | `apps/api/src/main.py` | Khởi tạo FastAPI, CORS, logging và router |
| Router | `apps/api/src/api/v1` | Nhận request, parse query/body và trả HTTP response |
| Schema | `apps/api/src/schemas` | Validate request/response bằng Pydantic v2 |
| Service | `apps/api/src/services` | Business rules, comparison và chat flow |
| Repository | `apps/api/src/repositories` | Query, filter, sort và pagination |
| Model | `apps/api/src/models` | Mapping bảng SQLAlchemy 2 |
| Database core | `apps/api/src/core/database.py` | Engine, session factory và dependency `get_db` |
| Migration | `apps/api/alembic` | Quản lý version schema database |
| Seed | `apps/api/src/seed` | Đưa dữ liệu demo vào database theo cách idempotent |

## 2.2. Pipeline khởi động API

Khi chạy bằng Docker Compose:

```text
postgres container start
  ▼
pg_isready healthcheck
  ▼
postgres = healthy
  ▼
api container start
  ▼
alembic upgrade head
  ▼
python -m src.seed.seed_products
  ▼
uvicorn src.main:app
  ▼
GET /api/v1/health
  ▼
api = healthy
```

Lệnh khởi động API được cấu hình để migration và seed hoàn tất trước khi Uvicorn nhận traffic. Seed kiểm tra SKU đã tồn tại, vì vậy restart container không tạo product trùng lặp.

## 2.3. Pipeline database migration

### Khi khởi tạo môi trường

```text
Alembic đọc alembic.ini
  ▼
env.py nạp DATABASE_URL từ Settings
  ▼
Nạp toàn bộ SQLAlchemy metadata
  ▼
Chạy các revision chưa được áp dụng
  ▼
Cập nhật bảng alembic_version
```

### Khi thay đổi model

1. Sửa model trong `apps/api/src/models`.
2. Tạo revision:

   ```bash
   docker compose run --rm api alembic revision --autogenerate -m "describe change"
   ```

3. Kiểm tra thủ công hàm `upgrade()` và `downgrade()`.
4. Chạy migration trên database development.
5. Chạy backend tests.
6. Không chỉnh sửa revision đã được triển khai ở môi trường dùng chung; tạo revision mới.

## 2.4. Pipeline seed sản phẩm

```text
data/demo/products.json
  ▼
Đọc và parse JSON
  ▼
Tìm/tạo category "Máy lạnh"
  ▼
Kiểm tra product theo SKU
  ├─ Đã tồn tại → bỏ qua
  └─ Chưa tồn tại
       ├─ Tạo Product
       ├─ Tạo ProductSpec
       ├─ Tạo Price
       ├─ Tạo Inventory
       └─ Tạo Promotion nếu có
  ▼
Commit transaction
```

Nguồn dữ liệu demo có 20 sản phẩm. JSON chỉ là input cho seed; API luôn đọc dữ liệu từ database.

## 2.5. Pipeline GET product list

Endpoint:

```http
GET /api/v1/products
```

Pipeline:

```text
HTTP query parameters
  ▼
FastAPI validation
  ▼
ProductService.list_products
  ▼
ProductRepository.list_products
  ├─ JOIN prices
  ├─ JOIN product_specs
  ├─ JOIN inventory
  ├─ Apply search/filter
  ├─ Count total rows
  ├─ Apply sort
  └─ Apply offset/limit
  ▼
Eager-load category/spec/price/inventory/promotion
  ▼
serialize_product
  ▼
PaginatedResponse<ProductRead>
```

Các filter được hỗ trợ:

| Query | Xử lý |
|---|---|
| `search` | Tìm gần đúng theo tên hoặc thương hiệu, không phân biệt hoa thường |
| `brand` | So khớp thương hiệu |
| `min_price` | Giá bán lớn hơn hoặc bằng giá tối thiểu |
| `max_price` | Giá bán nhỏ hơn hoặc bằng giá tối đa |
| `room_area` | Diện tích nằm trong khoảng khuyến nghị của product |
| `inverter` | Lọc theo công nghệ inverter |
| `in_stock` | Lọc theo số lượng tồn kho |
| `sort` | `featured`, `price_asc` hoặc `price_desc` |
| `page` | Trang hiện tại, bắt đầu từ 1 |
| `page_size` | Số item mỗi trang, tối đa 100 |

Response pagination:

```json
{
  "items": [],
  "total": 20,
  "page": 1,
  "page_size": 12,
  "pages": 2
}
```

## 2.6. Pipeline product detail

```text
GET /api/v1/products/{slug}
  ▼
ProductService.get_product
  ▼
ProductRepository.get_by_slug
  ▼
Không tìm thấy?
  ├─ Có → HTTP 404
  └─ Không → serialize ProductRead → HTTP 200
```

Slug là định danh public ổn định trên URL. Database ID vẫn được dùng cho comparison và quan hệ nội bộ.

## 2.7. Pipeline comparison

Request:

```json
{
  "product_ids": [2, 10, 18]
}
```

Pipeline:

```text
POST /api/v1/compare
  ▼
Pydantic kiểm tra 2–3 ID
  ▼
ComparisonService.compare
  ├─ Từ chối ID trùng
  ├─ Load product theo ID
  ├─ Kiểm tra thiếu product
  ├─ Tìm giá thấp nhất
  ├─ Tìm độ ồn thấp nhất trong các product có dữ liệu
  └─ Chọn phù hợp tổng thể theo rule mock
  ▼
ComparisonResponse
```

Các nhãn hiện tại:

- `best_price_id`: giá bán thấp nhất.
- `quietest_id`: `noise_db` thấp nhất; bỏ qua product thiếu dữ liệu.
- `best_overall_id`: rule deterministic dựa trên rating, inverter và featured.

## 2.8. Pipeline chatbot rule-based

> **Hiện tại vs kế hoạch:** mục này mô tả `MockChatService` đang chạy (rule-based, 3 bước hỏi cố định). Pipeline thay thế — 8 stage S1–S8, streaming, guardrail — đã chốt kiến trúc ở §6 nhưng **chưa build**. Khi triển khai, endpoint giữ nguyên path nhưng đổi sang SSE và Need Profile schema mới (§6.2).

Endpoint:

```http
POST /api/v1/chat/messages
```

Chat API là stateless. Frontend phải gửi lại `context` nhận từ response trước.

```text
User message + previous context
  ▼
ChatMessageRequest validation
  ▼
MockChatService.reply
  ├─ Regex trích diện tích "18m2"
  ├─ Map quick reply ngân sách
  └─ Map quick reply ưu tiên
  ▼
Đã có diện tích?
  ├─ Chưa → hỏi diện tích
  └─ Có
       ▼
Đã chọn ngân sách?
  ├─ Chưa → trả budget quick replies
  └─ Có
       ▼
Đã chọn ưu tiên?
  ├─ Chưa → trả priority quick replies
  └─ Có
       ▼
ProductService.products_for_need
  ├─ Filter room area
  ├─ Filter budget
  ├─ Filter in stock
  ├─ Fallback nếu ít hơn 3 product
  └─ Sort theo priority
       ▼
Tạo 3 Recommendation
  ▼
ChatResponse(response_type="recommendations")
```

### State transition

```text
START
  ▼
NEED_ROOM_AREA
  ▼
NEED_BUDGET
  ▼
NEED_PRIORITY
  ▼
RECOMMENDATIONS
```

`budget_max=0` là sentinel nội bộ cho lựa chọn “Không giới hạn”. Khi ranking sản phẩm, giá trị `0` được hiểu là không áp dụng filter ngân sách.

### Ranking mock theo ưu tiên

| Priority | Rule hiện tại |
|---|---|
| Tiết kiệm điện | Ưu tiên inverter, sau đó giá thấp |
| Chạy êm | `noise_db` thấp trước; thiếu dữ liệu xếp cuối |
| Làm lạnh nhanh | Công suất BTU cao trước |
| Giá tốt | Giá bán thấp trước |

Đây chỉ là rule skeleton. Match score, label và diễn giải chưa phải kết quả từ AI model.

## 2.9. Pipeline xử lý lỗi backend

```text
Invalid query/body
  └─ FastAPI/Pydantic → HTTP 422

Không tìm thấy product
  └─ Service → HTTP 404

ID comparison trùng
  └─ ComparisonService → HTTP 422

Database exception chưa xử lý riêng
  └─ FastAPI → HTTP 500 + server log
```

Hướng mở rộng production:

- Exception handler thống nhất error schema.
- Correlation/request ID.
- Structured JSON logging.
- Metrics về latency, error rate và database query.
- Timeout, circuit breaker và retry cho external AI/provider calls.

## 2.10. Backend test pipeline

```text
Pytest fixture
  ▼
SQLite in-memory + StaticPool
  ▼
Base.metadata.create_all
  ▼
Seed 20 demo products
  ▼
Override FastAPI get_db
  ▼
TestClient gọi API thật
  ▼
Assertions
  ▼
Drop schema
```

Các test hiện có:

- Health endpoint.
- Product list và tổng số product.
- Filter theo brand.
- Filter theo giá.
- Product detail.
- Compare 3 sản phẩm.
- Chat follow-up.
- Chat recommendations.
- Flow “Không giới hạn” qua nhiều request.

Lệnh kiểm tra:

```bash
cd apps/api
pytest
ruff check src tests
mypy src
```

## 2.11. Backend build/deploy pipeline

```text
Source code
  ▼
Docker build python:3.12-slim
  ▼
Copy pyproject + source + Alembic
  ▼
pip install .[dev]
  ▼
Create API image
  ▼
Compose start sau PostgreSQL healthy
  ▼
Migration + seed + Uvicorn
  ▼
Healthcheck /api/v1/health
```

Cho production thật nên tách migration thành release job riêng, không để nhiều API replica cùng chạy migration lúc startup.

---

# 3. Frontend pipeline

## 3.1. Cấu trúc các tầng

```text
Next.js Route
  ▼
Page composition
  ▼
Reusable Component
  ├─ TanStack Query → API client → FastAPI
  └─ Zustand → client state
```

| Tầng | Thư mục | Trách nhiệm |
|---|---|---|
| App Router | `apps/web/app` | Layout, metadata và các route page |
| Components | `apps/web/components` | UI và interaction tái sử dụng |
| UI primitives | `apps/web/components/ui` | Button theo shadcn/ui conventions |
| API adapter | `apps/web/lib/api.ts` | Fetch, JSON parsing và error mapping |
| Utility | `apps/web/lib/utils.ts` | Format giá, stock label và class merging |
| Stores | `apps/web/stores` | Cart, comparison và chat UI state |
| Types | `apps/web/types` | Contract TypeScript tương ứng API schema |
| Tests | `apps/web/tests` | Component/store regression tests |

## 3.2. Pipeline khởi tạo ứng dụng

```text
Browser request
  ▼
Next.js RootLayout
  ├─ Providers
  │   ├─ QueryClientProvider
  │   └─ Sonner Toaster
  ├─ Header
  ├─ Route content
  ├─ Footer
  └─ ChatWidget
  ▼
Hydration phía client
  ▼
Zustand hydrate persisted cart/comparison
  ▼
TanStack Query bắt đầu fetch khi component cần dữ liệu
```

`Cart` và `Comparison` được lưu trong browser local storage. Chat state hiện chỉ tồn tại trong memory và được reset khi reload trang.

## 3.3. API client pipeline

```text
Component gọi api.products/api.product/api.compare/api.chat
  ▼
lib/api.ts tạo URL + RequestInit
  ▼
fetch NEXT_PUBLIC_API_URL
  ▼
response.ok?
  ├─ Không → parse detail hoặc fallback message → throw Error
  └─ Có → parse JSON → trả typed Promise
```

Base URL mặc định:

```text
http://localhost:8000/api/v1
```

Giá trị production được inject lúc Docker build bằng `NEXT_PUBLIC_API_URL`. Vì biến bắt đầu bằng `NEXT_PUBLIC_`, giá trị được bundle vào JavaScript phía browser.

## 3.4. Pipeline trang chủ

```text
GET /
  ▼
Render Hero + Benefits
  ▼
ProductGrid(filters={sort: featured}, limit=6)
  ▼
TanStack Query fetch /products?sort=featured&page_size=6
  ▼
Loading / Error / Empty / Product cards
```

CTA “Nhờ AI tư vấn” gọi `chatStore.open()` để mở floating widget mà không chuyển route.

## 3.5. Pipeline product listing

```text
GET /products?search=...
  ▼
Server page đọc initial search param
  ▼
ProductsBrowser khởi tạo ProductFilters state
  ▼
ProductFilter thay đổi filter
  ▼
ProductGrid tạo queryKey ["products", filters]
  ▼
TanStack Query gọi api.products(filters)
  ▼
API trả ProductPage
  ▼
Render ProductCard grid
```

Mỗi tổ hợp filter là một TanStack Query cache key riêng. Khi filter thay đổi, UI giữ logic loading/error độc lập và không cần đọc JSON local.

### UI states

| State | Hiển thị |
|---|---|
| `isLoading` | Spinner và “Đang tải sản phẩm...” |
| `error` | Error message và nút thử lại |
| `items.length === 0` | Empty state |
| Success | Product grid và số lượng kết quả |

## 3.6. Pipeline ProductCard

```text
Product props từ API
  ▼
Render ảnh/tên/giá/spec/stock
  ├─ Chi tiết → /products/{slug}
  ├─ Thêm giỏ → cartStore.add → toast
  └─ Thêm so sánh → comparisonStore.add → toast
```

Guard ở UI:

- Disable “Thêm giỏ” khi hết hàng.
- Comparison store từ chối product trùng.
- Comparison store giới hạn ba product.
- `noise_db=null` hiển thị “Chưa có dữ liệu”.
- Placeholder image dùng `unoptimized` vì nguồn demo trả SVG.

## 3.7. Pipeline product detail

```text
GET /products/{slug}
  ▼
Server route resolve slug
  ▼
ProductDetail useQuery(["product", slug])
  ▼
GET /api/v1/products/{slug}
  ▼
Render ảnh, giá, promotion, stock, specs, warranty, review mock
  ├─ Add cart → Zustand + toast
  └─ Ask chatbot → chatStore.open()
```

Review và chính sách hiển thị ở phase này là mock UI. Product/spec/price/stock/promotion đến từ backend.

## 3.8. Pipeline comparison page

```text
ProductCard → comparisonStore.add(product)
  ▼
Persist localStorage
  ▼
GET /compare
  ▼
ComparisonTable lấy ID từ store
  ▼
Nếu < 2 product → empty guidance
  ▼
POST /api/v1/compare
  ▼
Render bảng và badge theo response ID
```

Frontend không tự tính “Giá tốt nhất”, “Êm nhất” hoặc “Phù hợp tổng thể”. Các nhãn được backend quyết định để tránh business rule bị phân tán giữa client và server.

## 3.9. Pipeline cart

```text
ProductCard/ProductDetail
  ▼
cartStore.add(product)
  ▼
Nếu đã tồn tại → quantity + 1
Nếu chưa tồn tại → thêm CartItem quantity=1
  ▼
Persist localStorage
  ▼
Cart page tính tổng từ sale_price × quantity
```

Các thao tác:

- Tăng số lượng.
- Giảm số lượng; quantity về 0 thì xóa item.
- Xóa item trực tiếp.
- Tính tổng client-side.
- Checkout chỉ hiển thị toast, chưa gọi payment/order API.

## 3.10. Pipeline chat frontend

```text
User mở ChatWidget
  ▼
chatStore.isOpen = true
  ▼
User nhập message hoặc chọn quick reply
  ▼
addMessage(role=user)
  ▼
setLoading(true)
  ▼
api.chat(sessionId, message, currentContext)
  ▼
POST /api/v1/chat/messages
  ▼
Response
  ├─ setContext(response.context)
  ├─ add assistant message
  ├─ attach quick replies nếu follow_up
  └─ attach recommendation cards nếu recommendations
  ▼
setLoading(false)
```

### Chat store state

```ts
{
  isOpen: boolean;
  isLoading: boolean;
  sessionId: string;
  context: {
    budget_max: number | null;
    room_area_m2: number | null;
    priority: string | null;
  };
  messages: ChatEntry[];
}
```

### Auto-scroll effect

Sau mỗi thay đổi `messages` hoặc `isLoading`, widget cuộn đến cuối danh sách. Effect phải dùng block body và không trả kết quả của `scrollIntoView`, vì React coi mọi giá trị trả về là cleanup callback:

```tsx
useEffect(() => {
  const element = bottom.current;
  if (element && typeof element.scrollIntoView === "function") {
    element.scrollIntoView({ behavior: "smooth", block: "end" });
  }
}, [messages, isLoading]);
```

### Chat error path

```text
API request thất bại
  ▼
Catch error
  ▼
Thêm assistant fallback message
  ▼
Finally setLoading(false)
```

Hướng mở rộng:

- Hiển thị nút retry.
- Phân biệt network error, validation error và server error.
- Abort request khi component unmount hoặc user gửi request mới.
- Persist session/chat history ở backend.
- Sinh UUID session thay vì fixed demo session.

### Kế hoạch chuyển sang SSE (§6, ADR D1/D2')

Khi backend chuyển sang pipeline AI-Native, `api.chat` đổi từ fetch JSON một lần sang đọc `ReadableStream` trực tiếp từ FastAPI SSE endpoint trong Client Component (`"use client"`) — không proxy qua Next.js Route Handler, để không thêm hop làm chậm TTFT. `chatStore` cần thêm state cho streaming: `partialMessage` (token đang stream), `sourcePanel` (source log per-turn từ S8), `verifierFlags` (claim bị S7 sửa/cắt, nếu có). Chi tiết interface xem §6.10.

## 3.11. Frontend state ownership

| Dữ liệu | Công cụ | Lý do |
|---|---|---|
| Product list/detail | TanStack Query | Server là source of truth; cần cache/loading/error/refetch |
| Compare result | TanStack Query | Kết quả business rule đến từ backend |
| Cart items | Zustand persist | Client-only demo state cần giữ qua reload |
| Selected comparison products | Zustand persist | Client selection cần giữ qua reload |
| Chat open/loading/messages/context | Zustand | Chia sẻ giữa CTA, detail page và floating widget |
| Filter form | React local state | Chỉ thuộc ProductsBrowser |

Không copy product catalog vào Zustand vì sẽ tạo hai nguồn dữ liệu và làm dữ liệu giá/tồn kho dễ lỗi thời.

## 3.12. Frontend test pipeline

```text
Vitest + jsdom
  ▼
Render component hoặc reset Zustand store
  ▼
Thực hiện user interaction/store action
  ▼
Assert DOM hoặc state
```

Các test hiện có:

- ProductCard render product và fallback khi thiếu `noise_db`.
- Cart store thêm product và cập nhật quantity.
- Comparison store chặn product trùng và giới hạn ba product.
- ChatWidget mở, cập nhật message, auto-scroll và đóng an toàn.

Lệnh kiểm tra:

```bash
cd apps/web
npm test -- --run
npm run lint
npm run type-check
npm run build
```

## 3.13. Frontend build/deploy pipeline

```text
package.json + package-lock.json
  ▼
Node 22 Alpine deps stage
  ▼
Pin npm 11.6.2
  ▼
npm ci
  ▼
Builder stage
  ├─ Inject NEXT_PUBLIC_API_URL
  └─ npm run build
  ▼
Next.js standalone output
  ▼
Runner image chỉ copy standalone/static/public
  ▼
node server.js :3000
  ▼
HTTP healthcheck
```

`HOSTNAME=0.0.0.0` được đặt trong runtime image để Next.js nhận traffic từ Docker port mapping và healthcheck nội bộ qua `localhost`.

---

# 4. Pipeline Docker Compose end-to-end

> **Kế hoạch (§6.9):** khi pipeline AI-Native lên, compose thêm service `vllm` (image chính thức, `--model Qwen3-32B-FP8`, prefix-caching + chunked-prefill). Vì mỗi lần bật vLLM tốn ~10' load model và ngân sách chỉ 10h GPU credit tổng (`dmx-phan-tich-ke-hoach-2026-07-17.md` §5b), service này **không** nằm trong `docker compose up` mặc định lúc dev — bật riêng trong cửa sổ tập trung; `api` gọi qua router (ADR A6) có fallback cloud/model nhỏ khi vLLM tắt.

```text
docker compose up --build
  ▼
Build API image ─────────────┐
Build Web image             │
Pull PostgreSQL image       │
                            ▼
Start postgres
  ▼ healthy
Start api
  ├─ migrate
  ├─ seed
  └─ uvicorn
  ▼ healthy
Start web
  └─ Next standalone server
  ▼ healthy
System ready
```

Service dependency:

```text
postgres (healthy)
  ▼
api (healthy)
  ▼
web (healthy)
```

Các URL sau khi hệ thống sẵn sàng:

- Frontend: `http://localhost:3000`
- Backend OpenAPI: `http://localhost:8000/docs`
- Backend health: `http://localhost:8000/api/v1/health`
- PostgreSQL: `localhost:5432`

## 4.1. Checklist kiểm tra end-to-end

1. `docker compose ps` hiển thị ba service healthy.
2. `GET /api/v1/health` trả `status=ok`.
3. `GET /api/v1/products?page_size=100` trả `total=20`.
4. Trang chủ trả HTTP 200.
5. Product grid lấy dữ liệu từ API.
6. Filter brand/price trả đúng kết quả.
7. Trang detail hiển thị product theo slug.
8. Chọn 2–3 product và mở comparison page.
9. Thêm product vào cart và thay đổi quantity.
10. Chat flow đi qua hai follow-up rồi trả ba recommendation.
11. Kiểm tra browser console không có runtime error.
12. Kiểm tra `docker compose logs web api` không có lỗi mới.

---

# 5. Pipeline phát triển một tính năng mới

## 5.1. Tính năng chỉ thuộc backend

```text
Chốt API contract
  ▼
Schema/model thay đổi?
  ├─ Có → model + migration
  └─ Không
  ▼
Repository query
  ▼
Service rule
  ▼
Route
  ▼
Pytest + Ruff + mypy
  ▼
OpenAPI/manual API verification
```

## 5.2. Tính năng full-stack

```text
Chốt request/response schema
  ▼
Backend model/repository/service/route
  ▼
Backend tests
  ▼
Cập nhật frontend TypeScript types
  ▼
Cập nhật lib/api.ts
  ▼
Component/page/store
  ▼
Loading + empty + error states
  ▼
Frontend tests + lint + type-check
  ▼
Docker build
  ▼
End-to-end verification
```

## 5.3. Checklist review code

- Route có query database trực tiếp không?
- Business rule có bị duplicate ở frontend và backend không?
- API request/response có type/schema đầy đủ không?
- Trường nullable có fallback UI không?
- Có loading, empty và error state không?
- Query key có chứa đầy đủ filter ảnh hưởng kết quả không?
- Zustand có đang giữ dữ liệu đáng lẽ thuộc server state không?
- Migration có cả upgrade và downgrade hợp lý không?
- Seed có idempotent không?
- Test có bao phủ success và failure/edge case quan trọng không?
- Docker image có build từ clean context không?
- Healthcheck có phản ánh service thực sự sẵn sàng không?

---

# 6. Pipeline AI-Native (kiến trúc đã chốt — xem docs/research/)

> **Trạng thái (18/07):** kiến trúc dưới đây đã **chốt** sau vòng research 17/07 (bản đồ tài liệu: `dmx-phan-tich-ke-hoach-2026-07-17.md` §1) nhưng **chưa build** — `MockChatService` (§2.8) vẫn là code đang chạy. Mục này là bản tóm tắt để code theo hằng ngày; rationale đầy đủ, ví dụ cụ thể và 4 benchmark gate phải chạy ở Phase 0 nằm ở `dmx-ai-workflow-v1.md`, `dmx-tech-decisions.md`, `dmx-guardrail-design.md` — đọc file tương ứng trước khi code stage đó.

## 6.1. Tổng quan 8 stage

```text
User message ──▶ S1 (chuẩn hóa) ──▶ S2 (intent + slot) ──┬─▶ [policy_faq] RAG chính sách ──────▶ S7
                                                           ├─▶ [ngoài_phạm_vi] từ chối lịch sự ──▶ S8
                                                           ├─▶ [so_sánh_trực_tiếp A vs B] ───────▶ S4
                                                           └─▶ [tư_vấn / hỏi_chi_tiết] ──▶ S3
S3 (đủ thông tin?) ─┬─ CAO/VỪA: hỏi ngược (S3a/S3b) ──▶ khách trả lời ──▶ quay lại S1 (merge slot)
                    └─ THẤP: đủ rồi
                         ▼
                        S4 (retrieval) ──▶ S5 (fit-score) ──▶ S6 (generation, streaming) ──▶ S7 (verify song song) ──▶ S8 (respond + source log)
```

| Stage | Việc | Latency | Tech | LLM? |
|---|---|---|---|---|
| S1 | NFC normalize, dict ngành hàng, parse tiền/đơn vị, giữ code-switching | ~50ms | regex + dict Python thuần | Không |
| S2 | Intent (5 loại) + slot extraction, merge vào Need Profile | ~400ms | Qwen3-32B FP8, `guided_json` (xgrammar), prefix caching | Có |
| S3 | Dialogue policy — 3 mức ambiguity (Cao/Vừa/Thấp) | ~110ms | rule + SQL `COUNT` pre-filter + information gain precompute | Không (câu hỏi S3a/b cần LLM ngắn) |
| S4 | Structured-first hybrid retrieval | ~250ms, song song | SQL filter (luật ngành) → pgvector+BM25/RRF rerank soft-pref → `asyncio.gather` Price/Promo/Stock | Không |
| S5 | Fit-score ranking tường minh + top-3 + anti-pick + trade-off extraction | ~50ms | Python thuần | Không |
| S6 | Sinh tư vấn từ statement templates, streaming | TTFT <1s | Qwen3-32B FP8; **card render thẳng từ S5, không qua LLM** | Có |
| S7 | Per-claim verification, song song với stream | ~200ms | regex claim extraction + numeric/enum match vào facts JSON, không NLI | Không |
| S8 | Respond + source panel + audit log | — | SSE + Postgres `audit_log` | Không |

**Quyết định kiến trúc quan trọng nhất (ADR A1):** workflow S1→S8 **cố định**, LLM chỉ quyết định tại 2 nút (S2 intent routing, S6 nội dung lời tư vấn) — không phải agent loop tự do. Lý do: SLA <3s/<5s cần số lần LLM call đoán được; demo cần deterministic (cùng câu hỏi → cùng hành vi).

## 6.2. Trạng thái hội thoại — Need Profile

Mỗi session giữ một Need Profile (JSON), quyết định mọi nhánh rẽ:

```json
{
  "category": "máy_lạnh",
  "slots": { "ngân_sách_max": 20000000, "diện_tích_m2": 18, "loại_phòng": null, "nắng_trực_tiếp": null, "ưu_tiên": ["tiết_kiệm_điện", "êm"], "trả_góp": null },
  "asked_slots": ["loại_phòng", "nắng_trực_tiếp"],
  "clarify_rounds": 1,
  "assumptions": []
}
```

- Ràng buộc cứng: tối đa **2 lượt hỏi**/hội thoại; không hỏi lại slot đã có/đã hỏi; mỗi lượt ≤3 câu gom 1 tin nhắn.
- Slot bắt buộc theo ngành hàng (máy lạnh: ngân sách + diện tích; tủ lạnh: ngân sách + số người; ...) đến từ **Category Profile** do compiler sinh (§6.6), không hardcode trong code.
- Đổi ngành giữa chừng → reset slot ngành cũ, giữ ngân sách, hỏi xác nhận nhẹ. Hết quota hỏi → đề xuất kèm giả định nêu rõ.
- Lưu trữ: in-memory `dict` + TTL, interface `SessionStore` tách riêng để đổi sang Redis khi pilot (ADR C7) — **không phải bảng Postgres**; Postgres chỉ giữ `need_profile_log` (snapshot mỗi turn, cho audit/eval).

## 6.3. S3 — Dialogue policy (10% điểm "hỏi ngược thông minh")

| Mức | Điều kiện | Hành động |
|---|---|---|
| Cao | Thiếu slot bắt buộc, hoặc pre-filter >20 SP tản mát | Hỏi theo slot: 2–3 slot information-gain cao nhất, gom 1 tin, kèm lý do |
| Vừa | Đủ slot bắt buộc, còn 6–20 candidates | Hỏi dựa trên dữ liệu đã lọc (thuộc tính phân tán nhất trong candidates) |
| Thấp | ≤5 candidates rõ, hoặc `clarify_rounds ≥ 2` | Bỏ qua hỏi → S4, nêu giả định nếu có |

Không để LLM tự quyết hỏi-hay-không — quyết định phải giải thích được trước giám khảo bằng rule + số, không phải hộp đen (ADR C3).

## 6.4. S4 — Structured-first hybrid retrieval (Postgres duy nhất)

1. **SQL filter cứng** trước tiên: category + giá ≤ ngân sách×1.05 + công suất theo luật ngành (`BTU_cần = diện_tích × 600 (+30% nếu nắng trực tiếp)`, `lít_tủ_lạnh ≈ 40–50/người + 100`, ...) + tồn kho.
2. **Hybrid rerank** trong tập đã lọc, chỉ cho sở thích mềm ("êm", "sang trọng"): dense = pgvector HNSW; lexical = BM25 (Postgres FTS `pg_textsearch`, fallback `tsvector` + `unaccent`); fusion = **RRF trên rank trong SQL** (không blend điểm — BM25 unbounded, cosine [-1,1] không tương thích thang đo).
3. Tên sản phẩm/mã model: `pg_trgm` + rapidfuzz (fuzzy), **không dùng embedding** — chuỗi ký hiệu biểu diễn kém trong vector.
4. Gọi song song (`asyncio.gather`) Price/Promo/Stock cho candidates → `facts JSON` với `source_id` + `fetched_at` per field — nguồn sự thật duy nhất cho S5–S8; field thiếu → `null`, không bao giờ điền mặc định.
5. **Adoption gate:** hybrid chỉ bật nếu ablation (`dmx-data-eval-roi-plan.md` §B1b) cho Hit@3/Recall@3 ≥ dense-only và lexical-only ở mọi slice — quyết định bằng số ở Phase 2, không mặc định bật.

## 6.5. Tools & Router

- **5 tool MCP-compatible** (hàm Python + JSON schema chuẩn MCP), pipeline gọi trực tiếp ở S4; chỉ nhánh `hỏi_chi_tiết_SP` cho LLM tự chọn tool (hermes tool parser): `catalog_search`, `price_promo_stock`, `policy_faq`, `review_summary`, `need_profile`.
- **Router (ADR A6):** mọi LLM call qua client OpenAI-compatible tự viết (~50 dòng) trỏ vLLM local; timeout/5xx → retry 1 lần → fallback cloud API. Cờ fallback **tắt khi demo** (thuần on-prem), bật khi dev vì vLLM không chạy suốt (ngân sách 10h GPU, §6.9).

## 6.6. Category Profile Compiler (ADR A7) — AI sinh, người duyệt, runtime đọc

Logic tư vấn theo ngành hàng (slot bắt buộc, luật quy đổi, câu hỏi mẫu) **không phải config dev viết tay** — pipeline offline chạy lúc ingest:

```text
catalog fields + phân bố giá trị + guide corpus (bài hướng dẫn chọn mua)
  ▼ LLM suy ra slot ứng viên + luật quy đổi (có citation) + câu hỏi mẫu + information gain
  ▼ auto-check "actionable" (loại slot không map field/luật nào)
  ▼ chuyên gia duyệt (human-in-the-loop)
  ▼ category_profile.json — AI sinh, người duyệt, runtime đọc
```

- **Lưới an toàn runtime:** dynamic aspect discovery (S3b) — khi candidates còn nhiều, chọn attribute phân tách tốt nhất từ entropy trên chính tập candidates hiện tại, hoạt động cả khi category chưa có profile.
- **Scoping 48h:** YAML v0 viết tay ở Phase 0 (bootstrap + fallback) → compiler v0 ở Phase 3, so với bản tay trên 4 ngành làm validation → demo "thêm ngành live" ở Phase 4 nếu xanh.
- Luật tư vấn ("phòng nắng cần +0.5HP") lấy từ guide corpus qua RAG có citation, không hardcode — nhất quán với guardrail Tầng 0 (§6.7).

## 6.7. S7 + Guardrail — chống hallucination (10% điểm)

Verifier (S7) chỉ là 1 trong 7 tầng guardrail (`dmx-guardrail-design.md`):

| Tầng | Cơ chế |
|---|---|
| 0. Data | Giá vốn không vào DB; fact nào cũng mang provenance; null là null |
| 1. Generation | LLM chỉ thấy `<facts>`; số liệu đến từ template điền sẵn; diễn đạt, không sáng tác |
| 2. Verifier | Tách atomic claims sau sinh, đối chiếu ngược facts JSON; lệch → sửa/cắt + log `hallucination_incident` |
| 3. Honesty | Thiếu data → nói thiếu; data cũ → ghi thời điểm (`fetched_at` >24h); nguồn mâu thuẫn có luật ưu tiên |
| 4. Tone | Không ép mua, không tuyệt đối hóa; mọi card bắt buộc có trade-off (ép bằng schema) |
| 5. Audit | Source panel mỗi câu trả lời (SP nào, field nào, từ đâu, lúc nào); mask PII; không lưu hội thoại thật |
| 6. Eval | Metric **per-claim rate** (% claim sai/tổng claim) + red-team set — chứng minh bằng số |

S7 kỹ thuật: regex claim extraction (mỗi số/giá/khuyến mãi/tồn kho = 1 claim) + so khớp facts JSON; **không dùng NLI model trong 48h** — 4 loại fact bắt buộc theo đề đều là số/enum, numeric matching phủ đủ (ADR C6). Product card (S6) render thẳng từ JSON của S5, **không đi qua LLM** — xác suất hallucination = 0 tuyệt đối về mặt cấu trúc cho phần chứa nhiều fact nhất (ADR C5); LLM chỉ viết lời dẫn + trade-off narrative, verifier chỉ cần soi phần prose.

## 6.8. Observability & audit log

Middleware đo timing từng stage S1–S8 → ghi Postgres `audit_log` mỗi turn: slots, tool calls, rows dùng, claims, verifier verdict, latency (mask PII, không log giá vốn). Một bảng, ba người dùng: dev debug, eval harness (`make eval`), dashboard nhu-cầu-thị-trường (tính năng 2.1) — ADR D4.

## 6.9. Latency budget & hạ tầng LLM

| Luồng | Stage | Tổng dự kiến | Yêu cầu |
|---|---|---|---|
| Hỏi ngược | S1+S2+S3+S6-câu-hỏi (stream) | ~1.2s tới token đầu | <3s ✓ |
| Top-3 so sánh | S1+S2+S3+S4+S5+S6 (TTFT)+S7 song song | ~1.7s TTFT, ~4s trọn | <5s ✓ |

Nếu S2 vượt 700ms p95 → tách model nhỏ 4–8B cho extraction (router 2 tầng, ADR A3) — vẫn đúng bất kể model chính host ở đâu.

**Hạ tầng LLM (revised 18/07, ADR A2'' — supersedes A2'/self-host vLLM):** model chính **Qwen3.6-27B qua API key OpenRouter** (OpenAI-compatible qua router A6, `base_url=https://openrouter.ai/api/v1`) — không tự thuê/vận hành VM GPU, không dùng FPT AI Factory. Chưa chọn provider fallback thứ 2 — `LLM_FALLBACK_ENABLED=false` mặc định.

**Vận hành:** lấy API key từ OpenRouter → set `LLM_API_KEY` trong `.env` thật (không commit); `LLM_BASE_URL`/`LLM_MODEL` đã có default OpenRouter/`qwen/qwen3.6-27b` trong `.env.example` → chạy ngay, không cần cửa sổ boot như tự host. Benchmark Gate 1 (p95 S2) và Gate 4 (guided_json + tool-call sạch) vẫn chạy bằng `scripts/bench/`, chỉ trỏ `VLLM_BASE_URL`/`VLLM_MODEL` sang OpenRouter. **Gate 2 (cặp flag prefix-caching/chunked-prefill) không còn áp dụng** — không có server tự host để chỉnh flag.

**Cần xác nhận trước khi code phụ thuộc vào guided_json/tool-call:** (1) `qwen/qwen3.6-27b` là slug dự kiến, kiểm tra đúng tên thật trong catalog OpenRouter trước khi set key thật; (2) chưa chắc route model này qua OpenRouter hỗ trợ đúng `response_format` json_schema + hermes-style tool-calling như vLLM — chạy Gate 4 trước để xác nhận; nếu shape khác, `apps/api/src/router/client.py` cần sửa thêm chứ không chỉ đổi `.env`.

**Archived:** self-host vLLM trên VM H100 thuê (`docker-compose.vllm.yml`, `make vllm-up/-down/-logs`) không còn dùng trong kế hoạch hiện tại — giữ nguyên trạng phòng khi roadmap pilot (ADR A8) cần quay lại self-host lúc traffic đủ lớn để amortize chi phí GPU rental.

## 6.10. Interface cần giữ ổn định

- `ChatMessageRequest` / `ChatContext` — mở rộng `ChatContext` với `need_profile` (thay vì 3 field rời `budget_max`/`room_area_m2`/`priority` như bản rule-based) để chứa toàn bộ Need Profile (§6.2).
- `ChatResponse` — thêm `source_panel` (list field→nguồn→thời điểm), `verifier_flags` (claim nào bị sửa/cắt), giữ `follow_up`/`recommendations`.
- `Recommendation` — thêm `anti_pick` (SP không nên chọn + lý do), `trade_off` (theo công thức §6.1 S5), giữ `score`/`reason`/`strengths`.
- Product retrieval luôn qua repository/service (§6.4) — LLM không tự sinh catalog.
- Endpoint `POST /api/v1/chat/messages` giữ nguyên path, đổi response sang SSE (`text/event-stream`) — xem ghi chú frontend ở §3.10.

Giữ các contract này để `apps/web` tiếp tục chạy khi `apps/api` chuyển từ `MockChatService` sang pipeline S1–S8 thật.

## 6.11. Nhánh phụ & edge cases

| Tình huống | Xử lý |
|---|---|
| Hỏi policy thuần ("trả góp 0% cần gì?") | Nhánh `policy_faq`: RAG trên Policy & FAQ docs, trích dẫn mục chính sách, không đi qua ranking |
| Hỏi chi tiết SP đang xem ("con thứ 2 pin bao nhiêu?") | Resolve "con thứ 2" từ context đề xuất gần nhất → lookup field → trả lời + nguồn |
| So sánh trực tiếp 2 SP khách tự nêu | Bỏ qua clarify → retrieve đúng 2 SP → so sánh theo template |
| Ngoài phạm vi (hỏi thời tiết, chửi bậy...) | Từ chối nhẹ nhàng + kéo về tư vấn sản phẩm |
| Catalog thiếu field hàng loạt (data bẩn) | Field null → guardrail honesty (Tầng 3), không suy diễn |
| Khách im lặng/câu quá ngắn ("ok", "ừ") | Hiểu là đồng ý bước gợi ý gần nhất, không hỏi lại từ đầu |
