"""
Backend diagnostic safety tests.

All credentials, prompts, and response bodies are synthetic.
No network requests are made.
"""

import json
import logging

import httpx
import pytest
from fastapi import HTTPException

import src.gateway.app as gateway_module


SERVICE_KEY = "synthetic-diagnostic-service-key-0123456789abcdef"
PROMPT = "SYNTHETIC_PRIVATE_PROMPT_CANARY"
BODY = "SYNTHETIC_PRIVATE_RESPONSE_CANARY"
ERROR = "SYNTHETIC_PRIVATE_EXCEPTION_CANARY"
BACKEND_URL = "https://private-backend.test"


@pytest.fixture
def configured_request(monkeypatch):
    monkeypatch.setenv("P9_INFERENCE_MODE", "backend")
    monkeypatch.setenv("P9_BACKEND_URL", BACKEND_URL)
    monkeypatch.setenv("P9_BACKEND_SERVICE_KEY", SERVICE_KEY)

    return gateway_module.InferenceRequest(
        model="research-model",
        prompt=PROMPT,
    )


@pytest.fixture
def mock_transport(monkeypatch):
    real_client = httpx.Client

    def install(handler):
        def client_factory(**kwargs):
            return real_client(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        monkeypatch.setattr(
            gateway_module.httpx,
            "Client",
            client_factory,
        )

    return install


@pytest.mark.parametrize(
    "scenario,expected_category,upstream_status",
    [
        ("timeout", "transport_timeout", None),
        ("connect", "connection_failure", None),
        ("protocol", "transport_failure", None),
        ("rejected", "upstream_rejected", 401),
        ("json", "invalid_json", None),
        ("contract", "invalid_contract", None),
    ],
)
def test_failure_logs_are_useful_and_sanitized(
    configured_request,
    mock_transport,
    caplog,
    scenario,
    expected_category,
    upstream_status,
):
    def handler(request):
        if scenario == "timeout":
            raise httpx.ReadTimeout(ERROR, request=request)

        if scenario == "connect":
            raise httpx.ConnectError(ERROR, request=request)

        if scenario == "protocol":
            raise httpx.RemoteProtocolError(ERROR, request=request)

        if scenario == "rejected":
            return httpx.Response(401, text=BODY)

        if scenario == "json":
            return httpx.Response(200, text=BODY)

        return httpx.Response(
            200,
            json={
                "model": "wrong-model",
                "response": BODY,
                "synthetic": True,
            },
        )

    mock_transport(handler)

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        with pytest.raises(HTTPException) as exc:
            gateway_module.invoke_backend(configured_request)

    assert exc.value.status_code == 502

    records = [
        record
        for record in caplog.records
        if record.name == "uvicorn.error"
    ]
    assert len(records) == 1

    event = json.loads(records[0].getMessage())

    expected_fields = {"event", "category", "elapsed_ms"}
    if upstream_status is not None:
        expected_fields.add("upstream_status")
        assert event["upstream_status"] == upstream_status

    assert set(event) == expected_fields
    assert event["event"] == "backend_failure"
    assert event["category"] == expected_category
    assert isinstance(event["elapsed_ms"], int)
    assert event["elapsed_ms"] >= 0
    assert records[0].exc_info is None

    exposed_text = caplog.text + str(exc.value.detail)

    for sensitive_value in (
        SERVICE_KEY,
        PROMPT,
        BODY,
        ERROR,
        BACKEND_URL,
    ):
        assert sensitive_value not in exposed_text


def test_success_does_not_emit_failure_event(
    configured_request,
    mock_transport,
    caplog,
):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "research-model",
                "response": "Synthetic inference response",
                "synthetic": True,
            },
        )

    mock_transport(handler)

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        result = gateway_module.invoke_backend(configured_request)

    assert result["synthetic"] is True
    assert not [
        record
        for record in caplog.records
        if record.name == "uvicorn.error"
    ]