"""Orchestrator tests — one advisory turn for the ``tu_van`` branch.

Drives :func:`src.pipeline.orchestrator.run_turn` end-to-end with fakes for
every injected dependency (queued LLM router double, canned retriever, canned
facts tool) and the *real* S1/S3/S5/S6-layer-1/S7 stages plus the real
``may_lanh`` slot YAML — so the turn-level contract (prefilter before S3, slot
merge rules, facts overwrite, report-only verification) is exercised without a
database or network. Async is driven with ``asyncio.run`` per repo convention
(no async pytest plugin installed).
"""

import asyncio
import json
from typing import Any

import pytest

from src.pipeline.need_profile import NeedProfile
from src.pipeline.orchestrator import (
    RetrievalResult,
    TurnResult,
    run_turn,
)
from src.tools.price_promo_stock import Fact, ProductFacts

FETCHED_AT = "2026-07-18T09:00:00+00:00"


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #
class QueuedRouter:
    """LLM double returning queued contents in call order (S2 first, then S6)."""

    def __init__(self, *contents: str) -> None:
        self._queue = list(contents)
        self.calls: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append((messages, kwargs))
        content = self._queue.pop(0)
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class FakeRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, *, category_key: str, budget_max: int | None, slots: dict[str, Any], limit: int
    ) -> RetrievalResult:
        self.calls.append(
            {"category_key": category_key, "budget_max": budget_max, "slots": slots, "limit": limit}
        )
        return self.result


class FakeFactsTool:
    def __init__(self, facts: dict[str, ProductFacts | None]) -> None:
        self._facts = facts
        self.calls: list[list[str]] = []

    async def get_facts_many(self, skus: list[str]) -> dict[str, ProductFacts | None]:
        self.calls.append(list(skus))
        return {sku: self._facts.get(sku) for sku in skus}


# --------------------------------------------------------------------------- #
# Fixture builders                                                            #
# --------------------------------------------------------------------------- #
def _s2(
    intent: str = "tu_van",
    category: str | None = "may_lanh",
    slots: dict[str, Any] | None = None,
) -> str:
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


# ``sku_a`` strictly dominates on every criterion (inverter/energy/noise) so it
# always ranks [1]; ``sku_c`` has no facts-tool entry (price stays None).
CANDIDATES: list[dict[str, Any]] = [
    {
        "sku": "sku_a",
        "name": "Panasonic Inverter 12000 BTU",
        "specs": {
            "capacity_btu": 12000,
            "noise_db_indoor": 29,
            "inverter": True,
            "energy_efficiency": 6.2,
        },
    },
    {
        "sku": "sku_b",
        "name": "Daikin 12000 BTU",
        "specs": {
            "capacity_btu": 12000,
            "noise_db_indoor": 31,
            "inverter": False,
            "energy_efficiency": 5.0,
        },
    },
    {
        "sku": "sku_c",
        "name": "Casper 12000 BTU",
        "specs": {
            "capacity_btu": 12000,
            "noise_db_indoor": 33,
            "inverter": False,
            "energy_efficiency": 4.8,
        },
    },
]

FACTS = {
    "sku_a": _product_facts("sku_a", 15_990_000),
    "sku_b": _product_facts("sku_b", 17_990_000),
    # sku_c intentionally absent → facts tool returns None for it.
}


def _run(
    text: str,
    profile: NeedProfile,
    router: QueuedRouter,
    retriever: FakeRetriever,
    facts_tool: FakeFactsTool | None = None,
) -> TurnResult:
    return asyncio.run(
        run_turn(
            text,
            profile,
            router=router,
            retriever=retriever,
            facts_tool=facts_tool or FakeFactsTool(FACTS),
        )
    )


def _full_retriever(total: int | None = None) -> FakeRetriever:
    return FakeRetriever(
        RetrievalResult(candidates=CANDIDATES, total_count=total or len(CANDIDATES))
    )


# --------------------------------------------------------------------------- #
# Intent routing (non-tư_vấn branches)                                        #
# --------------------------------------------------------------------------- #
def test_out_of_scope_refuses_without_retrieval() -> None:
    router = QueuedRouter(_s2(intent="ngoai_pham_vi", category=None))
    retriever = _full_retriever()
    res = _run("thời tiết mai thế nào?", NeedProfile(), router, retriever)
    assert res.kind == "out_of_scope"
    assert res.intent == "ngoai_pham_vi"
    assert retriever.calls == []
    assert len(router.calls) == 1  # S2 only, no S6


