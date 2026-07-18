from fastapi.testclient import TestClient


def test_chat_follow_up(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "test", "message": "Tư vấn máy lạnh cho phòng 18m2", "context": {"budget_max": None, "room_area_m2": None, "priority": None}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["response_type"] == "follow_up"
    assert "Dưới 10 triệu" in data["quick_replies"]
    assert data["context"]["room_area_m2"] == 18


def test_chat_recommendations(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "test", "message": "Tiết kiệm điện", "context": {"budget_max": 15000000, "room_area_m2": 18, "priority": None}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["response_type"] == "recommendations"
    assert len(data["recommendations"]) == 3
    assert all(item["match_score"] >= 80 for item in data["recommendations"])


def test_unlimited_budget_is_preserved(client: TestClient) -> None:
    budget_response = client.post(
        "/api/v1/chat/messages",
        json={
            "session_id": "test",
            "message": "Không giới hạn",
            "context": {"budget_max": None, "room_area_m2": 18, "priority": None},
        },
    ).json()
    assert budget_response["context"]["budget_max"] == 0
    assert "ưu tiên" in budget_response["message"].lower()

    result = client.post(
        "/api/v1/chat/messages",
        json={
            "session_id": "test",
            "message": "Chạy êm",
            "context": budget_response["context"],
        },
    ).json()
    assert result["response_type"] == "recommendations"
    assert len(result["recommendations"]) == 3


def test_xung_ho_detected_and_mirrored_in_next_question(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "session_id": "test",
            "message": "Cô muốn tư vấn máy lạnh cho phòng 18m2",
            "context": {"budget_max": None, "room_area_m2": None, "priority": None, "xung_ho": None},
        },
    ).json()
    assert response["context"]["xung_ho"] == "Cô"
    assert response["message"] == "Cô muốn ngân sách tối đa khoảng bao nhiêu?"


def test_xung_ho_is_sticky_across_turns(client: TestClient) -> None:
    first = client.post(
        "/api/v1/chat/messages",
        json={
            "session_id": "test",
            "message": "Chú cần tư vấn máy lạnh",
            "context": {"budget_max": None, "room_area_m2": None, "priority": None, "xung_ho": None},
        },
    ).json()
    assert first["context"]["xung_ho"] == "Chú"

    # A later message mentioning a different term must not overwrite it.
    second = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "test", "message": "Anh chị ơi phòng 18m2", "context": first["context"]},
    ).json()
    assert second["context"]["xung_ho"] == "Chú"
    assert "Chú" in second["message"]


def test_default_address_term_unchanged_when_no_pronoun_detected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "session_id": "test",
            "message": "Tư vấn máy lạnh cho phòng 18m2",
            "context": {"budget_max": None, "room_area_m2": None, "priority": None, "xung_ho": None},
        },
    ).json()
    assert response["context"]["xung_ho"] is None
    assert response["message"] == "Bạn muốn ngân sách tối đa khoảng bao nhiêu?"
