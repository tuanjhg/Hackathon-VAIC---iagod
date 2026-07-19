"""Advisor chat service + SSE endpoint tests.

Service-level tests run the REAL catalog_search over an in-memory SQLite
catalog (category_key rows) and the real S1/S3/S5/S6-layer-1/S7/S8 stages —
only the LLM router and the price/promo/stock tool are faked. The SSE wire
format is exercised at the endpoint level in mock-pipeline mode (no LLM),
since the wrapper is pipeline-agnostic.
"""

import asyncio
import json
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.config import settings
from src.core.database import Base
from src.models import AuditLog, Category, Product
from src.pipeline.need_profile import NeedProfile
from src.pipeline.session_store import InMemorySessionStore
from src.router.client import LLMRouterError
from src.schemas.chat import ChatContext, ChatMessageRequest, SelectedAction
from src.services.advisor_chat_service import AdvisorChatService
from src.tools.price_promo_stock import Fact, ProductFacts

FETCHED_AT = "2026-07-18T09:00:00+00:00"


# --------------------------------------------------------------------------- #
# Fakes (same doubles as tests/test_orchestrator.py)                          #
# --------------------------------------------------------------------------- #
class QueuedRouter:
    def __init__(self, *contents: str) -> None:
        self._queue = list(contents)
        self.calls: list[Any] = []

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append(messages)
        return {"choices": [{"message": {"role": "assistant", "content": self._queue.pop(0)}}]}


class RaisingRouter:
    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        raise LLMRouterError("provider down")


class FakeFactsTool:
    def __init__(self, facts: dict[str, ProductFacts | None]) -> None:
        self._facts = facts

    async def get_facts_many(self, skus: list[str]) -> dict[str, ProductFacts | None]:
        return {sku: self._facts.get(sku) for sku in skus}


def _s2(category: str | None = "may_lanh", slots: dict[str, Any] | None = None,
        intent: str = "tu_van") -> str:
    return json.dumps({"intent": intent, "category": category, "slots_moi": slots or {}})


def _product_facts(sku: str, sale_price: int | None) -> ProductFacts:
    def fact(field: str, value: Any) -> Fact:
        return Fact(
            value=value,
            source={"dataset": "may_lanh", "row": sku, "field": field},
            fetched_at=FETCHED_AT,
        )

    return ProductFacts(
        sku=sku,
        original_price=fact("original_price", None),
        sale_price=fact("sale_price", sale_price),
        promotions=fact("promotions", []),
        stock=Fact(
            value=None,
            source={"dataset": "unavailable", "row": sku, "field": "stock"},
            fetched_at=FETCHED_AT,
        ),
    )


FACTS = {
    "ml_a": _product_facts("ml_a", 15_990_000),
    "ml_b": _product_facts("ml_b", 17_990_000),
    # ml_c absent — no facts-tool entry, price stays honest None.
}


