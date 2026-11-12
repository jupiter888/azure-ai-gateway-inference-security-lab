"""
Gateway quota integration tests.

No external identity or backend requests are made.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.gateway.app as gateway_module
from src.identity.jwt_validator import (
    AuthenticatedPrincipal,
    AuthenticationError,
)
from src.policy.inference_quota import InferenceQuota


@pytest.fixture
def boundary(monkeypatch):
    state = {
        "now": 0.0,
        "calls": 0,
        "backend_fails": False,
    }

    class Validator:
        def validate(self, token):
            if token == "invalid":
                raise AuthenticationError("Synthetic invalid token")

            return AuthenticatedPrincipal(
                subject=token,
                roles=("Inference.Reader",),
            )

    def backend(request):
        state["calls"] += 1

        if state["backend_fails"]:
            raise HTTPException(
                status_code=502,
                detail="Inference backend unavailable",
            )

        return {
            "model": request.model,
            "response": "Synthetic inference response",
            "synthetic": True,
        }

    monkeypatch.setattr(
        gateway_module,
        "get_validator",
        lambda: Validator(),
    )
    monkeypatch.setattr(gateway_module, "invoke_backend", backend)
    monkeypatch.setattr(
        gateway_module,
        "quota",
        InferenceQuota(
            {"research-model": 1},
            clock=lambda: state["now"],
        ),
    )

    with TestClient(gateway_module.app) as client:
        yield client, state


def inference(client, token="subject-a", model="research-model"):
    headers = {}

    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    return client.post(
        "/v1/inference",
        headers=headers,
        json={
            "model": model,
            "prompt": "Synthetic quota test",
        },
    )


def test_quota_rejection_never_reaches_backend(boundary):
    client, state = boundary

    assert inference(client).status_code == 200

    denied = inference(client)

    assert denied.status_code == 429
    assert denied.headers["Retry-After"] == "60"
    assert denied.json() == {"detail": "Inference quota exceeded"}
    assert state["calls"] == 1


def test_authentication_and_authorization_denials_do_not_use_quota(
    boundary,
):
    client, state = boundary

    assert inference(client, token=None).status_code == 401
    assert inference(client, token="invalid").status_code == 401
    assert inference(
        client,
        model="restricted-model",
    ).status_code == 403

    assert state["calls"] == 0

    assert inference(client).status_code == 200
    assert state["calls"] == 1


def test_different_subject_has_independent_quota(boundary):
    client, state = boundary

    assert inference(client, token="subject-a").status_code == 200
    assert inference(client, token="subject-a").status_code == 429
    assert inference(client, token="subject-b").status_code == 200

    assert state["calls"] == 2


def test_backend_failure_still_consumes_admission(boundary):
    client, state = boundary
    state["backend_fails"] = True

    assert inference(client).status_code == 502
    assert inference(client).status_code == 429

    assert state["calls"] == 1


def test_admission_recovers_at_window_expiration(boundary):
    client, state = boundary

    assert inference(client).status_code == 200

    state["now"] = 59.0
    denied = inference(client)

    assert denied.status_code == 429
    assert denied.headers["Retry-After"] == "1"

    state["now"] = 60.0

    assert inference(client).status_code == 200
    assert state["calls"] == 2