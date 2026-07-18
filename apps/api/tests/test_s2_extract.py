"""S2 — intent + slot extraction tests (ADR C2).

The real LLM is never called: a hand-written ``FakeRouter`` test double (an
object with an ``async complete(...)`` method, structurally an ``LLMRouterLike``)
returns a canned OpenAI-compatible response body. This is deliberately *not*
``httpx.MockTransport`` — that mocks the transport one layer below, for testing
``LLMRouter`` itself; here we mock the router that S2 depends on.

Async ``extract`` is driven with ``asyncio.run`` so we do not depend on an async
pytest plugin (none is installed), matching ``tests/test_router.py``.
"""

import asyncio
import json
from typing import Any

import pytest

from src.pipeline.need_profile import NeedProfile
from src.pipeline.preprocess import S1Result, UnitMatch
from src.pipeline.s2_extract import (
    INTENTS,
    S2ExtractionError,
    S2Result,
    build_response_format,
    extract,
)


class FakeRouter:
    """Minimal ``LLMRouterLike`` double: returns a canned body and records its
    last call so tests can assert on the messages/kwargs S2 sent.
    """

    def __init__(self, content: str) -> None:
        self._content = content
        self.last_messages: list[dict[str, Any]] | None = None
        self.last_kwargs: dict[str, Any] | None = None
        self.call_count = 0

    async def complete(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        self.last_messages = messages
        self.last_kwargs = kwargs
        self.call_count += 1
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


def make_s1(
    raw: str, normalized: str, category_hint: str | None = None
) -> S1Result:
    return S1Result(raw=raw, normalized=normalized, category_hint=category_hint)


def fake_with(payload: dict[str, Any]) -> FakeRouter:
    return FakeRouter(json.dumps(payload, ensure_ascii=False))


# --- Schema building (no LLM call) --------------------------------------------


def test_build_response_format_may_lanh_includes_required_slots() -> None:
    response_format = build_response_format("may_lanh")

    schema = response_format["json_schema"]["schema"]
    slots_props = schema["properties"]["slots_moi"]["properties"]

    # Required slots from the may_lanh SlotProfile are present, keyed by name.
    assert "ngan_sach_max" in slots_props
    assert "dien_tich_m2" in slots_props

    # money -> nullable integer; area_m2 -> nullable number (type-mapping rules).
    assert slots_props["ngan_sach_max"]["type"] == ["integer", "null"]
    assert slots_props["dien_tich_m2"]["type"] == ["number", "null"]

    # intent is constrained to the canonical ASCII literals.
    assert set(schema["properties"]["intent"]["enum"]) == set(INTENTS)
    assert "ho_tro_giao_dich" in INTENTS


def test_build_response_format_generic_fallback_has_open_slots() -> None:
    # None category => generic open-ended object, no per-field schema, no lookup.
    response_format = build_response_format(None)
    slots_schema = response_format["json_schema"]["schema"]["properties"]["slots_moi"]

    assert slots_schema["type"] == "object"
    assert "properties" not in slots_schema


def test_build_response_format_maps_enum_and_multi_enum() -> None:
    schema = build_response_format("may_lanh")["json_schema"]["schema"]
    slots_props = schema["properties"]["slots_moi"]["properties"]

    # enum -> nullable string with the profile values plus a null sentinel.
    loai_phong = slots_props["loai_phong"]
    assert loai_phong["type"] == ["string", "null"]
    assert "phong_ngu" in loai_phong["enum"]
    assert None in loai_phong["enum"]

    # multi_enum -> array of enum strings.
    uu_tien = slots_props["uu_tien"]
    assert uu_tien["type"] == "array"
    assert uu_tien["items"]["enum"] == ["tiet_kiem_dien", "em", "ben", "gia_re"]


# --- extract() happy path -----------------------------------------------------


def test_extract_happy_path_returns_matching_result() -> None:
    router = fake_with(
        {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"ngan_sach_max": 20000000}}
    )
    s1 = make_s1("may lanh 20 trieu", "máy lạnh 20 triệu", category_hint="may_lanh")

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile(category="may_lanh")))

    assert isinstance(result, S2Result)
    assert result.intent == "tu_van"
    assert result.category == "may_lanh"
    assert result.slots_moi == {"ngan_sach_max": 20000000}
    assert router.call_count == 1