# --------------------------------------------------------------------------- #
# Catalog fixture — 3 realdata-shaped rows (category_key + specs_json)        #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as session:
        category = Category(code="may_lanh", name="Máy lạnh", slug="may-lanh")
        session.add(category)
        session.flush()
        # 3 rows fit an 18m² room (15–20) and 3 don't (25–35): an unfiltered
        # turn sees 6 candidates (> LOW threshold → S3 asks), while a turn with
        # dien_tich_m2=18 narrows to 3 (≤ LOW → proceed to recommend).
        specs = [
            ("ml_a", "Panasonic Inverter 12000 BTU",
             {"capacity_btu": 12000, "noise_db_indoor": 29, "inverter": True,
              "energy_efficiency": 6.2, "recommended_area_min": 15.0,
              "recommended_area_max": 20.0}),
            ("ml_b", "Daikin 12000 BTU",
             {"capacity_btu": 12000, "noise_db_indoor": 31, "inverter": False,
              "energy_efficiency": 5.0, "recommended_area_min": 15.0,
              "recommended_area_max": 20.0}),
            ("ml_c", "Casper 12000 BTU",
             {"capacity_btu": 12000, "noise_db_indoor": 33, "inverter": False,
              "energy_efficiency": 4.8, "recommended_area_min": 15.0,
              "recommended_area_max": 20.0}),
            ("ml_d", "LG 18000 BTU",
             {"capacity_btu": 18000, "noise_db_indoor": 34, "inverter": True,
              "energy_efficiency": 5.5, "recommended_area_min": 25.0,
              "recommended_area_max": 35.0}),
            ("ml_e", "Samsung 18000 BTU",
             {"capacity_btu": 18000, "noise_db_indoor": 35, "inverter": False,
              "energy_efficiency": 5.1, "recommended_area_min": 25.0,
              "recommended_area_max": 35.0}),
            ("ml_f", "Aqua 18000 BTU",
             {"capacity_btu": 18000, "noise_db_indoor": 36, "inverter": False,
              "energy_efficiency": 4.9, "recommended_area_min": 25.0,
              "recommended_area_max": 35.0}),
        ]
        for sku, name, spec in specs:
            session.add(
                Product(
                    sku=sku,
                    slug=sku.replace("_", "-"),
                    name=name,
                    display_name=name,
                    brand=name.split()[0],
                    category_id=category.id,
                    category_key="may_lanh",
                    specs_json=spec,
                    short_description=name,
                    image_url=f"https://img.example/{sku}.jpg",
                )
            )
        session.commit()
        yield session
    Base.metadata.drop_all(engine)


def _service(db: Session, router: Any, store: InMemorySessionStore | None = None) -> AdvisorChatService:
    return AdvisorChatService(
        db, router=router, facts_tool=FakeFactsTool(FACTS), store=store or InMemorySessionStore()
    )


def _request(message: str, profile: NeedProfile | None = None,
             session_id: str = "s-1") -> ChatMessageRequest:
    return ChatMessageRequest(
        session_id=session_id,
        message=message,
        context=ChatContext(need_profile=profile),
    )


def _ready_profile() -> NeedProfile:
    return NeedProfile(
        category="may_lanh", slots={"ngan_sach_max": 20_000_000, "dien_tich_m2": 18.0}
    )


# --------------------------------------------------------------------------- #
# AI-mode service                                                             #
# --------------------------------------------------------------------------- #
def test_recommend_turn_builds_cards_from_candidate_json(db: Session) -> None:
    router = QueuedRouter(_s2(), "[1] có độ ồn 29dB.")
    response = asyncio.run(
        _service(db, router).reply(_request("chốt giúp em", _ready_profile()))
    )

    assert response.response_type == "recommendations"
    assert response.intent == "tu_van"
    assert "đã ghi nhận anh/chị cần máy lạnh" in response.message
    assert "[1] có độ ồn 29dB." in response.message
    assert [c.sku for c in response.cards] == ["ml_a", "ml_b", "ml_c"]

    top = response.cards[0]
    assert top.match_score == 100
    assert top.price == 15_990_000  # from the facts tool, not the catalog
    assert top.image_url == "https://img.example/ml_a.jpg"
    assert top.product_slug == "ml-a"
    assert top.label == "Phù hợp nhất với nhu cầu"
    assert not top.reason.startswith("[1]")  # marker stripped for display
    assert top.trade_off  # Tầng 4: never empty
    assert "dữ liệu xếp hạng" not in top.trade_off
    assert response.cards[2].price is None  # ml_c honest absence

    # With only 3 candidates the anti-pick coincides with a recommended SKU
    # and is suppressed rather than contradicting the cards.
    assert response.anti_pick is None

    panel = {(e.sku, e.field): e.dataset for e in response.source_panel}
    assert panel[("ml_a", "price")] == "may_lanh"
    assert panel[("ml_a", "noise_db_indoor")] == "catalog_snapshot"

    assert response.context.need_profile is not None
    assert response.context.need_profile.category == "may_lanh"
    assert response.context.budget_max == 20_000_000
    assert response.guardrail.status in {"verified", "limited"}
    assert response.guardrail.source_count == len(response.source_panel)

    audit = db.scalars(select(AuditLog)).one()
    assert audit.response_kind == "recommend"
    assert audit.verdict_counts == {"match": 1}


