"""
HTTP enforcement and audit tests for backend concurrency admission.
"""

import json
import logging

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.gateway.app as gateway_module
from src.identity.jwt_validator import AuthenticatedPrincipal
from src.policy.inference_concurrency import InferenceConcurrency
from src.policy.inference_quota import InferenceQuota


@pytest.fixture
def boundary(monkeypatch):
    state = {"calls": 0, "fail": False}
    limiter = InferenceConcurrency(1)

    class Validator:
        def validate(self, token):
            return AuthenticatedPrincipal(
                subject="synthetic-subject",
                roles=("Inference.Reader",),
            )

    def backend(request):
        state["calls"] += 1

        if state["fail"]:
            raise HTTPException(502, "Inference backend unavailable")

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
    monkeypatch.setattr(gateway_module, "concurrency", limiter)
    monkeypatch.setattr(
        gateway_module,
        "quota",
        InferenceQuota({"research-model": 30}),
    )

    with TestClient(gateway_module.app) as client:
        yield client, state, limiter


def infer(client, authenticated=True, model="research-model"):
    headers = (
        {"Authorization": "Bearer synthetic-token"}
        if authenticated
        else {}
    )

    return client.post(
        "/v1/inference",
        headers=headers,
        json={"model": model, "prompt": "Synthetic concurrency test"},
    )


def test_overload_is_rejected_and_audited(boundary, caplog):
    client, state, limiter = boundary

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        with limiter.slot():
            response = infer(client)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json() == {
        "detail": "Inference concurrency capacity unavailable"
    }
    assert state["calls"] == 0

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "uvicorn.error"
    ]

    assert len(events) == 1
    assert events[0]["reason"] == "concurrency_exceeded"
    assert events[0]["outcome"] == "unavailable"

    assert infer(client).status_code == 200
    assert state["calls"] == 1


def test_backend_failure_releases_slot(boundary):
    client, state, _ = boundary
    state["fail"] = True

    assert infer(client).status_code == 502

    state["fail"] = False

    assert infer(client).status_code == 200
    assert state["calls"] == 2


def test_success_releases_slot(boundary):
    client, state, _ = boundary

    assert infer(client).status_code == 200
    assert infer(client).status_code == 200
    assert state["calls"] == 2


@pytest.mark.parametrize(
    "authenticated,model,expected",
    [
        (False, "research-model", 401),
        (True, "restricted-model", 403),
    ],
)
def test_identity_and_model_denials_precede_concurrency(
    boundary,
    authenticated,
    model,
    expected,
):
    client, state, limiter = boundary

    with limiter.slot():
        response = infer(
            client,
            authenticated=authenticated,
            model=model,
        )

    assert response.status_code == expected
    assert state["calls"] == 0