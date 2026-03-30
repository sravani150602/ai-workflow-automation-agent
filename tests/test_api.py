"""Integration tests for the FastAPI REST endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent.models import QueryResolution


@pytest.fixture
def mock_resolution():
    return QueryResolution(
        workflow_state="resolved",
        resolution="Your payment is processing normally and will clear within 1 business day.",
        confidence=0.93,
        escalated=False,
        escalation_reason=None,
        actions_taken=["context_loaded", "llm_called", "decision_finalized"],
        latency_ms=1240.5,
    )


@pytest.fixture
def mock_escalated_resolution():
    return QueryResolution(
        workflow_state="escalated",
        resolution="Your query has been escalated to a specialist for immediate review.",
        confidence=1.0,
        escalated=True,
        escalation_reason="Category 'fraud_alert' requires immediate human review",
        actions_taken=["query_received"],
        latency_ms=85.2,
    )


def get_test_client(mock_res):
    from api.main import app, save_query_record

    with patch("api.main.agent.resolve", new_callable=AsyncMock, return_value=mock_res), \
         patch("api.main.save_query_record", new_callable=AsyncMock), \
         patch("api.main.close_client", new_callable=AsyncMock):
        return TestClient(app, raise_server_exceptions=True)


def test_health_check():
    from api.main import app
    with patch("api.main.close_client", new_callable=AsyncMock):
        with TestClient(app) as client:
            response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_submit_query_resolved(mock_resolution):
    client = get_test_client(mock_resolution)
    response = client.post("/query", json={
        "user_id": "usr_test",
        "query": "Why is my payment pending for 3 days?",
        "category": "payment_status",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["workflow_state"] == "resolved"
    assert data["escalated"] is False
    assert data["confidence"] == 0.93
    assert "decision_finalized" in data["actions_taken"]


def test_submit_query_escalated(mock_escalated_resolution):
    client = get_test_client(mock_escalated_resolution)
    response = client.post("/query", json={
        "user_id": "usr_test",
        "query": "Someone made an unauthorized charge on my account.",
        "category": "fraud_alert",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["workflow_state"] == "escalated"
    assert data["escalated"] is True


def test_submit_query_validates_empty_query(mock_resolution):
    client = get_test_client(mock_resolution)
    response = client.post("/query", json={
        "user_id": "usr_test",
        "query": "",
        "category": "general",
    })
    assert response.status_code == 422
