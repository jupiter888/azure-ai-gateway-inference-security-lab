"""
Gateway decision-audit integration tests.

Identity and backend operations are stubbed.
All sensitive-data canaries are synthetic.
"""

import json
import logging

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.gateway.app as gateway_module
from src.identity.jwt_validator import (
    AuthenticatedPrincipal,
    AuthenticationError,
)
from src.policy.inference_quota import QuotaDecision


TOKEN = "SYNTHETIC_TOKEN_CANARY"
PROMPT = "SYNTHETIC_PROMPT_CANARY"
SUBJECT = "SYNTHETIC_IDENTITY_CANARY"
PRIVATE_ERROR = "SYNTHETIC_EXCEPTION_CANARY"


@pytest.mark.parametrize(
    "scenario,status,reason",
    [
        ("missing", 401, "authentication_required"),
        ("malformed", 401, "invalid_authorization_header"),
        ("invalid", 401, "authentication_failed"),
        ("model", 403, "model_access_denied"),
        ("quota", 429, "quota_exceeded"),
        ("capacity", 503, "admission_capacity_unavailable"),
        ("quota_config", 503, "quota_configuration_unavailable"),
        ("backend", 502, "backend_unavailable"),
        ("backend_config", 503, "backend_configuration_unavailable"),
        ("success", 200, "inference_succeeded"),
    ],
)
def test_gateway_emits_one_sanitized_decision(
    monkeypatch,
    caplog,
    scenario,
    status,
    reason,
):
    calls = {"backend": 0, "quota": 0}

    class Validator:
        def validate(self, token):
            if scenario == "invalid":
                raise AuthenticationError(PRIVATE_ERROR)

            return AuthenticatedPrincipal(
                subject=SUBJECT,
                roles=("Inference.Reader",),
            )

    class Quota:
        def admit(self, subject, model):
            calls["quota"] += 1
            assert subject == SUBJECT

            if scenario == "quota":
                return QuotaDecision(False, "quota_exceeded", 20)
            if scenario == "capacity":
                return QuotaDecision(False, "capacity_exhausted", 1)
            if scenario == "quota_config":
                return QuotaDecision(False, "unknown_model")

            return QuotaDecision(True, "admitted")

    def backend(request):
        calls["backend"] += 1

        if scenario == "backend":
            raise HTTPException(502, "Inference backend unavailable")
        if scenario == "backend_config":
            raise HTTPException(503, "Backend configuration unavailable")

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
    monkeypatch.setattr(gateway_module, "quota", Quota())
    monkeypatch.setattr(gateway_module, "invoke_backend", backend)

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Request-ID": "SYNTHETIC_CALLER_REQUEST_ID_CANARY",
    }

    if scenario == "missing":
        headers.pop("Authorization")
    elif scenario == "malformed":
        headers["Authorization"] = TOKEN

    model = (
        "SYNTHETIC_UNTRUSTED_MODEL_CANARY"
        if scenario == "model"
        else "research-model"
    )

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        with TestClient(gateway_module.app) as client:
            response = client.post(
                "/v1/inference",
                headers=headers,
                json={"model": model, "prompt": PROMPT},
            )

    assert response.status_code == status

    events = []
    for record in caplog.records:
        if record.name != "uvicorn.error":
            continue

        payload = json.loads(record.getMessage())
        if payload.get("event") == "inference_decision":
            events.append(payload)

    assert len(events) == 1
    assert events[0]["reason"] == reason

    if scenario in {"missing", "malformed", "invalid", "model"}:
        assert calls["quota"] == 0

    expected_backend_calls = (
        1 if scenario in {"backend", "backend_config", "success"} else 0
    )
    assert calls["backend"] == expected_backend_calls

    if scenario == "quota":
        assert response.headers["Retry-After"] == "20"

    for canary in (
        TOKEN,
        PROMPT,
        SUBJECT,
        PRIVATE_ERROR,
        "SYNTHETIC_UNTRUSTED_MODEL_CANARY",
        "SYNTHETIC_CALLER_REQUEST_ID_CANARY",
    ):
        assert canary not in caplog.text