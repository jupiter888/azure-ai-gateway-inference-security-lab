from dataclasses import dataclass
import jwt

from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from src.gateway.config import GatewayConfig


class AuthenticationError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject: str
    roles: tuple[str, ...]


class JWTValidator:
    def __init__(self, config: GatewayConfig):
        self.config = config

        self.jwks_client = PyJWKClient(
            config.jwks_url,
            timeout=5,
            lifespan=300,
        )

    def validate(self, token: str) -> AuthenticatedPrincipal:
        if not token or len(token) > 8192:
            raise AuthenticationError("Invalid token")

        try:
            signing_key = (
                self.jwks_client.get_signing_key_from_jwt(token)
            )

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self.config.algorithms),
                audience=self.config.audience,
                issuer=self.config.issuer,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "iss",
                        "aud",
                        "sub",
                    ],
                },
                leeway=0,
            )

        except (
            PyJWTError,
            ValueError,
            TypeError,
            OSError,
        ) as exc:
            raise AuthenticationError(
                "Token validation failed"
            ) from exc

        # --------------------------------------------------
        # Subject validation
        # --------------------------------------------------

        subject = claims.get("sub")

        if not isinstance(subject, str) or not subject:
            raise AuthenticationError(
                "Missing subject"
            )

        # --------------------------------------------------
        # Microsoft Entra token-version enforcement
        # --------------------------------------------------

        if self.config.required_token_version is not None:
            token_version = claims.get("ver")

            if token_version != self.config.required_token_version:
                raise AuthenticationError(
                    "Unsupported token version"
                )

        # --------------------------------------------------
        # Calling application allowlist
        # --------------------------------------------------

        if self.config.allowed_client_id is not None:
            token_version = claims.get("ver")

            if token_version == "1.0":
                calling_application = claims.get("appid")
            elif token_version == "2.0":
                calling_application = claims.get("azp")
            else:
                raise AuthenticationError(
                    "Unsupported application identity format"
                )

            if (
                not isinstance(calling_application, str)
                or calling_application
                != self.config.allowed_client_id
            ):
                raise AuthenticationError(
                    "Unauthorized calling application"
                )

        # --------------------------------------------------
        # Application role validation
        # --------------------------------------------------

        raw_roles = claims.get("roles", [])

        if not isinstance(raw_roles, list):
            raise AuthenticationError(
                "Invalid roles claim"
            )

        if not all(
            isinstance(role, str) and role
            for role in raw_roles
        ):
            raise AuthenticationError(
                "Invalid role value"
            )

        return AuthenticatedPrincipal(
            subject=subject,
            roles=tuple(raw_roles),
        )