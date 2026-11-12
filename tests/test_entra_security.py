"""
Project 9 — Microsoft Entra JWT Security Regression Tests

Synthetic, offline adversarial tests for:
- Entra v1 token validation
- Application identity allowlisting
- Token version enforcement
- Issuer and audience restrictions
- Token expiration
- Application role validation
- Missing subject
- Invalid signatures
- JWKS retrieval failures

No Azure credentials, live tokens, or infrastructure required.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import PyJWKClientError

from src.gateway.config import GatewayConfig
from src.identity.jwt_validator import (
    AuthenticationError,
    JWTValidator,
)


ISSUER = "https://sts.windows.net/synthetic-tenant/"
AUDIENCE = "api://synthetic-gateway"
ALLOWED_CLIENT = "synthetic-authorized-client"
UNAUTHORIZED_CLIENT = "synthetic-unauthorized-client"


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


@pytest.fixture
def validator(signing_key, monkeypatch):
    config = GatewayConfig(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://example.invalid/jwks",
        allowed_client_id=ALLOWED_CLIENT,
        required_token_version="1.0",
    )

    instance = JWTValidator(config)

    class SyntheticSigningKey:
        key = signing_key.public_key()

    monkeypatch.setattr(
        instance.jwks_client,
        "get_signing_key_from_jwt",
        lambda token: SyntheticSigningKey(),
    )

    return instance


def create_token(signing_key, **overrides):
    now = datetime.now(timezone.utc)

    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "synthetic-service-principal",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "ver": "1.0",
        "appid": ALLOWED_CLIENT,
        "roles": ["Inference.Reader"],
        "jti": str(uuid4()),
    }

    claims.update(overrides)

    return jwt.encode(
        claims,
        signing_key,
        algorithm="RS256",
        headers={"kid": "synthetic-test-key"},
    )


def test_valid_entra_reader_token(signing_key, validator):
    token = create_token(signing_key)

    principal = validator.validate(token)

    assert principal.subject == "synthetic-service-principal"
    assert principal.roles == ("Inference.Reader",)


@pytest.mark.parametrize(
    "claims",
    [
        {"appid": UNAUTHORIZED_CLIENT},
        {"appid": None},
        {"appid": ""},
        {"ver": "2.0"},
        {"ver": None},
        {"iss": "https://sts.windows.net/other-tenant/"},
        {"aud": "api://other-gateway"},
        {"roles": "Inference.Reader"},
        {"roles": [""]},
        {"roles": [123]},
        {"sub": None},
    ],
)
def test_invalid_claims_are_rejected(
    signing_key,
    validator,
    claims,
):
    token = create_token(signing_key, **claims)

    with pytest.raises(AuthenticationError):
        validator.validate(token)


def test_expired_token_rejected(signing_key, validator):
    token = create_token(
        signing_key,
        exp=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    with pytest.raises(AuthenticationError):
        validator.validate(token)


def test_future_token_rejected(signing_key, validator):
    token = create_token(
        signing_key,
        nbf=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    with pytest.raises(AuthenticationError):
        validator.validate(token)


def test_invalid_signature_rejected(validator):
    attacker_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    token = create_token(attacker_key)

    with pytest.raises(AuthenticationError):
        validator.validate(token)


def test_jwks_failure_rejected(
    signing_key,
    validator,
    monkeypatch,
):
    def fail_jwks_lookup(token):
        raise PyJWKClientError(
            "Synthetic JWKS retrieval failure"
        )

    monkeypatch.setattr(
        validator.jwks_client,
        "get_signing_key_from_jwt",
        fail_jwks_lookup,
    )

    token = create_token(signing_key)

    with pytest.raises(AuthenticationError):
        validator.validate(token)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not-a-jwt",
        "a" * 8193,
    ],
)
def test_malformed_tokens_rejected(validator, token):
    with pytest.raises(AuthenticationError):
        validator.validate(token)