@pytest.mark.parametrize("intent", ["policy_faq", "so_sanh_truc_tiep", "hoi_chi_tiet_sp"])
def test_unbuilt_branches_get_honest_stub(intent: str) -> None:
    router = QueuedRouter(_s2(intent=intent))
    retriever = _full_retriever()
    res = _run("trả góp 0% cần giấy tờ gì?", NeedProfile(), router, retriever)
    assert res.kind == "unsupported"
    assert retriever.calls == []


# --------------------------------------------------------------------------- #
# Category resolution                                                         #
# --------------------------------------------------------------------------- #
def test_asks_category_when_none_detected() -> None:
    router = QueuedRouter(_s2(category=None))
    retriever = _full_retriever()
    res = _run("chào em", NeedProfile(), router, retriever)
    assert res.kind == "ask_category"
    assert "Máy lạnh" in res.quick_replies
    assert retriever.calls == []  # no category → nothing to prefilter


def test_category_change_resets_slots_but_keeps_budget() -> None:
    profile = NeedProfile(
        category="tu_lanh", slots={"ngan_sach_max": 12_000_000, "so_nguoi_dung": 4}
    )
    router = QueuedRouter(_s2(category="may_lanh"))
    res = _run("thôi đổi qua máy lạnh đi", profile, router, _full_retriever(total=50))
    assert profile.category == "may_lanh"
    assert profile.slots.get("ngan_sach_max") == 12_000_000
    assert "so_nguoi_dung" not in profile.slots
    assert res.kind == "ask"  # new category still misses dien_tich_m2


def test_none_and_empty_extraction_values_are_not_merged() -> None:
    profile = NeedProfile()
    router = QueuedRouter(_s2(slots={"dien_tich_m2": None, "uu_tien": []}))
    _run("tư vấn máy lạnh", profile, router, _full_retriever(total=50))
    assert "dien_tich_m2" not in profile.slots
    assert "uu_tien" not in profile.slots


# --------------------------------------------------------------------------- #
# Ask path (prefilter runs first, question is deterministic)                  #
# --------------------------------------------------------------------------- #
def test_ask_path_batches_slots_and_offers_quick_replies() -> None:
    profile = NeedProfile()
    router = QueuedRouter(_s2())
    retriever = _full_retriever(total=50)
    res = _run("tư vấn máy lạnh", profile, router, retriever)

    assert res.kind == "ask"
    assert res.policy is not None and res.policy.action == "ask" and res.policy.level == "cao"
    # 2 required + highest-priority optional, joined into one message.
    assert profile.asked_slots == ["ngan_sach_max", "dien_tich_m2", "loai_phong"]
    assert "ngân sách" in res.message.lower()
    assert "mét vuông" in res.message.lower()
    # Quick replies from the first asked slot that has enum values (loai_phong).
    assert res.quick_replies == ["phong_ngu", "phong_khach", "van_phong", "khac"]
    assert profile.clarify_rounds == 1
    # Ask turns never call the S6 LLM — S2 was the only router call.
    assert len(router.calls) == 1
    # Timely-feedback readiness: prefiltered candidates ride along on ask turns.
    assert res.candidates == CANDIDATES


def test_prefilter_receives_budget_separately_from_slots() -> None:
    profile = NeedProfile(
        category="may_lanh", slots={"ngan_sach_max": 15_000_000, "dien_tich_m2": 18.0}
    )
    router = QueuedRouter(_s2(), "Dạ em gợi ý như trên ạ.")
    retriever = _full_retriever()
    _run("xem giúp em với", profile, router, retriever)

    assert retriever.calls == [
        {
            "category_key": "may_lanh",
            "budget_max": 15_000_000,
            "slots": {"dien_tich_m2": 18.0},
            "limit": 20,
        }
    ]


# --------------------------------------------------------------------------- #
# Recommend path (facts → S5 → S6 → S7)                                       #
# --------------------------------------------------------------------------- #
def _recommend_profile() -> NeedProfile:
    return NeedProfile(
        category="may_lanh", slots={"ngan_sach_max": 20_000_000, "dien_tich_m2": 18.0}
    )


