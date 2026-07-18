import json

from src.eval.golden import GoldenConversation, GoldenMessage
from src.eval.judge import _apply_applicability, _parse_scores, build_judge_messages
from src.eval.replay import ReplayedConversation, ReplayTurn


def test_parse_scores_keeps_legacy_scores_and_business_rubric() -> None:
    payload = {
        "helpfulness": 5,
        "grounding": 4,
        "scope_handling": 5,
        "overall": 4,
        "business_checks": {
            "needs_summary": True,
            "plain_vietnamese": True,
            "product_advantage_and_tradeoff": False,
            "anti_pick_with_reason": False,
            "non_pushy_tone": True,
            "clarification_has_reason": None,
            "consistent_vietnamese_pronouns": True,
        },
        "rationale": "Còn thiếu anti-pick.",
    }

    scores, checks, rationale = _parse_scores(json.dumps(payload, ensure_ascii=False))

    assert scores == {
        "helpfulness": 5,
        "grounding": 4,
        "scope_handling": 5,
        "overall": 4,
    }
    assert checks["needs_summary"] is True
    assert checks["anti_pick_with_reason"] is False
    assert checks["clarification_has_reason"] is None
    assert rationale == "Còn thiếu anti-pick."


def test_parse_scores_ignores_invalid_business_values() -> None:
    scores, checks, _ = _parse_scores(
        '{"helpfulness":9,"business_checks":{"needs_summary":"yes"}}'
    )

    assert scores["helpfulness"] == 5
    assert "needs_summary" not in checks


def test_judge_only_compares_turns_that_were_replayed() -> None:
    conversation = GoldenConversation(
        id="limited",
        source="synthetic",
        messages=[
            GoldenMessage(role="user", content="lượt một"),
            GoldenMessage(role="assistant", content="mẫu một"),
            GoldenMessage(role="user", content="lượt hai"),
            GoldenMessage(role="assistant", content="mẫu hai"),
        ],
    )
    replayed = ReplayedConversation(
        conversation=conversation,
        turns=[ReplayTurn(user_text="lượt một", result=None, error="test")],
    )

    messages = build_judge_messages(replayed)

    assert "[Lượt 1]" in messages[-1]["content"]
    assert "[Lượt 2]" not in messages[-1]["content"]
    assert "hệ thống tư vấn đang bận" in messages[-1]["content"]
    assert "lỗi pipeline" not in messages[-1]["content"]


def test_conditional_business_criteria_use_structural_applicability() -> None:
    conversation = GoldenConversation(id="error", source="synthetic", messages=[])
    replayed = ReplayedConversation(
        conversation=conversation,
        turns=[ReplayTurn(user_text="test", result=None, error="timeout")],
    )

    checks = _apply_applicability(
        replayed,
        {
            "needs_summary": False,
            "product_advantage_and_tradeoff": False,
            "anti_pick_with_reason": False,
            "clarification_has_reason": False,
            "plain_vietnamese": True,
        },
    )

    assert checks["needs_summary"] is None
    assert checks["product_advantage_and_tradeoff"] is None
    assert checks["anti_pick_with_reason"] is None
    assert checks["clarification_has_reason"] is None
    assert checks["plain_vietnamese"] is True
