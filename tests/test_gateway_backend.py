"""
Gateway-to-backend boundary tests.

Uses synthetic credentials and in-process HTTP transport only.
"""

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.gateway.app as gateway_module
from src.backend.app import app as backend_app


TEST_SERVICE_KEY = "synthetic-test-service-key-0123456789abcdef"

TIMEOUT_VARIABLES = (
    "P9_BACKEND_CONNECT_TIMEOUT_SECONDS",
    "P9_BACKEND_READ_TIMEOUT_SECONDS",
    "P9_BACKEND_WRITE_TIMEOUT_SECONDS",
    "P9_BACKEND_POOL_TIMEOUT_SECONDS",
)

DEFAULT_TIMEOUT = {
    "connect": 10.0,
    "read": 60.0,
    "write": 10.0,
    "pool": 5.0,
}


@pytest.fixture(autouse=True)
def backend_configuration(monkeypatch):
    monkeypatch.setenv("P9_INFERENCE_MODE", "backend")
    monkeypatch.setenv("P9_BACKEND_URL", "http://backend.test")
    monkeypatch.setenv("P9_BACKEND_SERVICE_KEY", TEST_SERVICE_KEY)

    for name in TIMEOUT_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def inference_request():
    return gateway_module.InferenceRequest(
        model="research-model",
        prompt="Synthetic boundary test",
    )


def install_transport(
    monkeypatch,
    handler,
    expected_timeout=None,
):
    real_client = httpx.Client

    if expected_timeout is None:
        expected_timeout = DEFAULT_TIMEOUT

    def client_factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        assert isinstance(kwargs["timeout"], httpx.Timeout)
        assert kwargs["timeout"].as_dict() == expected_timeout

        return real_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(
        gateway_module.httpx,
        "Client",
        client_factory,
    )


def assert_failure(request, status_code):
    with pytest.raises(HTTPException) as exc:
        gateway_module.invoke_backend(request)

    assert exc.value.status_code == status_code


def test_default_mode_requires_backend_url(monkeypatch, inference_request):
    monkeypatch.delenv("P9_INFERENCE_MODE", raising=False)
    monkeypatch.delenv("P9_BACKEND_URL", raising=False)

    assert_failure(inference_request, 503)


def test_explicit_local_synthetic_mode(monkeypatch, inference_request):
    monkeypatch.setenv("P9_INFERENCE_MODE", "local-synthetic")
    monkeypatch.delenv("P9_BACKEND_URL", raising=False)
    monkeypatch.delenv("P9_BACKEND_SERVICE_KEY", raising=False)

    assert gateway_module.invoke_backend(inference_request) == {
        "model": "research-model",
        "response": "Synthetic inference response",
        "synthetic": True,
    }


def test_unknown_mode_fails_closed(monkeypatch, inference_request):
    monkeypatch.setenv("P9_INFERENCE_MODE", "invalid")

    assert_failure(inference_request, 503)


@pytest.mark.parametrize("credential", ["", "short", "x" * 32 + "\n"])
def test_invalid_service_configuration(
    monkeypatch,
    inference_request,
    credential,
):
    monkeypatch.setenv("P9_BACKEND_SERVICE_KEY", credential)

    assert_failure(inference_request, 503)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://backend.test",
        "http://",
        "http://user:password@backend.test",
        "http://backend.test/unexpected-path",
        "http://backend.test?redirect=elsewhere",
        "http://backend.test#fragment",
        "http://backend.test:invalid",
    ],
)
def test_invalid_backend_url(monkeypatch, inference_request, url):
    monkeypatch.setenv("P9_BACKEND_URL", url)

    assert_failure(inference_request, 503)


