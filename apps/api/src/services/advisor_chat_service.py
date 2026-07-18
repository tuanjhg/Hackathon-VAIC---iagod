"""AI advisory chat service — wires the S1–S8 pipeline to /chat/messages.

The thin production shell around :func:`src.pipeline.orchestrator.run_turn`:

* adapts ``catalog_search`` ORM rows into the pipeline's plain candidate dicts
  (the pipeline stays framework-free; the ORM never crosses into it);
* owns the per-process :class:`InMemorySessionStore` (ADR C7) keyed by the
  request's ``session_id``, with the request's ``context.need_profile`` as the
  stateless recovery copy after an API restart;
* maps :class:`TurnResult` onto the wire :class:`ChatResponse` — cards render
  straight from the S5 candidate JSON (ADR C5), quick-reply slot tokens get
  display labels;
* writes the best-effort audit row (Tầng 5) and degrades to a polite
  follow-up message when the LLM chain fails — a chat turn never 500s over a
  provider hiccup.
"""

from __future__ import annotations

import re
from logging import getLogger
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.core.config import settings
from src.pipeline.need_profile import NeedProfile
from src.pipeline.orchestrator import RetrievalResult, TurnResult, run_turn
from src.pipeline.s2_extract import S2ExtractionError
from src.pipeline.s5_ranking import RankingResult, ScoreBreakdown
from src.pipeline.s6_generate import S6GenerationError, render_spec
from src.pipeline.s8_respond import field_label
from src.pipeline.session_store import InMemorySessionStore, SessionStore
from src.rag.embeddings import HashingEmbedding
from src.rag.memory_store import MemoryVectorStore
from src.rag.pipeline import PolicyIndexPipeline
from src.router.client import LLMRouter, LLMRouterError
from src.schemas.chat import (
    AdvisorAntiPick,
    AdvisorCard,
    ChatContext,
    ChatMessageRequest,
    ChatResponse,
)
from src.services.audit_service import write_audit_log
from src.tools.catalog_search import catalog_search
from src.tools.price_promo_stock import PricePromoStockTool

logger = getLogger(__name__)

_session_store = InMemorySessionStore()

_policy_pipeline: PolicyIndexPipeline | None = None
_policy_pipeline_ready = False


def _get_policy_pipeline() -> PolicyIndexPipeline | None:
    """Build the in-process policy RAG index once (HashingEmbedding — no model
    load, no I/O beyond reading the Markdown files), cached for the process.

    Returns ``None`` if the policy directory is absent, so the policy_faq branch
    degrades to the honest "chưa hỗ trợ" stub rather than crashing.
    """
    global _policy_pipeline, _policy_pipeline_ready
    if not _policy_pipeline_ready:
        _policy_pipeline_ready = True
        policy_dir = (Path(__file__).resolve().parents[2] / settings.policy_data_path).resolve()
        if policy_dir.exists():
            dim = settings.policy_embedding_dimension
            pipeline = PolicyIndexPipeline(MemoryVectorStore(dim, "hashing"), HashingEmbedding(dim))
            pipeline.build(policy_dir)
            _policy_pipeline = pipeline
            logger.info("policy RAG index built from %s", policy_dir)
        else:
            logger.warning("policy dir %s missing; policy_faq will stub", policy_dir)
    return _policy_pipeline

_FALLBACK_MESSAGE = (
    "Dạ hệ thống tư vấn đang bận một chút, anh/chị thử lại giúp em sau ít phút nhé. "
    "Trong lúc chờ, anh/chị có thể xem danh mục sản phẩm ạ."
)

_CARD_LABELS = ("Phù hợp nhất với nhu cầu", "Lựa chọn cân bằng", "Đáng cân nhắc")

# Display labels for slot enum tokens offered as quick replies. S2's guided
# schema maps the tapped label back to the enum value, so round-tripping works.
_QUICK_REPLY_LABELS: dict[str, str] = {
    "phong_ngu": "Phòng ngủ",
    "phong_khach": "Phòng khách",
    "van_phong": "Văn phòng",
    "khac": "Khác",
    "tiet_kiem_dien": "Tiết kiệm điện",
    "em": "Chạy êm",
    "ben": "Bền bỉ",
    "gia_re": "Giá rẻ",
}

_MARKER_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s*")


class AdvisorChatService:
    """One request-scoped facade over the advisory pipeline."""

    def __init__(
        self,
        db: Session,
        *,
        router: Any | None = None,
        facts_tool: Any | None = None,
        store: SessionStore | None = None,
        policy_search: Any | None = None,
    ) -> None:
        self._db = db
        self._router = router or LLMRouter()
        self._facts_tool = facts_tool or PricePromoStockTool()
        self._store = store or _session_store
        self._policy = policy_search if policy_search is not None else _get_policy_pipeline()

    async def reply(self, request: ChatMessageRequest) -> ChatResponse:
        profile = (
            self._store.get(request.session_id)
            or request.context.need_profile
            or NeedProfile()
        )

        try:
            result = await run_turn(
                request.message,
                profile,
                router=self._router,
                retriever=self._make_retriever(),
                facts_tool=self._facts_tool,
                policy_search=self._policy,
            )
        except (LLMRouterError, S2ExtractionError, S6GenerationError):
            logger.exception("advisory turn failed for session %s", request.session_id)
            return ChatResponse(
                response_type="follow_up",
                message=_FALLBACK_MESSAGE,
                context=_context_from(profile),
            )

        self._store.set(request.session_id, result.profile)
        write_audit_log(
            self._db, session_id=request.session_id, user_text=request.message, result=result
        )
        return _to_chat_response(result)

    def _make_retriever(self) -> Any:
        db = self._db

        def retrieve(
            *, category_key: str, budget_max: int | None, slots: dict[str, Any], limit: int
        ) -> RetrievalResult:
            found = catalog_search(
                db, category_key=category_key, budget_max=budget_max, slots=slots, limit=limit
            )
            candidates = [
                {
                    "sku": p.sku,
                    "name": p.name,
                    "specs": p.specs_json or {},
                    "image_url": p.image_url,
                }
                for p in found.products
            ]
            return RetrievalResult(candidates=candidates, total_count=found.total_count)

        return retrieve


