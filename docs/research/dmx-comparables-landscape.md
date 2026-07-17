# Bản đồ giải pháp tương đồng — tham khảo & so sánh

> v1 · 17/07/2026 · Mục đích kép: (1) tham khảo kỹ thuật từ hệ thống đi trước, (2) đạn cho pitch — brief C2 hỏi thẳng "đã có giải pháp nào, nhược điểm gì", mục I3 yêu cầu ví dụ truyền cảm hứng. Mỗi mục ghi rõ: **học gì · khác gì · số nào dùng được**.

---

## Nhóm A — Sản phẩm production quốc tế (gần nhất về chức năng)

| Hệ thống | Học được gì | Mình khác gì | Số dùng cho pitch |
|---|---|---|---|
| **Amazon Rufus** | Query planner trước khi sinh; RAG catalog+review; streaming <1s; model router theo tốc độ/chất lượng | Rufus không tập trung hỏi-ngược khai thác nhu cầu; cloud-scale model custom — không khả thi cho SME VN; mình: need-elicitation-first + on-prem + guardrail nhìn thấy được | Chuẩn mực UX: token đầu <1s |
| **Walmart Sparky** | Agentic assistant: hiểu intent → gợi ý → đoán trước câu hỏi tiếp; gắn thẳng vào giỏ hàng | Sparky phục vụ hệ sinh thái khép kín Walmart; mình thiết kế để cắm vào retailer VN qua API catalog/stock/promo | **Đơn qua Sparky có AOV cao hơn 35%** (Q4 FY26 earnings) — bằng chứng uplift thật cho mô hình ROI, thay giả định suông |
| **Taobao Wenwen** | Kết quả đa định dạng (text + video + link livestream) | Lịch sử Wenwen chứng minh luận điểm của brief: bot đời 2018 = "FAQ + finite-state machine" cho hậu mãi, KHÔNG phải shopping adviser — LLM mới mở khóa hiểu intent | Câu chuyện thị trường: "2018 FAQ bot → 2024+ adviser" |
| **Klarna AI assistant** | Quy mô hóa: 2.3M hội thoại/tháng, 2/3 lượng chat, ≈700 FTE, giải quyết 2' vs 11', repeat inquiry −25%, CSAT ngang người | **Vụ quay xe 2025**: Klarna phải tuyển lại người vì AI trả lời chung chung ở ca khó — đúng lý do mình thiết kế **QR bàn giao nhân viên (2.2) + human-in-the-loop** ngay từ đầu chứ không thay người 100% | $40M profit 2024 → ~$60M/853 FTE Q3 2025 — chuẩn tham chiếu deflection; VÀ bài học "đừng cắt quá tay" |
| **Best Buy (Google+Accenture)** | Triển khai nhanh (summarization 6–8 tuần) | Trọng tâm của họ là hậu mãi/support — **chưa thấy needs-based comparison advisor công khai** → khoảng trống đúng như brief mô tả | Khoảng trống thị trường ở chính ngành điện máy |

## Nhóm B — Thị trường Việt Nam (đối thủ trực tiếp khi pilot)

| Giải pháp | Bản chất | Nhược điểm so với yêu cầu brief |
|---|---|---|
| FPT.AI Conversation | Nền tảng bot builder NLP tiếng Việt, mạnh intent/flow, dùng nhiều ở bank/telco | Kịch bản định nghĩa trước — không hỏi ngược động theo catalog, không trade-off explanation, không guardrail đối chiếu số liệu |
| BotStar / BizFly Chat / Bot Bán Hàng | Bot bán hàng đa kênh (web/Messenger/Zalo): chốt đơn, theo dõi đơn, khuyến mãi | Đúng loại "chatbot FAQ/kịch bản" mà brief C2 chê: ít hỏi ngược hiểu nhu cầu, không gắn tồn kho/so sánh có căn cứ |
| Chat hỗ trợ của chính các chuỗi điện máy | Người thật + bot kịch bản đơn giản | Chính là baseline "chưa tích hợp" trong bài toán ROI của mình |

**Kết luận nhóm B:** chưa có giải pháp nội địa công khai nào làm need-elicitation + grounded comparison cho điện máy → luận điểm "khoảng trống thị trường VN" đứng vững, và các đội thi khác nếu build trên nền tảng bot cũ sẽ vướng đúng các nhược điểm này.

## Nhóm C — Mã nguồn mở (tham khảo code trực tiếp)

| Repo | Đáng đọc gì | Cảnh giác gì |
|---|---|---|
| **[NVIDIA Retail Shopping Assistant](https://github.com/NVIDIA-AI-Blueprints/retail-shopping-assistant/)** (blueprint chính thức) | Kiến trúc multi-agent LangGraph + streaming + cart — **reference architecture nghiêm túc nhất hiện có**, đáng đối chiếu sơ đồ của mình trước khi code | Gắn với NIM/cloud NVIDIA; nặng hơn cần thiết cho 48h; không có need-elicitation policy như mình |
| **[ShoppingGPT](https://github.com/Hoanganhvu123/ShoppingGPT)** (🇻🇳 tiếng Việt!) | Comparable gần nhất về ngôn ngữ: RAG + **semantic router** + SQLite, xử lý tiếng Việt mua sắm — đọc cách họ route intent | Dùng Gemini API — **chính là anti-pattern "phụ thuộc API ngoại" brief cảnh báo**; không guardrail, không hỏi ngược có chính sách; nêu trong pitch làm ví dụ tương phản rất đẹp |
| [retailGPT](https://github.com/unicamp-dl/retailGPT) | RAG chatbot bán lẻ chuẩn giáo khoa (GPT-4o), cấu trúc gọn dễ đọc | OpenAI API; recommendation không explainable |
| Bài mổ xẻ [Agentic RAG e-commerce — what broke](https://medium.com/@vineetchachondia/i-built-an-agentic-rag-chatbot-for-e-commerce-what-actually-worked-and-what-broke-8c36d1b62902) (02/2026) | Danh sách lỗi thực chiến: structured comparison tables, grounding từng câu trả lời — trùng nhiều quyết định của mình → đọc để né lỗi họ đã dẫm | — |

## Nhóm D — Research prototypes (đã phân tích sâu ở lượt research trước)

TTR (WWW 2026, 3-agent intent→retrieval→rank) · MACRS (multi-agent planner/responder) · ProductAgent + PROCLARE (clarification benchmark) · ASK (Amazon — clarify theo 3 mức ambiguity) — mình đã hấp thụ vào thiết kế S2/S3; trong slide ghi 1 dòng "dialogue policy theo ASK/ProductAgent, intent completion theo TTR" để chứng minh có nền khoa học.

---

## Ma trận so sánh năng lực (dùng thẳng cho slide "vì sao khác biệt")

| Năng lực | Bot kịch bản VN | ShoppingGPT OSS | Rufus/Sparky | **Giải pháp của mình** |
|---|---|---|---|---|
| Hỏi ngược theo nhu cầu (policy + quota) | ✗ | ✗ | một phần | ✅ 3 mức ambiguity, đo được |
| Trade-off bình dân + anti-pick | ✗ | ✗ | một phần | ✅ + quy ra tiền điện (TCO) |
| Guardrail đối chiếu số liệu + source log | ✗ | ✗ | ẩn bên trong | ✅ nhìn thấy được trên UI + eval report |
| Tiếng Việt bẩn + code-switching | một phần | một phần | ✗ | ✅ + bảng alias 34 tỉnh, xưng hô |
| On-prem / chủ quyền dữ liệu (Luật 91/2025) | tùy | ✗ (Gemini API) | ✗ (cloud) | ✅ self-host toàn stack |
| AI tự học logic tư vấn ngành hàng | ✗ (kịch bản tay) | ✗ | không rõ | ✅ Category Profile Compiler |
| Insight nhu cầu cho doanh nghiệp | ✗ | ✗ | nội bộ | ✅ dashboard 2.1 |

## Ba con số "mượn" cho câu chuyện kinh tế (có nguồn, ghi rõ là tham chiếu ngành)

1. **+35% AOV** đơn qua Sparky (Walmart Q4 FY26) → trần tham chiếu cho uplift; mô hình ROI của mình giả định khiêm tốn hơn nhiều (+10% CR tương đối) — "con số của chúng tôi thận trọng hơn Walmart 3 lần"
2. **Klarna $40M→60M/năm, giải quyết 2' vs 11'** → chuẩn deflection + time-to-resolution; kèm bài học quay xe 2025 → "chúng tôi thiết kế human-handoff từ ngày đầu, không thay người 100%"
3. **CSAT ngang người + repeat inquiry −25%** (Klarna) → trả lời trước câu hỏi "khách có chịu chat với bot không?"
