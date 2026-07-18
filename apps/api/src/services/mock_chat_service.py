import re

from src.schemas.chat import ChatContext, ChatMessageRequest, ChatResponse, Recommendation
from src.services.product_service import ProductService, serialize_product

BUDGET_OPTIONS = ["Dưới 10 triệu", "10–15 triệu", "15–20 triệu", "Không giới hạn"]
PRIORITY_OPTIONS = ["Tiết kiệm điện", "Chạy êm", "Làm lạnh nhanh", "Giá tốt"]
BUDGET_MAP = {
    "Dưới 10 triệu": 10_000_000,
    "10–15 triệu": 15_000_000,
    "15–20 triệu": 20_000_000,
    "Không giới hạn": 0,
}

# H2.1 pronoun mirroring: once the customer addresses themselves with one of
# these kinship terms, the bot mirrors it back for the rest of the session
# instead of the generic "bạn" (detect once, never overwrite -- "trong suốt
# phiên"). A real style-guide/system-prompt version belongs to the AI-Native
# pipeline's Need Profile (see docs/research/dmx-local-context-h2.md §H2.1);
# this is the equivalent behavior against the current rule-based service.
_XUNG_HO_TERMS = ("cô", "chú", "bác", "anh", "chị", "em", "ông", "bà")
_XUNG_HO_RE = re.compile(r"\b(" + "|".join(_XUNG_HO_TERMS) + r")\b", re.IGNORECASE)


def _detect_xung_ho(message: str) -> str | None:
    match = _XUNG_HO_RE.search(message.lower())
    return match.group(1).capitalize() if match else None


def _addr(context: ChatContext, *, capitalized: bool) -> str:
    term = context.xung_ho
    if term is None:
        return "Bạn" if capitalized else "bạn"
    return term if capitalized else term.lower()


class MockChatService:
    def __init__(self, product_service: ProductService):
        self.product_service = product_service

    def reply(self, request: ChatMessageRequest) -> ChatResponse:
        context = request.context.model_copy(deep=True)
        area_match = re.search(r"(\d+(?:[.,]\d+)?)\s*m2", request.message.lower())
        if area_match and context.room_area_m2 is None:
            context.room_area_m2 = float(area_match.group(1).replace(",", "."))
        if context.xung_ho is None:
            detected = _detect_xung_ho(request.message)
            if detected:
                context.xung_ho = detected
        if request.message in BUDGET_OPTIONS:
            context.budget_max = BUDGET_MAP.get(request.message)
        if request.message in PRIORITY_OPTIONS:
            context.priority = request.message

        if context.room_area_m2 is None:
            return self._follow_up(
                f"Phòng của {_addr(context, capitalized=False)} rộng khoảng bao nhiêu m²?", [], context
            )
        if context.budget_max is None:
            return self._follow_up(
                f"{_addr(context, capitalized=True)} muốn ngân sách tối đa khoảng bao nhiêu?",
                BUDGET_OPTIONS,
                context,
            )
        if context.priority is None:
            return self._follow_up(
                f"{_addr(context, capitalized=True)} ưu tiên điều gì nhất?", PRIORITY_OPTIONS, context
            )

        products = self.product_service.products_for_need(
            context.room_area_m2, context.budget_max, context.priority
        )
        labels = ["Phù hợp tổng thể nhất", "Giá trị tốt nhất", "Tốt nhất cho ưu tiên"]
        recommendations = []
        for index, product in enumerate(products):
            strengths = [f"Phù hợp phòng {product.specs.recommended_area_min}–{product.specs.recommended_area_max}m²"]
            if product.specs.inverter:
                strengths.append("Công nghệ Inverter tiết kiệm điện")
            if product.specs.noise_db is not None:
                strengths.append(f"Độ ồn {product.specs.noise_db:g} dB")
            recommendations.append(
                Recommendation(
                    product=serialize_product(product),
                    label=labels[index],
                    match_score=max(82, 96 - index * 4),
                    reason=f"Đáp ứng tốt phòng {context.room_area_m2:g}m² và ưu tiên {context.priority.lower()}.",
                    strengths=strengths,
                    trade_off="Giá cao hơn lựa chọn cơ bản" if index == 0 else "Ít tính năng cao cấp hơn",
                )
            )
        return ChatResponse(
            response_type="recommendations",
            message=f"Dưới đây là 3 lựa chọn phù hợp nhất cho {_addr(context, capitalized=False)}",
            recommendations=recommendations,
            context=context,
        )

    @staticmethod
    def _follow_up(message: str, replies: list[str], context: ChatContext) -> ChatResponse:
        return ChatResponse(
            response_type="follow_up", message=message, quick_replies=replies, context=context
        )