def test_gateway_authenticates_to_real_backend(
    monkeypatch,
    inference_request,
):
    with TestClient(backend_app) as backend_client:
        def handler(request):
            assert str(request.url) == (
                "http://backend.test/internal/inference"
            )
            assert request.headers["X-Service-Key"] == TEST_SERVICE_KEY
            assert "authorization" not in request.headers

            response = backend_client.post(
                "/internal/inference",
                content=request.content,
                headers={
                    "Content-Type": "application/json",
                    "X-Service-Key": request.headers["X-Service-Key"],
                },
            )

            return httpx.Response(
                response.status_code,
                json=response.json(),
            )

        install_transport(monkeypatch, handler)

        assert gateway_module.invoke_backend(inference_request) == {
            "model": "research-model",
            "response": "Synthetic inference response",
            "synthetic": True,
        }


def test_backend_rejects_wrong_forwarded_key(
    monkeypatch,
    inference_request,
):
    with TestClient(backend_app) as backend_client:
        def handler(request):
            response = backend_client.post(
                "/internal/inference",
                content=request.content,
                headers={
                    "Content-Type": "application/json",
                    "X-Service-Key": "wrong-synthetic-service-key-0123456789",
                },
            )

            assert response.status_code == 401

            return httpx.Response(
                response.status_code,
                json=response.json(),
            )

        install_transport(monkeypatch, handler)

        assert_failure(inference_request, 502)


@pytest.mark.parametrize("status_code", [301, 307, 401, 403, 500])
def test_backend_rejection_and_redirects(
    monkeypatch,
    inference_request,
    status_code,
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status_code,
            headers={"Location": "https://elsewhere.test"},
        )

    install_transport(monkeypatch, handler)

    assert_failure(inference_request, 502)
    assert len(calls) == 1


def test_backend_timeout(monkeypatch, inference_request):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout(
            "Synthetic timeout",
            request=request,
        )

    install_transport(monkeypatch, handler)

    assert_failure(inference_request, 502)
    assert len(calls) == 1


def test_backend_invalid_json(monkeypatch, inference_request):
    def handler(request):
        return httpx.Response(200, content=b"invalid-json")

    install_transport(monkeypatch, handler)

    assert_failure(inference_request, 502)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {
            "model": "wrong-model",
            "response": "Synthetic response",
            "synthetic": True,
        },
        {
            "model": "research-model",
            "response": "Synthetic response",
            "synthetic": False,
        },
        {
            "model": "research-model",
            "response": 123,
            "synthetic": True,
        },
    ],
)
def test_backend_invalid_contract(
    monkeypatch,
    inference_request,
    payload,
):
    def handler(request):
        return httpx.Response(200, json=payload)

    install_transport(monkeypatch, handler)

    assert_failure(inference_request, 502)


@pytest.mark.parametrize(
    "raw",
    ["", "invalid", "nan", "inf", "0", "-1", "121"],
)
def test_invalid_timeout_prevents_http_client_creation(
    monkeypatch,
    inference_request,
    raw,
):
    monkeypatch.setenv("P9_BACKEND_READ_TIMEOUT_SECONDS", raw)

    def forbidden_client(**kwargs):
        pytest.fail("Invalid timeout configuration reached HTTP client")

    monkeypatch.setattr(
        gateway_module.httpx,
        "Client",
        forbidden_client,
    )

    with pytest.raises(HTTPException) as exc:
        gateway_module.invoke_backend(inference_request)

    assert exc.value.status_code == 503
    assert exc.value.detail == "Backend timeout configuration invalid"


def test_custom_timeouts_reach_http_client(
    monkeypatch,
    inference_request,
):
    settings = {
        "connect": 3.0,
        "read": 45.0,
        "write": 4.0,
        "pool": 2.0,
    }

    for phase, value in settings.items():
        monkeypatch.setenv(
            f"P9_BACKEND_{phase.upper()}_TIMEOUT_SECONDS",
            str(value),
        )

    def handler(request):
        assert request.extensions["timeout"] == settings

        return httpx.Response(
            200,
            json={
                "model": "research-model",
                "response": "Synthetic inference response",
                "synthetic": True,
            },
        )

    install_transport(
        monkeypatch,
        handler,
        expected_timeout=settings,
    )

    assert gateway_module.invoke_backend(inference_request)["synthetic"]