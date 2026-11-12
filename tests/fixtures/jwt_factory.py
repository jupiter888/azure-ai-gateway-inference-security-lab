from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


TEST_ISSUER = "https://issuer.project09.test"
TEST_AUDIENCE = "api://project09-gateway"


def generate_key_pair():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def create_jwks(private_key, kid="test-key-001"):
    public_key = private_key.public_key()

    jwk = RSAAlgorithm.to_jwk(
        public_key,
        as_dict=True,
    )

    jwk.update({
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
    })

    return {"keys": [jwk]}


def create_token(
    private_key,
    *,
    issuer=TEST_ISSUER,
    audience=TEST_AUDIENCE,
    subject="synthetic-user",
    roles=None,
    expires_in=300,
    claims_override=None,
    kid="test-key-001",
):
    now = datetime.now(timezone.utc)

    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": str(uuid4()),
        "roles": (
            ["Inference.Reader"]
            if roles is None
            else roles
        ),
    }

    if claims_override:
        claims.update(claims_override)

    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )