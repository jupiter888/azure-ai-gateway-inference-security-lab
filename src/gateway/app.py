"""
Project 9 — AI Inference Security Gateway

Enforces identity, model authorization, process-local quotas,
and nonblocking backend concurrency admission.

Backend timeouts are configurable and bounded.
Inference requests are not automatically retried.

Security decision events exclude identities, credentials, tokens,
prompts, URLs, response bodies, and exception messages.
"""

import json
import logging
import os
import time
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.gateway.audit import audit_decision
from src.gateway.config import (
    load_backend_timeout_config,
    load_config,
)
from src.identity.jwt_validator import AuthenticationError, JWTValidator
from src.policy.inference_concurrency import (
    InferenceBusy,
    InferenceConcurrency,
)
from src.policy.inference_quota import InferenceQuota
from src.policy.model_authorization import authorize_model


app = FastAPI(
    title="Project 9 — AI Inference Security Gateway",
    version="0.7.1",
)

logger = logging.getLogger("uvicorn.error")
validator: JWTValidator | None = None

quota = InferenceQuota(
    limits={
        "research-model": 30,
        "restricted-model": 10,
    },
    window_seconds=60,
    max_entries=1000,
)

concurrency = InferenceConcurrency(maximum=2)


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(_request, _exception):
    # Never serialize validation errors: they can contain submitted data.
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request"},
    )


class InferenceRequest(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=2000)


def log_backend_failure(
    category: str,
    started: float,
    upstream_status: int | None = None,
) -> None:
    event = {
        "event": "backend_failure",
        "category": category,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }

    if upstream_status is not None:
        event["upstream_status"] = upstream_status

    logger.warning(json.dumps(event, sort_keys=True))


def get_validator() -> JWTValidator:
    global validator

    if validator is None:
        validator = JWTValidator(load_config())

    return validator


def invoke_backend(request: InferenceRequest) -> dict:
    mode = os.environ.get("P9_INFERENCE_MODE", "backend")

    if mode == "local-synthetic":
        return {
            "model": request.model,
            "response": "Synthetic inference response",
            "synthetic": True,
        }

    if mode != "backend":
        raise HTTPException(
            status_code=503,
            detail="Inference mode configuration invalid",
        )

    backend_url = os.environ.get(
        "P9_BACKEND_URL", ""
    ).strip().rstrip("/")

    if not backend_url:
        raise HTTPException(
            status_code=503,
            detail="Backend configuration unavailable",
        )

    try:
        parsed = urlsplit(backend_url)
        port = parsed.port

        valid_url = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.path == ""
            and not parsed.query
            and not parsed.fragment
            and not any(
                character.isspace() or ord(character) < 32
                for character in backend_url
            )
            and "\\" not in backend_url
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError:
        valid_url = False

    if not valid_url:
        raise HTTPException(
            status_code=503,
            detail="Backend configuration invalid",
        )

    service_key = os.environ.get("P9_BACKEND_SERVICE_KEY", "")

    if (
        len(service_key) < 32
        or not service_key.isascii()
        or any(
            ord(character) < 33 or ord(character) > 126
            for character in service_key
        )
    ):
        raise HTTPException(
            status_code=503,
            detail="Backend authentication unavailable",
        )

    try:
        settings = load_backend_timeout_config()
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="Backend timeout configuration invalid",
        ) from None

    timeout = httpx.Timeout(
        connect=settings.connect,
        read=settings.read,
        write=settings.write,
        pool=settings.pool,
    )

    started = time.monotonic()

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.post(
                f"{backend_url}/internal/inference",
                json=request.model_dump(),
                headers={"X-Service-Key": service_key},
            )
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.TimeoutException):
            category = "transport_timeout"
        elif isinstance(exc, httpx.ConnectError):
            category = "connection_failure"
        else:
            category = "transport_failure"

        log_backend_failure(category, started)

        raise HTTPException(
            status_code=502,
            detail="Inference backend unavailable",
        ) from None

    if response.status_code != 200:
        log_backend_failure(
            "upstream_rejected",
            started,
            upstream_status=response.status_code,
        )

        raise HTTPException(
            status_code=502,
            detail="Inference backend rejected request",
        )

    try:
        result = response.json()
    except ValueError:
        log_backend_failure("invalid_json", started)

        raise HTTPException(
            status_code=502,
            detail="Invalid inference backend response",
        ) from None

    if (
        not isinstance(result, dict)
        or result.get("model") != request.model
        or result.get("synthetic") is not True
        or not isinstance(result.get("response"), str)
    ):
        log_backend_failure("invalid_contract", started)

        raise HTTPException(
            status_code=502,
            detail="Invalid inference backend response",
        )

    return {
        "model": result["model"],
        "response": result["response"],
        "synthetic": True,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/inference")
def inference(
    request: InferenceRequest,
    authorization: str | None = Header(default=None),
):
    if authorization is None:
        audit_decision("authentication_required")
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token
        or token != token.strip()
    ):
        audit_decision("invalid_authorization_header")
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header",
        )

    try:
        principal = get_validator().validate(token)
    except AuthenticationError:
        audit_decision("authentication_failed")
        raise HTTPException(
            status_code=401,
            detail="Authentication failed",
        ) from None

    decision = authorize_model(
        principal=principal,
        model=request.model,
    )

    if not decision.allowed:
        audit_decision("model_access_denied", request.model)
        raise HTTPException(
            status_code=403,
            detail="Model access denied",
        )

    quota_decision = quota.admit(
        subject=principal.subject,
        model=request.model,
    )

    if not quota_decision.allowed:
        if quota_decision.reason == "quota_exceeded":
            audit_decision("quota_exceeded", request.model)
            raise HTTPException(
                status_code=429,
                detail="Inference quota exceeded",
                headers={
                    "Retry-After": str(quota_decision.retry_after),
                },
            )

        if quota_decision.reason == "capacity_exhausted":
            audit_decision(
                "admission_capacity_unavailable",
                request.model,
            )
            raise HTTPException(
                status_code=503,
                detail="Inference admission capacity unavailable",
                headers={
                    "Retry-After": str(quota_decision.retry_after),
                },
            )

        audit_decision(
            "quota_configuration_unavailable",
            request.model,
        )
        raise HTTPException(
            status_code=503,
            detail="Inference quota configuration unavailable",
        )

    try:
        with concurrency.slot():
            result = invoke_backend(request)
    except InferenceBusy:
        audit_decision("concurrency_exceeded", request.model)
        raise HTTPException(
            status_code=503,
            detail="Inference concurrency capacity unavailable",
            headers={"Retry-After": "1"},
        ) from None
    except HTTPException as exc:
        reason = (
            "backend_configuration_unavailable"
            if exc.status_code == 503
            else "backend_unavailable"
        )
        audit_decision(reason, request.model)
        raise

    audit_decision("inference_succeeded", request.model)
    return result