from fastapi.testclient import TestClient
from src.gateway.app import app
from src.identity.jwt_validator import AuthenticatedPrincipal
from src.policy.model_authorization import authorize_model


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200


def test_missing_token_rejected():
    response = client.post(
        "/v1/inference",
        json={
            "model": "research-model",
            "prompt": "Synthetic test",
        },
    )

    assert response.status_code == 401


def test_malformed_authorization_header_rejected():
    response = client.post(
        "/v1/inference",
        headers={"Authorization": "InvalidToken"},
        json={
            "model": "research-model",
            "prompt": "Synthetic test",
        },
    )

    assert response.status_code == 401


def test_unknown_model_denied():
    principal = AuthenticatedPrincipal(
        subject="synthetic-user",
        roles=("Inference.Admin",),
    )

    decision = authorize_model(
        principal,
        "unknown-model",
    )

    assert decision.allowed is False


def test_reader_can_access_research_model():
    principal = AuthenticatedPrincipal(
        subject="synthetic-user",
        roles=("Inference.Reader",),
    )

    decision = authorize_model(
        principal,
        "research-model",
    )

    assert decision.allowed is True


def test_reader_cannot_access_restricted_model():
    principal = AuthenticatedPrincipal(
        subject="synthetic-user",
        roles=("Inference.Reader",),
    )

    decision = authorize_model(
        principal,
        "restricted-model",
    )

    assert decision.allowed is False


def test_admin_can_access_restricted_model():
    principal = AuthenticatedPrincipal(
        subject="synthetic-admin",
        roles=("Inference.Admin",),
    )

    decision = authorize_model(
        principal,
        "restricted-model",
    )

    assert decision.allowed is True