"""
Project 9 — Azure Gateway Remote Authorization Validation

Tests the deployed gateway over HTTPS using a real Entra token.

Checks:
- Authorized inference returns the exact synthetic response contract.
- Reader access to the restricted model is denied.
- Missing and invalid tokens are rejected.
- Denied responses contain no prompt or inference output.

Tokens, private keys, and passphrases are never printed or saved
by this script.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from acquire_entra_token import acquire_token


TIMEOUT_SECONDS = 90.0
PROMPT = "Synthetic security validation request."
SYNTHETIC_RESPONSE = "Synthetic inference response"


def get_gateway_url() -> str:
    base_url = os.environ.get(
        "P9_AZURE_GATEWAY_URL", ""
    ).strip().rstrip("/")

    if not base_url:
        raise RuntimeError(
            "P9_AZURE_GATEWAY_URL is not configured."
        )

    try:
        parsed = urlsplit(base_url)
        port = parsed.port

        valid = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path == ""
            and "\\" not in base_url
            and not any(
                character.isspace() or ord(character) < 32
                for character in base_url
            )
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError:
        valid = False

    if not valid:
        raise RuntimeError(
            "Gateway URL must be an HTTPS origin without "
            "credentials, path, query, or fragment."
        )

    return f"{base_url}/v1/inference"


def request_inference(
    client: httpx.Client,
    endpoint: str,
    model: str,
    token: str | None,
) -> httpx.Response:
    headers = {}

    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    return client.post(
        endpoint,
        json={
            "model": model,
            "prompt": PROMPT,
        },
        headers=headers,
    )


def valid_success_response(
    response: httpx.Response,
    model: str,
) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False

    return (
        isinstance(payload, dict)
        and set(payload) == {"model", "response", "synthetic"}
        and payload.get("model") == model
        and payload.get("response") == SYNTHETIC_RESPONSE
        and payload.get("synthetic") is True
    )


def contains_inference_fields(value: object) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"model", "prompt", "response", "synthetic"}:
                return True

            if contains_inference_fields(nested):
                return True

    elif isinstance(value, list):
        return any(contains_inference_fields(item) for item in value)

    return False


def valid_denied_response(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False

    if (
        not isinstance(payload, dict)
        or set(payload) != {"detail"}
        or not isinstance(payload["detail"], str)
    ):
        return False

    text = response.text.casefold()

    return (
        not contains_inference_fields(payload)
        and PROMPT.casefold() not in text
        and SYNTHETIC_RESPONSE.casefold() not in text
        and "synthetic response" not in text
    )


def main() -> None:
    print("Project 9 — Azure Gateway Remote Validation")
    print("--------------------------------------------")

    endpoint = get_gateway_url()

    print("Transport: HTTPS")
    print("Target: Azure Container Apps")
    print("Token handling: memory only")

    token = acquire_token()

    if not isinstance(token, str) or not token:
        raise RuntimeError("Token acquisition failed.")

    cases = [
        (
            "Reader authorized",
            "research-model",
            token,
            200,
        ),
        (
            "Reader denied restricted model",
            "restricted-model",
            token,
            403,
        ),
        (
            "Missing token denied",
            "research-model",
            None,
            401,
        ),
        (
            "Invalid token denied",
            "research-model",
            "invalid.synthetic.token",
            401,
        ),
    ]

    failures = []

    with httpx.Client(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        for label, model, bearer, expected in cases:
            try:
                response = request_inference(
                    client,
                    endpoint,
                    model,
                    bearer,
                )

                status_ok = response.status_code == expected

                if expected == 200:
                    contract_ok = valid_success_response(
                        response,
                        model,
                    )
                    check_name = "inference contract"
                else:
                    contract_ok = valid_denied_response(response)
                    check_name = "denial contract and no inference leak"

                passed = status_ok and contract_ok

                print(
                    f"{'PASS' if passed else 'FAIL'}: "
                    f"{label} — HTTP {response.status_code} "
                    f"(expected {expected}); "
                    f"{check_name}: {contract_ok}"
                )

                if not passed:
                    failures.append(label)

            except httpx.HTTPError as exc:
                print(
                    f"FAIL: {label} — {type(exc).__name__}"
                )
                failures.append(label)

    if failures:
        print(
            f"\nAzure gateway validation FAILED: "
            f"{len(failures)}/{len(cases)}"
        )
        raise SystemExit(1)

    print(
        f"\nAzure gateway validation: "
        f"PASSED ({len(cases)}/{len(cases)})"
    )

if __name__ == "__main__":
    main()