# --------------------------------------------------------------------------- #
# TurnResult → ChatResponse mapping                                           #
# --------------------------------------------------------------------------- #
def _context_from(profile: NeedProfile) -> ChatContext:
    """Full profile plus the legacy scalar mirrors the old FE reads."""
    budget = profile.slots.get("ngan_sach_max")
    area = profile.slots.get("dien_tich_m2")
    priorities = profile.slots.get("uu_tien")
    priority: str | None = None
    if isinstance(priorities, list) and priorities:
        priority = str(priorities[0])
    elif isinstance(priorities, str):
        priority = priorities
    return ChatContext(
        budget_max=int(budget) if isinstance(budget, int | float) else None,
        room_area_m2=float(area) if isinstance(area, int | float) else None,
        priority=priority,
        need_profile=profile,
    )


def _quick_reply_labels(tokens: list[str]) -> list[str]:
    return [_QUICK_REPLY_LABELS.get(token, token) for token in tokens]


def _match_scores(top: list[ScoreBreakdown]) -> list[int]:
    """Relative fit percent of the best score (explainable: 'x% điểm của top-1').

    When every score is non-positive (all-penalty edge case) fall back to a
    fixed descending ladder rather than dividing by a non-positive max.
    """
    if not top:
        return []
    best = max(b.total_score for b in top)
    if best <= 0:
        return [max(50, 90 - 10 * i) for i in range(len(top))]
    return [max(50, min(100, round(100 * b.total_score / best))) for b in top]


def _trade_off_text(sku: str, ranking: RankingResult, breakdown: ScoreBreakdown) -> str:
    """Deterministic per-card trade-off from S5 data (Tầng 4: bắt buộc có)."""
    for trade_off in ranking.trade_offs:
        if sku == trade_off.sku_a and trade_off.b_wins_on:
            field = trade_off.b_wins_on[0]
            va, vb = trade_off.values[field]
            return f"Kém hơn về {field_label(field)} ({va} so với {vb})"
        if sku == trade_off.sku_b and trade_off.a_wins_on:
            field = trade_off.a_wins_on[0]
            va, vb = trade_off.values[field]
            return f"Kém hơn về {field_label(field)} ({vb} so với {va})"
    if breakdown.missing_fields:
        return "Chưa có dữ liệu: " + ", ".join(
            field_label(f) for f in breakdown.missing_fields
        )
    return "Không có điểm yếu nổi bật trong nhóm so sánh"


def _strengths(specs: dict[str, Any]) -> list[str]:
    phrases = [
        rendered
        for field in specs
        if (rendered := render_spec(field, specs.get(field))) is not None
    ]
    return phrases[:3]


def _build_cards(result: TurnResult) -> list[AdvisorCard]:
    assert result.ranking is not None
    by_sku = {str(c.get("sku")): c for c in result.candidates}
    statements = result.advice.statements if result.advice is not None else []
    scores = _match_scores(result.ranking.top)

    cards: list[AdvisorCard] = []
    for index, breakdown in enumerate(result.ranking.top):
        cand = by_sku.get(breakdown.sku, {})
        reason = ""
        if index < len(statements):
            reason = _MARKER_PREFIX_RE.sub("", statements[index])
        cards.append(
            AdvisorCard(
                sku=breakdown.sku,
                name=str(cand.get("name", breakdown.sku)),
                label=_CARD_LABELS[index] if index < len(_CARD_LABELS) else "Gợi ý thêm",
                match_score=scores[index],
                price=cand.get("price"),
                image_url=cand.get("image_url"),
                specs=cand.get("specs") or {},
                reason=reason,
                strengths=_strengths(cand.get("specs") or {}),
                trade_off=_trade_off_text(breakdown.sku, result.ranking, breakdown),
                missing_fields=breakdown.missing_fields,
            )
        )
    return cards


def _build_anti_pick(result: TurnResult) -> AdvisorAntiPick | None:
    assert result.ranking is not None
    anti = result.ranking.anti_pick
    if anti is None:
        return None
    # Never anti-pick something that is also being recommended (tiny sets).
    if any(b.sku == anti.sku for b in result.ranking.top):
        return None
    by_sku = {str(c.get("sku")): c for c in result.candidates}
    name = str(by_sku.get(anti.sku, {}).get("name", anti.sku))
    return AdvisorAntiPick(sku=anti.sku, name=name, reason=result.ranking.anti_pick_reason)


def _to_chat_response(result: TurnResult) -> ChatResponse:
    context = _context_from(result.profile)

    if result.kind == "recommend" and result.ranking is not None:
        return ChatResponse(
            response_type="recommendations",
            message=result.message,
            cards=_build_cards(result),
            anti_pick=_build_anti_pick(result),
            source_panel=result.source_panel,
            verifier_flags=result.verifier_flags,
            context=context,
        )

    return ChatResponse(
        response_type="follow_up",
        message=result.message,
        quick_replies=_quick_reply_labels(result.quick_replies),
        source_panel=result.source_panel,
        context=context,
    )