def test_ask_turn_offers_labelled_quick_replies_and_persists_session(db: Session) -> None:
    store = InMemorySessionStore()
    router = QueuedRouter(_s2())
    response = asyncio.run(
        _service(db, router, store).reply(_request("tư vấn máy lạnh", session_id="s-ask"))
    )

    assert response.response_type == "clarification"
    assert response.intent == "tu_van"
    assert "vì" in response.message
    assert "Phòng ngủ" in response.quick_replies  # enum token mapped for display
    room_action = next(action for action in response.actions if action.value == "phong_ngu")
    assert room_action.label == "Phòng ngủ"
    assert room_action.slot_name == "loai_phong"
    saved = store.get("s-ask")
    assert saved is not None and saved.clarify_rounds == 1
    assert saved.asked_slots == ["ngan_sach_max", "dien_tich_m2", "loai_phong"]


def test_conversation_carries_profile_across_turns(db: Session) -> None:
    store = InMemorySessionStore()
    router1 = QueuedRouter(_s2())
    asyncio.run(_service(db, router1, store).reply(_request("cần máy lạnh", session_id="s-2")))

    router2 = QueuedRouter(
        _s2(slots={"ngan_sach_max": 20_000_000, "dien_tich_m2": 18.0}),
        "[1] có độ ồn 29dB.",
    )
    response = asyncio.run(
        _service(db, router2, store).reply(_request("phòng 18m2, tầm 20 triệu", session_id="s-2"))
    )

    assert response.response_type == "recommendations"
    saved = store.get("s-2")
    assert saved is not None
    assert saved.slots["ngan_sach_max"] == 20_000_000
    assert saved.clarify_rounds == 1  # first turn's ask round survived


def test_llm_failure_degrades_to_grounded_recommendations(db: Session) -> None:
    response = asyncio.run(
        _service(db, RaisingRouter()).reply(_request("tư vấn máy lạnh", _ready_profile()))
    )
    assert response.response_type == "recommendations"
    assert response.intent == "tu_van"
    assert "số liệu trực tiếp từ hệ thống" in response.message
    assert response.cards
    assert response.guardrail.status == "grounded_fallback"
    assert "trực tiếp" in response.guardrail.label
    audit = db.scalars(select(AuditLog)).one()
    assert audit.response_kind == "recommend"
    assert audit.used_fallback_table


def test_selected_action_is_validated_and_merged_server_side(db: Session) -> None:
    store = InMemorySessionStore()
    profile = NeedProfile(category="may_lanh")
    request = ChatMessageRequest(
        session_id="action-session",
        message="Phòng ngủ",
        context=ChatContext(need_profile=profile),
        selected_action=SelectedAction(
            id="slot:loai_phong:phong_ngu",
            slot_name="loai_phong",
            value="phong_ngu",
        ),
    )

    asyncio.run(_service(db, QueuedRouter(_s2()), store).reply(request))

    saved = store.get("action-session")
    assert saved is not None
    assert saved.slots["loai_phong"] == "phong_ngu"


def test_tampered_selected_action_cannot_inject_a_slot(db: Session) -> None:
    store = InMemorySessionStore()
    request = ChatMessageRequest(
        session_id="tampered-action",
        message="Bất kỳ",
        context=ChatContext(need_profile=NeedProfile(category="may_lanh")),
        selected_action=SelectedAction(
            id="slot:loai_phong:not_allowed",
            slot_name="loai_phong",
            value="not_allowed",
        ),
    )

    asyncio.run(_service(db, QueuedRouter(_s2()), store).reply(request))

    saved = store.get("tampered-action")
    assert saved is not None
    assert "loai_phong" not in saved.slots


def test_simple_greeting_returns_follow_up_instead_of_out_of_scope(db: Session) -> None:
    router = QueuedRouter(_s2(intent="ngoai_pham_vi", category=None))

    response = asyncio.run(_service(db, router).reply(_request("hi")))

    assert response.response_type == "follow_up"
    assert response.intent == "giao_tiep_co_ban"
    assert "chào anh/chị" in response.message
    assert response.guardrail.status == "not_applicable"
    assert [action.label for action in response.actions] == [
        "Tư vấn máy lạnh",
        "Tư vấn tủ lạnh",
        "Xem chính sách trả góp",
    ]
    assert router.calls == []


