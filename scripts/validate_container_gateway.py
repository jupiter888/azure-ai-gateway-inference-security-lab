"""
Validate an already running gateway on the local loopback interface.

Uses a real Entra token. Does not start a container, change its mode,
or deploy Azure resources. HTTP is restricted to the fixed loopback URL.
"""

import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from acquire_entra_token import acquire_token
from validate_azure_gateway import (
    request_inference,
    valid_denied_response,
    valid_success_response,
)


GATEWAY_URL = "http://127.0.0.1:8000/v1/inference"


def main() -> None:
    print("Project 9 — Local HTTP Gateway Validation")
    print("Target: fixed loopback address, port 8000")
    print("Requires an already running local gateway")

    token = acquire_token()
    if not isinstance(token, str) or not token:
        raise RuntimeError("Token acquisition failed")

    cases = [
        ("Reader authorized", "research-model", token, 200),
        ("Reader denied restricted model", "restricted-model", token, 403),
        ("Missing token denied", "research-model", None, 401),
        ("Invalid token denied", "research-model", "invalid.synthetic.token", 401),
    ]
    failures = []

    with httpx.Client(
        timeout=90.0,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        for label, model, bearer, expected in cases:
            try:
                response = request_inference(
                    client, GATEWAY_URL, model, bearer
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

            except httpx.HTTPError as exc:
                print(
                    f"FAIL: {label} — {type(exc).__name__}"
                )
                failures.append(label)

    if failures:
        raise SystemExit(1)

    print("Local HTTP gateway validation: PASSED (4/4)")

if __name__ == "__main__":
    main()