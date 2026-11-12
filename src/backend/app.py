"""
Project 9 — Synthetic Inference Backend

Requires service authentication and returns synthetic data only.
Request validation errors do not reflect submitted values.

Azure deployment must additionally use internal-only ingress.
"""

import hmac
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


app = FastAPI(
    title="Project 9 Synthetic Inference Backend",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(_request, _exception):
    # Validation errors can contain submitted prompts or other values.
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request"},
    )


class InferenceRequest(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=4096)


def authorize_gateway(credential: str | None) -> None:
    expected = os.environ.get("P9_BACKEND_SERVICE_KEY", "")

    if (
        len(expected) < 32
        or not expected.isascii()
        or any(
            ord(character) < 33 or ord(character) > 126
            for character in expected
        )
    ):
        raise HTTPException(
            status_code=503,
            detail="Backend service authentication unavailable",
        )

    if (
        credential is None
        or not credential.isascii()
        or not hmac.compare_digest(credential, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail="Service authentication failed",
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/internal/inference")
def internal_inference(
    request: InferenceRequest,
    x_service_key: str | None = Header(default=None),
):
    authorize_gateway(x_service_key)

    return {
        "model": request.model,
        "response": "Synthetic inference response",
        "synthetic": True,
    }