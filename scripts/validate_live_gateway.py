"""
Validate real Entra authentication against an in-process gateway.

Inference uses explicit local-synthetic mode. No backend boundary
or deployed Azure gateway is exercised by this script.
"""

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from acquire_entra_token import acquire_token
from validate_azure_gateway import (
    request_inference,
    valid_denied_response,
    valid_success_response,
)
from src.gateway.app import app


def validate_live_gateway() -> None:
    print("Project 9 — In-process Entra Gateway Validation")
    print("Identity: real Entra token")
    print("Inference: explicit local-synthetic mode")
    print("Backend boundary: not exercised")

    token = acquire_token()
    if not isinstance(token, str) or not token:
        raise RuntimeError("Token acquisition failed")

    cases = [
        ("Reader authorized", "research-model", token, 200),
        ("Reader denied restricted model", "restricted-model", token, 403),
        ("Missing token denied", "research-model", None, 401),
        ("Invalid token denied", "research-model", "invalid.synthetic.token", 401),
    ]
    previous_mode = os.environ.get("P9_INFERENCE_MODE")
    failures = []

    try:
        os.environ["P9_INFERENCE_MODE"] = "local-synthetic"

        with TestClient(app) as client:
            for label, model, bearer, expected in cases:
                response = request_inference(
                    client, "/v1/inference", model, bearer
                )
                contract_ok = (
                    valid_success_response(response, model)
                    if expected == 200
                    else valid_denied_response(response)
                )
                passed = (
                    response.status_code == expected and contract_ok
                )

                print(
                    f"{'PASS' if passed else 'FAIL'}: {label} — "
                    f"HTTP {response.status_code} (expected {expected}); "
                    f"response contract: {contract_ok}"
                )

                if not passed:
                    failures.append(label)
    finally:
        if previous_mode is None:
            os.environ.pop("P9_INFERENCE_MODE", None)
        else:
            os.environ["P9_INFERENCE_MODE"] = previous_mode

    if failures:
        raise SystemExit(1)

    print("In-process gateway validation: PASSED (4/4)")

if __name__ == "__main__":
    validate_live_gateway()