def test_extract_passes_raw_and_normalized_and_temperature_zero() -> None:
    router = fake_with({"intent": "tu_van", "category": "may_lanh", "slots_moi": {}})
    s1 = make_s1(
        raw="may lanh 1.5 ngua tam 12 trieu",
        normalized="máy lạnh 1.5 ngựa tầm 12 triệu",
        category_hint="may_lanh",
    )

    asyncio.run(extract(router, s1.raw, s1, NeedProfile()))

    assert router.last_messages is not None
    serialized = json.dumps(router.last_messages, ensure_ascii=False)
    # Both the raw (no-diacritics) text and the normalized text reach the LLM.
    assert "may lanh 1.5 ngua tam 12 trieu" in serialized
    assert "máy lạnh 1.5 ngựa tầm 12 triệu" in serialized
    assert "loai_phong" in serialized and "phong_ngu" in serialized
    assert "nang_truc_tiep" in serialized

    # Deterministic extraction + guided JSON per the ADR.
    assert router.last_kwargs is not None
    assert router.last_kwargs["temperature"] == 0
    assert "response_format" in router.last_kwargs


def test_extract_includes_prior_profile_context_in_prompt() -> None:
    router = fake_with({"intent": "tu_van", "category": "may_lanh", "slots_moi": {}})
    s1 = make_s1("them thong tin", "thêm thông tin", category_hint="may_lanh")
    profile = NeedProfile(category="may_lanh", slots={"ngan_sach_max": 15000000})

    asyncio.run(extract(router, s1.raw, s1, profile))

    assert router.last_messages is not None
    serialized = json.dumps(router.last_messages, ensure_ascii=False)
    # Known slots are summarized so the model does not re-extract/re-ask them.
    assert "ngan_sach_max" in serialized
    assert "15000000" in serialized


# --- extract() error handling -------------------------------------------------


def test_extract_malformed_json_raises() -> None:
    router = FakeRouter("this is not json {oops")
    s1 = make_s1("may lanh", "máy lạnh", category_hint="may_lanh")

    with pytest.raises(S2ExtractionError):
        asyncio.run(extract(router, s1.raw, s1, NeedProfile()))


def test_extract_unknown_category_from_llm_raises() -> None:
    router = fake_with(
        {"intent": "tu_van", "category": "khong_ton_tai", "slots_moi": {}}
    )
    s1 = make_s1("gi do", "gì đó")

    with pytest.raises(S2ExtractionError):
        asyncio.run(extract(router, s1.raw, s1, NeedProfile()))


# --- extract() slot reconciliation (schema not always provider-enforced) ------
#
# The OpenRouter route for the primary model does not strictly enforce the
# guided-JSON schema (docs/pipelines.md §6.9), so the LLM can emit slot KEYS or
# VALUES outside the category schema. extract() must reconcile slots_moi against
# the canonical SlotProfile before returning, and overlay S1's deterministic
# numeric parses (regex-precise) which outrank the probabilistic LLM.


def make_s1_units(
    raw: str,
    normalized: str,
    category_hint: str | None,
    units: list[UnitMatch],
) -> S1Result:
    return S1Result(
        raw=raw, normalized=normalized, category_hint=category_hint, units=units
    )


def test_extract_drops_noncanonical_slot_keys() -> None:
    # LLM emits a key that is NOT in the may_lanh schema, and no S1 unit backs it.
    router = fake_with(
        {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"dien_tich_phong": 18.0}}
    )
    s1 = make_s1("phong nho", "phòng nhỏ", category_hint="may_lanh")

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile(category="may_lanh")))

    # The bogus key is dropped; the canonical area slot is not fabricated from it.
    assert "dien_tich_phong" not in result.slots_moi
    assert "dien_tich_m2" not in result.slots_moi


