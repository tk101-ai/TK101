"""Sprint 0 skeleton 검증 — /health 엔드포인트 동작 확인.

Design Ref: §8.3 L1 API Test Scenarios, #11
"""
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """/health 엔드포인트는 항상 200 OK 반환."""
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "tk101-backend"
    assert "version" in body
