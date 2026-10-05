from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "orders.db")
    with TestClient(main.app) as test_client:
        yield test_client


def test_health_and_seeded_orders(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    orders = client.get("/api/orders").json()
    assert len(orders) == 3
    assert {order["priority"] for order in orders} == {"standard", "express"}


def test_create_and_update_order(client):
    response = client.post(
        "/api/orders",
        json={"customer": "Taylor", "item": "Mug", "priority": "standard"},
    )
    assert response.status_code == 201
    order_id = response.json()["id"]
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "received"
    updated = client.patch(f"/api/orders/{order_id}", json={"status": "shipped"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "shipped"


def test_missing_order(client):
    assert client.get("/api/orders/missing").status_code == 404


def test_order_lookup_internal_error_records_500_metric(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "orders.db")
    recorded = []
    monkeypatch.setattr(
        main.lookup_counter,
        "add",
        lambda amount, attributes: recorded.append((amount, attributes)),
    )
    def raise_error(_row):
        raise RuntimeError("simulated order lookup failure")

    monkeypatch.setattr(main, "order_detail", raise_error)

    with TestClient(main.app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/orders/express-1002")

    assert response.status_code == 500
    assert recorded == [
        (1, {"http.route": "/api/orders/{order_id}", "http.response.status_code": 500})
    ]


def test_express_order_lookup_has_valid_estimated_delivery(client):
    response = client.get("/api/orders/express-1002")
    assert response.status_code == 200
    order = response.json()
    assert order["priority"] == "express"
    assert order["estimated_delivery"]
    placed_at = datetime.fromisoformat(order["created_at"])
    expected_delivery = (placed_at + timedelta(days=2)).date().isoformat()
    assert order["estimated_delivery"] == expected_delivery


def test_order_lookup_metric_uses_route_and_status(client, monkeypatch, caplog):
    recorded = []
    caplog.set_level("INFO", logger="order_tracker.lookups")
    monkeypatch.setattr(
        main.lookup_counter,
        "add",
        lambda amount, attributes: recorded.append((amount, attributes)),
    )

    assert client.get("/api/orders/standard-1001").status_code == 200
    assert client.get("/api/orders/missing").status_code == 404
    expected_attributes = [
        {"http.route": "/api/orders/{order_id}", "http.response.status_code": 200},
        {"http.route": "/api/orders/{order_id}", "http.response.status_code": 404},
    ]
    assert recorded == [(1, attributes) for attributes in expected_attributes]
    assert [record.__dict__["http.route"] for record in caplog.records] == [
        "/api/orders/{order_id}",
        "/api/orders/{order_id}",
    ]
    assert [record.__dict__["http.response.status_code"] for record in caplog.records] == [200, 404]
