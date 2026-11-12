
"""
Project 9 — Microsoft Entra Certificate Authentication

Acquire a Microsoft Entra ID access token using certificate-based
client credentials.

Security properties:
- Encrypted private key stored outside the project repository.
- Private-key passphrase entered interactively.
- Certificate-based client authentication through MSAL.
- No access tokens or private keys written to disk.
- Token claims displayed for inspection only.
- No unverified claims used for authorization decisions.
"""

import getpass
import os
from pathlib import Path

import jwt
import msal
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv


# --------------------------------------------------
# Environment configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

TENANT_ID = os.environ["P9_TENANT_ID"]
CLIENT_ID = os.environ["P9_TEST_CLIENT_ID"]
GATEWAY_ID = os.environ["P9_GATEWAY_CLIENT_ID"]

AUTHORITY = (
    f"https://login.microsoftonline.com/{TENANT_ID}"
)

SCOPES = [
    f"api://{GATEWAY_ID}/.default"
]


# --------------------------------------------------
# Certificate configuration
# --------------------------------------------------

CREDENTIAL_DIR = (
    Path.home()
    / ".config"
    / "project09"
    / "credentials"
)

PRIVATE_KEY_PATH = CREDENTIAL_DIR / "client-key.pem"
CERTIFICATE_PATH = CREDENTIAL_DIR / "client-cert.pem"


def load_certificate_credential() -> dict:
    """
    Load the encrypted RSA private key and public certificate.

    The private key is decrypted in memory and passed to MSAL.
    The unencrypted private key is never written to disk.
    """

    if not PRIVATE_KEY_PATH.is_file():
        raise FileNotFoundError(
            f"Private key not found: {PRIVATE_KEY_PATH}"
        )

    if not CERTIFICATE_PATH.is_file():
        raise FileNotFoundError(
            f"Certificate not found: {CERTIFICATE_PATH}"
        )

    passphrase = getpass.getpass(
        "Certificate private-key passphrase: "
    )

    encrypted_key = PRIVATE_KEY_PATH.read_bytes()

    private_key = serialization.load_pem_private_key(
        encrypted_key,
        password=passphrase.encode("utf-8"),
    )

    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    certificate_pem = CERTIFICATE_PATH.read_text(
        encoding="utf-8"
    )

    return {
        "private_key": private_key_pem,
        "public_certificate": certificate_pem,
    }


# --------------------------------------------------
# Microsoft Entra token acquisition
# --------------------------------------------------

def acquire_token() -> str:
    """
    Authenticate the registered test application using its
    certificate credential and request a gateway access token.
    """

    credential = load_certificate_credential()

    client = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
        client_credential=credential,
        token_cache=msal.SerializableTokenCache(),
    )

    result = client.acquire_token_for_client(
        scopes=SCOPES
    )

    if "access_token" not in result:
        print("\nToken acquisition failed.")
        print(
            "Error:",
            result.get("error", "unknown_error"),
        )
        print(
            "Description:",
            result.get(
                "error_description",
                "No description supplied",
            ),
        )
        raise SystemExit(1)

    token = result["access_token"]

    # Decode for inspection only.
    # Cryptographic verification is performed by the gateway.
    claims = jwt.decode(
        token,
        options={
            "verify_signature": False,
            "verify_aud": False,
            "verify_exp": False,
        },
    )

    print("\nMicrosoft Entra token acquired successfully.")
    print("-" * 50)

    print("Token version:", claims.get("ver"))
    print("Issuer:", claims.get("iss"))
    print("Audience:", claims.get("aud"))
    print("Roles:", claims.get("roles"))

    print(
        "Calling application:",
        claims.get("azp") or claims.get("appid"),
    )

    print(
        "Token type:",
        claims.get("idtyp", "not specified"),
    )

    print("-" * 50)
    print("Access token not displayed or saved.")

    return token


# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":
    acquire_token()
