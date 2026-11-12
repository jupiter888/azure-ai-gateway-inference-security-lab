"""
Project 9 — Backend Authentication Tests
"""

import pytest
from fastapi.testclient import TestClient

from src.backend.app import app


client = TestClient(app)
TEST_SERVICE_KEY = "synthetic-test-service-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def configure_service_key(monkeypatch):
    monkeypatch.setenv(
        "P9_BACKEND_SERVICE_KEY",
        TEST_SERVICE_KEY,
    )


def inference(headers=None, model="research-model", prompt="Synthetic test."):
    return client.post(
        "/internal/inference",
        json={
            "model": model,
            "prompt": prompt,
        },
        headers=headers or {},
    )


def test_backend_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_backend_authorized():
    response = inference(
        headers={"X-Service-Key": TEST_SERVICE_KEY},
    )
    assert response.status_code == 200
    assert response.json() == {
        "model": "research-model",
        "response": "Synthetic inference response",
        "synthetic": True,
    }


def test_backend_rejects_missing_credential():
    assert inference().status_code == 401


def test_backend_rejects_invalid_credential():
    assert inference(
        headers={"X-Service-Key": "invalid"},
    ).status_code == 401


def test_backend_rejects_missing_prompt():
    response = client.post(
        "/internal/inference",
        json={"model": "research-model"},
        headers={"X-Service-Key": TEST_SERVICE_KEY},
    )
    assert response.status_code == 422


def test_backend_rejects_empty_model():
    assert inference(
        headers={"X-Service-Key": TEST_SERVICE_KEY},
        model="",
    ).status_code == 422


def test_backend_rejects_oversized_prompt():
    assert inference(
        headers={"X-Service-Key": TEST_SERVICE_KEY},
        prompt="x" * 4097,
    ).status_code == 422


def test_backend_fails_closed_without_configuration(monkeypatch):
    monkeypatch.delenv("P9_BACKEND_SERVICE_KEY", raising=False)

    response = inference(
        headers={"X-Service-Key": TEST_SERVICE_KEY},
    )

    assert response.status_code == 503