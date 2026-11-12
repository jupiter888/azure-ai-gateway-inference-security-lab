from dataclasses import dataclass

from src.identity.jwt_validator import AuthenticatedPrincipal


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str


MODEL_PERMISSIONS = {
    "research-model": frozenset({"Inference.Reader"}),
    "restricted-model": frozenset({"Inference.Admin"}),
}


def authorize_model(
    principal: AuthenticatedPrincipal,
    model: str,
) -> AuthorizationDecision:

    permitted_roles = MODEL_PERMISSIONS.get(model)

    if permitted_roles is None:
        return AuthorizationDecision(
            allowed=False,
            reason="unknown_model",
        )

    if not permitted_roles.intersection(principal.roles):
        return AuthorizationDecision(
            allowed=False,
            reason="insufficient_permissions",
        )

    return AuthorizationDecision(
        allowed=True,
        reason="authorized",
    )