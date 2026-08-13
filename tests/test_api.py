"""API-тесты через TestClient. Используем его как контекстный менеджер —
без этого Starlette создаёт новый event loop на каждый отдельный вызов, и
второй же запрос к БД падает с 'Future attached to a different loop' (тот
же класс проблемы, что уже встречался на прошлых проектах). Зависимость
get_payment_service переопределяется на свежий per-test session_maker."""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_payment_service
from app.main import app
from app.payments.repository import PaymentRepository, OutboxRepository
from app.payments.service import PaymentService

VALID_BODY = {
    "amount": "100.50",
    "currency": "RUB",
    "description": "test",
    "metadata": {"order_id": 1},
    "webhook_url": "https://example.com/hook",
}


@pytest.fixture()
def client(session_maker):
    app.dependency_overrides[get_payment_service] = lambda: PaymentService(
        PaymentRepository(), OutboxRepository(), session_maker=session_maker
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth_headers(idempotency_key: str) -> dict:
    return {"X-API-Key": "super-secret-key", "Idempotency-Key": idempotency_key}


def test_create_payment_without_api_key_returns_401(client):
    response = client.post("/api/v1/payments", json=VALID_BODY, headers={"Idempotency-Key": "k1"})
    assert response.status_code == 401


def test_create_payment_without_idempotency_key_returns_422(client):
    response = client.post("/api/v1/payments", json=VALID_BODY, headers={"X-API-Key": "super-secret-key"})
    assert response.status_code == 422


def test_create_payment_success_returns_202(client):
    response = client.post("/api/v1/payments", json=VALID_BODY, headers=_auth_headers("k2"))
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert "payment_id" in body
    assert "created_at" in body


def test_create_payment_idempotent_repeat_returns_same_payment(client):
    first = client.post("/api/v1/payments", json=VALID_BODY, headers=_auth_headers("k3")).json()
    second = client.post("/api/v1/payments", json=VALID_BODY, headers=_auth_headers("k3")).json()
    assert first["payment_id"] == second["payment_id"]


def test_create_payment_rejects_non_positive_amount(client):
    body = {**VALID_BODY, "amount": "0"}
    response = client.post("/api/v1/payments", json=body, headers=_auth_headers("k4"))
    assert response.status_code == 422


def test_get_payment_returns_full_details(client):
    created = client.post("/api/v1/payments", json=VALID_BODY, headers=_auth_headers("k5")).json()
    response = client.get(
        f"/api/v1/payments/{created['payment_id']}", headers={"X-API-Key": "super-secret-key"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["amount"] == "100.50"
    assert body["metadata"] == {"order_id": 1}
    assert body["status"] == "pending"


def test_get_missing_payment_returns_404(client):
    response = client.get("/api/v1/payments/999999", headers={"X-API-Key": "super-secret-key"})
    assert response.status_code == 404


def test_get_payment_without_api_key_returns_401(client):
    response = client.get("/api/v1/payments/1")
    assert response.status_code == 401
