from dataclasses import dataclass
import math
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class GatewayConfig:
    issuer: str
    audience: str
    jwks_url: str
    algorithms: tuple[str, ...] = ("RS256",)
    allowed_client_id: str | None = None
    required_token_version: str | None = None


@dataclass(frozen=True)
class BackendTimeoutConfig:
    connect: float
    read: float
    write: float
    pool: float


def read_timeout_setting(
    name: str,
    default: float,
    maximum: float,
) -> float:
    raw = os.environ.get(name)

    try:
        value = default if raw is None else float(raw)
    except (ValueError, OverflowError):
        raise ValueError(
            f"{name} must be a finite number between "
            f"0.1 and {maximum} seconds"
        ) from None

    if not math.isfinite(value) or not 0.1 <= value <= maximum:
        raise ValueError(
            f"{name} must be a finite number between "
            f"0.1 and {maximum} seconds"
        )

    return value


def load_backend_timeout_config() -> BackendTimeoutConfig:
    return BackendTimeoutConfig(
        connect=read_timeout_setting(
            "P9_BACKEND_CONNECT_TIMEOUT_SECONDS",
            default=10.0,
            maximum=30.0,
        ),
        read=read_timeout_setting(
            "P9_BACKEND_READ_TIMEOUT_SECONDS",
            default=60.0,
            maximum=120.0,
        ),
        write=read_timeout_setting(
            "P9_BACKEND_WRITE_TIMEOUT_SECONDS",
            default=10.0,
            maximum=30.0,
        ),
        pool=read_timeout_setting(
            "P9_BACKEND_POOL_TIMEOUT_SECONDS",
            default=5.0,
            maximum=30.0,
        ),
    )


def load_config() -> GatewayConfig:
    load_dotenv()

    issuer = os.environ.get("P9_JWT_ISSUER", "").strip()
    audience = os.environ.get("P9_JWT_AUDIENCE", "").strip()
    jwks_url = os.environ.get("P9_JWKS_URL", "").strip()

    allowed_client_id = (
        os.environ.get("P9_ALLOWED_CLIENT_ID", "").strip() or None
    )
    required_token_version = (
        os.environ.get("P9_REQUIRED_TOKEN_VERSION", "").strip() or None
    )

    if not issuer or not audience or not jwks_url:
        raise RuntimeError(
            "Missing required JWT configuration: "
            "P9_JWT_ISSUER, P9_JWT_AUDIENCE, P9_JWKS_URL"
        )

    if not issuer.startswith("https://"):
        raise RuntimeError("JWT issuer must use HTTPS")

    if not jwks_url.startswith("https://"):
        raise RuntimeError("JWKS endpoint must use HTTPS")

    if issuer.startswith("https://sts.windows.net/"):
        if not allowed_client_id:
            raise RuntimeError(
                "P9_ALLOWED_CLIENT_ID is required "
                "for Microsoft Entra tokens"
            )

        if required_token_version != "1.0":
            raise RuntimeError(
                "Microsoft Entra v1 issuer requires "
                "P9_REQUIRED_TOKEN_VERSION=1.0"
            )

    return GatewayConfig(
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_url,
        allowed_client_id=allowed_client_id,
        required_token_version=required_token_version,
    )