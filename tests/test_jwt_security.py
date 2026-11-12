import json
import jwt
import pytest

from src.gateway.config import GatewayConfig
from src.identity.jwt_validator import (
    AuthenticationError,
    JWTValidator,
)
from tests.fixtures.jwt_factory import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    create_jwks,
    create_token,
    generate_key_pair,
)


@pytest.fixture
def jwt_environment(monkeypatch):
    private_key = generate_key_pair()

    config = GatewayConfig(
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        jwks_url="https://issuer.project09.test/jwks",
    )

    validator = JWTValidator(config)
    jwks = create_jwks(private_key)

    # Stub the network boundary, not the JWT verifier.
    monkeypatch.setattr(
        validator.jwks_client,
        "fetch_data",
        lambda: jwks,
    )

    return private_key, validator


def assert_rejected(validator, token):
    with pytest.raises(AuthenticationError):
        validator.validate(token)


def test_jwt001_valid_signed_token(jwt_environment):
    key, validator = jwt_environment

    token = create_token(key)

    principal = validator.validate(token)

    assert principal.subject == "synthetic-user"
    assert "Inference.Reader" in principal.roles


def test_jwt002_expired_token(jwt_environment):
    key, validator = jwt_environment

    token = create_token(key, expires_in=-60)

    assert_rejected(validator, token)


def test_jwt003_wrong_audience(jwt_environment):
    key, validator = jwt_environment

    token = create_token(
        key,
        audience="api://unauthorized-service",
    )

    assert_rejected(validator, token)


def test_jwt004_wrong_issuer(jwt_environment):
    key, validator = jwt_environment

    token = create_token(
        key,
        issuer="https://attacker.example",
    )

    assert_rejected(validator, token)


def test_jwt005_forged_signature(jwt_environment):
    _, validator = jwt_environment

    attacker_key = generate_key_pair()

    token = create_token(attacker_key)

    assert_rejected(validator, token)


def test_jwt006_missing_expiration(jwt_environment):
    key, validator = jwt_environment

    token = create_token(key)

    claims = jwt.decode(
        token,
        options={"verify_signature": False},
    )

    claims.pop("exp")

    modified = jwt.encode(
        claims,
        key,
        algorithm="RS256",
        headers={"kid": "test-key-001"},
    )

    assert_rejected(validator, modified)


def test_jwt007_unsigned_token(jwt_environment):
    _, validator = jwt_environment

    token = jwt.encode(
        {
            "iss": TEST_ISSUER,
            "aud": TEST_AUDIENCE,
            "sub": "synthetic-user",
            "exp": 4102444800,
            "iat": 1700000000,
        },
        key="",
        algorithm="none",
        headers={"kid": "test-key-001"},
    )

    assert_rejected(validator, token)


def test_jwt008_malformed_token(jwt_environment):
    _, validator = jwt_environment

    assert_rejected(validator, "not.a.valid.jwt")


def test_jwt009_missing_subject(jwt_environment):
    key, validator = jwt_environment

    token = create_token(
        key,
        claims_override={"sub": ""},
    )

    assert_rejected(validator, token)


def test_jwt010_malformed_roles(jwt_environment):
    key, validator = jwt_environment

    token = create_token(
        key,
        roles="Inference.Admin",
    )

    assert_rejected(validator, token)