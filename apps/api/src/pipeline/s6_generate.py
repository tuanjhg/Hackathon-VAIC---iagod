"""S6 — statement-template generation (ADR A8 "bảng quy đổi cảm nhận" + ADR C5).

Per `docs/research/dmx-ai-workflow-v1.md` §3 "S6" and ADR A8/C5 of
`docs/research/dmx-tech-decisions.md`: S6 turns S5's *structured* ranking
(:class:`~src.pipeline.s5_ranking.RankingResult`) into the natural-sounding
Vietnamese **lời dẫn tư vấn** (the advisory prose that accompanies the product
cards). The product cards themselves are NOT built here — per ADR C5 they render
straight from the S5/candidate JSON on the frontend, no LLM involved. S6 only
produces the prose.

Two layers, in order:

* **Layer 1 — deterministic statement building (no LLM, pure Python).** A small
  :data:`GLOSSARY` registry maps technical spec fields → plain-language
  Vietnamese phrases (ADR A8's "bảng quy đổi cảm nhận"). For each top candidate
  we render its real spec values through that glossary into a filled-in
  statement string; each trade-off and the anti-pick get one statement too. A
  :class:`marker_map <GeneratedAdvice>` binds ``[1]/[2]/[3]/[A]`` → SKU — the
  contract S7 (verifier) uses to know which SKU a claim refers to.

* **Layer 2 — LLM rephrase.** The deterministic statements (and *only* those,
  never the raw candidate dicts or ``RankingResult``) are handed to the router
  with a system prompt that instructs the model to rephrase them into warm,
  casual Vietnamese while inventing/altering no fact — keeping the "the LLM only
  rephrases what is already true" guarantee auditable.

Like the other stages this is a decoupled building block: it takes an
``LLMRouterLike`` by dependency injection (tests inject a fake) and raises
:class:`S6GenerationError` on an unexpected response shape rather than swallowing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, Field

from src.pipeline.need_profile import NeedProfile
from src.pipeline.s5_ranking import RankingResult, TradeOff

__all__ = [
    "GLOSSARY",
    "GeneratedAdvice",
    "S6GenerationError",
    "build_advisory_statements",
    "generate",
    "render_spec",
]

# Generative prose (unlike S2's temperature=0 extraction) — a low-but-non-zero
# temperature gives natural phrasing variety without wandering off the facts.
_TEMPERATURE = 0.4

# Marker strings, in the exact order S7 depends on: top[0..2] → [1]/[2]/[3],
# anti_pick → [A]. Kept as named constants so the contract lives in one place.
_TOP_MARKERS: tuple[str, ...] = ("[1]", "[2]", "[3]")
_ANTI_MARKER = "[A]"


class LLMRouterLike(Protocol):
    """Structural type for anything with the router's ``complete`` coroutine.

    Lets S6 accept a real :class:`~src.router.client.LLMRouter` in production and
    a lightweight fake in tests without a shared base class.
    """

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]: ...


class S6GenerationError(RuntimeError):
    """Raised when the LLM's S6 response cannot be trusted.

    Cause: the OpenAI-compatible body is missing ``choices[0].message.content``
    or that content is not a usable string. Never swallowed — the caller decides
    whether to retry or fall back.
    """


class GeneratedAdvice(BaseModel):
    """Structured output of the S6 stage.

    ``statements`` is the Layer-1 deterministic material (in the exact order fed
    to the LLM) kept alongside the prose so a downstream verifier (S7) can audit
    that every claim in ``text`` traces back to a statement. ``marker_map`` binds
    each ``[N]``/``[A]`` marker to the SKU it refers to.
    """

    text: str
    statements: list[str] = Field(default_factory=list)
    marker_map: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Layer 1a — glossary ("bảng quy đổi cảm nhận", ADR A8)                        #
# --------------------------------------------------------------------------- #
# v0 hand-authored registry: field name → a renderer that turns the raw spec
# value into a plain-language Vietnamese phrase. Deliberately a small dict of
# per-field callables (not a giant if/else) so it is trivial to extend as more
# categories/fields arrive. The Category Profile Compiler (ADR A7) may later
# generate richer entries per category; this is the Phase-0 "bản tay" seed.
_LOW_NOISE_DB = 30  # below a whisper-ish threshold, phrase it as "êm hơn tiếng thì thầm"


def _render_inverter(value: Any) -> str:
    if value:
        return "tự điều chỉnh công suất, đỡ tốn điện"
    return "không phải inverter, chạy công suất cố định"


def _render_noise(value: Any) -> str:
    if isinstance(value, int | float) and not isinstance(value, bool) and value < _LOW_NOISE_DB:
        return f"êm hơn tiếng thì thầm ({value}dB)"
    return f"độ ồn {value}dB"


GLOSSARY: dict[str, Callable[[Any], str]] = {
    # máy lạnh
    "inverter": _render_inverter,
    "noise_db_indoor": _render_noise,
    "noise_db": _render_noise,
    "capacity_btu": lambda v: f"đủ sức làm lạnh phòng theo công suất {v} BTU",
    "energy_efficiency": lambda v: f"{v} sao tiết kiệm điện",
    "energy_stars": lambda v: f"{v} sao tiết kiệm điện",
    "warranty_years_compressor": lambda v: f"bảo hành máy nén {v} năm",
    # tủ lạnh
    "capacity_total_l": lambda v: f"dung tích {v} lít",
    "capacity_l": lambda v: f"dung tích {v} lít",
    # máy giặt
    "capacity_kg": lambda v: f"giặt được {v} kg mỗi mẻ",
    # generic
    "warranty_years": lambda v: f"bảo hành {v} năm",
    "power_watt": lambda v: f"công suất {v}W",
}

# Short human noun per field, used only in the comparative trade-off statements
# (the glossary renders full phrases; here we want a bare label). Falls back to
# the raw field name for anything unmapped.
_FIELD_LABELS: dict[str, str] = {
    "inverter": "công nghệ inverter",
    "noise_db_indoor": "độ ồn",
    "noise_db": "độ ồn",
    "energy_efficiency": "khả năng tiết kiệm điện",
    "energy_stars": "khả năng tiết kiệm điện",
    "capacity_btu": "công suất làm lạnh",
    "capacity_total_l": "dung tích",
    "capacity_l": "dung tích",
    "capacity_kg": "khối lượng giặt",
    "warranty_years_compressor": "bảo hành máy nén",
    "warranty_years": "bảo hành",
    "power_watt": "công suất điện",
}


def render_spec(field: str, value: Any) -> str | None:
    """Render a single spec ``field``/``value`` into a plain-language phrase.

    Returns ``None`` when the field is not in the glossary or the value is
    ``None`` (missing) — nothing to say, and never a fabricated phrase.
    """
    if value is None:
        return None
    renderer = GLOSSARY.get(field)
    if renderer is None:
        return None
    return renderer(value)


def _label(field: str) -> str:
    return _FIELD_LABELS.get(field, field)


# --------------------------------------------------------------------------- #
# Layer 1b — statement building + marker map                                  #
# --------------------------------------------------------------------------- #
def _marker_map(ranking: RankingResult) -> dict[str, str]:
    """Bind ``[1]/[2]/[3]`` to the top SKUs and ``[A]`` to the anti-pick.

    Omits ``[A]`` entirely when there is no anti-pick — the exact contract S7
    reads to resolve a marker back to its SKU.
    """
    marker_map: dict[str, str] = {}
    for marker, breakdown in zip(_TOP_MARKERS, ranking.top, strict=False):
        marker_map[marker] = breakdown.sku
    if ranking.anti_pick is not None:
        marker_map[_ANTI_MARKER] = ranking.anti_pick.sku
    return marker_map


def _top_statement(marker: str, name: str, specs: dict[str, Any]) -> str:
    """One statement for a top candidate: its marker + name + the glossary
    phrases for whatever glossary-known specs it actually has (in glossary
    order, so output is stable regardless of dict ordering).
    """
    phrases = [
        rendered
        for field in GLOSSARY
        if (rendered := render_spec(field, specs.get(field))) is not None
    ]
    if not phrases:
        return f"{marker} {name}"
    return f"{marker} {name}: " + "; ".join(phrases)


def _trade_off_statement(trade_off: TradeOff, sku_to_marker: dict[str, str]) -> str:
    """One comparative statement per trade-off, built purely from the trade-off's
    already-real differentiating values — no candidate lookup, no invented number.
    """
    marker_a = sku_to_marker.get(trade_off.sku_a, trade_off.sku_a)
    marker_b = sku_to_marker.get(trade_off.sku_b, trade_off.sku_b)
    a_wins = set(trade_off.a_wins_on)
    b_wins = set(trade_off.b_wins_on)

    clauses: list[str] = []
    for field in sorted(trade_off.values):
        va, vb = trade_off.values[field]
        if field in a_wins:
            clauses.append(f"{marker_a} tốt hơn về {_label(field)} ({va} so với {vb})")
        elif field in b_wins:
            clauses.append(f"{marker_b} tốt hơn về {_label(field)} ({vb} so với {va})")
        else:
            clauses.append(f"{_label(field)}: {marker_a}={va}, {marker_b}={vb}")
    return f"{marker_a} vs {marker_b}: " + "; ".join(clauses)


def _anti_pick_statement(ranking: RankingResult, name: str) -> str:
    """One statement for the anti-pick: its ``[A]`` marker + name + the reason
    S5 already computed + any missing fields it is weak on (surfaced, not hidden).
    """
    parts: list[str] = []
    if ranking.anti_pick_reason:
        parts.append(ranking.anti_pick_reason)
    if ranking.anti_pick is not None and ranking.anti_pick.missing_fields:
        parts.append("còn thiếu dữ liệu: " + ", ".join(ranking.anti_pick.missing_fields))
    if not parts:
        return f"{_ANTI_MARKER} {name}"
    return f"{_ANTI_MARKER} {name}: " + "; ".join(parts)


def build_advisory_statements(
    ranking: RankingResult,
    candidates: list[dict[str, Any]],
) -> tuple[list[str], dict[str, str]]:
    """Build the Layer-1 deterministic statements + marker map (no LLM).

    Order (also the order fed to the LLM): each top candidate, then each
    trade-off, then the anti-pick. Product names/specs are looked up from the
    original ``candidates`` list by ``sku`` (``ScoreBreakdown`` carries only the
    score breakdown). Returns ``(statements, marker_map)``.
    """
    by_sku = {str(c.get("sku")): c for c in candidates}
    marker_map = _marker_map(ranking)
    # Reverse map for trade-offs, from the numeric top markers only (so the
    # anti-pick marker never shadows a top SKU that happens to coincide).
    sku_to_marker: dict[str, str] = {}
    for marker in _TOP_MARKERS:
        sku = marker_map.get(marker)
        if sku is not None:
            sku_to_marker.setdefault(sku, marker)

    statements: list[str] = []

    for marker, breakdown in zip(_TOP_MARKERS, ranking.top, strict=False):
        cand = by_sku.get(breakdown.sku, {})
        name = str(cand.get("name", breakdown.sku))
        specs = cand.get("specs") or {}
        statements.append(_top_statement(marker, name, specs))

    for trade_off in ranking.trade_offs:
        statements.append(_trade_off_statement(trade_off, sku_to_marker))

    if ranking.anti_pick is not None:
        cand = by_sku.get(ranking.anti_pick.sku, {})
        name = str(cand.get("name", ranking.anti_pick.sku))
        statements.append(_anti_pick_statement(ranking, name))

    return statements, marker_map


# --------------------------------------------------------------------------- #
# Layer 2 — LLM rephrase                                                       #
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = (
    "Bạn là nhân viên tư vấn điện máy, nói chuyện ấm áp, tự nhiên bằng tiếng Việt "
    "(xưng 'em', gọi khách là 'anh/chị'). Nhiệm vụ: diễn đạt lại các DỮ KIỆN được "
    "cung cấp thành lời dẫn tư vấn ngắn gọn.\n\n"
    "QUY TẮC BẮT BUỘC:\n"
    "- TUYỆT ĐỐI không bịa hay đổi bất kỳ con số/thông tin nào không có trong DỮ KIỆN. "
    "Chỉ được diễn đạt lại điều đã cho.\n"
    "- Luôn gọi sản phẩm bằng đúng marker [1]/[2]/[3]/[A] (không gọi trống bằng tên) "
    "để hệ thống đối chiếu được từng ý.\n"
    "- Không dùng markdown, không dùng từ quảng cáo thổi phồng ('tốt nhất', 'số 1'...), "
    "không thúc ép mua.\n\n"
    "CẤU TRÚC câu trả lời:\n"
    "① Một câu tóm tắt nhu cầu em hiểu (để khách thầm xác nhận).\n"
    "② Với mỗi sản phẩm gợi ý: vì sao hợp + ĐÚNG MỘT điểm đánh đổi thật lấy từ DỮ KIỆN.\n"
    "③ Sản phẩm nên cân nhắc bỏ qua ([A]) và lý do.\n"
    "④ Một câu hỏi/đề nghị nhẹ nhàng để khách nói thêm."
)


def _build_user_content(profile: NeedProfile, statements: list[str]) -> str:
    """User-turn content: a short Need-Profile summary for context + the Layer-1
    statements as the ONLY source of facts. Deliberately never dumps the raw
    candidate dicts or ``RankingResult`` — keeps the "only rephrase what is true"
    guarantee auditable.
    """
    known_slots = {k: v for k, v in profile.slots.items() if v is not None}
    slots_summary = (
        ", ".join(f"{k}={v}" for k, v in known_slots.items()) if known_slots else "chưa rõ thêm"
    )
    facts = "\n".join(f"- {s}" for s in statements)
    return (
        f"Ngành hàng: {profile.category}. Nhu cầu đã biết: {slots_summary}.\n\n"
        "DỮ KIỆN (chỉ được dùng đúng những dữ kiện này, không thêm số/thông tin nào khác):\n"
        f"{facts}"
    )


def _parse_content(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise S6GenerationError(f"S6 LLM response shape unexpected: {response!r}") from exc
    if not isinstance(content, str) or not content.strip():
        raise S6GenerationError(f"S6 LLM response 'content' missing or empty: {content!r}")
    return content


async def generate(
    router: LLMRouterLike,
    ranking: RankingResult,
    candidates: list[dict[str, Any]],
    profile: NeedProfile,
) -> GeneratedAdvice:
    """Run S6: build deterministic statements, then LLM-rephrase them into prose.

    Layer 1 (:func:`build_advisory_statements`) produces the statements +
    marker map with zero LLM involvement. Layer 2 hands ONLY those statements
    (plus a short Need-Profile summary) to the router — at a low non-zero
    temperature for phrasing variety, with OpenRouter's ``reasoning`` switch OFF
    — and returns the parsed prose. Raises :class:`S6GenerationError` if the
    response shape is unexpected.
    """
    statements, marker_map = build_advisory_statements(ranking, candidates)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_content(profile, statements)},
    ]

    response = await router.complete(
        messages,
        temperature=_TEMPERATURE,
        # Provider-level reasoning switch (OpenRouter's own field, ADR A2'').
        # NOT vLLM's chat_template_kwargs.enable_thinking -- confirmed 18/07 that
        # OpenRouter silently ignores that field for this model, leaving it to
        # reason at length and return malformed output. Mirrors s2_extract.extract.
        reasoning={"enabled": False},
    )

    text = _parse_content(response)
    return GeneratedAdvice(text=text, statements=statements, marker_map=marker_map)
