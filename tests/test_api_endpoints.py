"""
Tests for FastAPI Backend Endpoints.
"""

from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "BidCheck API"
    assert "DECISION SUPPORT ONLY" in data["disclaimer"]


def test_mock_registry_routes():
    res = client.get("/mock-registry/gstin/27AABCT1234A1Z5")
    assert res.status_code == 200
    data = res.json()
    assert data["is_mock"] is True
    assert data["status"] == "ACTIVE"


def test_audit_verify_route():
    res = client.get("/audit/verify")
    assert res.status_code == 200
    data = res.json()
    assert "is_valid" in data
