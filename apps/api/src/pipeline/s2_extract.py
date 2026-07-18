"""S2 — intent + slot extraction (LLM guided-JSON).

Per `docs/research/dmx-ai-workflow-v1.md` §3 "S2" and ADR C2 of
`docs/research/dmx-tech-decisions.md`: given the raw user text, the deterministic
S1 result already computed by the caller, and the current Need Profile, S2 asks
the LLM (``temperature=0`` + a ``response_format`` guided-JSON schema) to extract:

* ``intent`` — one of five ASCII literals (see :data:`INTENTS`);
* ``category`` — a ``category_key`` known to the slot-profile system, or ``None``;
* ``slots_moi`` — newly-extracted slot values, keyed by the slot names of the
  active category's :class:`~src.pipeline.slots.SlotProfile`.

The JSON schema for ``slots_moi`` is built *dynamically per category* from that
profile's required + optional slots. Until the category is pinned down (first
turn, S1's ``category_hint`` also ``None``, profile has no category) S2 falls
back to a generic open-ended ``slots_moi`` object — extraction is best-effort.

This stage is a decoupled building block: it takes an ``LLMRouterLike`` by
dependency injection (so tests inject a fake), returns the extracted data as an
:class:`S2Result`, and does *not* mutate the Need Profile (the caller merges).
On unparseable output or an unrecognised category it raises
:class:`S2ExtractionError` rather than swallowing — retry/fallback is the
router's job, not S2's.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from src.pipeline.need_profile import NeedProfile
from src.pipeline.preprocess import S1Result
from src.pipeline.slots import SlotDef, available_categories, load_slot_profile

# Five intent literals, ASCII (no diacritics) to match the slot-name convention
# already used in this codebase (``ngan_sach_max`` etc.).
INTENTS: tuple[str, ...] = (
    "tu_van",
    "so_sanh_truc_tiep",
    "policy_faq",
    "hoi_chi_tiet_sp",
    "ngoai_pham_vi",
)

# One-line definition per intent, injected into the system prompt.
_INTENT_DEFINITIONS: dict[str, str] = {
    "tu_van": "khách cần tư vấn/gợi ý sản phẩm phù hợp (mặc định khi chưa rõ ý khác).",
    "so_sanh_truc_tiep": "khách nêu tên >=2 sản phẩm cụ thể và muốn so sánh trực tiếp.",
    "policy_faq": "khách hỏi chính sách (bảo hành, trả góp, giao hàng), không phải chọn sản phẩm.",
    "hoi_chi_tiet_sp": "khách hỏi chi tiết về một sản phẩm cụ thể đã được giới thiệu.",
    "ngoai_pham_vi": "câu hỏi ngoài phạm vi tư vấn điện máy.",
}


class LLMRouterLike(Protocol):
    """Structural type for anything with the router's ``complete`` coroutine.

    Lets S2 accept a real :class:`~src.router.client.LLMRouter` in production and
    a lightweight fake in tests without a shared base class.
    """

    async def complete(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]: ...


class S2ExtractionError(RuntimeError):
    """Raised when the LLM's S2 output cannot be trusted.

    Two causes: the ``content`` is not valid JSON, or it names an ``intent`` /
    ``category`` the profile system does not recognise. Never swallowed — the
    caller decides whether to retry or fall back.
    """


@dataclass(frozen=True)
class S2Result:
    """Structured output of the S2 stage (feeds ``NeedProfile.merge_slots``)."""

    intent: str
    category: str | None
    slots_moi: dict[str, Any]


def _slot_property_schema(slot: SlotDef) -> dict[str, Any]:
    """Map a :class:`SlotDef` ``type`` to its JSON-Schema fragment.

    Scalar slots are nullable (``["<type>", "null"]``) so the model can emit
    ``null`` when a value is not present in the turn; ``multi_enum`` is a plain
    array of enum strings (empty array when nothing selected).
    """
    slot_type = slot.type
    if slot_type == "money":
        return {"type": ["integer", "null"]}
    if slot_type in ("area_m2", "volume_liter", "power_watt"):
        return {"type": ["number", "null"]}
    if slot_type == "enum":
        # Nullable-via-enum: include the profile values plus a ``null`` sentinel.
        return {"type": ["string", "null"], "enum": [*(slot.values or []), None]}
    if slot_type == "multi_enum":
        return {"type": "array", "items": {"type": "string", "enum": list(slot.values or [])}}
    if slot_type == "boolean":
        return {"type": ["boolean", "null"]}
    # "text" and any future/unknown type: nullable free string.
    return {"type": ["string", "null"]}


def build_response_format(category_key: str | None) -> dict[str, Any]:
    """Build the guided-JSON ``response_format`` payload for ``category_key``.

    When ``category_key`` is a known category, ``slots_moi`` gets a strict
    per-field object schema derived from that category's required + optional
    slots. When ``category_key`` is ``None`` (category not yet known), it falls
    back to a generic open-ended object with no per-field schema — no
    :class:`SlotProfile` lookup happens, so this never raises ``FileNotFoundError``.
    """
    if category_key is None:
        slots_schema: dict[str, Any] = {"type": "object"}
        category_schema: dict[str, Any] = {"type": ["string", "null"]}
    else:
        profile = load_slot_profile(category_key)
        properties = {
            slot.name: _slot_property_schema(slot)
            for slot in [*profile.required_slots, *profile.optional_slots]
        }
        slots_schema = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        category_schema = {"type": ["string", "null"], "enum": [*available_categories(), None]}

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": list(INTENTS)},
            "category": category_schema,
            "slots_moi": slots_schema,
        },
        "required": ["intent", "category", "slots_moi"],
    }
    return {
        "type": "json_schema",
        "json_schema": {"name": "s2_extraction", "schema": schema},
    }


def _resolve_schema_category(s1_result: S1Result, profile: NeedProfile) -> str | None:
    """Pick the category the guided-JSON schema is built for.

    Prefer the profile's locked-in category, else S1's dictionary hint. Only a
    category the slot-profile system actually knows is returned; anything else
    resolves to ``None`` so schema-building degrades to the generic fallback
    instead of raising ``FileNotFoundError`` mid-conversation.
    """
    candidate = profile.category or s1_result.category_hint
    if candidate is not None and candidate in available_categories():
        return candidate
    return None


def _build_system_prompt(category_key: str | None, profile: NeedProfile) -> str:
    intents_block = "\n".join(f"- {name}: {desc}" for name, desc in _INTENT_DEFINITIONS.items())

    if category_key is None:
        category_block = (
            "Ngành hàng CHƯA xác định. Nếu đoán được, đặt `category` là một "
            "category_key hợp lệ; nếu chưa chắc, để `null`. `slots_moi` để trống "
            "hoặc chỉ điền slot chắc chắn."
        )
    else:
        category_block = (
            f"Ngành hàng hiện tại: `{category_key}`. Chỉ điền `slots_moi` bằng các "
            "slot có trong schema của ngành này. Nếu khách đổi sang ngành khác, đặt "
            "`category` sang category_key mới."
        )

    known_slots = {k: v for k, v in profile.slots.items() if v is not None}
    prior_context = (
        f"Bối cảnh đã biết (đừng hỏi/không trích lại): category={profile.category!r}, "
        f"slots đã có={json.dumps(known_slots, ensure_ascii=False)}."
    )

    examples = _few_shot_examples()

    return (
        "Bạn là bộ trích xuất ý định + slot cho trợ lý tư vấn điện máy (tiếng Việt).\n"
        "Chỉ trả về JSON đúng schema, không giải thích.\n\n"
        "Các ý định (`intent`) khả dĩ:\n"
        f"{intents_block}\n\n"
        f"{category_block}\n\n"
        f"{prior_context}\n\n"
        "Lưu ý: khách có thể viết không dấu, chèn thuật ngữ tiếng Anh, hoặc đổi ý "
        "giữa chừng — bám vào ý mới nhất.\n\n"
        "Ví dụ:\n"
        f"{examples}"
    )


def _few_shot_examples() -> str:
    """3-4 few-shot examples: no-diacritics, code-switching, and a mid-chat
    category change. Rendered as ``<input> -> <json>`` lines.
    """
    examples: list[tuple[str, dict[str, Any]]] = [
        # No-diacritics input.
        (
            "may lanh 1.5 ngua tam 12 trieu",
            {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"ngan_sach_max": 12000000}},
        ),
        # Code-switching (English tech terms mixed in).
        (
            "can con may giat inverter, budget khoang 10tr",
            {"intent": "tu_van", "category": "may_giat", "slots_moi": {"ngan_sach_max": 10000000}},
        ),
        # Customer changes their mind mid-conversation (was tủ lạnh, switches).
        (
            "(dang tu van tu lanh) thoi doi qua may lanh di anh",
            {"intent": "tu_van", "category": "may_lanh", "slots_moi": {}},
        ),
        # Direct comparison of 2+ named products.
        (
            "so sanh Panasonic XPU va Daikin FTKB cai nao tot hon",
            {"intent": "so_sanh_truc_tiep", "category": "may_lanh", "slots_moi": {}},
        ),
    ]
    return "\n".join(
        f"- {text} -> {json.dumps(out, ensure_ascii=False)}" for text, out in examples
    )


def _build_user_content(text: str, s1_result: S1Result) -> str:
    """User-turn content: raw + normalized text together (ADR: "text gốc +
    text chuẩn hóa cùng đưa vào S2"), plus S1's deterministic hints.
    """
    lines = [
        f"Text gốc (raw): {text}",
        f"Text chuẩn hóa (normalized): {s1_result.normalized}",
    ]
    if s1_result.category_hint:
        lines.append(f"Gợi ý ngành hàng từ S1: {s1_result.category_hint}")
    if s1_result.money:
        money = ", ".join(f"{m.min_vnd}-{m.max_vnd} VND" for m in s1_result.money)
        lines.append(f"Số tiền S1 bắt được: {money}")
    if s1_result.units:
        units = ", ".join(f"{u.kind}={u.value}" for u in s1_result.units)
        lines.append(f"Đơn vị S1 bắt được: {units}")
    return "\n".join(lines)


def _parse_s2_payload(data: Any) -> S2Result:
    if not isinstance(data, dict):
        raise S2ExtractionError(f"S2 payload must be a JSON object, got {type(data).__name__}")

    intent = data.get("intent")
    if intent not in INTENTS:
        raise S2ExtractionError(f"S2 payload has unknown intent {intent!r}")

    category = data.get("category")
    if category is not None and category not in available_categories():
        raise S2ExtractionError(f"S2 payload names unknown category {category!r}")

    slots_moi = data.get("slots_moi")
    if slots_moi is None:
        slots_moi = {}
    if not isinstance(slots_moi, dict):
        raise S2ExtractionError("S2 payload 'slots_moi' must be a JSON object")

    return S2Result(intent=intent, category=category, slots_moi=slots_moi)


async def extract(
    router: LLMRouterLike,
    text: str,
    s1_result: S1Result,
    profile: NeedProfile,
) -> S2Result:
    """Run S2: extract ``intent`` + ``category`` + ``slots_moi`` via the LLM.

    Builds a guided-JSON schema for the active (or generic) category, sends the
    raw + normalized text plus prior Need-Profile context at ``temperature=0``,
    and returns the parsed :class:`S2Result`. Raises :class:`S2ExtractionError`
    if the model's output is not valid JSON or names an unknown intent/category.
    """
    category_key = _resolve_schema_category(s1_result, profile)
    response_format = build_response_format(category_key)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _build_system_prompt(category_key, profile)},
        {"role": "user", "content": _build_user_content(text, s1_result)},
    ]

    response = await router.complete(
        messages,
        temperature=0,
        response_format=response_format,
        # Provider-level reasoning switch (OpenRouter's own field, ADR A2'').
        # NOT vLLM's chat_template_kwargs.enable_thinking -- confirmed 18/07 that
        # OpenRouter silently ignores that field for this model, leaving the model
        # to reason at length (~25s/call, malformed/null content). If the primary
        # provider ever moves off OpenRouter, this needs re-verifying against
        # whatever that provider's equivalent switch is.
        reasoning={"enabled": False},
    )

    content = response["choices"][0]["message"]["content"]
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise S2ExtractionError(f"S2 LLM output was not valid JSON: {content!r}") from exc

    return _parse_s2_payload(data)
