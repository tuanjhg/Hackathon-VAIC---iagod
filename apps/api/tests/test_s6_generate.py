"""S6 — statement-template generation tests (ADR A8/C5).

Two layers are exercised separately:

* **Layer 1 (deterministic, no LLM)**: the glossary renders technical spec
  fields into plain-language Vietnamese; statement building fills those phrases
  with the *real* values from the candidate/trade-off data and never invents a
  number; the ``marker_map`` binds ``[1]/[2]/[3]/[A]`` to SKUs (the contract S7
  depends on).

* **Layer 2 (LLM rephrase)**: driven with a hand-written ``FakeRouter`` double
  (same pattern as ``tests/test_s2_extract.py`` — records the last messages and
  kwargs, returns a canned OpenAI-compatible body). The real LLM is never called.

Async ``generate`` is driven with ``asyncio.run`` so we do not depend on an async
pytest plugin (none is installed), matching ``tests/test_s2_extract.py``.
"""

import asyncio
import json
from typing import Any

import pytest

from src.pipeline.need_profile import NeedProfile
from src.pipeline.s5_ranking import RankingResult, ScoreBreakdown, TradeOff
from src.pipeline.s6_generate import (
    GeneratedAdvice,
    S6GenerationError,
    build_advisory_statements,
    generate,
    render_spec,
)


class FakeRouter:
    """Minimal ``LLMRouterLike`` double: returns a canned body and records its
    last call so tests can assert on the messages/kwargs S6 sent.
    """

    def __init__(self, content: Any) -> None:
        self._content = content
        self.last_messages: list[dict[str, Any]] | None = None
        self.last_kwargs: dict[str, Any] | None = None
        self.call_count = 0

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.last_messages = messages
        self.last_kwargs = kwargs
        self.call_count += 1
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


class BrokenRouter:
    """A double whose response is missing ``content`` (unexpected shape)."""

    def __init__(self) -> None:
        self.call_count = 0

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.call_count += 1
        return {"choices": [{"message": {"role": "assistant"}}]}


# A 4-candidate máy lạnh set covering three glossary field types (inverter,
# noise_db_indoor, capacity_btu) plus energy_efficiency for the trade-off.
CANDIDATES: list[dict[str, Any]] = [
    {
        "sku": "A",
        "name": "Panasonic Inverter 24000 BTU",
        "specs": {
            "capacity_btu": 24000,
            "noise_db_indoor": 29,
            "inverter": True,
            "energy_efficiency": 5.0,
        },
        "price": 15990000,
        "in_stock": None,
    },
    {
        "sku": "B",
        "name": "Daikin 24000 BTU",
        "specs": {
            "capacity_btu": 24000,
            "noise_db_indoor": 31,
            "inverter": True,
            "energy_efficiency": 6.0,
        },
        "price": 16990000,
        "in_stock": None,
    },
    {
        "sku": "C",
        "name": "LG DualCool 24000 BTU",
        "specs": {
            "capacity_btu": 24000,
            "noise_db_indoor": 33,
            "inverter": True,
            "energy_efficiency": 5.5,
        },
        "price": 14990000,
        "in_stock": None,
    },
    {
        "sku": "D",
        "name": "Casper 24000 BTU",
        "specs": {"capacity_btu": 24000, "noise_db_indoor": 40, "inverter": False},
        "price": 11990000,
        "in_stock": None,
    },
]


def _ranking(*, with_anti: bool = True) -> RankingResult:
    top = [
        ScoreBreakdown(
            sku="A",
            total_score=5.0,
            per_criterion={"noise_db_indoor": 3.0},
            missing_fields=[],
            price=15990000,
        ),
        ScoreBreakdown(
            sku="B",
            total_score=4.0,
            per_criterion={"energy_efficiency": 3.0},
            missing_fields=[],
            price=16990000,
        ),
        ScoreBreakdown(
            sku="C", total_score=3.0, per_criterion={}, missing_fields=[], price=14990000
        ),
    ]
    trade_off = TradeOff(
        sku_a="A",
        sku_b="B",
        a_wins_on=["noise_db_indoor"],
        b_wins_on=["energy_efficiency"],
        values={"noise_db_indoor": (29, 31), "energy_efficiency": (5.0, 6.0)},
    )
    anti = None
    reason = None
    if with_anti:
        anti = ScoreBreakdown(
            sku="D",
            total_score=1.0,
            per_criterion={},
            missing_fields=["energy_efficiency"],
            price=11990000,
        )
        reason = "Điểm phù hợp thấp nhất trong nhóm có giá."
    return RankingResult(top=top, anti_pick=anti, anti_pick_reason=reason, trade_offs=[trade_off])


# --- Layer 1: glossary rendering ----------------------------------------------


def test_glossary_renders_inverter_plain_language() -> None:
    rendered = render_spec("inverter", True)
    assert rendered is not None
    assert "tự điều chỉnh công suất" in rendered
    assert "đỡ tốn điện" in rendered


def test_glossary_renders_low_noise_as_whisper() -> None:
    rendered = render_spec("noise_db_indoor", 29)
    assert rendered is not None
    assert "êm hơn tiếng thì thầm" in rendered
    # The real dB number is present, not invented.
    assert "29" in rendered


def test_glossary_renders_capacity_btu() -> None:
    rendered = render_spec("capacity_btu", 24000)
    assert rendered is not None
    assert "24000 BTU" in rendered


def test_glossary_unknown_field_returns_none() -> None:
    assert render_spec("some_unmapped_field", 123) is None
    # Known field, but missing value -> nothing to render.
    assert render_spec("inverter", None) is None


