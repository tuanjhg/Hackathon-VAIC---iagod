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