def test_extract_recovers_area_from_s1_units_when_llm_misses_it() -> None:
    # The bug: user said "18m2", S1 parsed it deterministically, but the LLM
    # emitted no area slot (or a non-canonical one). S1's area must land in
    # the canonical dien_tich_m2 slot so S3 does not re-ask it.
    router = fake_with({"intent": "tu_van", "category": "may_lanh", "slots_moi": {}})
    s1 = make_s1_units(
        "phong 18m2", "phòng 18m2", "may_lanh", [UnitMatch("area_m2", 18.0, "18m2", (6, 10))]
    )

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile(category="may_lanh")))

    assert result.slots_moi["dien_tich_m2"] == 18.0


def test_extract_s1_area_overrides_llm_area_value() -> None:
    # Deterministic S1 parse outranks the probabilistic LLM for the same slot.
    router = fake_with(
        {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"dien_tich_m2": 25.0}}
    )
    s1 = make_s1_units(
        "phong 18m2", "phòng 18m2", "may_lanh", [UnitMatch("area_m2", 18.0, "18m2", (6, 10))]
    )

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile(category="may_lanh")))

    assert result.slots_moi["dien_tich_m2"] == 18.0


def test_extract_recovers_enum_slot_by_value_when_key_is_wrong() -> None:
    # LLM used a non-canonical KEY ("dia_diem_dat") but a VALID loai_phong VALUE.
    router = fake_with(
        {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"dia_diem_dat": "phong_ngu"}}
    )
    s1 = make_s1("phong ngu", "phòng ngủ", category_hint="may_lanh")

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile(category="may_lanh")))

    assert result.slots_moi["loai_phong"] == "phong_ngu"
    assert "dia_diem_dat" not in result.slots_moi


def test_extract_drops_invalid_enum_value() -> None:
    # Correct key, but a value outside the loai_phong enum -> dropped, not merged.
    router = fake_with(
        {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"loai_phong": "garage"}}
    )
    s1 = make_s1("noi khac", "nơi khác", category_hint="may_lanh")

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile(category="may_lanh")))

    assert "loai_phong" not in result.slots_moi


def test_extract_matches_accented_enum_value_to_canonical() -> None:
    # Correct key, but the value carries diacritics/spacing (schema unenforced) —
    # ViSoLex-style accent folding maps "Phòng ngủ" to canonical "phong_ngu".
    router = fake_with(
        {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"loai_phong": "Phòng ngủ"}}
    )
    s1 = make_s1("phong ngu", "phòng ngủ", category_hint="may_lanh")

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile(category="may_lanh")))

    assert result.slots_moi["loai_phong"] == "phong_ngu"


def test_extract_recovers_accented_enum_under_wrong_key() -> None:
    # Wrong KEY *and* accented VALUE -> still recovered to canonical loai_phong.
    router = fake_with(
        {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"dia_diem_dat": "phòng ngủ"}}
    )
    s1 = make_s1("phong ngu", "phòng ngủ", category_hint="may_lanh")

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile(category="may_lanh")))

    assert result.slots_moi["loai_phong"] == "phong_ngu"


def test_extract_matches_accented_multi_enum_priority() -> None:
    # multi_enum value with diacritics folds to the canonical priority token.
    router = fake_with(
        {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"uu_tien": ["tiết kiệm điện"]}}
    )
    s1 = make_s1("tiet kiem dien", "tiết kiệm điện", category_hint="may_lanh")

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile(category="may_lanh")))

    assert result.slots_moi["uu_tien"] == ["tiet_kiem_dien"]


# --- extract() generic fallback (no category known yet) -----------------------


def test_extract_generic_fallback_no_category() -> None:
    # First turn: S1 has no category hint, profile has no category. Must still
    # call the router and return a result WITHOUT a SlotProfile lookup
    # (no FileNotFoundError).
    router = fake_with({"intent": "tu_van", "category": None, "slots_moi": {}})
    s1 = make_s1("cho minh hoi chut", "cho mình hỏi chút", category_hint=None)

    result = asyncio.run(extract(router, s1.raw, s1, NeedProfile()))

    assert result.intent == "tu_van"
    assert result.category is None
    assert result.slots_moi == {}
    assert router.call_count == 1
