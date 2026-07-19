"""S2 — intent + slot extraction (LLM guided-JSON).

Per `docs/research/dmx-ai-workflow-v1.md` §3 "S2" and ADR C2 of
`docs/research/dmx-tech-decisions.md`: given the raw user text, the deterministic
S1 result already computed by the caller, and the current Need Profile, S2 asks
the LLM (``temperature=0`` + a ``response_format`` guided-JSON schema) to extract:

* ``intent`` — one of the ASCII literals in :data:`INTENTS`;
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
import re
from dataclasses import dataclass
from typing import Any, Protocol

from src.pipeline.humanize import fold_ascii
from src.pipeline.need_profile import NeedProfile
from src.pipeline.preprocess import S1Result
from src.pipeline.slots import SlotDef, SlotProfile, available_categories, load_slot_profile

# Intent literals, ASCII (no diacritics) to match the slot-name convention
# already used in this codebase (``ngan_sach_max`` etc.).
INTENTS: tuple[str, ...] = (
    "tu_van",
    "so_sanh_truc_tiep",
    "policy_faq",
    "hoi_chi_tiet_sp",
    "ho_tro_giao_dich",
    "ngoai_pham_vi",
)

# One-line definition per intent, injected into the system prompt.
_INTENT_DEFINITIONS: dict[str, str] = {
    "tu_van": "khách cần tư vấn/gợi ý sản phẩm phù hợp (mặc định khi chưa rõ ý khác).",
    "so_sanh_truc_tiep": "khách nêu tên >=2 sản phẩm cụ thể và muốn so sánh trực tiếp.",
    "policy_faq": "khách hỏi chính sách (bảo hành, trả góp, giao hàng), không phải chọn sản phẩm.",
    "hoi_chi_tiet_sp": "khách hỏi chi tiết về một sản phẩm cụ thể đã được giới thiệu.",
    "ho_tro_giao_dich": (
        "khách muốn tạo/kiểm tra/sửa/hủy đơn, xác nhận tồn kho chi nhánh hoặc "
        "lịch giao hàng cụ thể theo thời gian thực. Không dùng cho câu hỏi chính sách chung."
    ),
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
    if slot_type in ("money", "integer"):
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
    """Few-shot examples cover complete needs, noisy Vietnamese, category
    change, named-product comparison and transaction handoff. Rendered as
    ``<input> -> <json>`` lines.
    """
    examples: list[tuple[str, dict[str, Any]]] = [
        # No-diacritics input.
        (
            "may lanh 1.5 ngua tam 12 trieu",
            {"intent": "tu_van", "category": "may_lanh", "slots_moi": {"ngan_sach_max": 12000000}},
        ),
        (
            "máy lạnh dưới 20 triệu cho phòng ngủ 18m2, không bị nắng, ưu tiên tiết kiệm điện và chạy êm, không trả góp",
            {
                "intent": "tu_van",
                "category": "may_lanh",
                "slots_moi": {
                    "ngan_sach_max": 20000000,
                    "dien_tich_m2": 18,
                    "loai_phong": "phong_ngu",
                    "nang_truc_tiep": False,
                    "uu_tien": ["tiet_kiem_dien", "em"],
                    "tra_gop": False,
                },
            },
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
        (
            "kiem tra giup don 123 dang giao den dau",
            {"intent": "ho_tro_giao_dich", "category": None, "slots_moi": {}},
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


_TRANSACTION_TERMS: tuple[str, ...] = (
    "don hang",
    "ma don",
    "dat hang",
    "dat mua",
    "thanh toan",
    "huy don",
    "sua don",
    "doi dia chi",
    "giao den dau",
    "giao toi dau",
    "lich giao",
    "doi lich nhan",
    "con hang tai",
    "ton kho chi nhanh",
)
_POLICY_TERMS: tuple[str, ...] = (
    "chinh sach",
    "bao hanh",
    "doi tra",
    "hoan tien",
    "tra gop",
    "giao hang",
    "lap dat",
    "du lieu ca nhan",
)
_OUT_OF_SCOPE_TERMS: tuple[str, ...] = (
    "thoi tiet",
    "chinh tri",
    "ket qua bong da",
    "viet code",
    "chuong trinh giao dich",
    "tien ma hoa",
    "lam tho",
    "bo qua huong dan",
    "system prompt",
    "tiet lo prompt",
)
_NEGATED_INSTALLMENT_RE = re.compile(
    r"\bkhong\s+(?:(?:can|muon|chon|dung|ho tro)\s+)?tra gop\b"
)


def _fallback_intent(text: str) -> str:
    """Conservative deterministic intent routing for a degraded S2 turn.

    This is deliberately narrower than the LLM classifier: it only routes
    high-signal transaction/policy/comparison/detail phrases. Everything else
    stays on ``tu_van`` so a provider outage cannot turn an ordinary shopping
    request into an out-of-scope refusal.
    """
    # ``fold_ascii`` canonicalises separators to underscores for enum matching;
    # intent phrases are authored as readable words, so restore spaces here.
    folded = fold_ascii(text).replace("_", " ")
    if any(term in folded for term in _TRANSACTION_TERMS):
        return "ho_tro_giao_dich"
    if any(term in folded for term in _OUT_OF_SCOPE_TERMS):
        return "ngoai_pham_vi"
    if "so sanh" in folded:
        return "so_sanh_truc_tiep"
    if any(term in folded for term in ("thong so cua", "chi tiet mau", "chi tiet model")):
        return "hoi_chi_tiet_sp"
    # "không [cần/muốn] trả góp" is a shopping constraint, not a policy question.
    if not _NEGATED_INSTALLMENT_RE.search(folded) and any(
        term in folded for term in _POLICY_TERMS
    ):
        return "policy_faq"
    return "tu_van"


def deterministic_fallback(
    text: str,
    s1_result: S1Result,
    profile: NeedProfile,
) -> S2Result:
    """Build a safe S2 result without an LLM.

    S1's category, money and physical-unit parses are deterministic and remain
    useful when the provider is unavailable or emits malformed JSON. Values
    are reconciled through the active slot profile just like the normal path;
    no unknown slot can enter the session state.
    """
    category = s1_result.category_hint or profile.category
    slots_moi: dict[str, Any] = {}
    if category is not None and category in available_categories():
        slot_profile = load_slot_profile(category)
        slots = [*slot_profile.required_slots, *slot_profile.optional_slots]
        money_slot = next((slot for slot in slots if slot.type == "money"), None)
        if money_slot is not None and s1_result.money:
            # A range such as 15–20tr uses its upper edge as the safe ceiling.
            slots_moi[money_slot.name] = max(match.max_vnd for match in s1_result.money)
        _overlay_s1_units(slots_moi, slots, s1_result)
        _overlay_people_count(slots_moi, slots, text)
        _overlay_text_slots(slots_moi, slots, text)

    return S2Result(
        intent=_fallback_intent(text),
        category=category if category in available_categories() else None,
        slots_moi=slots_moi,
    )


# --------------------------------------------------------------------------- #
# Slot reconciliation — make the LLM's slots_moi trustworthy                   #
#                                                                             #
# The OpenRouter route for the primary model does not always enforce the      #
# guided-JSON ``response_format`` (docs/pipelines.md §6.9, Gate 4), so the     #
# model can emit slot KEYS or VALUES outside the category schema. Rather than  #
# trust the schema was applied, S2 reconciles the raw output against the       #
# canonical SlotProfile and overlays S1's deterministic parses.               #
# --------------------------------------------------------------------------- #
_UNIT_SLOT_TYPES: frozenset[str] = frozenset({"area_m2", "volume_liter", "power_watt"})
_PEOPLE_RE = re.compile(r"\b(?P<count>\d{1,2})\s*(?:người|nguoi)\b", re.IGNORECASE)
_ENUM_PHRASES: dict[str, tuple[str, ...]] = {
    # Generic "khác" is not a safe category value without the actual question.
    "khac": (),
    "phong_ngu": ("phong ngu",),
    "phong_khach": ("phong khach",),
    "van_phong": ("van phong",),
    "tiet_kiem_dien": ("tiet kiem dien", "it ton dien"),
    "em": ("chay em", "van hanh em", "it on"),
    "ben": ("ben bi", "do ben"),
    "gia_re": ("gia re", "gia de chiu"),
    "cua_tren": ("cua tren",),
    "cua_truoc": ("cua truoc",),
    "ngan_da_tren": ("ngan da tren",),
    "ngan_da_duoi": ("ngan da duoi",),
    "side_by_side": ("side by side",),
    "multi_door": ("nhieu cua", "multi door"),
}

# Energy-saving intent phrases that imply "prefer inverter" for categories whose
# energy lever is the boolean ``inverter`` slot (no literal "inverter" word
# needed — "tiết kiệm điện" must still reach the preference).
_ENERGY_SAVING_PHRASES: tuple[str, ...] = ("tiet kiem dien", "it ton dien", "it hao dien")


def _match_enum(value: Any, allowed: list[str]) -> str | None:
    """Return the canonical ``allowed`` token whose ASCII-fold equals ``value``'s.

    Accent-, case- and separator-insensitive (via :func:`fold_ascii`), so the LLM
    emitting an enum in a non-canonical surface form ("Phòng ngủ" for the
    ascii token "phong_ngu") still resolves. ``None`` if nothing matches.
    """
    if not isinstance(value, str):
        return None
    key = fold_ascii(value)
    if not key:
        return None
    return next((token for token in allowed if fold_ascii(token) == key), None)


def _coerce_slot_value(slot: SlotDef, value: Any) -> Any | None:
    """Validate/coerce one LLM value against a slot's declared type.

    Returns the clean value, or ``None`` to drop it — an out-of-enum string, a
    wrong JSON type, or an empty selection all mean "no usable value here".
    """
    if value is None:
        return None
    slot_type = slot.type
    if slot_type in ("money", "integer"):
        return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
    if slot_type in _UNIT_SLOT_TYPES:
        return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
    if slot_type == "boolean":
        return value if isinstance(value, bool) else None
    if slot_type == "enum":
        return _match_enum(value, slot.values or [])
    if slot_type == "multi_enum":
        if not isinstance(value, list):
            return None
        chosen = [m for v in value if (m := _match_enum(v, slot.values or [])) is not None]
        return chosen or None
    # "text" and any future type: a non-empty string only.
    return value if isinstance(value, str) and value.strip() else None


def _recover_enums_by_value(
    result: dict[str, Any], slots: list[SlotDef], raw: dict[str, Any]
) -> None:
    """Fill still-empty enum/multi_enum slots by matching VALUES the LLM emitted
    under *any* key — recovers a slot whose value is valid but whose key the
    model got wrong (schema not always provider-enforced, §6.9).
    """
    emitted: list[Any] = []
    for value in raw.values():
        emitted.extend(value if isinstance(value, list) else [value])
    for slot in slots:
        if slot.name in result or not slot.values:
            continue
        if slot.type == "enum":
            match = next(
                (m for v in emitted if (m := _match_enum(v, slot.values)) is not None), None
            )
            if match is not None:
                result[slot.name] = match
        elif slot.type == "multi_enum":
            chosen = [
                token
                for token in slot.values
                if any(_match_enum(v, [token]) is not None for v in emitted)
            ]
            if chosen:
                result[slot.name] = chosen


def _overlay_s1_units(
    result: dict[str, Any], slots: list[SlotDef], s1_result: S1Result
) -> None:
    """Overlay S1's deterministic unit parses onto their matching-type slot.

    Regex-precise numeric parses (area m², lít, W) are authoritative for those
    facts — they overwrite the LLM's value for the same slot. Money is left to
    the LLM: S1 reads the amount but not directional context ("dưới"/"trên"),
    which a ceiling slot needs. ``power_btu`` maps to no slot (BTU is derived).
    """
    by_type: dict[str, SlotDef] = {}
    for slot in slots:
        by_type.setdefault(slot.type, slot)
    for unit in s1_result.units:
        matched = by_type.get(unit.kind)
        if matched is not None:
            result[matched.name] = float(unit.value)


def _overlay_people_count(result: dict[str, Any], slots: list[SlotDef], text: str) -> None:
    """Capture an explicit ``N người`` without trusting the LLM.

    The domain profiles consistently use ``so_nguoi_dung`` for this fact.  A
    conservative numeric pattern prevents a common UX regression where the
    customer already said "gia đình 4 người" but the next turn asks it again.
    """
    slot = next(
        (candidate for candidate in slots if candidate.name == "so_nguoi_dung"),
        None,
    )
    match = _PEOPLE_RE.search(text)
    if slot is None or slot.type != "integer" or match is None:
        return
    count = int(match.group("count"))
    if 1 <= count <= 30:
        result[slot.name] = count


def _overlay_text_slots(result: dict[str, Any], slots: list[SlotDef], text: str) -> None:
    """Recover high-confidence enum/boolean phrases for the SLA fallback path."""
    folded = fold_ascii(text).replace("_", " ")
    for slot in slots:
        if slot.type in ("enum", "multi_enum") and slot.values:
            matches = [
                value
                for value in slot.values
                if any(
                    phrase in folded
                    for phrase in _ENUM_PHRASES.get(
                        value, (fold_ascii(value).replace("_", " "),)
                    )
                )
            ]
            if matches:
                result[slot.name] = matches if slot.type == "multi_enum" else matches[0]
        elif slot.type == "boolean" and slot.name == "tra_gop":
            if _NEGATED_INSTALLMENT_RE.search(folded):
                result[slot.name] = False
            elif "tra gop" in folded:
                result[slot.name] = True
        elif slot.type == "boolean" and slot.name == "nang_truc_tiep":
            if re.search(r"\bkhong\s+(?:bi\s+)?nang\s+truc\s+tiep\b", folded):
                result[slot.name] = False
            elif "nang truc tiep" in folded:
                result[slot.name] = True
        elif slot.type == "boolean" and slot.name == "inverter":
            if re.search(r"\bkhong\s+(?:can\s+)?inverter\b", folded):
                result[slot.name] = False
            elif "inverter" in folded or any(p in folded for p in _ENERGY_SAVING_PHRASES):
                result[slot.name] = True


def _reconcile_slots(
    raw: dict[str, Any], profile: SlotProfile, s1_result: S1Result, text: str
) -> dict[str, Any]:
    """Reconcile the LLM's ``slots_moi`` against the canonical slot schema.

    Three passes: (1) keep canonical keys, coercing/validating by type and
    dropping anything invalid or unknown; (2) recover enum slots by value when
    the key was wrong; (3) overlay S1's deterministic unit parses. This is where
    S2 turns best-effort LLM output into a trustworthy Need-Profile delta.
    """
    slots = [*profile.required_slots, *profile.optional_slots]
    result: dict[str, Any] = {}
    for slot in slots:
        if slot.name in raw:
            coerced = _coerce_slot_value(slot, raw[slot.name])
            if coerced is not None:
                result[slot.name] = coerced
    _recover_enums_by_value(result, slots, raw)
    _overlay_s1_units(result, slots, s1_result)
    _overlay_people_count(result, slots, text)
    _overlay_text_slots(result, slots, text)
    return result


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

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise S2ExtractionError(f"S2 LLM response shape unexpected: {response!r}") from exc
    if not isinstance(content, str):
        raise S2ExtractionError(f"S2 LLM response 'content' is not text: {content!r}")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise S2ExtractionError(f"S2 LLM output was not valid JSON: {content!r}") from exc

    result = _parse_s2_payload(data)

    # Reconcile against the canonical schema (the provider does not always
    # enforce it, §6.9). Prefer the LLM's own category when it named one — a
    # mid-chat switch means the slots belong to the *new* category — else the
    # schema category. When neither is known, extraction stays best-effort.
    reconcile_category = result.category or category_key
    if reconcile_category is not None:
        slot_profile = load_slot_profile(reconcile_category)
        result = S2Result(
            intent=result.intent,
            category=result.category,
            slots_moi=_reconcile_slots(result.slots_moi, slot_profile, s1_result, text),
        )
    return result