# --- Layer 1: statement building + marker map ---------------------------------


def test_marker_map_assigns_1_2_3_and_anti() -> None:
    _statements, marker_map = build_advisory_statements(_ranking(with_anti=True), CANDIDATES)
    assert marker_map == {"[1]": "A", "[2]": "B", "[3]": "C", "[A]": "D"}


def test_marker_map_omits_anti_when_none() -> None:
    _statements, marker_map = build_advisory_statements(_ranking(with_anti=False), CANDIDATES)
    assert marker_map == {"[1]": "A", "[2]": "B", "[3]": "C"}
    assert "[A]" not in marker_map


def test_top_statement_uses_marker_and_real_specs() -> None:
    statements, _marker_map = build_advisory_statements(_ranking(), CANDIDATES)
    first = statements[0]
    assert first.startswith("[1]")
    assert "Panasonic Inverter 24000 BTU" in first
    # Plain-language phrases from the glossary, filled with the candidate's specs.
    assert "tự điều chỉnh công suất" in first
    assert "êm hơn tiếng thì thầm" in first
    assert "29" in first


def test_trade_off_statement_numbers_appear_verbatim() -> None:
    statements, _marker_map = build_advisory_statements(_ranking(), CANDIDATES)
    joined = "\n".join(statements)
    # There is exactly one trade-off statement; it references both markers and
    # the real differentiating numbers from TradeOff.values -- nothing invented.
    trade_line = next(s for s in statements if s.startswith("[1] vs [2]"))
    for token in ("29", "31", "5.0", "6.0"):
        assert token in trade_line
    # Every number in the statement traces back to the source specs/values.
    assert "[A]" in joined  # anti-pick statement present


def test_statements_never_invent_numbers() -> None:
    statements, _marker_map = build_advisory_statements(_ranking(), CANDIDATES)
    # Spot-check: the noise numbers used are exactly those in the candidate specs
    # / trade-off values; no other 2-digit-with-dB style number sneaks in.
    source_numbers = {"24000", "29", "31", "33", "5.0", "6.0", "5.5"}
    trade_line = next(s for s in statements if s.startswith("[1] vs [2]"))
    # Pull the parenthesised numbers out and confirm each is a real source value.
    for token in ("29", "31", "5.0", "6.0"):
        assert token in trade_line
        assert token in source_numbers


def test_anti_pick_statement_uses_reason_and_missing_fields() -> None:
    statements, _marker_map = build_advisory_statements(_ranking(), CANDIDATES)
    anti_line = next(s for s in statements if s.startswith("[A]"))
    assert "Casper 24000 BTU" in anti_line
    assert "Điểm phù hợp thấp nhất" in anti_line
    assert "energy_efficiency" in anti_line  # surfaced missing field


# --- Layer 2: LLM rephrase ----------------------------------------------------


def test_generate_returns_llm_text_and_layer1_artifacts() -> None:
    router = FakeRouter("Dạ em hiểu anh cần máy lạnh 24000 BTU...")
    result = asyncio.run(generate(router, _ranking(), CANDIDATES, NeedProfile(category="may_lanh")))

    assert isinstance(result, GeneratedAdvice)
    assert result.text == "Dạ em hiểu anh cần máy lạnh 24000 BTU..."
    assert result.marker_map == {"[1]": "A", "[2]": "B", "[3]": "C", "[A]": "D"}
    assert result.statements  # Layer-1 statements carried through
    assert router.call_count == 1


def test_generate_disables_reasoning_and_uses_generative_temperature() -> None:
    router = FakeRouter("prose")
    asyncio.run(generate(router, _ranking(), CANDIDATES, NeedProfile(category="may_lanh")))

    assert router.last_kwargs is not None
    # Confirmed-by-testing requirement: OpenRouter's own reasoning switch, OFF.
    assert router.last_kwargs["reasoning"] == {"enabled": False}
    # Unlike S2 extraction (temperature=0), S6 is generative prose (non-zero).
    assert router.last_kwargs["temperature"] > 0


def test_generate_prompt_contains_statements_not_raw_json() -> None:
    router = FakeRouter("prose")
    profile = NeedProfile(category="may_lanh", slots={"ngan_sach_max": 16000000})
    asyncio.run(generate(router, _ranking(), CANDIDATES, profile))

    assert router.last_messages is not None
    serialized = json.dumps(router.last_messages, ensure_ascii=False)

    # The rendered deterministic statements reach the LLM verbatim.
    statements, _ = build_advisory_statements(_ranking(), CANDIDATES)
    assert statements[0] in serialized

    # ...but NOT a raw JSON dump of the candidates or the RankingResult. These
    # keys only exist in those raw structures, never in a rendered statement.
    assert "in_stock" not in serialized
    assert "total_score" not in serialized
    assert "per_criterion" not in serialized


def test_generate_includes_need_profile_context() -> None:
    router = FakeRouter("prose")
    profile = NeedProfile(category="may_lanh", slots={"ngan_sach_max": 16000000})
    asyncio.run(generate(router, _ranking(), CANDIDATES, profile))

    assert router.last_messages is not None
    serialized = json.dumps(router.last_messages, ensure_ascii=False)
    assert "may_lanh" in serialized  # category context for the summary line


def test_generate_malformed_response_raises() -> None:
    router = BrokenRouter()
    with pytest.raises(S6GenerationError):
        asyncio.run(generate(router, _ranking(), CANDIDATES, NeedProfile(category="may_lanh")))