def test_recommend_happy_path_runs_full_chain() -> None:
    router = QueuedRouter(_s2(), "[1] có độ ồn 29dB.")
    retriever = _full_retriever()
    facts_tool = FakeFactsTool(FACTS)
    res = _run("chốt giúp em", _recommend_profile(), router, retriever, facts_tool)

    assert res.kind == "recommend"
    assert len(router.calls) == 2  # S2 + S6
    assert facts_tool.calls == [["sku_a", "sku_b", "sku_c"]]

    # S5 ran over the enriched candidates; dominant sku_a is [1].
    assert res.ranking is not None and res.ranking.top[0].sku == "sku_a"
    assert res.advice is not None and res.advice.marker_map["[1]"] == "sku_a"

    # Volatile fields overwritten from the facts tool, absence stays absence.
    by_sku = {c["sku"]: c for c in res.candidates}
    assert by_sku["sku_a"]["price"] == 15_990_000
    assert by_sku["sku_c"]["price"] is None
    assert res.facts["sku_a"] == {
        "capacity_btu": 12000,
        "noise_db_indoor": 29,
        "inverter": True,
        "energy_efficiency": 6.2,
        "price": 15_990_000,
    }
    assert set(res.fetched_at) == {"sku_a", "sku_b"}  # sku_c has no snapshot

    # S7 verified the prose claim against those facts.
    assert res.verification is not None
    assert [c.verdict for c in res.verification.claims] == ["match"]
    assert res.verification.per_claim_error_rate == 0.0
    assert res.message.startswith("[1] có độ ồn 29dB.")
    assert res.verifier_flags == [] and not res.regenerated

    # S8 side outputs: provenance panel + per-stage timings.
    panel = {(e.sku, e.field): e.dataset for e in res.source_panel}
    assert panel[("sku_a", "price")] == "may_lanh"
    assert panel[("sku_a", "noise_db_indoor")] == "catalog_snapshot"
    assert {"s1", "s2", "s4_prefilter", "s3_policy", "s5_rank", "s6_generate"} <= set(
        res.timings_ms
    )


def test_recommend_corrects_mismatch_in_place() -> None:
    # ≤2 incidents: enforcement fixes the number, no regenerate.
    router = QueuedRouter(_s2(), "[1] có độ ồn 25dB.")
    res = _run("chốt giúp em", _recommend_profile(), router, _full_retriever())
    assert res.kind == "recommend"
    assert res.message.startswith("[1] có độ ồn 29dB.")
    assert [f.action for f in res.verifier_flags] == ["corrected"]
    assert not res.regenerated and not res.used_fallback_table
    assert len(router.calls) == 2  # no S6 retry


_BAD_PROSE = "[1] có độ ồn 20dB. [1] giá 9.990.000đ. [2] có độ ồn 20dB."  # 3 mismatches


def test_escalation_regenerates_once_with_error_feedback() -> None:
    router = QueuedRouter(_s2(), _BAD_PROSE, "[1] có độ ồn 29dB.")
    res = _run("chốt giúp em", _recommend_profile(), router, _full_retriever())

    assert res.regenerated and not res.used_fallback_table
    assert res.message.startswith("[1] có độ ồn 29dB.")
    assert len(router.calls) == 3  # S2 + S6 + S6-retry
    retry_user_content = router.calls[2][0][1]["content"]
    assert "PHẢI SỬA" in retry_user_content  # specific error feedback was injected
    assert "s6_regenerate" in res.timings_ms


def test_escalation_falls_back_to_table_when_retry_still_bad() -> None:
    router = QueuedRouter(_s2(), _BAD_PROSE, _BAD_PROSE)
    res = _run("chốt giúp em", _recommend_profile(), router, _full_retriever())

    assert res.regenerated and res.used_fallback_table
    assert "số liệu trực tiếp từ hệ thống" in res.message
    assert "Panasonic Inverter 12000 BTU" in res.message
    assert "20dB" not in res.message  # fabricated numbers never reach the user


def test_quota_exhausted_proceeds_with_stated_assumptions() -> None:
    profile = NeedProfile(category="may_lanh", clarify_rounds=2)  # quota spent
    router = QueuedRouter(_s2(), "Dạ em gợi ý tạm như trên ạ.")
    res = _run("gợi ý luôn đi", profile, router, _full_retriever(total=50))

    assert res.kind == "recommend"
    assert res.policy is not None
    assert res.policy.proceeded_with_assumptions == ["ngan_sach_max", "dien_tich_m2"]
    assert "Lưu ý:" in res.message
    assert "Giả định" in res.message


def test_no_results_is_honest_and_skips_generation() -> None:
    profile = _recommend_profile()
    router = QueuedRouter(_s2())
    retriever = FakeRetriever(RetrievalResult(candidates=[], total_count=0))
    res = _run("tìm giúp em", profile, router, retriever)

    assert res.kind == "no_results"
    assert "chưa tìm được" in res.message
    assert len(router.calls) == 1  # no S6 call on an empty candidate set
    assert res.ranking is None and res.advice is None
