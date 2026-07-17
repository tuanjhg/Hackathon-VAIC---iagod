from fastapi.testclient import TestClient


def test_product_list(client: TestClient) -> None:
    response = client.get("/api/v1/products?page_size=100")
    assert response.status_code == 200
    assert response.json()["total"] == 20


def test_filter_by_brand(client: TestClient) -> None:
    data = client.get("/api/v1/products?brand=Daikin").json()
    assert data["total"] == 4
    assert all(item["brand"] == "Daikin" for item in data["items"])


def test_filter_by_price(client: TestClient) -> None:
    data = client.get("/api/v1/products?max_price=10000000&page_size=100").json()
    assert data["items"]
    assert all(float(item["sale_price"]) <= 10_000_000 for item in data["items"])


def test_product_detail(client: TestClient) -> None:
    response = client.get("/api/v1/products/daikin-inverter-ftkb35-12000")
    assert response.status_code == 200
    assert response.json()["capacity_btu"] == 12000


def test_compare(client: TestClient) -> None:
    response = client.post("/api/v1/compare", json={"product_ids": [2, 10, 18]})
    assert response.status_code == 200
    assert len(response.json()["products"]) == 3
    assert response.json()["best_price_id"] == 18