# --------------------------------------------------------------------------- #
# SSE wire format (endpoint level, mock pipeline — no LLM needed)             #
# --------------------------------------------------------------------------- #
def test_sse_streams_deltas_then_final(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chat_pipeline", "mock")
    response = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "sse", "message": "Tư vấn máy lạnh cho phòng 18m2",
              "context": {"budget_max": None, "room_area_m2": None, "priority": None}},
        headers={"accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [e["type"] for e in events[:-1]] == ["delta"] * (len(events) - 1)
    assert len(events) >= 2  # at least one delta + final
    final = events[-1]
    assert final["type"] == "final"
    assert final["response"]["response_type"] == "follow_up"
    # The deltas reassemble the final message.
    assert "".join(e["text"] for e in events[:-1]).replace(" ", "") in (
        final["response"]["message"].replace(" ", "")
    )


def test_plain_json_mode_unchanged_without_accept_header(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "chat_pipeline", "mock")
    response = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "json", "message": "Tư vấn máy lạnh cho phòng 18m2",
              "context": {"budget_max": None, "room_area_m2": None, "priority": None}},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["response_type"] == "follow_up"


def test_delete_session_endpoint_is_idempotent(client: TestClient) -> None:
    first = client.delete("/api/v1/chat/sessions/session-to-forget")
    second = client.delete("/api/v1/chat/sessions/session-to-forget")

    assert first.status_code == 204
    assert second.status_code == 204


# --------------------------------------------------------------------------- #
# Card copy honesty (unit-level on the deterministic helpers).               #
# --------------------------------------------------------------------------- #
from src.pipeline.s5_ranking import RankingResult, ScoreBreakdown  # noqa: E402
from src.services.advisor_chat_service import (  # noqa: E402
    _match_scores,
    _reason_text,
    _strengths,
    _trade_off_text,
)


def test_strengths_drops_false_boolean_specs() -> None:
    out = _strengths({"inverter": False, "capacity_total_l": 235})
    assert all("không phải inverter" not in s for s in out)
    assert any("235" in s for s in out)


def test_strengths_keeps_true_boolean_specs() -> None:
    out = _strengths({"inverter": True})
    assert any("đỡ tốn điện" in s for s in out)


def test_match_scores_tie_avoids_triple_hundred() -> None:
    top = [
        ScoreBreakdown(sku="A", total_score=1.0),
        ScoreBreakdown(sku="B", total_score=1.0),
        ScoreBreakdown(sku="C", total_score=1.0),
    ]
    assert _match_scores(top) == [75, 75, 75]


def test_match_scores_keeps_spread_when_differentiated() -> None:
    top = [
        ScoreBreakdown(sku="A", total_score=1.0),
        ScoreBreakdown(sku="B", total_score=0.5),
    ]
    assert _match_scores(top) == [100, 50]


def test_trade_off_honest_when_no_criteria() -> None:
    ranking = RankingResult(top=[ScoreBreakdown(sku="A", total_score=0.05)], trade_offs=[])
    bd = ScoreBreakdown(
        sku="A", total_score=0.05, per_criterion={"bonus:price_available": 0.05}
    )
    text = _trade_off_text("A", ranking, bd)
    assert "bảo hành và chi phí lắp đặt" not in text
    assert "chưa đủ dữ liệu" in text.lower()


def test_reason_is_deterministic_from_strongest_criterion() -> None:
    bd = ScoreBreakdown(
        sku="A", total_score=3.05,
        per_criterion={"inverter": 3.0, "bonus:price_available": 0.05},
    )
    text = _reason_text(bd, {"inverter": True})
    assert "đỡ tốn điện" in text
    assert "Phù hợp" in text


def test_reason_falls_back_when_no_positive_criterion() -> None:
    bd = ScoreBreakdown(
        sku="A", total_score=0.05, per_criterion={"bonus:price_available": 0.05}
    )
    text = _reason_text(bd, {})
    assert "Phù hợp với nhu cầu đã nêu" in text
