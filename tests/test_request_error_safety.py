"""
Regression tests for safe request errors and credential rejection.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.backend.app import app as backend_app, authorize_gateway
from src.gateway.app import app as gateway_app


CANARY = "SYNTHETIC_REQUEST_SECRET_CANARY"
SERVICE_KEY = "synthetic-test-service-key-0123456789abcdef"


@pytest.mark.parametrize(
    "app,path",
    [
        (gateway_app, "/v1/inference"),
        (backend_app, "/internal/inference"),
    ],
)
@pytest.mark.parametrize(
    "case",
    ["type", "length", "missing", "json", "root"],
)
def test_invalid_requests_do_not_reflect_input(
    app,
    path,
    case,
    monkeypatch,
    caplog,
):
    monkeypatch.setenv("P9_BACKEND_SERVICE_KEY", SERVICE_KEY)

    headers = {
        "Authorization": "Bearer " + CANARY,
        "X-Service-Key": SERVICE_KEY,
    }

    with TestClient(app) as client:
        if case == "json":
            response = client.post(
                path,
                content='{"prompt":"' + CANARY + '",BROKEN}',
                headers={
                    **headers,
                    "Content-Type": "application/json",
                },
            )
        else:
            payload = {
                "type": {
                    "model": "research-model",
                    "prompt": {"private": CANARY},
                },
                "length": {
                    "model": "research-model",
                    "prompt": CANARY * 300,
                },
                "missing": {"prompt": CANARY},
                "root": [CANARY],
            }[case]

            response = client.post(
                path,
                json=payload,
                headers=headers,
            )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
    assert CANARY not in response.text + caplog.text
    assert SERVICE_KEY not in response.text + caplog.text


def test_non_ascii_service_credential_is_rejected(monkeypatch):
    monkeypatch.setenv("P9_BACKEND_SERVICE_KEY", SERVICE_KEY)

    with TestClient(backend_app) as client:
        response = client.post(
            "/internal/inference",
            json={
                "model": "research-model",
                "prompt": "Synthetic test",
            },
            headers=[
                (b"x-service-key", b"invalid-\xc3\xa9-credential"),
            ],
        )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Service authentication failed"
    }


@pytest.mark.parametrize(
    "configured",
    [
        "x" * 32 + "é",
        "x" * 32 + "\n",
        " " * 32,
    ],
)
def test_invalid_configured_service_key_fails_closed(
    monkeypatch,
    configured,
):
    monkeypatch.setenv("P9_BACKEND_SERVICE_KEY", configured)

    with pytest.raises(HTTPException) as exc:
        authorize_gateway(SERVICE_KEY)

    assert exc.value.status_code == 503