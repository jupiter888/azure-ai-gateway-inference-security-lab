"""
External JWT validation and model authorization tests.

Synthetic inference is explicitly enabled for these offline tests.
Backend communication is tested in test_gateway_backend.py.
"""

import pytest
from fastapi.testclient import TestClient

import src.gateway.app as gateway_module
from src.gateway.config import GatewayConfig
from src.identity.jwt_validator import JWTValidator
from tests.fixtures.jwt_factory import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    create_jwks,
    create_token,
    generate_key_pair,
)


@pytest.fixture
def authenticated_client(monkeypatch):
    monkeypatch.setenv("P9_INFERENCE_MODE", "local-synthetic")
    monkeypatch.delenv("P9_BACKEND_URL", raising=False)
    monkeypatch.delenv("P9_BACKEND_SERVICE_KEY", raising=False)

    private_key = generate_key_pair()

    validator = JWTValidator(
        GatewayConfig(
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            jwks_url="https://issuer.project09.test/jwks",
        )
    )

    monkeypatch.setattr(
        validator.jwks_client,
        "fetch_data",
        lambda: create_jwks(private_key),
    )

    monkeypatch.setattr(
        gateway_module,
        "validator",
        validator,
    )

    with TestClient(gateway_module.app) as client:
        yield client, private_key


def request_inference(client, token, model):
    return client.post(
        "/v1/inference",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": model,
            "prompt": "Synthetic security test",
        },
    )


def test_valid_reader_inference(authenticated_client):
    client, key = authenticated_client
    token = create_token(key, roles=["Inference.Reader"])

    response = request_inference(client, token, "research-model")

    assert response.status_code == 200
    assert response.json()["synthetic"] is True


def test_reader_cannot_access_restricted_model(authenticated_client):
    client, key = authenticated_client
    token = create_token(key, roles=["Inference.Reader"])

    response = request_inference(client, token, "restricted-model")

    assert response.status_code == 403


def test_admin_can_access_restricted_model(authenticated_client):
    client, key = authenticated_client
    token = create_token(key, roles=["Inference.Admin"])

    response = request_inference(client, token, "restricted-model")

    assert response.status_code == 200


def test_forged_gateway_token_rejected(authenticated_client):
    client, _ = authenticated_client
    attacker_key = generate_key_pair()
    token = create_token(attacker_key, roles=["Inference.Admin"])

    response = request_inference(client, token, "restricted-model")

    assert response.status_code == 401