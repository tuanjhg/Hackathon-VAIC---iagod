# Pipeline Backend và Frontend — NeedWise Copilot

Tài liệu này mô tả cách dữ liệu và request đi xuyên suốt hệ thống, cách build/test/deploy từng phần, và những điểm mở rộng dự kiến cho các phase AI-Native tiếp theo.

## 1. Tổng quan hệ thống

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

# 6. Pipeline AI-Native dự kiến

Trong phase hiện tại, `MockChatService` là strategy rule-based. Pipeline tương lai có thể được thay bằng:

```text
User message + conversation context
  ▼
Need extraction
  ├─ room area
  ├─ budget
  ├─ priority
  ├─ constraints
  └─ missing/ambiguous fields
  ▼
Conversation policy
  ├─ hỏi follow-up
  └─ tiếp tục recommendation
  ▼
Catalog retrieval / RAG
  ├─ structured product database
  ├─ manufacturer documents
  ├─ warranty/promotion policies
  └─ review evidence
  ▼
Hard filters
  ├─ room compatibility
  ├─ budget
  ├─ stock
  └─ mandatory constraints
  ▼
Ranking engine
  ├─ feature scoring
  ├─ priority weights
  ├─ trade-off calculation
  └─ diversity
  ▼
LLM response composer
  ▼
Guardrail/evidence validation
  ├─ product tồn tại
  ├─ giá/tồn kho đúng snapshot
  ├─ không bịa thông số
  └─ citation/provenance
  ▼
Structured Recommendation response
  ▼
Frontend RecommendationCard
```

Các interface nên được giữ ổn định:

- `ChatMessageRequest` và `ChatContext`.
- `ChatResponse` với `follow_up` hoặc `recommendations`.
- `Recommendation` gồm product, score, reason, strengths và trade-off.
- Product retrieval qua repository/service, không để LLM tự sinh catalog.

Nhờ giữ contract này, frontend có thể tiếp tục hoạt động khi backend chuyển từ rule-based sang AI orchestration thực sự.
